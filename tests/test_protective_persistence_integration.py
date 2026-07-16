from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs
from uuid import uuid4

import pytest
from sqlalchemy import Column, MetaData, String, Table, create_engine, event, select
from sqlalchemy.orm import Session

from engine.diagnostics.binance_futures_testnet_protective_orders_engine import BinanceFuturesTestnetProtectiveOrdersEngine
from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import BinanceLifecycleHTTPResponse
from infrastructure.exchanges.binance_futures_testnet_protective_orders_client import BinanceFuturesTestnetProtectiveAPIError
from infrastructure.persistence.execution_orm import (
    AuditEventORM,
    ExchangeOrderIdentityORM,
    ExecutionIntentORM,
    ExecutionPersistenceBase,
    ProtectivePairORM,
    RecoveryEventORM,
)
from infrastructure.persistence.protective_lifecycle_persistence import ProtectiveLifecyclePersistence
from infrastructure.persistence.protective_lifecycle_persistence import ProtectivePersistenceError
from infrastructure.persistence.schema_contract import PERSISTENCE_REVISION
from models.binance_futures_testnet_protective_orders import (
    BinanceFuturesTestnetProtectiveJournal,
    BinanceFuturesTestnetProtectiveOrdersConfig,
    ProtectiveMutationIntent,
)
from models.execution_persistence import ExchangeOrderIdentity, ExecutionIntent, ProtectivePair

PAIR_ID = "pair-001"
STOP_ID = "smcbot-protect-sl-001"
TP_ID = "smcbot-protect-tp-001"
CONFIRMATION = "CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE"


def _database(tmp_path: Path) -> tuple[str, object]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "persistence.db"
    engine = create_engine(f"sqlite:///{path}", future=True)
    ExecutionPersistenceBase.metadata.create_all(engine)
    version = Table("alembic_version", MetaData(), Column("version_num", String(64), primary_key=True))
    version.create(engine)
    with engine.begin() as connection:
        connection.execute(version.insert().values(version_num=PERSISTENCE_REVISION))
    return f"sqlite:///{path}", engine


def _env(database_url: str | None) -> dict[str, str]:
    env = {
        "BINANCE_FUTURES_TESTNET_API_KEY": "unit-test-key",
        "BINANCE_FUTURES_TESTNET_API_SECRET": "unit-test-secret",
    }
    if database_url is not None:
        env["ICT_DATABASE_URL"] = database_url
    return env


def _config(tmp_path: Path) -> Path:
    path = tmp_path / "configs" / "binance_futures_testnet_protective_orders.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(BinanceFuturesTestnetProtectiveOrdersConfig().to_dict()), encoding="utf-8")
    return path


def _position() -> list[dict]:
    return [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": "0.001", "entryPrice": "49000", "markPrice": "50000", "notional": "50"}]


def _order(client_id: str, order_type: str, status: str = "NEW") -> dict:
    return {
        "symbol": "BTCUSDT",
        "algoType": "CONDITIONAL",
        "clientAlgoId": client_id,
        "algoId": "42" if order_type == "STOP_MARKET" else "43",
        "side": "SELL",
        "positionSide": "BOTH",
        "orderType": order_type,
        "triggerPrice": "45000.00" if order_type == "STOP_MARKET" else "55000.00",
        "algoStatus": status,
        "actualQty": "0",
        "actualPrice": "0",
        "closePosition": True,
        "workingType": "MARK_PRICE",
        "priceProtect": True,
    }


def _http_get(url, timeout):
    if url.endswith("/fapi/v1/time"):
        return BinanceLifecycleHTTPResponse(200, url, {"serverTime": 1000}, 1)
    if "/fapi/v1/exchangeInfo" in url:
        return BinanceLifecycleHTTPResponse(
            200,
            url,
            {"symbols": [{"symbol": "BTCUSDT", "filters": [{"filterType": "PRICE_FILTER", "minPrice": "1", "maxPrice": "1000000", "tickSize": "0.10"}]}]},
            1,
        )
    raise AssertionError(f"unexpected public request: {url}")


class LifecycleTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.created: set[str] = set()
        self.deleted: set[str] = set()

    def __call__(self, method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        self.calls.append((method, url))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 1)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 1)
        client_id = params["clientAlgoId"][0]
        order_type = "STOP_MARKET" if client_id == STOP_ID else "TAKE_PROFIT_MARKET"
        if method == "POST":
            self.created.add(client_id)
            return BinanceLifecycleHTTPResponse(200, url, _order(client_id, order_type), 1)
        if method == "DELETE":
            self.deleted.add(client_id)
            return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": "42", "code": 200}, 1)
        if client_id in self.deleted or client_id not in self.created:
            raise BinanceFuturesTestnetProtectiveAPIError(
                "NO_SUCH_ORDER",
                http_status=400,
                binance_code=-2013,
                method="GET",
                path="/fapi/v1/algoOrder",
                request_transmitted=True,
                response_received=True,
            )
        return BinanceLifecycleHTTPResponse(200, url, _order(client_id, order_type), 1)


def _run(tmp_path: Path, database_url: str | None, transport=None):
    transport = LifecycleTransport() if transport is None else transport
    result = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=ProtectiveLifecyclePersistence,
    ).run_protective_lifecycle(
        PAIR_ID,
        STOP_ID,
        TP_ID,
        confirmation=CONFIRMATION,
        config_path=str(_config(tmp_path)),
    )
    return result, transport


def _db_snapshot(database_engine) -> dict[str, list[tuple]]:
    models = (ExecutionIntentORM, ProtectivePairORM, ExchangeOrderIdentityORM, AuditEventORM, RecoveryEventORM)

    def stable(value):
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return json.dumps(value, sort_keys=True, separators=(",", ":"))
        return None if value is None else str(value)

    snapshot: dict[str, list[tuple]] = {}
    with Session(database_engine) as session:
        for model in models:
            rows = list(session.scalars(select(model).order_by(model.id.asc())).all())
            snapshot[model.__tablename__] = [
                tuple(stable(getattr(row, column.name)) for column in model.__table__.columns)
                for row in rows
            ]
    return snapshot


def test_persistence_unavailable_blocks_before_transport_journal_and_lock(tmp_path: Path) -> None:
    def no_transport(*args, **kwargs):
        raise AssertionError("persistence failure must precede authenticated transport")

    result, _ = _run(tmp_path, None, no_transport)

    assert result.decision == "PERSISTENCE_UNAVAILABLE"
    assert not (tmp_path / "data" / "runtime" / "binance_futures_testnet_protective_orders" / "protective.json").exists()
    assert not (tmp_path / "data" / "runtime" / "binance_futures_testnet_protective_orders" / "protective.lock").exists()


