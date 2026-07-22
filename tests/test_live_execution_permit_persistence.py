from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, MetaData, String, Table, create_engine, event, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateIndex, CreateTable

from infrastructure.persistence.execution_orm import AuditEventORM, ExecutionPersistenceBase, LiveExecutionPermitORM
from infrastructure.persistence.execution_repositories import SqlAlchemyLiveExecutionPermitRepository
from infrastructure.persistence.live_execution_permit_persistence import (
    ISSUE_CONFIRMATION,
    REVOKE_CONFIRMATION,
    LiveExecutionPermitPersistence,
    LiveExecutionPermitPersistenceError,
)
from infrastructure.persistence.schema_contract import PERSISTENCE_REVISION, validate_persistence_schema
from infrastructure.security.live_execution_request_fingerprint import build_live_execution_request_fingerprint
from models.execution_persistence import OptimisticLockError
from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit import LiveExecutionPermitState

NOW = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
HOSTILE_MARKERS = ["postgresql://user:secret@", "connectionString", "SELECT * FROM", "traceback", "X-MBX-APIKEY", "signature=", "signed-url", "rawResponse", "Authorization", "secret-token"]
HOSTILE_AUDIT_FAILURE = "postgresql://user:secret@ connectionString SELECT * FROM traceback X-MBX-APIKEY signature= signed-url rawResponse Authorization secret-token"


