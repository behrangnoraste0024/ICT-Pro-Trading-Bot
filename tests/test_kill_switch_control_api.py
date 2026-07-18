from __future__ import annotations

import json
import importlib.util
import gc
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, MetaData, String, Table, create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations

from api.kill_switch_control_models import ENGAGE_CONFIRMATION, RELEASE_CONFIRMATION
from api.kill_switch_control_service import KillSwitchControlService
from api.live_control_plane_routes import get_kill_switch_control_service
from api.main import create_app
from infrastructure.persistence.execution_orm import (
    AuditEventORM,
    ExchangeOrderIdentityORM,
    ExecutionIntentORM,
    ExecutionPersistenceBase,
    KillSwitchStateORM,
    ProtectivePairORM,
    RecoveryEventORM,
)
from infrastructure.persistence.kill_switch_persistence import KillSwitchPersistence
from infrastructure.persistence.kill_switch_persistence import KillSwitchPersistenceError
from infrastructure.persistence.kill_switch_gate import DurableKillSwitchGate, KillSwitchGateError
from infrastructure.persistence.schema_contract import PERSISTENCE_REVISION
from models.binance_futures_testnet_protective_orders import BinanceFuturesTestnetProtectiveOrdersConfig
from tests import kill_switch_test_support
from tests.kill_switch_test_support import durable_state_env


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, method: str, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(method)
        if method != "GET":
            raise AssertionError("kill-switch endpoints must not send mutations")
        raise AssertionError("kill-switch endpoints must not use Binance transport")


def _write_config(root: Path) -> None:
    config_dir = root / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    config = BinanceFuturesTestnetProtectiveOrdersConfig()
    (config_dir / "binance_futures_testnet_protective_orders.json").write_text(
        json.dumps(config.to_dict()), encoding="utf-8"
    )