def test_successful_lifecycle_persists_exact_state_transitions_and_identities(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path)

    result, transport = _run(tmp_path, database_url)

    assert result.status == "PASS"
    assert [method for method, _ in transport.calls].count("POST") == 2
    assert [method for method, _ in transport.calls].count("DELETE") == 2
    with Session(database_engine) as session:
        intents = list(session.scalars(select(ExecutionIntentORM).order_by(ExecutionIntentORM.intent_type)).all())
        pair = session.scalar(select(ProtectivePairORM))
        identities = list(session.scalars(select(ExchangeOrderIdentityORM).order_by(ExchangeOrderIdentityORM.leg_type)).all())
        actions = list(session.scalars(select(AuditEventORM.action)).all())
    assert [(item.intent_type, item.state) for item in intents] == [
        ("PROTECTIVE_PAIR_CANCEL", "COMPLETED"),
        ("PROTECTIVE_PAIR_CANCEL", "COMPLETED"),
        ("PROTECTIVE_PAIR_CREATE", "COMPLETED"),
    ]
    assert pair is not None and pair.state == "COMPLETED" and pair.quantity == Decimal("0.001")
    assert {(item.leg_type, item.client_algo_id, item.status) for item in identities} == {
        ("STOP", STOP_ID, "ABSENT"),
        ("TAKE_PROFIT", TP_ID, "ABSENT"),
    }
    assert {"INTENT_PERSISTED", "MUTATION_TRANSMITTED", "CREATE_CONFIRMED", "DELETE_CONFIRMED"}.issubset(actions)


def test_duplicate_completed_lifecycle_does_not_resend_or_duplicate(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path)
    first, first_transport = _run(tmp_path, database_url)
    second_transport = LifecycleTransport()

    second, _ = _run(tmp_path, database_url, second_transport)

    assert first.status == "PASS"
    assert second.decision == "PROTECTIVE_LIFECYCLE_ALREADY_COMPLETED"
    assert second_transport.calls == []
    with Session(database_engine) as session:
        assert len(list(session.scalars(select(ProtectivePairORM)).all())) == 1
        assert len(list(session.scalars(select(ExecutionIntentORM)).all())) == 3
        assert len(list(session.scalars(select(ExchangeOrderIdentityORM)).all())) == 2
    assert [method for method, _ in first_transport.calls].count("POST") == 2


def test_db_only_unresolved_pair_blocks_without_exchange_or_journal_change(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path)
    coordinator = ProtectiveLifecyclePersistence(env=_env(database_url))
    coordinator.ensure_available()
    from models.binance_futures_testnet_protective_orders import BinanceFuturesTestnetProtectivePosition, BinanceFuturesTestnetProtectivePreview
    position = BinanceFuturesTestnetProtectivePosition(position_amt=Decimal("0.001"), mark_price=Decimal("50000"), direction="LONG", position_side="BOTH")
    preview = BinanceFuturesTestnetProtectivePreview(pair_id=PAIR_ID, position_amount=position.position_amt, mark_price=position.mark_price, position_direction="LONG", protective_side="SELL", stop_client_algo_id=STOP_ID, take_profit_client_algo_id=TP_ID, stop_trigger=Decimal("45000"), take_profit_trigger=Decimal("55000"))
    coordinator.prepare_lifecycle(PAIR_ID, STOP_ID, TP_ID, position, preview)
    coordinator.close()
    transport = LifecycleTransport()

    result, _ = _run(tmp_path, database_url, transport)

    assert result.decision == "PERSISTENCE_DB_ONLY_UNRESOLVED"
    assert transport.calls == []
    assert not (tmp_path / "data" / "runtime" / "binance_futures_testnet_protective_orders" / "protective.json").exists()
    database_engine.dispose()


@pytest.mark.parametrize("field,value", [("pair_id", "other-pair"), ("stop_client_algo_id", "smcbot-protect-sl-other"), ("take_profit_client_algo_id", "smcbot-protect-tp-other")])
def test_replay_identity_mismatch_fails_closed(tmp_path: Path, field: str, value: str) -> None:
    database_url, _ = _database(tmp_path)
    result, _ = _run(tmp_path, database_url)
    assert result.status == "PASS"
    journal_path = tmp_path / "data" / "runtime" / "binance_futures_testnet_protective_orders" / "protective.json"
    payload = json.loads(journal_path.read_text(encoding="utf-8"))
    payload[field] = value
    journal_path.write_text(json.dumps(payload), encoding="utf-8")
    transport = LifecycleTransport()

    replay, _ = _run(tmp_path, database_url, transport)

    assert replay.status == "FAIL"
    assert transport.calls == []


def test_ambiguous_create_with_failed_lookup_marks_recovery_without_second_post(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path)

    class AmbiguousTransport(LifecycleTransport):
        post_attempted = False

        def __call__(self, method, url, body, timeout, headers):
            params = parse_qs(body.decode("utf-8"))
            if method == "POST":
                self.post_attempted = True
                self.calls.append((method, url))
                raise TimeoutError("ambiguous transport")
            if method == "GET" and "algoOrder" in url and self.post_attempted:
                self.calls.append((method, url))
                raise TimeoutError("lookup unavailable")
            return super().__call__(method, url, body, timeout, headers)

    transport = AmbiguousTransport()
    result, _ = _run(tmp_path, database_url, transport)

    assert result.decision == "RECOVERY_REQUIRED"
    assert [method for method, _ in transport.calls].count("POST") == 1
    with Session(database_engine) as session:
        pair = session.scalar(select(ProtectivePairORM))
        intent = session.scalar(select(ExecutionIntentORM).where(ExecutionIntentORM.intent_type == "PROTECTIVE_PAIR_CREATE"))
        recovery_events = list(session.scalars(select(RecoveryEventORM)).all())
    assert pair is not None and pair.state == "RECOVERY_REQUIRED" and pair.recovery_required is True
    assert intent is not None and intent.state == "RECOVERY_REQUIRED"
    assert len(recovery_events) >= 1


def test_schema_revision_mismatch_blocks_without_authenticated_transport(tmp_path: Path) -> None:
    database_url, engine = _database(tmp_path)
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE alembic_version SET version_num='unsupported'")
    calls: list[str] = []

    def transport(method, url, body, timeout, headers):
        calls.append(method)
        raise AssertionError("invalid schema must block transport")

    result, _ = _run(tmp_path, database_url, transport)

    assert result.decision == "PERSISTENCE_SCHEMA_INVALID"
    assert calls == []


