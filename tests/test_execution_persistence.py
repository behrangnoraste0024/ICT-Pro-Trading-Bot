from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateTable

from api.main import create_app
from infrastructure.persistence.execution_orm import AuditEventORM, ExecutionPersistenceBase, RecoveryEventORM
from infrastructure.persistence.execution_repositories import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyExchangeOrderIdentityRepository,
    SqlAlchemyExecutionIntentRepository,
    SqlAlchemyProtectivePairRepository,
    SqlAlchemyRecoveryEventRepository,
)
from models.execution_persistence import (
    AuditEvent,
    DuplicateIdentityError,
    ExchangeOrderIdentity,
    ExecutionIntent,
    ForbiddenAuditMetadataError,
    OptimisticLockError,
    PersistenceValidationError,
    ProtectivePair,
    RecoveryEvent,
)

RELEASE_TABLES = {
    "execution_intents",
    "protective_pairs",
    "exchange_order_identities",
    "recovery_events",
    "audit_events",
}


def _engine():
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _file_engine(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'persistence.db'}", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@dataclass
class _UnsafeMetadataValue:
    value: str = "unsafe"


@pytest.fixture
def session() -> Session:
    engine = _engine()
    ExecutionPersistenceBase.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as db:
        yield db


def _migration_module():
    path = Path("alembic/versions/20260714_0286_execution_persistence.py")
    spec = importlib.util.spec_from_file_location("release_0286_execution_persistence", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _run_migration(engine, fn_name: str) -> None:
    module = _migration_module()
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        ops = Operations(context)
        previous = module.op
        module.op = ops
        try:
            getattr(module, fn_name)()
        finally:
            module.op = previous


def _intent(**overrides) -> ExecutionIntent:
    values = {
        "environment": "BINANCE_FUTURES_TESTNET",
        "symbol": "BTCUSDT",
        "intent_type": "PROTECTIVE_PAIR",
        "state": "PENDING",
        "requested_quantity": Decimal("0.001600000000000001"),
        "requested_price": Decimal("63099.660000000000000001"),
    }
    values.update(overrides)
    return ExecutionIntent(**values)


def _persisted_intent(session: Session) -> ExecutionIntent:
    return SqlAlchemyExecutionIntentRepository(session).create(_intent())


def _pair(intent: ExecutionIntent, **overrides) -> ProtectivePair:
    values = {
        "pair_id": f"pair-{uuid4()}",
        "correlation_id": intent.correlation_id,
        "execution_intent_id": intent.id,
        "environment": "BINANCE_FUTURES_TESTNET",
        "symbol": "BTCUSDT",
        "position_side": "BOTH",
        "direction": "LONG",
        "quantity": Decimal("0.001600000000000001"),
        "state": "PENDING",
    }
    values.update(overrides)
    return ProtectivePair(**values)


def _persisted_pair(session: Session) -> ProtectivePair:
    intent = _persisted_intent(session)
    return SqlAlchemyProtectivePairRepository(session).create(_pair(intent))


def test_migration_upgrade_creates_tables_indexes_constraints_and_downgrade_removes_only_release_objects() -> None:
    engine = _engine()
    _run_migration(engine, "upgrade")
    inspector = inspect(engine)
    assert RELEASE_TABLES.issubset(set(inspector.get_table_names()))
    indexes = {idx["name"] for table in RELEASE_TABLES for idx in inspector.get_indexes(table)}
    assert "ix_execution_intents_correlation_id" in indexes
    assert "ix_protective_pairs_pair_id" in indexes
    assert "ix_exchange_order_identities_client_algo_id" in indexes
    assert "ix_recovery_events_created_at" in indexes
    assert "ix_audit_events_created_at" in indexes
    uniques = {constraint["name"] for constraint in inspector.get_unique_constraints("exchange_order_identities")}
    assert "uq_exchange_order_identity_client_algo" in uniques
    assert "uq_exchange_order_identity_pair_leg" in uniques
    for table in ("protective_pairs", "exchange_order_identities", "recovery_events"):
        foreign_keys = inspector.get_foreign_keys(table)
        assert foreign_keys
        assert all(foreign_key["options"].get("ondelete") == "RESTRICT" for foreign_key in foreign_keys)

    _run_migration(engine, "downgrade")
    assert RELEASE_TABLES.isdisjoint(set(inspect(engine).get_table_names()))


def test_decimal_precision_and_utc_timestamps_are_preserved(session: Session) -> None:
    saved = SqlAlchemyExecutionIntentRepository(session).create(_intent())
    loaded = SqlAlchemyExecutionIntentRepository(session).get_by_correlation_id(saved.correlation_id)
    assert loaded is not None
    assert loaded.requested_quantity == Decimal("0.001600000000000001")
    assert loaded.requested_price == Decimal("63099.660000000000000001")
    assert loaded.created_at.tzinfo is not None
    assert loaded.updated_at.tzinfo is not None


def test_duplicate_execution_intent_correlation_id_is_rejected(session: Session) -> None:
    repo = SqlAlchemyExecutionIntentRepository(session)
    saved = repo.create(_intent())
    session.commit()
    with pytest.raises(DuplicateIdentityError):
        repo.create(_intent(correlation_id=saved.correlation_id))


def test_duplicate_exchange_identity_and_leg_constraints_are_rejected(session: Session) -> None:
    pair = _persisted_pair(session)
    repo = SqlAlchemyExchangeOrderIdentityRepository(session)
    identity = repo.create(ExchangeOrderIdentity(protective_pair_id=pair.id, environment="BINANCE_FUTURES_TESTNET", symbol="BTCUSDT", leg_type="STOP", client_algo_id="smcbot-protect-sl-001", status="PENDING", trigger_price=Decimal("62000.123456789012345678")))
    assert repo.get_by_client_algo_id("BINANCE_FUTURES_TESTNET", "BTCUSDT", identity.client_algo_id) is not None
    with pytest.raises(DuplicateIdentityError):
        repo.create(ExchangeOrderIdentity(protective_pair_id=pair.id, environment="BINANCE_FUTURES_TESTNET", symbol="BTCUSDT", leg_type="TAKE_PROFIT", client_algo_id=identity.client_algo_id, status="PENDING"))
    with pytest.raises(DuplicateIdentityError):
        repo.create(ExchangeOrderIdentity(protective_pair_id=pair.id, environment="BINANCE_FUTURES_TESTNET", symbol="BTCUSDT", leg_type="STOP", client_algo_id="smcbot-protect-sl-002", status="PENDING"))


def test_foreign_key_violations_are_rejected(session: Session) -> None:
    repo = SqlAlchemyProtectivePairRepository(session)
    with pytest.raises(DuplicateIdentityError):
        repo.create(ProtectivePair(pair_id="missing-intent", correlation_id=uuid4(), execution_intent_id=uuid4(), environment="BINANCE_FUTURES_TESTNET", symbol="BTCUSDT", position_side="BOTH", direction="LONG", quantity=Decimal("0.0016"), state="PENDING"))


def test_optimistic_version_conflict_fails_safely(session: Session) -> None:
    repo = SqlAlchemyExecutionIntentRepository(session)
    saved = repo.create(_intent())
    updated = repo.update_state(saved.id, expected_version=saved.version, state="PERSISTED")
    assert updated.version == 2
    with pytest.raises(OptimisticLockError):
        repo.update_state(saved.id, expected_version=saved.version, state="TRANSMITTED")
    assert repo.get_by_id(saved.id).state == "PERSISTED"


def test_execution_intent_atomic_optimistic_locking_prevents_lost_update(tmp_path: Path) -> None:
    engine = _file_engine(tmp_path)
    ExecutionPersistenceBase.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as seed_session:
        saved = SqlAlchemyExecutionIntentRepository(seed_session).create(_intent())
        seed_session.commit()

    with SessionLocal() as first_session, SessionLocal() as second_session:
        first_repo = SqlAlchemyExecutionIntentRepository(first_session)
        second_repo = SqlAlchemyExecutionIntentRepository(second_session)
        first_view = first_repo.get_by_id(saved.id)
        second_view = second_repo.get_by_id(saved.id)
        assert first_view is not None and first_view.version == 1
        assert second_view is not None and second_view.version == 1

        winner = first_repo.update_state(saved.id, expected_version=first_view.version, state="PERSISTED")
        first_session.commit()
        assert winner.version == 2

        with pytest.raises(OptimisticLockError):
            second_repo.update_state(saved.id, expected_version=second_view.version, state="TRANSMITTED")
        second_session.rollback()

    with SessionLocal() as final_session:
        final = SqlAlchemyExecutionIntentRepository(final_session).get_by_id(saved.id)
        assert final is not None
        assert final.version == 2
        assert final.state == "PERSISTED"


def test_protective_pair_atomic_optimistic_locking_prevents_lost_update(tmp_path: Path) -> None:
    engine = _file_engine(tmp_path)
    ExecutionPersistenceBase.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as seed_session:
        intent = _persisted_intent(seed_session)
        saved = SqlAlchemyProtectivePairRepository(seed_session).create(_pair(intent))
        seed_session.commit()

    with SessionLocal() as first_session, SessionLocal() as second_session:
        first_repo = SqlAlchemyProtectivePairRepository(first_session)
        second_repo = SqlAlchemyProtectivePairRepository(second_session)
        first_view = first_repo.get_by_id(saved.id)
        second_view = second_repo.get_by_id(saved.id)
        assert first_view is not None and first_view.version == 1
        assert second_view is not None and second_view.version == 1

        winner = first_repo.update_state(saved.id, expected_version=first_view.version, state="STOP_ACTIVE")
        first_session.commit()
        assert winner.version == 2

        with pytest.raises(OptimisticLockError):
            second_repo.update_state(saved.id, expected_version=second_view.version, state="PAIR_ACTIVE")
        second_session.rollback()

    with SessionLocal() as final_session:
        final = SqlAlchemyProtectivePairRepository(final_session).get_by_id(saved.id)
        assert final is not None
        assert final.version == 2
        assert final.state == "STOP_ACTIVE"


def test_exchange_identity_atomic_optimistic_locking_prevents_lost_update(tmp_path: Path) -> None:
    engine = _file_engine(tmp_path)
    ExecutionPersistenceBase.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as seed_session:
        pair = _persisted_pair(seed_session)
        saved = SqlAlchemyExchangeOrderIdentityRepository(seed_session).create(
            ExchangeOrderIdentity(
                protective_pair_id=pair.id,
                environment="BINANCE_FUTURES_TESTNET",
                symbol="BTCUSDT",
                leg_type="STOP",
                client_algo_id="smcbot-protect-atomic-stop",
                status="PENDING",
            )
        )
        seed_session.commit()

    with SessionLocal() as first_session, SessionLocal() as second_session:
        first_repo = SqlAlchemyExchangeOrderIdentityRepository(first_session)
        second_repo = SqlAlchemyExchangeOrderIdentityRepository(second_session)
        first_view = first_repo.get_by_client_algo_id(saved.environment, saved.symbol, saved.client_algo_id)
        second_view = second_repo.get_by_client_algo_id(saved.environment, saved.symbol, saved.client_algo_id)
        assert first_view is not None and first_view.version == 1
        assert second_view is not None and second_view.version == 1

        winner = first_repo.update_status(saved.id, expected_version=first_view.version, status="CONFIRMED")
        first_session.commit()
        assert winner.version == 2

        with pytest.raises(OptimisticLockError):
            second_repo.update_status(saved.id, expected_version=second_view.version, status="CANCELLED")
        second_session.rollback()

    with SessionLocal() as final_session:
        final = SqlAlchemyExchangeOrderIdentityRepository(final_session).get_by_client_algo_id(saved.environment, saved.symbol, saved.client_algo_id)
        assert final is not None
        assert final.version == 2
        assert final.status == "CONFIRMED"


def test_unknown_states_and_leg_values_are_rejected_fail_closed(session: Session) -> None:
    with pytest.raises(PersistenceValidationError):
        ExecutionIntent(environment="BINANCE_FUTURES_TESTNET", symbol="BTCUSDT", intent_type="X", state="UNKNOWN")
    intent = _persisted_intent(session)
    with pytest.raises(PersistenceValidationError):
        ProtectivePair(pair_id="pair", correlation_id=intent.correlation_id, execution_intent_id=intent.id, environment="BINANCE_FUTURES_TESTNET", symbol="BTCUSDT", position_side="BOTH", direction="LONG", quantity=Decimal("0.0016"), state="UNKNOWN")
    pair = SqlAlchemyProtectivePairRepository(session).create(_pair(intent))
    with pytest.raises(PersistenceValidationError):
        ExchangeOrderIdentity(protective_pair_id=pair.id, environment="BINANCE_FUTURES_TESTNET", symbol="BTCUSDT", leg_type="ENTRY", client_algo_id="bad", status="PENDING")


def test_event_repositories_are_append_only(session: Session) -> None:
    pair = _persisted_pair(session)
    recovery_repo = SqlAlchemyRecoveryEventRepository(session)
    audit_repo = SqlAlchemyAuditEventRepository(session)
    first = recovery_repo.append(RecoveryEvent(correlation_id=pair.correlation_id, protective_pair_id=pair.id, event_type="LOOKUP", result="RECOVERY_REQUIRED"))
    second = recovery_repo.append(RecoveryEvent(correlation_id=pair.correlation_id, protective_pair_id=pair.id, event_type="LOOKUP", result="RECOVERED"))
    audit = audit_repo.append(AuditEvent(correlation_id=pair.correlation_id, category="CONTROL_PLANE", action="READ", environment="BINANCE_FUTURES_TESTNET", symbol="BTCUSDT", result="PASS", metadata_json={"nested": {"safe": True}}))
    assert first.id != second.id
    assert len(session.scalars(select(RecoveryEventORM)).all()) == 2
    assert audit.metadata_json == {"nested": {"safe": True}}
    assert not hasattr(recovery_repo, "delete_all")
    assert not hasattr(audit_repo, "truncate")


def test_failed_transactions_roll_back_and_do_not_silently_overwrite(session: Session) -> None:
    repo = SqlAlchemyExecutionIntentRepository(session)
    saved = repo.create(_intent())
    session.commit()
    with pytest.raises(DuplicateIdentityError):
        repo.create(_intent(correlation_id=saved.correlation_id, state="FAILED_SAFE"))
    assert repo.get_by_correlation_id(saved.correlation_id).state == "PENDING"
    recovered = repo.create(_intent(correlation_id=uuid4()))
    assert recovered.state == "PENDING"


@pytest.mark.parametrize("forbidden", [
    {"api_key": "x"},
    {"ApiSecret": "x"},
    {"nested": {"SIGNATURE": "x"}},
    {"items": [{"authorization": "Bearer x"}]},
    {"credentialLengths": {"key": 10}},
    {"raw_response": {"exchange": "payload"}},
    {"headers": {"x": "value"}},
    {"X-MBX-APIKEY": "value"},
    {"rawExchangeResponse": {"status": "payload"}},
    {"signed-url": "value"},
    {"authenticatedHeaders": {"x": "value"}},
    {"items": [{"requestHeaders": {"x": "value"}}]},
    {"nested": {"responses": [{"exchange_response": {"x": "value"}}]}},
])
def test_audit_metadata_rejects_nested_case_variant_forbidden_keys(session: Session, forbidden: dict) -> None:
    repo = SqlAlchemyAuditEventRepository(session)
    with pytest.raises(ForbiddenAuditMetadataError):
        repo.append(AuditEvent(category="AUDIT", action="WRITE", environment="BINANCE_FUTURES_TESTNET", result="FAIL", metadata_json=forbidden))
    assert session.scalars(select(AuditEventORM)).all() == []


@pytest.mark.parametrize("unsafe", [
    Decimal("1.25"),
    datetime.now(),
    uuid4(),
    AuditEventORM(),
    _UnsafeMetadataValue(),
    {"set"},
    b"bytes",
])
def test_audit_metadata_rejects_non_json_values_before_serialization(session: Session, unsafe: object) -> None:
    repo = SqlAlchemyAuditEventRepository(session)
    with pytest.raises(PersistenceValidationError):
        repo.append(AuditEvent(category="AUDIT", action="WRITE", environment="BINANCE_FUTURES_TESTNET", result="FAIL", metadata_json={"safe_key": unsafe}))
    assert session.scalars(select(AuditEventORM)).all() == []


def test_safe_audit_metadata_is_persisted_without_secret_material(session: Session) -> None:
    event = SqlAlchemyAuditEventRepository(session).append(AuditEvent(category="AUDIT", action="READ", environment="BINANCE_FUTURES_TESTNET", symbol="BTCUSDT", result="PASS", metadata_json={"decision": "READ_ONLY", "legs": ({"type": "STOP"},)}))
    dumped = str(event.metadata_json).lower()
    assert "secret" not in dumped
    assert "signature" not in dumped
    assert "authorization" not in dumped
    assert "raw_response" not in dumped
    assert event.metadata_json == {"decision": "READ_ONLY", "legs": [{"type": "STOP"}]}


def test_alembic_requires_environment_database_url_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    config = Config("alembic.ini")
    assert config.get_main_option("sqlalchemy.url") == ""
    monkeypatch.delenv("ICT_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="ICT_DATABASE_URL or DATABASE_URL"):
        command.upgrade(config, "head")


def test_postgresql_dialect_schema_uses_jsonb_uuid_timestamptz_numeric_and_restrict_fks() -> None:
    ddl = " ".join(str(CreateTable(ExecutionPersistenceBase.metadata.tables["audit_events"]).compile(dialect=postgresql.dialect())).upper().split())
    assert "UUID" in ddl
    assert "TIMESTAMP WITH TIME ZONE" in ddl
    assert "JSONB" in ddl
    intent_ddl = " ".join(str(CreateTable(ExecutionPersistenceBase.metadata.tables["execution_intents"]).compile(dialect=postgresql.dialect())).upper().split())
    assert "NUMERIC(38, 18)" in intent_ddl
    for table_name in ("protective_pairs", "exchange_order_identities", "recovery_events"):
        table = ExecutionPersistenceBase.metadata.tables[table_name]
        assert all(foreign_key.ondelete == "RESTRICT" for foreign_key in table.foreign_keys)
    module = _migration_module()
    assert "JSONB" in str(module._metadata_json().compile(dialect=postgresql.dialect())).upper()


def test_only_supervised_recovery_mutation_api_route_exists_and_no_binance_transport_is_invoked() -> None:
    client = TestClient(create_app())
    paths = client.get("/openapi.json").json()["paths"]
    live_paths = {path: methods for path, methods in paths.items() if path.startswith("/api/v1/live")}
    assert live_paths
    assert set(live_paths["/api/v1/live/recovery/run"]) == {"post"}
    assert all(
        set(methods) == {"get"}
        for path, methods in live_paths.items()
        if path != "/api/v1/live/recovery/run"
    )