def _engine(path: Path):
    engine = create_engine(f"sqlite:///{path}", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _prepare_database(tmp_path: Path) -> tuple[dict[str, str], Path]:
    db_path = tmp_path / "permits.db"
    engine = _engine(db_path)
    ExecutionPersistenceBase.metadata.create_all(engine)
    metadata = MetaData()
    version = Table("alembic_version", metadata, Column("version_num", String(64), primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(version.insert().values(version_num=PERSISTENCE_REVISION))
    engine.dispose()
    return {"ICT_DATABASE_URL": f"sqlite:///{db_path}"}, db_path


def _fingerprint(pair_id: str = "pair-abc"):
    return build_live_execution_request_fingerprint(
        {
            "schema_version": "1.0",
            "operation": "PROTECTIVE_CREATE",
            "environment": "TESTNET",
            "symbol": "BTCUSDT",
            "pair_id": pair_id,
            "leg_type": "STOP",
            "side": "SELL",
            "position_side": "LONG",
            "quantity": "0.0016",
            "trigger_price": "62000",
            "close_position": True,
            "reduce_only": None,
            "client_algo_id": "smcbot-protect-sl-001",
            "order_type": "STOP_MARKET",
            "working_type": "MARK_PRICE",
            "price_protect": True,
        }
    )


def _service(env: dict[str, str], current: dict[str, datetime]) -> LiveExecutionPermitPersistence:
    svc = LiveExecutionPermitPersistence(env=env, now_provider=lambda: current["now"])
    svc.ensure_available()
    return svc


def _audit_actions(db_path: Path) -> list[str]:
    engine = _engine(db_path)
    with Session(engine, future=True) as session:
        actions = [row.action for row in session.scalars(select(AuditEventORM).order_by(AuditEventORM.created_at, AuditEventORM.id)).all()]
    engine.dispose()
    return actions


def _permits(db_path: Path):
    engine = _engine(db_path)
    with Session(engine, future=True) as session:
        rows = list(session.scalars(select(LiveExecutionPermitORM).order_by(LiveExecutionPermitORM.issued_at, LiveExecutionPermitORM.id)).all())
        values = [(row.permit_id, row.state, row.version, row.request_fingerprint) for row in rows]
    engine.dispose()
    return values


def _permit_snapshot(db_path: Path) -> list[dict[str, object]]:
    engine = _engine(db_path)
    with Session(engine, future=True) as session:
        rows = list(session.scalars(select(LiveExecutionPermitORM).order_by(LiveExecutionPermitORM.issued_at, LiveExecutionPermitORM.id)).all())
        values = [
            {
                "permit_id": row.permit_id,
                "operation": row.operation,
                "environment": row.environment,
                "symbol": row.symbol,
                "request_fingerprint": row.request_fingerprint,
                "subject_type": row.subject_type,
                "subject_id": row.subject_id,
                "state": row.state,
                "issued_at": row.issued_at,
                "expires_at": row.expires_at,
                "consumed_at": row.consumed_at,
                "revoked_at": row.revoked_at,
                "expired_at": row.expired_at,
                "issued_by": row.issued_by,
                "revocation_reason_code": row.revocation_reason_code,
                "consumption_correlation_id": row.consumption_correlation_id,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "version": row.version,
            }
            for row in rows
        ]
    engine.dispose()
    return values


def _audit_snapshot(db_path: Path) -> list[dict[str, object]]:
    engine = _engine(db_path)
    with Session(engine, future=True) as session:
        rows = list(session.scalars(select(AuditEventORM).order_by(AuditEventORM.created_at, AuditEventORM.id)).all())
        values = [
            {
                "action": row.action,
                "environment": row.environment,
                "symbol": row.symbol,
                "result": row.result,
                "error_code": row.error_code,
                "metadata_json": row.metadata_json,
            }
            for row in rows
        ]
    engine.dispose()
    return values


def _consume_audits_for(db_path: Path, permit_id: str, correlation_id) -> list[dict[str, object]]:
    return [
        audit
        for audit in _audit_snapshot(db_path)
        if audit["action"] == "PERMIT_CONSUMED"
        and audit["metadata_json"]["permit_id"] == permit_id
        and audit["metadata_json"]["consumption_correlation_id"] == str(correlation_id)
    ]


def _assert_sanitized(value: object) -> None:
    text = str(value)
    for marker in HOSTILE_MARKERS:
        assert marker not in text


def _install_audit_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from infrastructure.persistence.execution_repositories import SqlAlchemyAuditEventRepository

    def fail_append(self, event):
        raise RuntimeError(HOSTILE_AUDIT_FAILURE)

    monkeypatch.setattr(SqlAlchemyAuditEventRepository, "append", fail_append)


def _corrupt_permit(db_path: Path, permit_id: str, field: str, value: str) -> None:
    engine = _engine(db_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(f"UPDATE live_execution_permits SET {field} = ? WHERE permit_id = ?", (value, permit_id))
    engine.dispose()


def test_issue_creates_permit_and_atomic_audit(tmp_path: Path) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    svc = _service(env, current)
    try:
        permit = svc.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
    finally:
        svc.close()

    assert permit.permit_id.startswith("permit-")
    assert permit.state == LiveExecutionPermitState.ISSUED
    assert permit.expires_at == NOW + timedelta(seconds=300)
    assert permit.request_fingerprint == _fingerprint().request_fingerprint
    assert permit.subject_id == "pair-abc:STOP:smcbot-protect-sl-001"
    assert _audit_actions(db_path) == ["PERMIT_ISSUED"]


@pytest.mark.parametrize("ttl", [29, 901, True])
def test_issue_rejects_bad_confirmation_and_ttl(tmp_path: Path, ttl: object) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    svc = _service(env, current)
    try:
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            svc.issue(_fingerprint(), ttl_seconds=ttl, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        assert exc.value.code == "PERMIT_TTL_INVALID"
        with pytest.raises(LiveExecutionPermitPersistenceError) as missing:
            svc.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation="wrong")
        assert missing.value.code == "PERMIT_CONFIRMATION_REQUIRED"
    finally:
        svc.close()
    assert _permits(db_path) == []
    assert _audit_actions(db_path) == []


def test_issue_audit_failure_rolls_back_permit_creation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    before_permits = _permit_snapshot(db_path)
    before_audits = _audit_snapshot(db_path)
    svc = _service(env, current)
    try:
        _install_audit_failure(monkeypatch)
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            svc.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        assert exc.value.code == "PERMIT_UNAVAILABLE"
        _assert_sanitized(exc.value)
        assert _permit_snapshot(db_path) == before_permits
        assert _audit_snapshot(db_path) == before_audits

        monkeypatch.undo()
        issued = svc.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        assert issued.state == LiveExecutionPermitState.ISSUED
    finally:
        svc.close()
    assert len(_permit_snapshot(db_path)) == 1
    assert _audit_actions(db_path) == ["PERMIT_ISSUED"]


def test_duplicate_unexpired_active_is_denied_without_extra_row(tmp_path: Path) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    svc = _service(env, current)
    try:
        first = svc.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            svc.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        assert exc.value.code == "PERMIT_DUPLICATE_ACTIVE"
    finally:
        svc.close()
    assert _permits(db_path) == [(first.permit_id, "ISSUED", 1, first.request_fingerprint)]


def test_expired_active_is_transitioned_before_replacement_issue(tmp_path: Path) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    svc = _service(env, current)
    try:
        first = svc.issue(_fingerprint(), ttl_seconds=30, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        current["now"] = NOW + timedelta(seconds=31)
        second = svc.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
    finally:
        svc.close()
    assert first.permit_id != second.permit_id
    assert [state for _, state, _, _ in _permits(db_path)] == ["EXPIRED", "ISSUED"]
    actions = _audit_actions(db_path)
    assert actions[0] == "PERMIT_ISSUED"
    assert sorted(actions[1:]) == ["PERMIT_EXPIRED", "PERMIT_ISSUED"]


def test_revoke_and_expire_are_versioned_and_terminal(tmp_path: Path) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    svc = _service(env, current)
    try:
        permit = svc.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        revoked = svc.revoke(permit.permit_id, expected_version=permit.version, reason_code="OPERATOR_REVOKED", confirmation=REVOKE_CONFIRMATION)
        assert revoked.state == LiveExecutionPermitState.REVOKED
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            svc.revoke(permit.permit_id, expected_version=revoked.version, reason_code="OPERATOR_REVOKED", confirmation=REVOKE_CONFIRMATION)
        assert exc.value.code == "PERMIT_ALREADY_REVOKED"
    finally:
        svc.close()
    assert sorted(_audit_actions(db_path)) == ["PERMIT_ISSUED", "PERMIT_REVOKED"]


def test_revoke_expired_by_time_marks_expired_not_revoked(tmp_path: Path) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    svc = _service(env, current)
    try:
        permit = svc.issue(_fingerprint(), ttl_seconds=30, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        current["now"] = NOW + timedelta(seconds=31)
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            svc.revoke(permit.permit_id, expected_version=permit.version, reason_code="OPERATOR_REVOKED", confirmation=REVOKE_CONFIRMATION)
        assert exc.value.code == "PERMIT_ALREADY_EXPIRED"
    finally:
        svc.close()
    assert _permits(db_path)[0][1] == "EXPIRED"
    assert _audit_actions(db_path) == ["PERMIT_ISSUED", "PERMIT_EXPIRED"]


def test_consume_is_atomic_one_time_and_classifies_mismatches(tmp_path: Path) -> None:
    env, _ = _prepare_database(tmp_path)
    current = {"now": NOW}
    svc = _service(env, current)
    try:
        permit = svc.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        consumed = svc.consume(
            permit_id=permit.permit_id,
            expected_version=permit.version,
            expected_operation=permit.operation,
            expected_environment=permit.environment,
            expected_symbol=permit.symbol,
            expected_subject_type=permit.subject_type,
            expected_subject_id=permit.subject_id,
            expected_request_fingerprint=permit.request_fingerprint,
            consumption_correlation_id=uuid4(),
        )
        assert consumed.state == LiveExecutionPermitState.CONSUMED
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            svc.consume(
                permit_id=permit.permit_id,
                expected_version=permit.version,
                expected_operation=permit.operation,
                expected_environment=permit.environment,
                expected_symbol=permit.symbol,
                expected_subject_type=permit.subject_type,
                expected_subject_id=permit.subject_id,
                expected_request_fingerprint=permit.request_fingerprint,
                consumption_correlation_id=uuid4(),
            )
        assert exc.value.code == "PERMIT_ALREADY_CONSUMED"
    finally:
        svc.close()


def test_consume_audit_failure_rolls_back_consumption(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    correlation = uuid4()
    svc = _service(env, current)
    try:
        permit = svc.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        before_permits = _permit_snapshot(db_path)
        before_audits = _audit_snapshot(db_path)
        _install_audit_failure(monkeypatch)
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            svc.consume(
                permit_id=permit.permit_id,
                expected_version=permit.version,
                expected_operation=permit.operation,
                expected_environment=permit.environment,
                expected_symbol=permit.symbol,
                expected_subject_type=permit.subject_type,
                expected_subject_id=permit.subject_id,
                expected_request_fingerprint=permit.request_fingerprint,
                consumption_correlation_id=correlation,
            )
        assert exc.value.code == "PERMIT_UNAVAILABLE"
        _assert_sanitized(exc.value)
        assert _permit_snapshot(db_path) == before_permits
        assert _audit_snapshot(db_path) == before_audits

        monkeypatch.undo()
        consumed = svc.consume(
            permit_id=permit.permit_id,
            expected_version=permit.version,
            expected_operation=permit.operation,
            expected_environment=permit.environment,
            expected_symbol=permit.symbol,
            expected_subject_type=permit.subject_type,
            expected_subject_id=permit.subject_id,
            expected_request_fingerprint=permit.request_fingerprint,
            consumption_correlation_id=correlation,
        )
        assert consumed.state == LiveExecutionPermitState.CONSUMED
        assert consumed.consumption_correlation_id == correlation
    finally:
        svc.close()
    rows = _permit_snapshot(db_path)
    assert rows[0]["state"] == "CONSUMED"
    assert rows[0]["version"] == 2
    assert rows[0]["consumption_correlation_id"] == correlation
    assert sorted(_audit_actions(db_path)) == ["PERMIT_CONSUMED", "PERMIT_ISSUED"]


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("expected_operation", LiveExecutionOperation.PROTECTIVE_CANCEL, "PERMIT_SCOPE_MISMATCH"),
        ("expected_environment", "PRODUCTION", "PERMIT_SCOPE_MISMATCH"),
        ("expected_symbol", "ETHUSDT", "PERMIT_SCOPE_MISMATCH"),
        ("expected_subject_type", "CLIENT_ORDER", "PERMIT_SUBJECT_MISMATCH"),
        ("expected_subject_id", "other", "PERMIT_SUBJECT_MISMATCH"),
        ("expected_request_fingerprint", "b" * 64, "PERMIT_FINGERPRINT_MISMATCH"),
        ("expected_version", 99, "PERMIT_VERSION_CONFLICT"),
    ],
)
def test_consume_rowcount_zero_is_classified_deterministically(tmp_path: Path, field: str, value: object, code: str) -> None:
    env, _ = _prepare_database(tmp_path)
    current = {"now": NOW}
    svc = _service(env, current)
    try:
        permit = svc.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        kwargs = {
            "permit_id": permit.permit_id,
            "expected_version": permit.version,
            "expected_operation": permit.operation,
            "expected_environment": permit.environment,
            "expected_symbol": permit.symbol,
            "expected_subject_type": permit.subject_type,
            "expected_subject_id": permit.subject_id,
            "expected_request_fingerprint": permit.request_fingerprint,
            "consumption_correlation_id": uuid4(),
        }
        kwargs[field] = value
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            svc.consume(**kwargs)
        assert exc.value.code == code
    finally:
        svc.close()


def test_two_sessions_only_one_can_consume_same_version(tmp_path: Path) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    svc = _service(env, current)
    try:
        permit = svc.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
    finally:
        svc.close()
    engine = _engine(db_path)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as first, SessionLocal() as second:
        first_repo = SqlAlchemyLiveExecutionPermitRepository(first)
        second_repo = SqlAlchemyLiveExecutionPermitRepository(second)
        first_view = first_repo.get_by_permit_id(permit.permit_id)
        second_view = second_repo.get_by_permit_id(permit.permit_id)
        assert first_view is not None and second_view is not None and first_view.version == second_view.version == 1
        first_repo.consume_if_issued(permit.permit_id, 1, permit.operation, permit.environment, permit.symbol, permit.subject_type, permit.subject_id, permit.request_fingerprint, uuid4(), NOW)
        first.commit()
        with pytest.raises(OptimisticLockError):
            second_repo.consume_if_issued(permit.permit_id, 1, permit.operation, permit.environment, permit.symbol, permit.subject_type, permit.subject_id, permit.request_fingerprint, uuid4(), NOW)
        second.rollback()
    engine.dispose()


def test_duplicate_consumption_correlation_is_fail_closed_and_does_not_consume_second_permit(tmp_path: Path) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    correlation = uuid4()
    svc = _service(env, current)
    try:
        first = svc.issue(_fingerprint("pair-a"), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        second = svc.issue(_fingerprint("pair-b"), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        consumed = svc.consume(
            permit_id=first.permit_id,
            expected_version=first.version,
            expected_operation=first.operation,
            expected_environment=first.environment,
            expected_symbol=first.symbol,
            expected_subject_type=first.subject_type,
            expected_subject_id=first.subject_id,
            expected_request_fingerprint=first.request_fingerprint,
            consumption_correlation_id=correlation,
        )
        assert consumed.state == LiveExecutionPermitState.CONSUMED
        before_second = [row for row in _permit_snapshot(db_path) if row["permit_id"] == second.permit_id][0]
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            svc.consume(
                permit_id=second.permit_id,
                expected_version=second.version,
                expected_operation=second.operation,
                expected_environment=second.environment,
                expected_symbol=second.symbol,
                expected_subject_type=second.subject_type,
                expected_subject_id=second.subject_id,
                expected_request_fingerprint=second.request_fingerprint,
                consumption_correlation_id=correlation,
            )
        assert exc.value.code == "PERMIT_CONSUMPTION_CORRELATION_CONFLICT"
        _assert_sanitized(exc.value)
    finally:
        svc.close()

    rows = _permit_snapshot(db_path)
    first_row = [row for row in rows if row["permit_id"] == first.permit_id][0]
    second_row = [row for row in rows if row["permit_id"] == second.permit_id][0]
    assert first_row["state"] == "CONSUMED"
    assert first_row["version"] == 2
    assert first_row["consumed_at"] is not None
    assert first_row["consumption_correlation_id"] == correlation
    assert second_row == before_second
    assert second_row["state"] == "ISSUED"
    assert second_row["version"] == 1
    assert second_row["consumed_at"] is None
    assert second_row["consumption_correlation_id"] is None
    assert sum(1 for row in rows if row["consumption_correlation_id"] == correlation) == 1
    assert len(_consume_audits_for(db_path, first.permit_id, correlation)) == 1
    assert len(_consume_audits_for(db_path, second.permit_id, correlation)) == 0
    assert sum(1 for audit in _audit_snapshot(db_path) if audit["action"] == "PERMIT_CONSUMED" and audit["metadata_json"]["consumption_correlation_id"] == str(correlation)) == 1


def test_unrelated_consume_integrity_error_is_not_classified_as_duplicate_correlation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    correlation = uuid4()
    svc = _service(env, current)
    try:
        permit = svc.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        before_permits = _permit_snapshot(db_path)
        before_audits = _audit_snapshot(db_path)

        def fail_consume(self, *args, **kwargs):
            raise IntegrityError(HOSTILE_AUDIT_FAILURE, {}, RuntimeError(HOSTILE_AUDIT_FAILURE))

        monkeypatch.setattr(SqlAlchemyLiveExecutionPermitRepository, "consume_if_issued", fail_consume)
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            svc.consume(
                permit_id=permit.permit_id,
                expected_version=permit.version,
                expected_operation=permit.operation,
                expected_environment=permit.environment,
                expected_symbol=permit.symbol,
                expected_subject_type=permit.subject_type,
                expected_subject_id=permit.subject_id,
                expected_request_fingerprint=permit.request_fingerprint,
                consumption_correlation_id=correlation,
            )
        assert exc.value.code == "PERMIT_UNAVAILABLE"
        assert exc.value.code != "PERMIT_CONSUMPTION_CORRELATION_CONFLICT"
        _assert_sanitized(exc.value)
    finally:
        svc.close()
    assert _permit_snapshot(db_path) == before_permits
    assert _audit_snapshot(db_path) == before_audits


def test_malformed_correlation_owner_does_not_classify_as_duplicate_correlation(tmp_path: Path) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    correlation = uuid4()
    svc = _service(env, current)
    try:
        first = svc.issue(_fingerprint("pair-a"), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        second = svc.issue(_fingerprint("pair-b"), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        svc.consume(
            permit_id=first.permit_id,
            expected_version=first.version,
            expected_operation=first.operation,
            expected_environment=first.environment,
            expected_symbol=first.symbol,
            expected_subject_type=first.subject_type,
            expected_subject_id=first.subject_id,
            expected_request_fingerprint=first.request_fingerprint,
            consumption_correlation_id=correlation,
        )
    finally:
        svc.close()
    _corrupt_permit(db_path, first.permit_id, "operation", "UNKNOWN_OPERATION")
    before_permits = _permit_snapshot(db_path)
    before_audits = _audit_snapshot(db_path)

    consumer = _service(env, current)
    try:
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            consumer.consume(
                permit_id=second.permit_id,
                expected_version=second.version,
                expected_operation=second.operation,
                expected_environment=second.environment,
                expected_symbol=second.symbol,
                expected_subject_type=second.subject_type,
                expected_subject_id=second.subject_id,
                expected_request_fingerprint=second.request_fingerprint,
                consumption_correlation_id=correlation,
            )
        assert exc.value.code == "PERMIT_INVALID"
        assert exc.value.code != "PERMIT_CONSUMPTION_CORRELATION_CONFLICT"
        _assert_sanitized(exc.value)
    finally:
        consumer.close()
    assert _permit_snapshot(db_path) == before_permits
    assert _audit_snapshot(db_path) == before_audits


def test_two_persistence_instances_consume_once_with_exactly_one_audit(tmp_path: Path) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    issuer = _service(env, current)
    try:
        permit = issuer.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
    finally:
        issuer.close()

    first = _service(env, current)
    second = _service(env, current)
    correlation_a = uuid4()
    correlation_b = uuid4()
    try:
        first_view, first_expired = first.show(permit.permit_id)
        second_view, second_expired = second.show(permit.permit_id)
        assert first_view is not None and second_view is not None
        assert first_expired is False and second_expired is False
        assert first_view.version == second_view.version == permit.version
        consumed = first.consume(
            permit_id=permit.permit_id,
            expected_version=first_view.version,
            expected_operation=first_view.operation,
            expected_environment=first_view.environment,
            expected_symbol=first_view.symbol,
            expected_subject_type=first_view.subject_type,
            expected_subject_id=first_view.subject_id,
            expected_request_fingerprint=first_view.request_fingerprint,
            consumption_correlation_id=correlation_a,
        )
        assert consumed.state == LiveExecutionPermitState.CONSUMED
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            second.consume(
                permit_id=permit.permit_id,
                expected_version=second_view.version,
                expected_operation=second_view.operation,
                expected_environment=second_view.environment,
                expected_symbol=second_view.symbol,
                expected_subject_type=second_view.subject_type,
                expected_subject_id=second_view.subject_id,
                expected_request_fingerprint=second_view.request_fingerprint,
                consumption_correlation_id=correlation_b,
            )
        assert exc.value.code == "PERMIT_ALREADY_CONSUMED"
    finally:
        first.close()
        second.close()

    restart = _service(env, current)
    try:
        final, effective_expired = restart.show(permit.permit_id)
        assert final is not None and effective_expired is False
        assert final.state == LiveExecutionPermitState.CONSUMED
        assert final.version == 2
        assert final.consumption_correlation_id == correlation_a
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            restart.consume(
                permit_id=permit.permit_id,
                expected_version=final.version,
                expected_operation=final.operation,
                expected_environment=final.environment,
                expected_symbol=final.symbol,
                expected_subject_type=final.subject_type,
                expected_subject_id=final.subject_id,
                expected_request_fingerprint=final.request_fingerprint,
                consumption_correlation_id=uuid4(),
            )
        assert exc.value.code == "PERMIT_ALREADY_CONSUMED"
    finally:
        restart.close()

    assert _audit_actions(db_path).count("PERMIT_CONSUMED") == 1
    consumed_audits = [audit for audit in _audit_snapshot(db_path) if audit["action"] == "PERMIT_CONSUMED"]
    assert consumed_audits[0]["metadata_json"]["consumption_correlation_id"] == str(correlation_a)


def test_show_is_read_only_and_effective_expired_does_not_mutate_state(tmp_path: Path) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    svc = _service(env, current)
    try:
        permit = svc.issue(_fingerprint(), ttl_seconds=30, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        current["now"] = NOW + timedelta(seconds=31)
        shown, effective_expired = svc.show(permit.permit_id)
    finally:
        svc.close()
    assert shown is not None and effective_expired is True
    assert _permits(db_path)[0][1] == "ISSUED"
    assert _audit_actions(db_path) == ["PERMIT_ISSUED"]


def test_revoke_audit_failure_rolls_back_complete_transition(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    svc = _service(env, current)
    try:
        permit = svc.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        from infrastructure.persistence.execution_repositories import SqlAlchemyAuditEventRepository

        before_permits = _permit_snapshot(db_path)
        before_audits = _audit_snapshot(db_path)

        def fail_append(self, event):
            row = self.session.scalar(select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == permit.permit_id))
            assert row.state == "REVOKED"
            assert row.version == permit.version + 1
            assert row.revoked_at is not None
            assert row.revocation_reason_code == "OPERATOR_REVOKED"
            raise RuntimeError(HOSTILE_AUDIT_FAILURE)

        monkeypatch.setattr(SqlAlchemyAuditEventRepository, "append", fail_append)
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            svc.revoke(permit.permit_id, expected_version=permit.version, reason_code="OPERATOR_REVOKED", confirmation=REVOKE_CONFIRMATION)
        assert exc.value.code == "PERMIT_UNAVAILABLE"
        _assert_sanitized(exc.value)
        assert _permit_snapshot(db_path) == before_permits
        assert _audit_snapshot(db_path) == before_audits

        monkeypatch.undo()
        revoked = svc.revoke(permit.permit_id, expected_version=permit.version, reason_code="OPERATOR_REVOKED", confirmation=REVOKE_CONFIRMATION)
        assert revoked.state == LiveExecutionPermitState.REVOKED
        assert revoked.version == permit.version + 1
        assert revoked.revoked_at is not None
        assert revoked.revocation_reason_code == "OPERATOR_REVOKED"
        with pytest.raises(LiveExecutionPermitPersistenceError) as terminal:
            svc.revoke(permit.permit_id, expected_version=revoked.version, reason_code="OPERATOR_REVOKED", confirmation=REVOKE_CONFIRMATION)
        assert terminal.value.code == "PERMIT_ALREADY_REVOKED"
    finally:
        svc.close()
    rows = _permit_snapshot(db_path)
    assert rows[0]["state"] == "REVOKED"
    assert rows[0]["version"] == 2
    assert rows[0]["revoked_at"] is not None
    assert rows[0]["revocation_reason_code"] == "OPERATOR_REVOKED"
    assert _audit_actions(db_path).count("PERMIT_REVOKED") == 1


def test_expire_audit_failure_rolls_back_expiration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    svc = _service(env, current)
    try:
        permit = svc.issue(_fingerprint(), ttl_seconds=30, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
        current["now"] = NOW + timedelta(seconds=31)
        before_permits = _permit_snapshot(db_path)
        before_audits = _audit_snapshot(db_path)
        _install_audit_failure(monkeypatch)
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            svc.expire(permit.permit_id, expected_version=permit.version, now=current["now"])
        assert exc.value.code == "PERMIT_UNAVAILABLE"
        _assert_sanitized(exc.value)
        assert _permit_snapshot(db_path) == before_permits
        assert _audit_snapshot(db_path) == before_audits

        monkeypatch.undo()
        expired = svc.expire(permit.permit_id, expected_version=permit.version, now=current["now"])
        assert expired.state == LiveExecutionPermitState.EXPIRED
    finally:
        svc.close()
    rows = _permit_snapshot(db_path)
    assert rows[0]["state"] == "EXPIRED"
    assert rows[0]["version"] == 2
    assert _audit_actions(db_path) == ["PERMIT_ISSUED", "PERMIT_EXPIRED"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_fingerprint", "NOT-A-LOWERCASE-SHA256"),
        ("subject_id", "bad subject"),
    ],
)
def test_show_malformed_persisted_permit_returns_permit_invalid_without_mutation(tmp_path: Path, field: str, value: str) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    svc = _service(env, current)
    try:
        permit = svc.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
    finally:
        svc.close()
    _corrupt_permit(db_path, permit.permit_id, field, value)
    before_permits = _permit_snapshot(db_path)
    before_audits = _audit_snapshot(db_path)

    reader = _service(env, current)
    try:
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            reader.show(permit.permit_id)
        assert exc.value.code == "PERMIT_INVALID"
        _assert_sanitized(exc.value)
    finally:
        reader.close()
    assert _permit_snapshot(db_path) == before_permits
    assert _audit_snapshot(db_path) == before_audits


def test_consume_malformed_persisted_permit_returns_permit_invalid_without_mutation(tmp_path: Path) -> None:
    env, db_path = _prepare_database(tmp_path)
    current = {"now": NOW}
    svc = _service(env, current)
    try:
        permit = svc.issue(_fingerprint(), ttl_seconds=300, issued_by="operator-1", confirmation=ISSUE_CONFIRMATION)
    finally:
        svc.close()
    _corrupt_permit(db_path, permit.permit_id, "operation", "UNKNOWN_OPERATION")
    before_permits = _permit_snapshot(db_path)
    before_audits = _audit_snapshot(db_path)

    consumer = _service(env, current)
    try:
        with pytest.raises(LiveExecutionPermitPersistenceError) as exc:
            consumer.consume(
                permit_id=permit.permit_id,
                expected_version=permit.version,
                expected_operation=permit.operation,
                expected_environment=permit.environment,
                expected_symbol=permit.symbol,
                expected_subject_type=permit.subject_type,
                expected_subject_id=permit.subject_id,
                expected_request_fingerprint=permit.request_fingerprint,
                consumption_correlation_id=uuid4(),
            )
        assert exc.value.code == "PERMIT_INVALID"
        _assert_sanitized(exc.value)
    finally:
        consumer.close()
    assert _permit_snapshot(db_path) == before_permits
    assert _audit_snapshot(db_path) == before_audits


def _migration_module(path: str):
    spec = importlib.util.spec_from_file_location(path.replace("/", "_"), Path(path))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _run_migration(engine, module_path: str, fn_name: str) -> None:
    module = _migration_module(module_path)
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        ops = Operations(context)
        previous = module.op
        module.op = ops
        try:
            getattr(module, fn_name)()
        finally:
            module.op = previous


def test_migration_upgrade_and_downgrade_live_execution_permits_table(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "migration.db")
    _run_migration(engine, "alembic/versions/20260714_0286_execution_persistence.py", "upgrade")
    _run_migration(engine, "alembic/versions/20260717_0290_kill_switch_state.py", "upgrade")
    _run_migration(engine, "alembic/versions/20260722_0292_live_execution_permits.py", "upgrade")
    inspector = inspect(engine)
    assert "live_execution_permits" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("live_execution_permits")}
    assert {"permit_id", "request_fingerprint", "state", "expires_at", "consumption_correlation_id"}.issubset(columns)
    indexes = {index["name"] for index in inspector.get_indexes("live_execution_permits")}
    assert "uq_live_execution_permits_active_match" in indexes
    assert "ix_live_execution_permits_subject" in indexes
    uniques = {constraint["name"] for constraint in inspector.get_unique_constraints("live_execution_permits")}
    assert "uq_live_execution_permits_permit_id" in uniques
    assert "uq_live_execution_permits_consumption_correlation_id" in uniques
    checks = {constraint["name"] for constraint in inspector.get_check_constraints("live_execution_permits")}
    assert "ck_live_execution_permits_state" in checks
    assert "ck_live_execution_permits_state_timestamps" in checks

    _run_migration(engine, "alembic/versions/20260722_0292_live_execution_permits.py", "downgrade")
    tables = set(inspect(engine).get_table_names())
    assert "live_execution_permits" not in tables
    assert "kill_switch_states" in tables
    engine.dispose()


def test_schema_contract_accepts_only_release_292_revision(tmp_path: Path) -> None:
    env, db_path = _prepare_database(tmp_path)
    engine = _engine(db_path)
    with engine.connect() as connection:
        assert validate_persistence_schema(connection) is True
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE alembic_version SET version_num='20260717_0290'")
    with engine.connect() as connection:
        assert validate_persistence_schema(connection) is False
    engine.dispose()


def test_postgresql_ddl_compilation_contains_required_types_and_indexes() -> None:
    ddl = " ".join(str(CreateTable(ExecutionPersistenceBase.metadata.tables["live_execution_permits"]).compile(dialect=postgresql.dialect())).upper().split())
    assert "UUID" in ddl
    assert "TIMESTAMP WITH TIME ZONE" in ddl
    assert "CHECK" in ddl
    assert "UNIQUE" in ddl
    table = ExecutionPersistenceBase.metadata.tables["live_execution_permits"]
    indexes = {index.name: str(CreateIndex(index).compile(dialect=postgresql.dialect())).upper() for index in table.indexes}
    assert "uq_live_execution_permits_active_match" in indexes
    assert "WHERE STATE = 'ISSUED'" in indexes["uq_live_execution_permits_active_match"]