def test_initial_commit_failure_rolls_back_and_prevents_mutation_journal_and_retained_lock(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path)

    def failing_session_factory(**kwargs):
        session = Session(**kwargs)

        def fail_commit(_session):
            raise OSError("database commit unavailable")

        event.listen(session, "before_commit", fail_commit)
        return session

    coordinator = ProtectiveLifecyclePersistence(env=_env(database_url), session_factory=failing_session_factory)
    transport = LifecycleTransport()
    engine = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=lambda **kwargs: coordinator,
    )

    result = engine.run_protective_lifecycle(PAIR_ID, STOP_ID, TP_ID, confirmation=CONFIRMATION, config_path=str(_config(tmp_path)))

    assert result.decision == "PERSISTENCE_COMMIT_FAILED"
    assert [method for method, _ in transport.calls].count("POST") == 0
    assert [method for method, _ in transport.calls].count("DELETE") == 0
    runtime = tmp_path / "data" / "runtime" / "binance_futures_testnet_protective_orders"
    assert not (runtime / "protective.json").exists()
    assert not (runtime / "protective.lock").exists()
    with Session(database_engine) as session:
        assert session.scalar(select(ExecutionIntentORM)) is None
        assert session.scalar(select(ProtectivePairORM)) is None
        assert session.scalar(select(AuditEventORM)) is None


def test_no_database_transaction_is_open_during_exchange_transport(tmp_path: Path) -> None:
    database_url, _ = _database(tmp_path)

    class TrackingPersistence(ProtectiveLifecyclePersistence):
        transaction_open = False

        @contextmanager
        def _transaction(self):
            assert self.transaction_open is False
            self.transaction_open = True
            try:
                with super()._transaction() as session:
                    yield session
            finally:
                self.transaction_open = False

    coordinator = TrackingPersistence(env=_env(database_url))

    class CheckingTransport(LifecycleTransport):
        def __call__(self, method, url, body, timeout, headers):
            assert coordinator.transaction_open is False
            return super().__call__(method, url, body, timeout, headers)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=CheckingTransport(),
        now_ms_provider=lambda: 1000,
        persistence_factory=lambda **kwargs: coordinator,
    ).run_protective_lifecycle(PAIR_ID, STOP_ID, TP_ID, confirmation=CONFIRMATION, config_path=str(_config(tmp_path)))

    assert result.status == "PASS"
    assert coordinator.transaction_open is False


def test_definitive_absent_create_is_failed_safe_without_retry(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path)

    class AbsentAfterTimeoutTransport(LifecycleTransport):
        post_attempted = False

        def __call__(self, method, url, body, timeout, headers):
            if method == "POST":
                self.post_attempted = True
                self.calls.append((method, url))
                raise TimeoutError("ambiguous create")
            if method == "GET" and "algoOrder" in url and self.post_attempted:
                self.calls.append((method, url))
                raise BinanceFuturesTestnetProtectiveAPIError(
                    "NO_SUCH_ORDER",
                    http_status=400,
                    binance_code=-2013,
                    method="GET",
                    path="/fapi/v1/algoOrder",
                    request_transmitted=True,
                    response_received=True,
                )
            return super().__call__(method, url, body, timeout, headers)

    transport = AbsentAfterTimeoutTransport()
    result, _ = _run(tmp_path, database_url, transport)

    assert result.decision == "CREATE_NOT_APPLIED"
    assert result.recovery_required is False
    assert [method for method, _ in transport.calls].count("POST") == 1
    with Session(database_engine) as session:
        pair = session.scalar(select(ProtectivePairORM))
        intent = session.scalar(select(ExecutionIntentORM))
    assert pair is not None and pair.state == "FAILED_SAFE" and pair.recovery_required is False
    assert intent is not None and intent.state == "FAILED_SAFE"


def test_ambiguous_delete_marks_pair_and_cancel_intent_recovery_without_retry(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path)

    class AmbiguousDeleteTransport(LifecycleTransport):
        delete_attempted = False

        def __call__(self, method, url, body, timeout, headers):
            if method == "DELETE":
                self.delete_attempted = True
                self.calls.append((method, url))
                raise ConnectionResetError("delete outcome unknown")
            if method == "GET" and "algoOrder" in url and self.delete_attempted:
                self.calls.append((method, url))
                raise OSError("temporary TLS lookup failure")
            return super().__call__(method, url, body, timeout, headers)

    transport = AmbiguousDeleteTransport()
    result, _ = _run(tmp_path, database_url, transport)

    assert result.decision == "RECOVERY_REQUIRED"
    assert [method for method, _ in transport.calls].count("DELETE") == 1
    with Session(database_engine) as session:
        pair = session.scalar(select(ProtectivePairORM))
        cancel_intent = session.scalar(select(ExecutionIntentORM).where(ExecutionIntentORM.intent_type == "PROTECTIVE_PAIR_CANCEL"))
    assert pair is not None and pair.state == "RECOVERY_REQUIRED" and pair.recovery_required is True
    assert cancel_intent is not None and cancel_intent.state == "RECOVERY_REQUIRED"


def test_restart_reconciles_present_stop_and_absent_tp_without_duplicate_post(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path)

    class CrashWindowTransport(LifecycleTransport):
        post_attempted = False

        def __call__(self, method, url, body, timeout, headers):
            params = parse_qs(body.decode("utf-8"))
            if method == "POST":
                client_id = params["clientAlgoId"][0]
                self.created.add(client_id)
                self.post_attempted = True
                self.calls.append((method, url))
                raise TimeoutError("response lost after create")
            if method == "GET" and "algoOrder" in url and self.post_attempted:
                self.calls.append((method, url))
                raise OSError("lookup unavailable during first process")
            return super().__call__(method, url, body, timeout, headers)

    first_transport = CrashWindowTransport()
    first, _ = _run(tmp_path, database_url, first_transport)
    assert first.decision == "RECOVERY_REQUIRED"

    class RestartTransport(LifecycleTransport):
        def __init__(self) -> None:
            super().__init__()
            self.created.add(STOP_ID)

    restart_transport = RestartTransport()
    recovery = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=restart_transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=ProtectiveLifecyclePersistence,
    ).recover_protective_pair(
        STOP_ID,
        TP_ID,
        confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY",
        config_path=str(_config(tmp_path)),
    )

    assert recovery.status == "PASS", (recovery.decision, recovery.reason, [item.to_dict() for item in recovery.issues])
    assert [method for method, _ in restart_transport.calls].count("POST") == 0
    assert [method for method, _ in restart_transport.calls].count("DELETE") == 1
    with Session(database_engine) as session:
        pair = session.scalar(select(ProtectivePairORM))
        intents = list(session.scalars(select(ExecutionIntentORM)).all())
    assert pair is not None and pair.state == "COMPLETED" and pair.recovery_required is False
    assert {intent.state for intent in intents} == {"COMPLETED", "FAILED_SAFE"}