def _database(tmp_path: Path) -> tuple[dict[str, str], Any]:
    database_url = f"sqlite:///{tmp_path / 'kill_switch.sqlite'}"
    engine = create_engine(database_url, future=True)
    ExecutionPersistenceBase.metadata.create_all(engine)
    metadata = MetaData()
    revision = Table("alembic_version", metadata, Column("version_num", String(64), primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(revision.insert().values(version_num=PERSISTENCE_REVISION))
    return {"ICT_DATABASE_URL": database_url}, engine


def _migration(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _run_migration(engine: Any, migration: Any, operation: str) -> None:
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        previous = migration.op
        migration.op = operations
        try:
            getattr(migration, operation)()
        finally:
            migration.op = previous


def _set_migration_revision(engine: Any, revision: str) -> None:
    metadata = MetaData()
    version = Table("alembic_version", metadata, Column("version_num", String(64), primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(version.delete())
        connection.execute(version.insert().values(version_num=revision))


def test_kill_switch_alembic_upgrade_downgrade_reupgrade_preserves_286_data(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.sqlite'}", future=True)
    release_286 = _migration(
        "alembic/versions/20260714_0286_execution_persistence.py",
        "release_0286_execution_persistence",
    )
    release_290 = _migration(
        "alembic/versions/20260717_0290_kill_switch_state.py",
        "release_0290_kill_switch_state",
    )
    audit_id = uuid4().hex
    correlation_id = uuid4().hex

    _run_migration(engine, release_286, "upgrade")
    _set_migration_revision(engine, release_286.revision)
    with engine.begin() as connection:
        audit_events = Table("audit_events", MetaData(), autoload_with=connection)
        connection.execute(audit_events.insert().values(
            id=audit_id,
            correlation_id=correlation_id,
            category="MIGRATION_TEST",
            action="PREEXISTING_ROW",
            environment="BINANCE_FUTURES_TESTNET",
            symbol="BTCUSDT",
            result="PASS",
            error_code=None,
            metadata_json={"preserved": True},
            created_at=datetime(2026, 7, 17, tzinfo=UTC),
        ))

    def assert_preexisting_row() -> None:
        with engine.connect() as connection:
            audit_events = Table("audit_events", MetaData(), autoload_with=connection)
            row = connection.execute(select(audit_events).where(audit_events.c.id == audit_id)).mappings().one()
        assert row["correlation_id"] == correlation_id
        assert row["action"] == "PREEXISTING_ROW"
        assert row["metadata_json"] == {"preserved": True}

    _run_migration(engine, release_290, "upgrade")
    _set_migration_revision(engine, PERSISTENCE_REVISION)
    inspector = inspect(engine)
    assert "kill_switch_states" in inspector.get_table_names()
    columns = {column["name"]: column for column in inspector.get_columns("kill_switch_states")}
    assert set(columns) == {"id", "scope", "environment", "symbol", "state", "created_at", "updated_at", "version"}
    assert columns["scope"]["nullable"] is False
    assert columns["state"]["nullable"] is False
    assert columns["version"]["nullable"] is False
    assert any(constraint["column_names"] == ["scope"] for constraint in inspector.get_unique_constraints("kill_switch_states"))
    assert_preexisting_row()

    env = {"ICT_DATABASE_URL": str(engine.url)}
    gate = DurableKillSwitchGate(env=env)
    with pytest.raises(KillSwitchGateError, match="KILL_SWITCH_ENGAGED"):
        gate.require_released()

    kill_switch_states = Table("kill_switch_states", MetaData(), autoload_with=engine)
    malformed_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(kill_switch_states.insert().values(
            id=malformed_id,
            scope="BINANCE_FUTURES_TESTNET:BTCUSDT",
            environment="BINANCE_FUTURES_TESTNET",
            symbol="BTCUSDT",
            state="released",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            version=1,
        ))
    with pytest.raises(KillSwitchGateError, match="KILL_SWITCH_STATE_UNAVAILABLE"):
        gate.require_released()
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(kill_switch_states.insert().values(
                id=uuid4().hex,
                scope="BINANCE_FUTURES_TESTNET:BTCUSDT",
                environment="BINANCE_FUTURES_TESTNET",
                symbol="BTCUSDT",
                state="ENGAGED",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                version=1,
            ))
    with engine.begin() as connection:
        connection.execute(kill_switch_states.delete().where(kill_switch_states.c.id == malformed_id))

    persistence = KillSwitchPersistence(env=env)
    persistence.ensure_available()
    engaged, changed = persistence.engage()
    assert changed is True and engaged.state == "ENGAGED" and engaged.version == 1
    released = persistence.release(expected_version=engaged.version)
    assert released.state == "RELEASED" and released.version == 2
    persistence.close()
    gate.require_released()

    _run_migration(engine, release_290, "downgrade")
    _set_migration_revision(engine, release_286.revision)
    assert "kill_switch_states" not in inspect(engine).get_table_names()
    assert_preexisting_row()

    _run_migration(engine, release_290, "upgrade")
    _set_migration_revision(engine, PERSISTENCE_REVISION)
    assert "kill_switch_states" in inspect(engine).get_table_names()
    assert_preexisting_row()
    final_persistence = KillSwitchPersistence(env=env)
    final_persistence.ensure_available()
    assert final_persistence.current() is None
    final_persistence.close()
    with pytest.raises(KillSwitchGateError, match="KILL_SWITCH_ENGAGED"):
        gate.require_released()
    engine.dispose()


def test_durable_state_test_helper_removes_temporary_sqlite_directory() -> None:
    env = durable_state_env()
    database = make_url(env["ICT_DATABASE_URL"]).database
    assert database is not None
    temporary_directory = Path(database).parent
    assert temporary_directory.exists()

    del env
    gc.collect()

    assert not temporary_directory.exists()


def test_durable_state_test_helper_cleans_up_synchronously_when_setup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temporary_directory = tmp_path / "failed-kill-switch-setup"
    database_path = temporary_directory / "kill_switch.sqlite"
    order: list[str] = []

    class FixedTemporaryDirectory:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            temporary_directory.mkdir()
            self.name = str(temporary_directory)

        def cleanup(self) -> None:
            order.append("cleanup")
            assert database_path.exists()
            shutil.rmtree(temporary_directory)

    original_close = kill_switch_test_support.KillSwitchPersistence.close
    original_dispose = Engine.dispose

    def tracked_close(self: KillSwitchPersistence) -> None:
        order.append("persistence_close")
        original_close(self)

    def tracked_dispose(self: Engine, close: bool = True) -> None:
        order.append("engine_dispose")
        original_dispose(self, close=close)

    def fail_engage(self: KillSwitchPersistence):
        assert Path(make_url(self.env["ICT_DATABASE_URL"]).database or "") == database_path
        assert database_path.exists()
        raise KillSwitchPersistenceError("TEST_SETUP_FAILURE")

    monkeypatch.setattr(kill_switch_test_support.tempfile, "TemporaryDirectory", FixedTemporaryDirectory)
    monkeypatch.setattr(kill_switch_test_support.KillSwitchPersistence, "close", tracked_close)
    monkeypatch.setattr(Engine, "dispose", tracked_dispose)
    monkeypatch.setattr(kill_switch_test_support.KillSwitchPersistence, "engage", fail_engage)

    with pytest.raises(KillSwitchPersistenceError, match="TEST_SETUP_FAILURE"):
        durable_state_env()

    assert order[-1] == "cleanup"
    assert "persistence_close" in order[:-1]
    assert "engine_dispose" in order[:-1]
    assert not database_path.exists()
    assert not temporary_directory.exists()


def _request(confirmation: str, **changes: Any) -> dict[str, Any]:
    payload = {
        "environment": "BINANCE_FUTURES_TESTNET",
        "symbol": "BTCUSDT",
        "acknowledged": True,
        "confirmation": confirmation,
    }
    payload.update(changes)
    return payload


def _snapshot(engine: Any) -> dict[str, list[tuple[Any, ...]]]:
    def rows(model: Any, fields: tuple[str, ...]) -> list[tuple[Any, ...]]:
        with Session(engine) as session:
            return [tuple(getattr(row, field) for field in fields) for row in session.scalars(select(model).order_by(model.id)).all()]

    return {
        "switch": rows(KillSwitchStateORM, ("id", "scope", "environment", "symbol", "state", "version")),
        "intents": rows(ExecutionIntentORM, ("id", "correlation_id", "state", "version")),
        "pairs": rows(ProtectivePairORM, ("id", "pair_id", "state", "recovery_required", "version")),
        "identities": rows(ExchangeOrderIdentityORM, ("id", "protective_pair_id", "leg_type", "status", "version")),
        "audits": rows(AuditEventORM, ("id", "category", "action", "result")),
        "recovery": rows(RecoveryEventORM, ("id", "correlation_id", "event_type", "result")),
    }


def _client(tmp_path: Path, env: dict[str, str], transport: RecordingTransport, **service_changes: Any) -> TestClient:
    _write_config(tmp_path)
    service = KillSwitchControlService(repo_root=tmp_path, env=env, **service_changes)
    app = create_app()
    app.dependency_overrides[get_kill_switch_control_service] = lambda: service
    return TestClient(app)


def test_engage_persists_before_success_and_is_idempotent(tmp_path: Path) -> None:
    env, engine = _database(tmp_path)
    transport = RecordingTransport()
    client = _client(tmp_path, env, transport)

    first = client.post("/api/v1/live/kill-switch/engage", json=_request(ENGAGE_CONFIRMATION))
    second = client.post("/api/v1/live/kill-switch/engage", json=_request(ENGAGE_CONFIRMATION))

    assert first.status_code == 200
    assert first.json() == {
        "accepted": True, "environment": "BINANCE_FUTURES_TESTNET", "symbol": "BTCUSDT",
        "state": "ENGAGED", "changed": True, "version": 1, "updated_at": first.json()["updated_at"], "blocking_code": None,
    }
    assert second.status_code == 200
    assert second.json()["state"] == "ENGAGED"
    assert second.json()["changed"] is False
    assert second.json()["version"] == 1
    assert transport.calls == []
    snapshot = _snapshot(engine)
    assert snapshot["switch"][0][4:] == ("ENGAGED", 1)
    assert [row[2] for row in snapshot["audits"]] == ["KILL_SWITCH_ENGAGED"]


def test_release_succeeds_only_after_durable_engagement_and_never_uses_transport(tmp_path: Path) -> None:
    env, engine = _database(tmp_path)
    transport = RecordingTransport()
    client = _client(tmp_path, env, transport)
    assert client.post("/api/v1/live/kill-switch/engage", json=_request(ENGAGE_CONFIRMATION)).status_code == 200

    response = client.post("/api/v1/live/kill-switch/release", json=_request(RELEASE_CONFIRMATION))

    assert response.status_code == 200
    assert response.json()["state"] == "RELEASED"
    assert response.json()["changed"] is True
    assert response.json()["version"] == 2
    assert transport.calls == []
    assert not (tmp_path / "data/runtime/binance_futures_testnet_protective_orders/protective.lock").exists()
    snapshot = _snapshot(engine)
    assert snapshot["switch"][0][4:] == ("RELEASED", 2)
    assert {row[2] for row in snapshot["audits"]} == {"KILL_SWITCH_ENGAGED", "KILL_SWITCH_RELEASED"}


@pytest.mark.parametrize("reason", ["stale_lock", "untrusted_journal"])
def test_rejected_release_preserves_state_journal_and_uses_no_transport(tmp_path: Path, reason: str) -> None:
    env, engine = _database(tmp_path)
    transport = RecordingTransport()
    client = _client(tmp_path, env, transport)
    assert client.post("/api/v1/live/kill-switch/engage", json=_request(ENGAGE_CONFIRMATION)).status_code == 200
    runtime = tmp_path / "data/runtime/binance_futures_testnet_protective_orders"
    runtime.mkdir(parents=True, exist_ok=True)
    journal = runtime / "protective.json"
    original_journal = b'{"invalid":"journal"}'
    if reason == "stale_lock":
        (runtime / "protective.lock").write_text("held", encoding="ascii")
    else:
        journal.write_bytes(original_journal)
    before = _snapshot(engine)

    response = client.post("/api/v1/live/kill-switch/release", json=_request(RELEASE_CONFIRMATION))

    assert response.status_code == 409
    assert response.json()["detail"]["code"] in {"MUTATION_LOCK_ACTIVE", "PROTECTIVE_JOURNAL_UNTRUSTED"}
    assert _snapshot(engine) == before
    assert journal.read_bytes() == original_journal if journal.exists() else True
    assert transport.calls == []


def test_release_blocks_when_persistence_missing_without_writing_journal_or_transport(tmp_path: Path) -> None:
    transport = RecordingTransport()
    client = _client(tmp_path, {}, transport)
    journal = tmp_path / "data/runtime/binance_futures_testnet_protective_orders/protective.json"
    journal.parent.mkdir(parents=True, exist_ok=True)
    original = b"preserve-me"
    journal.write_bytes(original)

    response = client.post("/api/v1/live/kill-switch/release", json=_request(RELEASE_CONFIRMATION))

    assert response.status_code == 503
    assert response.json()["detail"] == {"code": "PERSISTENCE_UNAVAILABLE", "message": "Kill switch persistence is unavailable.", "details": {}}
    assert journal.read_bytes() == original
    assert transport.calls == []


def test_release_blocks_unresolved_protective_lifecycle_without_mutating_it(tmp_path: Path) -> None:
    env, engine = _database(tmp_path)
    transport = RecordingTransport()
    client = _client(tmp_path, env, transport)
    assert client.post("/api/v1/live/kill-switch/engage", json=_request(ENGAGE_CONFIRMATION)).status_code == 200
    intent_id = uuid4()
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        session.add(ExecutionIntentORM(
            id=intent_id, correlation_id=uuid4(), environment="BINANCE_FUTURES_TESTNET", symbol="BTCUSDT",
            intent_type="PROTECTIVE_PAIR_CREATE", state="PERSISTED", requested_quantity=Decimal("0.001"),
            requested_price=Decimal("60000"), failure_code=None, created_at=now, updated_at=now, version=1,
        ))
        session.add(ProtectivePairORM(
            id=uuid4(), pair_id="unresolved-kill-switch-test", correlation_id=uuid4(), execution_intent_id=intent_id,
            environment="BINANCE_FUTURES_TESTNET", symbol="BTCUSDT", position_side="BOTH", direction="LONG",
            quantity=Decimal("0.001"), state="RECOVERY_REQUIRED", recovery_required=True, blocking_reason=None,
            created_at=now, updated_at=now, version=1,
        ))
    before = _snapshot(engine)

    response = client.post("/api/v1/live/kill-switch/release", json=_request(RELEASE_CONFIRMATION))

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "UNRESOLVED_PROTECTIVE_PAIR"
    assert _snapshot(engine) == before
    assert transport.calls == []


def test_engage_persistence_failure_is_sanitized_and_uses_no_transport(tmp_path: Path) -> None:
    transport = RecordingTransport()

    class BrokenPersistence:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def ensure_available(self) -> None:
            raise KillSwitchPersistenceError("PERSISTENCE_UNAVAILABLE")

        def close(self) -> None:
            pass

    client = _client(tmp_path, {}, transport, persistence_factory=BrokenPersistence)

    response = client.post("/api/v1/live/kill-switch/engage", json=_request(ENGAGE_CONFIRMATION))

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "PERSISTENCE_UNAVAILABLE",
        "message": "Kill switch persistence is unavailable.",
        "details": {},
    }
    assert "postgresql" not in response.text.lower()
    assert transport.calls == []


def test_durable_gate_fails_closed_for_missing_schema_and_malformed_state(tmp_path: Path) -> None:
    missing_schema_url = f"sqlite:///{tmp_path / 'missing-schema.sqlite'}"
    with pytest.raises(KillSwitchGateError) as missing_schema:
        DurableKillSwitchGate(env={"ICT_DATABASE_URL": missing_schema_url}).require_released()
    assert missing_schema.value.code == "KILL_SWITCH_STATE_UNAVAILABLE"

    env, engine = _database(tmp_path)
    persistence = KillSwitchPersistence(env=env)
    persistence.ensure_available()
    persistence.engage()
    persistence.close()
    with Session(engine) as session, session.begin():
        state = session.scalar(select(KillSwitchStateORM))
        assert state is not None
        state.state = "MALFORMED"

    with pytest.raises(KillSwitchGateError) as malformed:
        DurableKillSwitchGate(env=env).require_released()
    assert malformed.value.code == "KILL_SWITCH_STATE_UNAVAILABLE"


def test_release_blocks_terminal_pair_with_recovery_required_without_journal(tmp_path: Path) -> None:
    env, engine = _database(tmp_path)
    transport = RecordingTransport()
    client = _client(tmp_path, env, transport)
    assert client.post("/api/v1/live/kill-switch/engage", json=_request(ENGAGE_CONFIRMATION)).status_code == 200
    intent_id = uuid4()
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        session.add(ExecutionIntentORM(id=intent_id, correlation_id=uuid4(), environment="BINANCE_FUTURES_TESTNET", symbol="BTCUSDT", intent_type="PROTECTIVE_PAIR_CREATE", state="PERSISTED", requested_quantity=Decimal("0.001"), requested_price=Decimal("60000"), failure_code=None, created_at=now, updated_at=now, version=1))
        session.add(ProtectivePairORM(id=uuid4(), pair_id="terminal-recovery-required", correlation_id=uuid4(), execution_intent_id=intent_id, environment="BINANCE_FUTURES_TESTNET", symbol="BTCUSDT", position_side="BOTH", direction="LONG", quantity=Decimal("0.001"), state="COMPLETED", recovery_required=True, blocking_reason=None, created_at=now, updated_at=now, version=1))
    before = _snapshot(engine)

    response = client.post("/api/v1/live/kill-switch/release", json=_request(RELEASE_CONFIRMATION))

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "UNRESOLVED_PROTECTIVE_PAIR"
    assert _snapshot(engine) == before
    assert not (tmp_path / "data/runtime/binance_futures_testnet_protective_orders/protective.lock").exists()
    assert transport.calls == []


def test_release_optimistic_conflict_keeps_durable_state_and_releases_lock(tmp_path: Path) -> None:
    env, engine = _database(tmp_path)
    transport = RecordingTransport()

    class StalePersistence(KillSwitchPersistence):
        def current(self):
            state = super().current()
            assert state is not None
            return replace(state, version=state.version + 1)

    normal_client = _client(tmp_path, env, transport)
    assert normal_client.post("/api/v1/live/kill-switch/engage", json=_request(ENGAGE_CONFIRMATION)).status_code == 200
    client = _client(tmp_path, env, transport, persistence_factory=StalePersistence)
    before = _snapshot(engine)

    response = client.post("/api/v1/live/kill-switch/release", json=_request(RELEASE_CONFIRMATION))

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "KILL_SWITCH_VERSION_CONFLICT"
    assert _snapshot(engine) == before
    assert not (tmp_path / "data/runtime/binance_futures_testnet_protective_orders/protective.lock").exists()
    assert transport.calls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("confirmation", "postgresql://user:secret@host/db SELECT * FROM x"),
        ("acknowledged", "X-MBX-APIKEY=secret\ntraceback"),
        ("unknown", "signed-url=https://secret"),
    ],
)
def test_kill_switch_validation_errors_are_fixed_and_sanitized(tmp_path: Path, field: str, value: Any) -> None:
    env, _ = _database(tmp_path)
    transport = RecordingTransport()
    client = _client(tmp_path, env, transport)
    payload = _request(ENGAGE_CONFIRMATION)
    payload[field] = value

    response = client.post("/api/v1/live/kill-switch/engage", json=payload)

    assert response.status_code == 422
    assert response.json() == {
        "accepted": False,
        "blocking_code": "INVALID_REQUEST",
        "message": "Request validation failed.",
    }
    body = json.dumps(response.json())
    for marker in ("postgresql://", "secret", "X-MBX-APIKEY", "traceback", "signed-url", "SELECT"):
        assert marker not in body
    assert transport.calls == []