def test_journal_only_state_blocks_without_exchange_or_archive(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source_url, _ = _database(source)
    successful, _ = _run(source, source_url)
    assert successful.status == "PASS"
    source_journal = source / "data" / "runtime" / "binance_futures_testnet_protective_orders" / "protective.json"

    target = tmp_path / "target"
    target_url, _ = _database(target)
    target_journal = target / "data" / "runtime" / "binance_futures_testnet_protective_orders" / "protective.json"
    target_journal.parent.mkdir(parents=True, exist_ok=True)
    original = source_journal.read_bytes()
    target_journal.write_bytes(original)
    transport = LifecycleTransport()

    result, _ = _run(target, target_url, transport)

    assert result.decision == "PERSISTENCE_JOURNAL_ONLY_UNRESOLVED"
    assert transport.calls == []
    assert target_journal.read_bytes() == original
    assert not list(target_journal.parent.glob("protective.json.archived.*"))


def test_multiple_unresolved_pairs_block_fresh_lifecycle(tmp_path: Path) -> None:
    database_url, _ = _database(tmp_path)
    coordinator = ProtectiveLifecyclePersistence(env=_env(database_url))
    coordinator.ensure_available()
    from models.binance_futures_testnet_protective_orders import BinanceFuturesTestnetProtectivePosition, BinanceFuturesTestnetProtectivePreview

    position = BinanceFuturesTestnetProtectivePosition(position_amt=Decimal("0.001"), mark_price=Decimal("50000"), direction="LONG", position_side="BOTH")
    for suffix in ("a", "b"):
        preview = BinanceFuturesTestnetProtectivePreview(
            pair_id=f"pair-{suffix}",
            position_amount=position.position_amt,
            mark_price=position.mark_price,
            position_direction="LONG",
            protective_side="SELL",
            stop_client_algo_id=f"smcbot-protect-sl-{suffix}",
            take_profit_client_algo_id=f"smcbot-protect-tp-{suffix}",
            stop_trigger=Decimal("45000"),
            take_profit_trigger=Decimal("55000"),
        )
        coordinator.prepare_lifecycle(preview.pair_id, preview.stop_client_algo_id, preview.take_profit_client_algo_id, position, preview)
    coordinator.close()
    transport = LifecycleTransport()

    result, _ = _run(tmp_path, database_url, transport)

    assert result.decision == "PERSISTENCE_MULTIPLE_UNRESOLVED"
    assert transport.calls == []


def test_pre_delete_version_conflict_blocks_delete_and_does_not_retry(tmp_path: Path) -> None:
    database_url, _ = _database(tmp_path)

    class ConflictBeforeDeletePersistence(ProtectiveLifecyclePersistence):
        def prepare_cancel(self, state, label, quantity, price):
            raise ProtectivePersistenceError("PERSISTENCE_VERSION_CONFLICT")

    transport = LifecycleTransport()
    result = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=ConflictBeforeDeletePersistence,
    ).run_protective_lifecycle(PAIR_ID, STOP_ID, TP_ID, confirmation=CONFIRMATION, config_path=str(_config(tmp_path)))

    assert result.status == "FAIL"
    assert [method for method, _ in transport.calls].count("POST") == 2
    assert [method for method, _ in transport.calls].count("DELETE") == 0


@pytest.mark.parametrize(
    "mutation,expected_decision",
    [
        ("correlation", "PERSISTENCE_CORRELATION_MISMATCH"),
        ("client_ids", "PERSISTENCE_CLIENT_ID_MISMATCH"),
        ("state", "PERSISTENCE_STATE_MISMATCH"),
        ("scope", "PERSISTENCE_SCOPE_INVALID"),
    ],
)
def test_database_identity_state_and_scope_mismatches_block_replay(tmp_path: Path, mutation: str, expected_decision: str) -> None:
    database_url, database_engine = _database(tmp_path)
    completed, _ = _run(tmp_path, database_url)
    assert completed.status == "PASS"
    with database_engine.begin() as connection:
        if mutation == "correlation":
            connection.exec_driver_sql("UPDATE protective_pairs SET correlation_id='00000000000000000000000000000000'")
        elif mutation == "client_ids":
            connection.exec_driver_sql(
                "UPDATE audit_events SET metadata_json=replace(metadata_json, ?, ?)",
                (STOP_ID, "smcbot-protect-sl-mismatch"),
            )
        elif mutation == "state":
            connection.exec_driver_sql("UPDATE protective_pairs SET state='PENDING'")
        else:
            connection.exec_driver_sql("UPDATE protective_pairs SET environment='PRODUCTION'")
    transport = LifecycleTransport()

    result, _ = _run(tmp_path, database_url, transport)

    assert result.decision == expected_decision
    assert transport.calls == []


def test_post_transport_persistence_conflict_requires_recovery_without_second_post(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path)

    class ConflictAfterPostPersistence(ProtectiveLifecyclePersistence):
        def confirm_create(self, state, label, order):
            raise ProtectivePersistenceError("PERSISTENCE_VERSION_CONFLICT", after_transport=True)

    transport = LifecycleTransport()
    result = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=ConflictAfterPostPersistence,
    ).run_protective_lifecycle(PAIR_ID, STOP_ID, TP_ID, confirmation=CONFIRMATION, config_path=str(_config(tmp_path)))

    assert result.decision == "RECOVERY_REQUIRED"
    assert [method for method, _ in transport.calls].count("POST") == 1
    with Session(database_engine) as session:
        pair = session.scalar(select(ProtectivePairORM))
        intent = session.scalar(select(ExecutionIntentORM))
    assert pair is not None and pair.state == "RECOVERY_REQUIRED"
    assert intent is not None and intent.state == "RECOVERY_REQUIRED"


def test_persisted_audit_events_are_sanitized_and_contain_no_credentials(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path)
    result, _ = _run(tmp_path, database_url)
    assert result.status == "PASS"

    with Session(database_engine) as session:
        events = list(session.scalars(select(AuditEventORM)).all())
    serialized = json.dumps([event.metadata_json for event in events], sort_keys=True)
    forbidden = ("unit-test-key", "unit-test-secret", "signature", "signed-url", "headers", "database_url", "sqlite://")
    assert all(marker not in serialized for marker in forbidden)


@pytest.mark.parametrize("failed_label", ["TAKE_PROFIT", "STOP"])
def test_cancel_prepare_failure_preserves_exact_journal_and_blocks_failed_leg_delete(tmp_path: Path, failed_label: str) -> None:
    database_url, database_engine = _database(tmp_path)
    journal_path = tmp_path / "data" / "runtime" / "binance_futures_testnet_protective_orders" / "protective.json"
    snapshots: dict[str, bytes] = {}
    database_snapshots: dict[str, dict[str, list[tuple]]] = {}

    class ObservedCancelPersistence(ProtectiveLifecyclePersistence):
        def prepare_cancel(self, state, label, quantity, price):
            snapshots[label] = journal_path.read_bytes()
            database_snapshots[label] = _db_snapshot(database_engine)
            return super().prepare_cancel(state, label, quantity, price)

    def failing_session_factory(**kwargs):
        session = Session(**kwargs)

        def identify_target_cancel(current_session, _flush_context, _instances):
            for item in current_session.new:
                if not isinstance(item, AuditEventORM) or item.action != "INTENT_PERSISTED":
                    continue
                metadata = item.metadata_json
                if isinstance(metadata, dict) and metadata.get("intent_type") == "PROTECTIVE_PAIR_CANCEL" and metadata.get("leg_type") == failed_label:
                    current_session.info["fail_target_cancel_commit"] = True

        def fail_target_cancel_commit(current_session):
            if current_session.info.get("fail_target_cancel_commit"):
                raise OSError("postgresql://user:secret@host/db SELECT rollback traceback rawResponse")

        event.listen(session, "before_flush", identify_target_cancel)
        event.listen(session, "before_commit", fail_target_cancel_commit)
        return session

    coordinator = ObservedCancelPersistence(env=_env(database_url), session_factory=failing_session_factory)

    class RecordingTransport(LifecycleTransport):
        def __init__(self) -> None:
            super().__init__()
            self.deleted_ids: list[str] = []

        def __call__(self, method, url, body, timeout, headers):
            params = parse_qs(body.decode("utf-8"))
            if method == "DELETE":
                self.deleted_ids.append(params["clientAlgoId"][0])
            return super().__call__(method, url, body, timeout, headers)

    transport = RecordingTransport()
    result = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=lambda **kwargs: coordinator,
    ).run_protective_lifecycle(PAIR_ID, STOP_ID, TP_ID, confirmation=CONFIRMATION, config_path=str(_config(tmp_path)))

    failed_id = STOP_ID if failed_label == "STOP" else TP_ID
    assert result.status == "FAIL"
    assert journal_path.read_bytes() == snapshots[failed_label]
    assert failed_id not in transport.deleted_ids
    assert not (journal_path.parent / "protective.lock").exists()
    assert _db_snapshot(database_engine) == database_snapshots[failed_label]
    serialized = json.dumps(result.to_dict()).casefold()
    assert all(marker not in serialized for marker in ("postgresql://", "select rollback", "traceback", "rawresponse", "secret@"))


def test_each_cancel_commit_immediately_precedes_journal_and_delete(tmp_path: Path) -> None:
    database_url, _ = _database(tmp_path)
    events: list[str] = []

    class OrderedPersistence(ProtectiveLifecyclePersistence):
        def prepare_cancel(self, state, label, quantity, price):
            super().prepare_cancel(state, label, quantity, price)
            events.append(f"DB_COMMITTED:{label}")

    class OrderedEngine(BinanceFuturesTestnetProtectiveOrdersEngine):
        def _write_journal(self, config, journal, phase, details):
            if phase in {"STOP_CANCEL_STARTED", "TAKE_PROFIT_CANCEL_STARTED"}:
                events.append(f"JOURNAL:{phase.split('_CANCEL')[0]}")
            return super()._write_journal(config, journal, phase, details)

    class OrderedTransport(LifecycleTransport):
        def __call__(self, method, url, body, timeout, headers):
            params = parse_qs(body.decode("utf-8"))
            if method == "DELETE":
                label = "STOP" if params["clientAlgoId"][0] == STOP_ID else "TAKE_PROFIT"
                events.append(f"DELETE:{label}")
            return super().__call__(method, url, body, timeout, headers)

    result = OrderedEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=OrderedTransport(),
        now_ms_provider=lambda: 1000,
        persistence_factory=OrderedPersistence,
    ).run_protective_lifecycle(PAIR_ID, STOP_ID, TP_ID, confirmation=CONFIRMATION, config_path=str(_config(tmp_path)))

    assert result.status == "PASS"
    assert events == [
        "DB_COMMITTED:TAKE_PROFIT",
        "JOURNAL:TAKE_PROFIT",
        "DELETE:TAKE_PROFIT",
        "DB_COMMITTED:STOP",
        "JOURNAL:STOP",
        "DELETE:STOP",
    ]


def test_create_intent_commit_precedes_every_post(tmp_path: Path) -> None:
    database_url, _ = _database(tmp_path)
    committed = False

    class OrderedPersistence(ProtectiveLifecyclePersistence):
        def prepare_lifecycle(self, *args, **kwargs):
            nonlocal committed
            state = super().prepare_lifecycle(*args, **kwargs)
            committed = True
            return state

    class OrderedTransport(LifecycleTransport):
        def __call__(self, method, url, body, timeout, headers):
            if method == "POST":
                assert committed is True
            return super().__call__(method, url, body, timeout, headers)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=OrderedTransport(),
        now_ms_provider=lambda: 1000,
        persistence_factory=OrderedPersistence,
    ).run_protective_lifecycle(PAIR_ID, STOP_ID, TP_ID, confirmation=CONFIRMATION, config_path=str(_config(tmp_path)))

    assert result.status == "PASS"


def _phase_projection(phase, pair_state, create_state, journal_keys, stop_cancel_state=None, take_cancel_state=None, stop_status=None, take_status=None, recovery_required=False):
    persistence = ProtectiveLifecyclePersistence(env={})
    state = persistence._deterministic_state(PAIR_ID, STOP_ID, TP_ID)
    create_intent = ExecutionIntent(
        id=state.create_intent_id, correlation_id=state.create_correlation_id,
        environment="BINANCE_FUTURES_TESTNET", symbol="BTCUSDT",
        intent_type="PROTECTIVE_PAIR_CREATE", state=create_state,
        requested_quantity=Decimal("0.001"), requested_price=Decimal("50000"),
    )
    pair = ProtectivePair(
        id=state.pair_id, pair_id=PAIR_ID, correlation_id=state.create_correlation_id,
        execution_intent_id=state.create_intent_id, environment="BINANCE_FUTURES_TESTNET",
        symbol="BTCUSDT", position_side="BOTH", direction="LONG",
        quantity=Decimal("0.001"), state=pair_state, recovery_required=recovery_required,
    )

    def cancel_intent(label, intent_state):
        if intent_state is None:
            return None
        intent_id, correlation_id = persistence._cancel_identity(state, label)
        return ExecutionIntent(
            id=intent_id, correlation_id=correlation_id, environment="BINANCE_FUTURES_TESTNET",
            symbol="BTCUSDT", intent_type="PROTECTIVE_PAIR_CANCEL", state=intent_state,
            requested_quantity=Decimal("0.001"), requested_price=Decimal("50000"),
        )

    def identity(label, status):
        if status is None:
            return None
        return ExchangeOrderIdentity(
            protective_pair_id=state.pair_id, environment="BINANCE_FUTURES_TESTNET", symbol="BTCUSDT",
            leg_type=label, client_algo_id=STOP_ID if label == "STOP" else TP_ID,
            exchange_algo_id="42" if label == "STOP" else "43", status=status,
            trigger_price=Decimal("45000") if label == "STOP" else Decimal("55000"),
        )

    identities = {}
    for label, status in (("STOP", stop_status), ("TAKE_PROFIT", take_status)):
        item = identity(label, status)
        if item is not None:
            identities[label] = item
    journal = BinanceFuturesTestnetProtectiveJournal(
        pair_id=PAIR_ID, stop_client_algo_id=STOP_ID, take_profit_client_algo_id=TP_ID,
        phase=phase, recovery_required=recovery_required,
        mutation_intents=[ProtectiveMutationIntent(label=label, mutation_kind=kind) for label, kind in sorted(journal_keys)],
    )
    return persistence, journal, pair, create_intent, {
        "STOP": cancel_intent("STOP", stop_cancel_state),
        "TAKE_PROFIT": cancel_intent("TAKE_PROFIT", take_cancel_state),
    }, identities


CREATE_KEYS = {("STOP", "CREATE"), ("TAKE_PROFIT", "CREATE")}
ALL_INTENT_KEYS = CREATE_KEYS | {("STOP", "DELETE"), ("TAKE_PROFIT", "DELETE")}


@pytest.mark.parametrize("case", [
    ("PRECHECK_STARTED", "PENDING", "PERSISTED", set()),
    ("STOP_CREATE_INTENT_PERSISTED", "PENDING", "PERSISTED", {("STOP", "CREATE")}),
    ("STOP_CREATE_CREATE_CONFIRMED", "STOP_ACTIVE", "TRANSMITTED", {("STOP", "CREATE")}, None, None, "NEW"),
    ("STOP_CREATED", "STOP_ACTIVE", "TRANSMITTED", {("STOP", "CREATE")}, None, None, "NEW"),
    ("TAKE_PROFIT_CREATE_INTENT_PERSISTED", "STOP_ACTIVE", "TRANSMITTED", CREATE_KEYS, None, None, "NEW"),
    ("TAKE_PROFIT_QUERY_COMPLETE", "PAIR_ACTIVE", "COMPLETED", CREATE_KEYS, None, None, "NEW", "NEW"),
    ("TAKE_PROFIT_QUERY_COMPLETE", "CANCEL_PENDING", "COMPLETED", CREATE_KEYS, None, "PERSISTED", "NEW", "NEW"),
    ("TAKE_PROFIT_CANCEL_STARTED", "CANCEL_PENDING", "COMPLETED", CREATE_KEYS, None, "PERSISTED", "NEW", "NEW"),
    ("TAKE_PROFIT_CANCELED", "CANCEL_PENDING", "COMPLETED", CREATE_KEYS | {("TAKE_PROFIT", "DELETE")}, None, "COMPLETED", "NEW", "ABSENT"),
    ("TAKE_PROFIT_CANCELED", "CANCEL_PENDING", "COMPLETED", CREATE_KEYS | {("TAKE_PROFIT", "DELETE")}, "PERSISTED", "COMPLETED", "NEW", "ABSENT"),
    ("STOP_CANCEL_STARTED", "CANCEL_PENDING", "COMPLETED", CREATE_KEYS | {("TAKE_PROFIT", "DELETE")}, "PERSISTED", "COMPLETED", "NEW", "ABSENT"),
    ("STOP_CANCELED", "COMPLETED", "COMPLETED", ALL_INTENT_KEYS, "COMPLETED", "COMPLETED", "ABSENT", "ABSENT"),
    ("RECOVERY_REQUIRED", "RECOVERY_REQUIRED", "RECOVERY_REQUIRED", {("STOP", "CREATE")}, None, None, None, None, True),
    ("RECOVERY_STARTED", "RECOVERY_REQUIRED", "COMPLETED", CREATE_KEYS | {("TAKE_PROFIT", "DELETE")}, None, "RECOVERY_REQUIRED", "NEW", "NEW", True),
    ("COMPLETE", "COMPLETED", "COMPLETED", ALL_INTENT_KEYS, "COMPLETED", "COMPLETED", "ABSENT", "ABSENT"),
    ("RECOVERY_COMPLETE", "COMPLETED", "COMPLETED", ALL_INTENT_KEYS, "COMPLETED", "COMPLETED", "ABSENT", "ABSENT"),
])
def test_exact_phase_projection_allowlist_accepts_each_semantic_group(case) -> None:
    persistence, journal, pair, create_intent, cancel_intents, identities = _phase_projection(*case)
    persistence._validate_exact_phase_projection(journal, pair, create_intent, cancel_intents, identities)


@pytest.mark.parametrize("case", [
    ("STOP_CREATED", "CANCEL_PENDING", "COMPLETED", {("STOP", "CREATE")}, None, "COMPLETED", "NEW", "ABSENT"),
    ("STOP_CANCEL_STARTED", "STOP_ACTIVE", "TRANSMITTED", CREATE_KEYS | {("TAKE_PROFIT", "DELETE")}, "PERSISTED", "COMPLETED", "NEW", "ABSENT"),
    ("TAKE_PROFIT_CANCEL_STARTED", "CANCEL_PENDING", "COMPLETED", CREATE_KEYS, None, None, "NEW", "NEW"),
    ("TAKE_PROFIT_CANCEL_STARTED", "CANCEL_PENDING", "COMPLETED", CREATE_KEYS, "TRANSMITTED", "PERSISTED", "NEW", "NEW"),
    ("STOP_CANCEL_STARTED", "CANCEL_PENDING", "COMPLETED", CREATE_KEYS | {("TAKE_PROFIT", "DELETE")}, "PERSISTED", "COMPLETED", "NEW", "NEW"),
    ("RECOVERY_STARTED", "RECOVERY_REQUIRED", "RECOVERY_REQUIRED", {("STOP", "CREATE")}, None, None, None, None, False),
    ("COMPLETE", "COMPLETED", "COMPLETED", ALL_INTENT_KEYS, "COMPLETED", "COMPLETED", "NEW", "ABSENT"),
    ("STOP_CREATED", "STOP_ACTIVE", "TRANSMITTED", {("STOP", "CREATE"), ("STOP", "DELETE")}, None, None, "NEW"),
    ("STOP_CANCEL_STARTED", "CANCEL_PENDING", "COMPLETED", CREATE_KEYS, "PERSISTED", "COMPLETED", "NEW", "ABSENT"),
])
def test_exact_phase_projection_allowlist_rejects_inverse_and_intent_mismatches(case) -> None:
    persistence, journal, pair, create_intent, cancel_intents, identities = _phase_projection(*case)
    with pytest.raises(ProtectivePersistenceError, match="PERSISTENCE_PHASE_PROJECTION_MISMATCH"):
        persistence._validate_exact_phase_projection(journal, pair, create_intent, cancel_intents, identities)


@pytest.mark.parametrize(
    "name,sql,params",
    [
        ("environment", "UPDATE execution_intents SET environment='PRODUCTION' WHERE intent_type='PROTECTIVE_PAIR_CREATE'", ()),
        ("symbol", "UPDATE execution_intents SET symbol='ETHUSDT' WHERE intent_type='PROTECTIVE_PAIR_CREATE'", ()),
        ("quantity", "UPDATE execution_intents SET requested_quantity=? WHERE intent_type='PROTECTIVE_PAIR_CREATE'", ("0.0011",)),
        ("price", "UPDATE execution_intents SET requested_price=? WHERE intent_type='PROTECTIVE_PAIR_CREATE'", ("49999",)),
        ("intent_type", "UPDATE execution_intents SET intent_type='WRONG_CREATE' WHERE intent_type='PROTECTIVE_PAIR_CREATE'", ()),
        ("intent_state", "UPDATE execution_intents SET state='PERSISTED' WHERE intent_type='PROTECTIVE_PAIR_CREATE'", ()),
        ("client_algo_id", "UPDATE exchange_order_identities SET client_algo_id='smcbot-protect-sl-wrong' WHERE leg_type='STOP'", ()),
        ("exchange_algo_id", "UPDATE exchange_order_identities SET exchange_algo_id='999' WHERE leg_type='STOP'", ()),
        ("exchange_order_id", "UPDATE exchange_order_identities SET exchange_order_id='unexpected' WHERE leg_type='STOP'", ()),
        ("status", "UPDATE exchange_order_identities SET status='NEW' WHERE leg_type='STOP'", ()),
        ("create_intent_relation", "UPDATE protective_pairs SET execution_intent_id='00000000000000000000000000000001'", ()),
        ("cancel_intent_relation", "UPDATE execution_intents SET id='00000000000000000000000000000002' WHERE intent_type='PROTECTIVE_PAIR_CANCEL' AND id=(SELECT id FROM execution_intents WHERE intent_type='PROTECTIVE_PAIR_CANCEL' LIMIT 1)", ()),
        ("pair_ownership", "UPDATE exchange_order_identities SET protective_pair_id='00000000000000000000000000000003' WHERE leg_type='STOP'", ()),
        ("trigger_price", "UPDATE exchange_order_identities SET trigger_price='44000' WHERE leg_type='STOP'", ()),
    ],
)
def test_completed_replay_rejects_exact_business_field_mismatch(tmp_path: Path, name: str, sql: str, params: tuple) -> None:
    database_url, database_engine = _database(tmp_path)
    completed, _ = _run(tmp_path, database_url)
    assert completed.status == "PASS"
    journal_path = tmp_path / "data" / "runtime" / "binance_futures_testnet_protective_orders" / "protective.json"
    original = journal_path.read_bytes()
    with database_engine.begin() as connection:
        connection.exec_driver_sql(sql, params)
    database_before = _db_snapshot(database_engine)
    transport = LifecycleTransport()

    replay, _ = _run(tmp_path, database_url, transport)

    assert replay.status == "FAIL", name
    assert transport.calls == []
    assert journal_path.read_bytes() == original
    assert _db_snapshot(database_engine) == database_before


@pytest.mark.parametrize(
    "name,db_sql,journal_phase,journal_recovery",
    [
        ("completed_pair_nonterminal_journal", None, "STOP_CREATED", False),
        ("terminal_journal_unresolved_pair", "UPDATE protective_pairs SET state='PENDING'", None, None),
        ("completed_pair_unresolved_create", "UPDATE execution_intents SET state='TRANSMITTED' WHERE intent_type='PROTECTIVE_PAIR_CREATE'", None, None),
        ("completed_pair_unresolved_cancel", "UPDATE execution_intents SET state='TRANSMITTED' WHERE intent_type='PROTECTIVE_PAIR_CANCEL'", None, None),
        ("db_recovery_journal_not_recovery", "UPDATE protective_pairs SET state='RECOVERY_REQUIRED', recovery_required=1", None, None),
        ("active_identity_completed_pair", "UPDATE exchange_order_identities SET status='NEW' WHERE leg_type='STOP'", None, None),
        ("missing_identity_completed_pair", "DELETE FROM exchange_order_identities WHERE leg_type='STOP'", None, None),
    ],
)
def test_completed_replay_rejects_unlisted_state_matrix_combination(tmp_path: Path, name: str, db_sql: str | None, journal_phase: str | None, journal_recovery: bool | None) -> None:
    database_url, database_engine = _database(tmp_path)
    completed, _ = _run(tmp_path, database_url)
    assert completed.status == "PASS"
    journal_path = tmp_path / "data" / "runtime" / "binance_futures_testnet_protective_orders" / "protective.json"
    payload = json.loads(journal_path.read_text(encoding="utf-8"))
    if journal_phase is not None:
        payload["phase"] = journal_phase
    if journal_recovery is not None:
        payload["recovery_required"] = journal_recovery
    if journal_phase is not None or journal_recovery is not None:
        journal_path.write_text(json.dumps(payload), encoding="utf-8")
    original = journal_path.read_bytes()
    if db_sql is not None:
        with database_engine.begin() as connection:
            connection.exec_driver_sql(db_sql)
    database_before = _db_snapshot(database_engine)
    transport = LifecycleTransport()

    replay, _ = _run(tmp_path, database_url, transport)

    assert replay.status == "FAIL", name
    assert transport.calls == []
    assert journal_path.read_bytes() == original
    assert _db_snapshot(database_engine) == database_before


def test_recovery_journal_with_database_recovery_false_is_rejected(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path)

    class AmbiguousTransport(LifecycleTransport):
        post_attempted = False

        def __call__(self, method, url, body, timeout, headers):
            if method == "POST":
                self.post_attempted = True
                self.calls.append((method, url))
                raise TimeoutError("ambiguous")
            if method == "GET" and "algoOrder" in url and self.post_attempted:
                self.calls.append((method, url))
                raise OSError("lookup unavailable")
            return super().__call__(method, url, body, timeout, headers)

    first, _ = _run(tmp_path, database_url, AmbiguousTransport())
    assert first.decision == "RECOVERY_REQUIRED"
    with database_engine.begin() as connection:
        connection.exec_driver_sql("UPDATE protective_pairs SET recovery_required=0")
    journal_path = tmp_path / "data" / "runtime" / "binance_futures_testnet_protective_orders" / "protective.json"
    original = journal_path.read_bytes()
    transport = LifecycleTransport()

    replay, _ = _run(tmp_path, database_url, transport)

    assert replay.status == "FAIL"
    assert transport.calls == []
    assert journal_path.read_bytes() == original


def test_completed_pair_with_extra_identity_is_rejected(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path)
    completed, _ = _run(tmp_path, database_url)
    assert completed.status == "PASS"
    with Session(database_engine) as session, session.begin():
        pair = session.scalar(select(ProtectivePairORM))
        assert pair is not None
        session.add(
            ExchangeOrderIdentityORM(
                id=uuid4(),
                protective_pair_id=pair.id,
                environment="BINANCE_FUTURES_TESTNET",
                symbol="BTCUSDT",
                leg_type="UNKNOWN",
                client_algo_id="smcbot-protect-extra-001",
                exchange_algo_id="999",
                exchange_order_id=None,
                status="ABSENT",
                trigger_price=Decimal("50000"),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                version=1,
            )
        )
    transport = LifecycleTransport()

    replay, _ = _run(tmp_path, database_url, transport)

    assert replay.status == "FAIL"
    assert transport.calls == []


def test_restart_catches_up_definitive_create_without_duplicate_post(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path)

    class FailCreateConfirmation(ProtectiveLifecyclePersistence):
        def confirm_create(self, state, label, order):
            raise ProtectivePersistenceError("PERSISTENCE_POST_TRANSPORT_FAILED", after_transport=True)

    first_transport = LifecycleTransport()
    first = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=first_transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=FailCreateConfirmation,
    ).run_protective_lifecycle(PAIR_ID, STOP_ID, TP_ID, confirmation=CONFIRMATION, config_path=str(_config(tmp_path)))
    assert first.decision == "RECOVERY_REQUIRED"
    assert [method for method, _ in first_transport.calls].count("POST") == 1

    restart_transport = LifecycleTransport()
    restart_transport.created.add(STOP_ID)
    recovered = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=restart_transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=ProtectiveLifecyclePersistence,
    ).recover_protective_pair(
        STOP_ID,
        TP_ID,
        confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY",
        config_path=str(_config(tmp_path)),
    )

    assert recovered.status == "PASS", (recovered.decision, recovered.reason)
    assert [method for method, _ in restart_transport.calls].count("POST") == 0
    assert [method for method, _ in restart_transport.calls].count("DELETE") == 1
    with Session(database_engine) as session:
        identities = list(session.scalars(select(ExchangeOrderIdentityORM)).all())
        pair = session.scalar(select(ProtectivePairORM))
    assert len(identities) == 1 and identities[0].client_algo_id == STOP_ID and identities[0].status == "ABSENT"
    assert pair is not None and pair.state == "COMPLETED" and pair.recovery_required is False


def test_restart_catches_up_definitive_delete_without_duplicate_delete(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path)

    class FailTakeDeleteConfirmation(ProtectiveLifecyclePersistence):
        def confirm_delete(self, state, label, status, complete):
            if label == "TAKE_PROFIT":
                raise ProtectivePersistenceError("PERSISTENCE_VERSION_CONFLICT", after_transport=True)
            return super().confirm_delete(state, label, status, complete)

    first_transport = LifecycleTransport()
    first = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=first_transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=FailTakeDeleteConfirmation,
    ).run_protective_lifecycle(PAIR_ID, STOP_ID, TP_ID, confirmation=CONFIRMATION, config_path=str(_config(tmp_path)))
    assert first.decision == "RECOVERY_REQUIRED"
    assert [method for method, _ in first_transport.calls].count("DELETE") == 1

    class RestartTransport(LifecycleTransport):
        def __init__(self) -> None:
            super().__init__()
            self.created.update({STOP_ID, TP_ID})
            self.deleted.add(TP_ID)
            self.deleted_ids: list[str] = []

        def __call__(self, method, url, body, timeout, headers):
            params = parse_qs(body.decode("utf-8"))
            if method == "DELETE":
                self.deleted_ids.append(params["clientAlgoId"][0])
            return super().__call__(method, url, body, timeout, headers)

    restart_transport = RestartTransport()
    recovered = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=restart_transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=ProtectiveLifecyclePersistence,
    ).recover_protective_pair(
        STOP_ID,
        TP_ID,
        confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY",
        config_path=str(_config(tmp_path)),
    )

    assert recovered.status == "PASS", (recovered.decision, recovered.reason)
    assert restart_transport.deleted_ids == [STOP_ID]
    assert [method for method, _ in restart_transport.calls].count("POST") == 0
    with Session(database_engine) as session:
        pair = session.scalar(select(ProtectivePairORM))
        identities = list(session.scalars(select(ExchangeOrderIdentityORM)).all())
    assert pair is not None and pair.state == "COMPLETED"
    assert {identity.status for identity in identities} == {"ABSENT"}


def test_post_delete_optimistic_conflict_is_recovery_required_without_retry(tmp_path: Path) -> None:
    database_url, _ = _database(tmp_path)

    class ConflictAfterDelete(ProtectiveLifecyclePersistence):
        def confirm_delete(self, state, label, status, complete):
            raise ProtectivePersistenceError("PERSISTENCE_VERSION_CONFLICT", after_transport=True)

    transport = LifecycleTransport()
    result = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=ConflictAfterDelete,
    ).run_protective_lifecycle(PAIR_ID, STOP_ID, TP_ID, confirmation=CONFIRMATION, config_path=str(_config(tmp_path)))

    assert result.decision == "RECOVERY_REQUIRED"
    assert [method for method, _ in transport.calls].count("DELETE") == 1


def test_catch_up_conflict_fails_closed_without_mutation(tmp_path: Path) -> None:
    database_url, _ = _database(tmp_path)

    class FailCreateConfirmation(ProtectiveLifecyclePersistence):
        def confirm_create(self, state, label, order):
            raise ProtectivePersistenceError("PERSISTENCE_VERSION_CONFLICT", after_transport=True)

    first_transport = LifecycleTransport()
    first = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=first_transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=FailCreateConfirmation,
    ).run_protective_lifecycle(PAIR_ID, STOP_ID, TP_ID, confirmation=CONFIRMATION, config_path=str(_config(tmp_path)))
    assert first.decision == "RECOVERY_REQUIRED"

    restart_transport = LifecycleTransport()
    restart_transport.created.add(STOP_ID)
    retry = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=restart_transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=FailCreateConfirmation,
    ).recover_protective_pair(
        STOP_ID,
        TP_ID,
        confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY",
        config_path=str(_config(tmp_path)),
    )

    assert retry.decision == "RECOVERY_REQUIRED"
    assert [method for method, _ in restart_transport.calls].count("POST") == 0
    assert [method for method, _ in restart_transport.calls].count("DELETE") == 0


def test_hostile_persistence_exception_is_sanitized(tmp_path: Path) -> None:
    database_url, _ = _database(tmp_path)
    hostile = "postgresql://user:secret@host/db SELECT * FROM credentials traceback rawResponse"

    def failing_session_factory(**kwargs):
        session = Session(**kwargs)

        def fail_commit(_session):
            raise OSError(hostile)

        event.listen(session, "before_commit", fail_commit)
        return session

    coordinator = ProtectiveLifecyclePersistence(env=_env(database_url), session_factory=failing_session_factory)
    result = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(database_url),
        http_get=_http_get,
        authenticated_request=LifecycleTransport(),
        now_ms_provider=lambda: 1000,
        persistence_factory=lambda **kwargs: coordinator,
    ).run_protective_lifecycle(PAIR_ID, STOP_ID, TP_ID, confirmation=CONFIRMATION, config_path=str(_config(tmp_path)))

    serialized = json.dumps(result.to_dict()).casefold()
    assert result.decision == "PERSISTENCE_COMMIT_FAILED"
    assert all(marker not in serialized for marker in ("postgresql://", "select *", "traceback", "rawresponse", "secret@"))
