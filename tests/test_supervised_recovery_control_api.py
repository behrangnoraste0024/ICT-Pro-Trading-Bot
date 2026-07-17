from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, MetaData, String, Table, create_engine, select
from sqlalchemy.orm import Session

from api.live_control_plane_routes import get_supervised_recovery_service
from api.main import create_app
from api.supervised_recovery_models import CONFIRMATION, SupervisedRecoveryRequest
from api.supervised_recovery_service import SupervisedRecoveryService
from engine.diagnostics.binance_futures_testnet_protective_orders_engine import (
    BinanceFuturesTestnetProtectiveOrdersEngine,
)
from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import (
    BinanceLifecycleHTTPResponse,
)
from infrastructure.exchanges.binance_futures_testnet_protective_orders_client import (
    BinanceFuturesTestnetProtectiveAPIError,
)
from infrastructure.persistence.protective_lifecycle_persistence import (
    ProtectiveLifecyclePersistence,
    ProtectiveConsistencyResult,
    ProtectivePersistenceError,
    ProtectivePersistenceState,
)
from infrastructure.persistence.kill_switch_persistence import KillSwitchPersistence
from infrastructure.persistence.kill_switch_gate import KillSwitchGateError
from infrastructure.persistence.execution_orm import (
    AuditEventORM,
    ExchangeOrderIdentityORM,
    ExecutionIntentORM,
    ExecutionPersistenceBase,
    ProtectivePairORM,
    RecoveryEventORM,
)
from infrastructure.persistence.execution_repositories import SqlAlchemyProtectivePairRepository
from infrastructure.persistence.schema_contract import PERSISTENCE_REVISION
from models.binance_futures_testnet_protective_orders import (
    BinanceFuturesTestnetProtectiveAlgoSummary,
    BinanceFuturesTestnetProtectivePosition,
    BinanceFuturesTestnetProtectivePreview,
    BinanceFuturesTestnetProtectiveJournal,
    BinanceFuturesTestnetProtectiveOrdersConfig,
    ProtectiveMutationIntent,
)
from models.execution_persistence import OptimisticLockError

PAIR_ID = "11111111-1111-4111-8111-111111111111"
CORRELATION_ID = "22222222-2222-4222-8222-222222222222"
STOP_ID = "smcbot-protect-sl-api"
TP_ID = "smcbot-protect-tp-api"


def _request(**changes):
    payload = {
        "environment": "BINANCE_FUTURES_TESTNET",
        "symbol": "BTCUSDT",
        "pair_id": PAIR_ID,
        "correlation_id": CORRELATION_ID,
        "confirmation": CONFIRMATION,
        "dry_run": True,
    }
    payload.update(changes)
    return payload


def _intent(label="STOP", kind="CREATE", resolved=False):
    return ProtectiveMutationIntent(
        pair_id=PAIR_ID,
        symbol="BTCUSDT",
        label=label,
        mutation_kind=kind,
        client_algo_id=STOP_ID if label == "STOP" else TP_ID,
        expected_order_type="STOP_MARKET" if label == "STOP" else "TAKE_PROFIT_MARKET",
        expected_side="SELL",
        expected_trigger_price=Decimal("45000") if label == "STOP" else Decimal("55000"),
        expected_close_position=True,
        expected_working_type="MARK_PRICE",
        expected_price_protect=True,
        baseline_position_amount=Decimal("0.001"),
        baseline_position_direction="LONG",
        created_at="2026-01-01T00:00:00+00:00",
        mutation_phase=f"{label}_{kind}_INTENT_PERSISTED",
        resolved=resolved,
        reconciliation_state="PRESENT" if resolved else "AMBIGUOUS",
        reconciliation_reason="Exact prior proof." if resolved else "Ambiguous transport.",
    )


def _journal() -> BinanceFuturesTestnetProtectiveJournal:
    return BinanceFuturesTestnetProtectiveJournal(
        pair_id=PAIR_ID,
        stop_client_algo_id=STOP_ID,
        take_profit_client_algo_id=TP_ID,
        phase="RECOVERY_REQUIRED",
        recovery_required=True,
        baseline_available=True,
        baseline_position_amount="0.001",
        baseline_position_direction="LONG",
        stop_trigger="45000",
        take_profit_trigger="55000",
        mutation_intents=[_intent()],
    )


class FakeEngine:
    def __init__(self, root: Path, journal: BinanceFuturesTestnetProtectiveJournal) -> None:
        self.root = root
        self.journal = journal

    def load_config(self, path):
        return BinanceFuturesTestnetProtectiveOrdersConfig()

    def _load_existing_journal_strict(self, config, pair_id, stop_id, take_id):
        assert pair_id == self.journal.pair_id
        assert stop_id == self.journal.stop_client_algo_id
        assert take_id == self.journal.take_profit_client_algo_id
        return self.journal

    def recover_protective_pair(self, *args, **kwargs):
        raise AssertionError("dry-run must not invoke recovery")


class FakePersistence:
    def __init__(self, *, consistency=None, error=None, catch_up=False) -> None:
        self.error = error
        self.catch_up = catch_up
        self.closed = False
        self.calls: list[str] = []
        state = ProtectivePersistenceState(
            pair_id=UUID("33333333-3333-4333-8333-333333333333"),
            create_intent_id=UUID("44444444-4444-4444-8444-444444444444"),
            create_correlation_id=UUID(CORRELATION_ID),
            stop_cancel_intent_id=UUID("55555555-5555-4555-8555-555555555555"),
            stop_cancel_correlation_id=UUID("66666666-6666-4666-8666-666666666666"),
            take_profit_cancel_intent_id=UUID("77777777-7777-4777-8777-777777777777"),
            take_profit_cancel_correlation_id=UUID("88888888-8888-4888-8888-888888888888"),
            stop_client_algo_id=STOP_ID,
            take_profit_client_algo_id=TP_ID,
        )
        self.consistency = consistency or ProtectiveConsistencyResult(
            "RECOVERY", state, "RECOVERY_REQUIRED", True, UUID(CORRELATION_ID)
        )

    def ensure_available(self):
        self.calls.append("ensure")
        if self.error:
            raise self.error

    def check_consistency(self, *args):
        self.calls.append("consistency")
        return self.consistency

    def needs_catch_up(self, state, intent):
        self.calls.append("catch_up")
        return self.catch_up

    def close(self):
        self.closed = True


def _service(tmp_path: Path, *, journal=None, persistence=None, runner=None, credentials=False, kill_switch_gate=None):
    journal = journal or _journal()
    runtime = tmp_path / "data/runtime/binance_futures_testnet_protective_orders"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "protective.json").write_text(json.dumps(journal.to_dict()), encoding="utf-8")
    configs = tmp_path / "configs"
    configs.mkdir(exist_ok=True)
    (configs / "btc_paper_runtime.json").write_text(json.dumps({"kill_switch_enabled": True}), encoding="utf-8")
    persistence = persistence or FakePersistence()
    env = {}
    if credentials:
        env.update(BINANCE_FUTURES_TESTNET_API_KEY="key", BINANCE_FUTURES_TESTNET_API_SECRET="secret")
    gate = kill_switch_gate or type("EngagedGate", (), {"require_engaged": lambda self: None})()
    service = SupervisedRecoveryService(
        repo_root=tmp_path,
        env=env,
        protective_engine=FakeEngine(tmp_path, journal),
        persistence_factory=lambda **kwargs: persistence,
        recovery_runner=runner,
        kill_switch_gate=gate,
    )
    return service, persistence, runtime


@pytest.mark.parametrize(
    "changes",
    [
        {"environment": "binance_futures_testnet"}, {"symbol": "ETHUSDT"},
        {"pair_id": "bad"}, {"correlation_id": "bad"},
        {"confirmation": CONFIRMATION.lower()}, {"confirmation": f" {CONFIRMATION}"},
        {"confirmation": CONFIRMATION + "\n"}, {"confirmation": "RUN BTCUSDT TESTNET RECОVERY"},
        {"dry_run": 1},
    ],
)
def test_request_contract_rejects_non_exact_values(changes) -> None:
    with pytest.raises(Exception):
        SupervisedRecoveryRequest(**_request(**changes))


def test_route_rejects_missing_and_unknown_fields() -> None:
    app = create_app()
    client = TestClient(app)
    missing = _request()
    missing.pop("confirmation")
    assert client.post("/api/v1/live/recovery/run", json=missing).status_code == 422
    assert client.post("/api/v1/live/recovery/run", json=_request(extra=True)).status_code == 422


@pytest.mark.parametrize(
    ("changes", "marker"),
    [
        ({"confirmation": "secret-marker"}, "secret-marker"),
        ({"confirmation": "X-MBX-APIKEY=hostile-key"}, "hostile-key"),
        ({"confirmation": "postgresql://user:password@host/db"}, "postgresql"),
        ({"confirmation": "SELECT * FROM execution_intents"}, "select"),
        ({"confirmation": "Traceback (most recent call last)"}, "traceback"),
        ({"unknown": "secret-unknown-value"}, "secret-unknown-value"),
        ({"pair_id": "bad-secret-marker"}, "bad-secret-marker"),
        ({"confirmation": "line-one\nsecret-control\u0001"}, "secret-control"),
        ({"confirmation": "RUN BTCUSDT TESTNET RECОVERY"}, "recоvery"),
    ],
)
def test_recovery_validation_errors_never_echo_hostile_input(changes, marker) -> None:
    response = TestClient(create_app()).post("/api/v1/live/recovery/run", json=_request(**changes))

    assert response.status_code == 422
    assert response.json() == {
        "accepted": False,
        "blocking_code": "INVALID_REQUEST",
        "message": "Request validation failed.",
    }
    assert marker.lower() not in response.text.lower()


def test_only_approved_control_routes_are_post_and_all_other_live_routes_remain_get() -> None:
    paths = create_app().openapi()["paths"]
    live = {path: set(methods) for path, methods in paths.items() if path.startswith("/api/v1/live")}
    mutation_paths = {
        "/api/v1/live/recovery/run",
        "/api/v1/live/kill-switch/engage",
        "/api/v1/live/kill-switch/release",
    }
    assert all(live[path] == {"post"} for path in mutation_paths)
    assert all(methods == {"get"} for path, methods in live.items() if path not in mutation_paths)


def test_dry_run_is_immutable_network_free_and_does_not_require_credentials(tmp_path: Path) -> None:
    service, persistence, runtime = _service(tmp_path)
    journal_path = runtime / "protective.json"
    before = journal_path.read_bytes()

    result = service.run(SupervisedRecoveryRequest(**_request()))

    assert result["recovery_ready"] is True
    assert result["planned_actions"] == ["EXACT_GET_STOP_CREATE"]
    assert journal_path.read_bytes() == before
    assert not (runtime / "protective.lock").exists()
    assert persistence.calls == ["ensure", "consistency"]
    assert persistence.closed is True


def test_dry_run_with_real_sqlite_persistence_preserves_exact_db_and_journal(tmp_path: Path) -> None:
    database = tmp_path / "recovery.db"
    database_url = f"sqlite:///{database}"
    engine = create_engine(database_url, future=True)
    ExecutionPersistenceBase.metadata.create_all(engine)
    version = Table("alembic_version", MetaData(), Column("version_num", String(64), primary_key=True))
    version.create(engine)
    with engine.begin() as connection:
        connection.execute(version.insert().values(version_num=PERSISTENCE_REVISION))
    env = {"ICT_DATABASE_URL": database_url}
    persistence = ProtectiveLifecyclePersistence(env=env)
    persistence.ensure_available()
    position = BinanceFuturesTestnetProtectivePosition(
        position_amt=Decimal("0.001"), mark_price=Decimal("50000"), notional=Decimal("50"), direction="LONG"
    )
    preview = BinanceFuturesTestnetProtectivePreview(
        pair_id=PAIR_ID,
        position_direction="LONG",
        position_amount=Decimal("0.001"),
        protective_side="SELL",
        stop_client_algo_id=STOP_ID,
        take_profit_client_algo_id=TP_ID,
        stop_trigger=Decimal("45000"),
        take_profit_trigger=Decimal("55000"),
        transmission_ready=True,
    )
    state = persistence.prepare_lifecycle(PAIR_ID, STOP_ID, TP_ID, position, preview)
    persistence.mark_create_transmitted(state)
    persistence.mark_recovery_required(state, "CREATE", "AMBIGUOUS_TRANSPORT")
    persistence.close()

    journal = _journal()
    service, _, runtime = _service(
        tmp_path,
        journal=journal,
        persistence=ProtectiveLifecyclePersistence(env=env),
    )

    def snapshot():
        models = (ExecutionIntentORM, ProtectivePairORM, ExchangeOrderIdentityORM, AuditEventORM, RecoveryEventORM)
        with Session(engine) as session:
            return {
                model.__tablename__: [tuple(str(getattr(row, column.name)) for column in model.__table__.columns) for row in session.scalars(select(model).order_by(model.id)).all()]
                for model in models
            }

    before_db = snapshot()
    before_journal = (runtime / "protective.json").read_bytes()
    request = SupervisedRecoveryRequest(**_request(correlation_id=str(state.create_correlation_id)))

    result = service.run(request)

    assert result["recovery_ready"] is True
    assert snapshot() == before_db
    assert (runtime / "protective.json").read_bytes() == before_journal
    assert not (runtime / "protective.lock").exists()
    engine.dispose()


def test_route_returns_sanitized_dry_run_response(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)
    app = create_app()
    app.dependency_overrides[get_supervised_recovery_service] = lambda: service
    response = TestClient(app).post("/api/v1/live/recovery/run", json=_request())
    assert response.status_code == 200
    text = response.text.lower()
    assert "secret" not in text and "signature" not in text and "metadata_json" not in text


def test_execution_requires_credentials_before_recovery_runner(tmp_path: Path) -> None:
    calls = []
    service, _, _ = _service(tmp_path, runner=lambda *args, **kwargs: calls.append("run"))
    with pytest.raises(Exception) as caught:
        service.run(SupervisedRecoveryRequest(**_request(dry_run=False)))
    assert getattr(caught.value, "code", None) == "CREDENTIALS_NOT_CONFIGURED"
    assert calls == []


def test_execution_delegates_existing_exact_recovery_without_api_post_or_delete(tmp_path: Path) -> None:
    calls = []

    def runner(stop_id, take_id, confirmation, reconcile_only):
        calls.append(("EXACT_RECOVERY", stop_id, take_id, confirmation, reconcile_only))
        return SimpleNamespace(status="PASS", phase="RECOVERY_COMPLETE", recovery_required=False, final_stop_order=None, final_take_profit_order=None)

    service, persistence, _ = _service(tmp_path, runner=runner, credentials=True)
    result = service.run(SupervisedRecoveryRequest(**_request(dry_run=False)))
    assert result["recovery_executed"] is True
    assert result["stop_result"] == result["take_profit_result"] == "ABSENT"
    assert [call[0] for call in calls] == ["EXACT_RECOVERY"]
    assert calls[0][-1] is True
    assert "audit_recorded" not in result
    assert persistence.closed is True


def test_lock_and_kill_switch_block_before_persistence_or_runner(tmp_path: Path) -> None:
    service, persistence, runtime = _service(tmp_path)
    (runtime / "protective.lock").write_text("held", encoding="utf-8")
    with pytest.raises(Exception) as locked:
        service.run(SupervisedRecoveryRequest(**_request()))
    assert getattr(locked.value, "code", None) == "RECOVERY_LOCKED"
    assert persistence.calls == []

    (runtime / "protective.lock").unlink()
    blocked_gate = type(
        "BlockedGate",
        (), {"require_engaged": lambda self: (_ for _ in ()).throw(KillSwitchGateError("KILL_SWITCH_NOT_ENGAGED"))},
    )()
    service, persistence, _ = _service(tmp_path, persistence=persistence, kill_switch_gate=blocked_gate)
    with pytest.raises(Exception) as killed:
        service.run(SupervisedRecoveryRequest(**_request()))
    assert getattr(killed.value, "code", None) == "KILL_SWITCH_NOT_ENGAGED"
    assert persistence.calls == []


@pytest.mark.parametrize(
    ("consistency", "expected"),
    [
        (ProtectiveConsistencyResult("ALREADY_COMPLETED"), "RECOVERY_NOT_REQUIRED"),
        (ProtectiveConsistencyResult("RECOVERY", None), "RECOVERY_NOT_REQUIRED"),
    ],
)
def test_ineligible_persistence_states_fail_closed(tmp_path: Path, consistency, expected) -> None:
    service, persistence, _ = _service(tmp_path, persistence=FakePersistence(consistency=consistency))
    with pytest.raises(Exception) as caught:
        service.run(SupervisedRecoveryRequest(**_request()))
    assert getattr(caught.value, "code", None) == expected
    assert persistence.closed is True


def test_correlation_mismatch_and_persistence_failure_are_sanitized(tmp_path: Path) -> None:
    base = FakePersistence().consistency
    mismatch = ProtectiveConsistencyResult(base.status, base.state, base.pair_state, True, UUID("99999999-9999-4999-8999-999999999999"))
    service, _, _ = _service(tmp_path, persistence=FakePersistence(consistency=mismatch))
    with pytest.raises(Exception) as caught:
        service.run(SupervisedRecoveryRequest(**_request()))
    assert getattr(caught.value, "code", None) == "RECOVERY_OWNERSHIP_MISMATCH"

    other = tmp_path / "other"
    service, _, _ = _service(other, persistence=FakePersistence(error=ProtectivePersistenceError("PERSISTENCE_UNAVAILABLE")))
    with pytest.raises(Exception) as unavailable:
        service.run(SupervisedRecoveryRequest(**_request()))
    assert getattr(unavailable.value, "message", "") == "Recovery persistence is unavailable."
    assert "database" not in str(unavailable.value).lower()


def test_projection_gap_uses_deterministic_catch_up_plan(tmp_path: Path) -> None:
    journal = _journal()
    journal.mutation_intents[0].resolved = True
    journal.recovery_required = False
    persistence = FakePersistence(catch_up=True)
    persistence.consistency = ProtectiveConsistencyResult(
        "RECOVERY", persistence.consistency.state, "RECOVERY_REQUIRED", True, UUID(CORRELATION_ID)
    )
    service, _, _ = _service(tmp_path, journal=journal, persistence=persistence)
    result = service.run(SupervisedRecoveryRequest(**_request()))
    assert result["planned_actions"] == ["CATCH_UP_STOP_CREATE"]


def test_recovery_runner_failure_is_sanitized_and_keeps_recovery_required(tmp_path: Path) -> None:
    result = SimpleNamespace(status="FAIL", decision="rawResponse databaseUrl SELECT secret")
    service, _, _ = _service(tmp_path, runner=lambda *args, **kwargs: result, credentials=True)
    with pytest.raises(Exception) as caught:
        service.run(SupervisedRecoveryRequest(**_request(dry_run=False)))
    assert getattr(caught.value, "code", None) == "RECOVERY_FAILED"
    assert "rawresponse" not in getattr(caught.value, "message", "").lower()


def _real_database(tmp_path: Path) -> tuple[str, object]:
    database = tmp_path / "recovery-integration.db"
    database_url = f"sqlite:///{database}"
    engine = create_engine(database_url, future=True)
    ExecutionPersistenceBase.metadata.create_all(engine)
    version = Table("alembic_version", MetaData(), Column("version_num", String(64), primary_key=True))
    version.create(engine)
    with engine.begin() as connection:
        connection.execute(version.insert().values(version_num=PERSISTENCE_REVISION))
    gate = KillSwitchPersistence(env={"ICT_DATABASE_URL": database_url})
    gate.ensure_available()
    gate.engage()
    gate.close()
    return database_url, engine


def _stable_database_snapshot(database_engine) -> dict[str, list[tuple[str | None, ...]]]:
    models = (ExecutionIntentORM, ProtectivePairORM, ExchangeOrderIdentityORM, AuditEventORM, RecoveryEventORM)

    def stable(value):
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, dict):
            return json.dumps(value, sort_keys=True, separators=(",", ":"))
        return None if value is None else str(value)

    with Session(database_engine) as session:
        return {
            model.__tablename__: [
                tuple(stable(getattr(row, column.name)) for column in model.__table__.columns)
                for row in session.scalars(select(model).order_by(model.id.asc())).all()
            ]
            for model in models
        }


def _assert_rejected_state_unchanged(service, request, runtime, database_engine, transport, expected_code=None) -> None:
    journal_existed = runtime.exists()
    journal_before = runtime.read_bytes() if journal_existed else None
    database_before = _stable_database_snapshot(database_engine)

    with pytest.raises(Exception) as caught:
        service.run(request)

    if expected_code is not None:
        assert getattr(caught.value, "code", None) == expected_code
    assert transport.calls == []
    assert runtime.exists() is journal_existed
    assert (runtime.read_bytes() if journal_existed else None) == journal_before
    assert _stable_database_snapshot(database_engine) == database_before
    assert not (runtime.parent / "protective.lock").exists()


def _algo_summary(label: str, status: str = "NEW") -> BinanceFuturesTestnetProtectiveAlgoSummary:
    return BinanceFuturesTestnetProtectiveAlgoSummary(
        symbol="BTCUSDT",
        client_algo_id=STOP_ID if label == "STOP" else TP_ID,
        algo_id="42" if label == "STOP" else "43",
        algo_type="CONDITIONAL",
        side="SELL",
        position_side="BOTH",
        order_type="STOP_MARKET" if label == "STOP" else "TAKE_PROFIT_MARKET",
        trigger_price=Decimal("45000") if label == "STOP" else Decimal("55000"),
        algo_status=status,
        executed_quantity=Decimal("0"),
        actual_price=Decimal("0"),
        close_position=True,
        working_type="MARK_PRICE",
        price_protect=True,
    )


def _algo_payload(label: str, status: str = "NEW") -> dict:
    summary = _algo_summary(label, status)
    return {
        "symbol": summary.symbol,
        "clientAlgoId": summary.client_algo_id,
        "algoId": summary.algo_id,
        "algoType": summary.algo_type,
        "side": summary.side,
        "positionSide": summary.position_side,
        "orderType": summary.order_type,
        "triggerPrice": str(summary.trigger_price),
        "algoStatus": summary.algo_status,
        "actualQty": "0",
        "actualPrice": "0",
        "closePosition": True,
        "workingType": "MARK_PRICE",
        "priceProtect": True,
    }


def _public_time(url, timeout):
    assert url.endswith("/fapi/v1/time")
    return BinanceLifecycleHTTPResponse(200, url, {"serverTime": 1000}, 1)


class ReconcileOnlyTransport:
    def __init__(self, present: set[str], *, fail_client_id: str | None = None, mismatch: bool = False) -> None:
        self.present = set(present)
        self.fail_client_id = fail_client_id
        self.mismatch = mismatch
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        if not params:
            params = parse_qs(urlparse(url).query)
        client_id = params.get("clientAlgoId", [None])[0]
        self.calls.append((method, client_id))
        if method != "GET":
            raise AssertionError("supervised recovery must never transmit POST or DELETE")
        if client_id == self.fail_client_id:
            raise TimeoutError("rawResponse secret timeout")
        if client_id not in self.present:
            raise BinanceFuturesTestnetProtectiveAPIError(
                "NO_SUCH_ORDER",
                http_status=400,
                binance_code=-2013,
                method="GET",
                path="/fapi/v1/algoOrder",
                request_transmitted=True,
                response_received=True,
            )
        label = "STOP" if client_id == STOP_ID else "TAKE_PROFIT"
        payload = _algo_payload(label)
        if self.mismatch and client_id == STOP_ID:
            payload["symbol"] = "ETHUSDT"
        return BinanceLifecycleHTTPResponse(200, url, payload, 1)


def _lifecycle_public_get(url, timeout):
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


class LifecycleSetupTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.created: set[str] = set()
        self.deleted: set[str] = set()

    def __call__(self, method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        if "positionSide/dual" in url:
            self.calls.append((method, None))
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 1)
        if "positionRisk" in url:
            self.calls.append((method, None))
            return BinanceLifecycleHTTPResponse(
                200,
                url,
                [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": "0.001", "entryPrice": "49000", "markPrice": "50000", "notional": "50"}],
                1,
            )
        client_id = params.get("clientAlgoId", [None])[0]
        self.calls.append((method, client_id))
        label = "STOP" if client_id == STOP_ID else "TAKE_PROFIT"
        if method == "POST":
            self.created.add(client_id)
            return BinanceLifecycleHTTPResponse(200, url, _algo_payload(label), 1)
        if method == "DELETE":
            self.deleted.add(client_id)
            return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": "42", "code": 200}, 1)
        if client_id in self.deleted or client_id not in self.created:
            raise BinanceFuturesTestnetProtectiveAPIError(
                "NO_SUCH_ORDER", http_status=400, binance_code=-2013, method="GET",
                path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True,
            )
        return BinanceLifecycleHTTPResponse(200, url, _algo_payload(label), 1)


def _projection_gap_service(tmp_path: Path, failure_kind: str):
    database_url, database_engine = _real_database(tmp_path)
    env = {
        "ICT_DATABASE_URL": database_url,
        "BINANCE_FUTURES_TESTNET_API_KEY": "unit-key",
        "BINANCE_FUTURES_TESTNET_API_SECRET": "unit-secret",
    }
    config = BinanceFuturesTestnetProtectiveOrdersConfig()
    config_path = tmp_path / "configs/binance_futures_testnet_protective_orders.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps(config.to_dict()), encoding="utf-8")
    (config_path.parent / "btc_paper_runtime.json").write_text(json.dumps({"kill_switch_enabled": True}), encoding="utf-8")

    setup_gate = KillSwitchPersistence(env={"ICT_DATABASE_URL": database_url})
    setup_gate.ensure_available()
    setup_gate.release(1)
    setup_gate.close()

    class GapPersistence(ProtectiveLifecyclePersistence):
        def confirm_create(self, state, label, order):
            if failure_kind == "CREATE" and label == "STOP":
                raise ProtectivePersistenceError("PERSISTENCE_POST_TRANSPORT_FAILED", after_transport=True)
            return super().confirm_create(state, label, order)

        def confirm_delete(self, state, label, status, complete):
            if failure_kind == "DELETE" and label == "TAKE_PROFIT":
                raise ProtectivePersistenceError("PERSISTENCE_POST_TRANSPORT_FAILED", after_transport=True)
            return super().confirm_delete(state, label, status, complete)

    setup_transport = LifecycleSetupTransport()
    initial = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=env,
        http_get=_lifecycle_public_get,
        authenticated_request=setup_transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=GapPersistence,
    ).run_protective_lifecycle(
        PAIR_ID,
        STOP_ID,
        TP_ID,
        confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE",
        config_path=str(config_path),
    )
    assert initial.decision == "RECOVERY_REQUIRED"
    recovery_gate = KillSwitchPersistence(env={"ICT_DATABASE_URL": database_url})
    recovery_gate.ensure_available()
    recovery_gate.engage()
    recovery_gate.close()
    present = {STOP_ID} if failure_kind == "CREATE" else {STOP_ID}
    recovery_transport = ReconcileOnlyTransport(present)
    protective_engine = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=env,
        http_get=_public_time,
        authenticated_request=recovery_transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=ProtectiveLifecyclePersistence,
    )
    service = SupervisedRecoveryService(
        repo_root=tmp_path,
        env=env,
        protective_engine=protective_engine,
        persistence_factory=ProtectiveLifecyclePersistence,
    )
    with Session(database_engine) as session:
        pair = session.scalar(select(ProtectivePairORM))
        correlation_id = str(pair.correlation_id)
    runtime = tmp_path / config.journal_path
    request = SupervisedRecoveryRequest(**_request(correlation_id=correlation_id, dry_run=False))
    return service, request, runtime, database_engine, setup_transport, recovery_transport


def _real_recovery_service(tmp_path: Path, stage: str, transport: ReconcileOnlyTransport):
    database_url, database_engine = _real_database(tmp_path)
    env = {
        "ICT_DATABASE_URL": database_url,
        "BINANCE_FUTURES_TESTNET_API_KEY": "unit-key",
        "BINANCE_FUTURES_TESTNET_API_SECRET": "unit-secret",
    }
    config = BinanceFuturesTestnetProtectiveOrdersConfig()
    config_path = tmp_path / "configs/binance_futures_testnet_protective_orders.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps(config.to_dict()), encoding="utf-8")
    (config_path.parent / "btc_paper_runtime.json").write_text(
        json.dumps({"kill_switch_enabled": True}), encoding="utf-8"
    )
    persistence = ProtectiveLifecyclePersistence(env=env)
    persistence.ensure_available()
    position = BinanceFuturesTestnetProtectivePosition(
        position_amt=Decimal("0.001"), mark_price=Decimal("50000"), notional=Decimal("50"), direction="LONG"
    )
    preview = BinanceFuturesTestnetProtectivePreview(
        pair_id=PAIR_ID,
        position_direction="LONG",
        position_amount=Decimal("0.001"),
        protective_side="SELL",
        stop_client_algo_id=STOP_ID,
        take_profit_client_algo_id=TP_ID,
        stop_trigger=Decimal("45000"),
        take_profit_trigger=Decimal("55000"),
        transmission_ready=True,
    )
    state = persistence.prepare_lifecycle(PAIR_ID, STOP_ID, TP_ID, position, preview)
    persistence.mark_create_transmitted(state)
    intents = [_intent("STOP", resolved=False)]
    if stage in {"TAKE_PROFIT_CREATE", "TAKE_PROFIT_DELETE"}:
        persistence.confirm_create(state, "STOP", _algo_summary("STOP"))
        intents = [_intent("STOP", resolved=True), _intent("TAKE_PROFIT", resolved=False)]
    if stage == "TAKE_PROFIT_DELETE":
        persistence.confirm_create(state, "TAKE_PROFIT", _algo_summary("TAKE_PROFIT"))
        persistence.prepare_cancel(state, "TAKE_PROFIT", Decimal("0.001"), Decimal("50000"))
        persistence.mark_cancel_transmitted(state, "TAKE_PROFIT")
        intents = [
            _intent("STOP", resolved=True),
            _intent("TAKE_PROFIT", resolved=True),
            _intent("TAKE_PROFIT", kind="DELETE", resolved=False),
        ]
        persistence.mark_recovery_required(state, "DELETE", "AMBIGUOUS_TRANSPORT")
    else:
        persistence.mark_recovery_required(state, "CREATE", "AMBIGUOUS_TRANSPORT")
    persistence.close()

    journal = BinanceFuturesTestnetProtectiveJournal(
        pair_id=PAIR_ID,
        stop_client_algo_id=STOP_ID,
        take_profit_client_algo_id=TP_ID,
        phase="RECOVERY_REQUIRED",
        recovery_required=True,
        baseline_available=True,
        baseline_position_amount=Decimal("0.001"),
        baseline_position_direction="LONG",
        stop_trigger=Decimal("45000"),
        take_profit_trigger=Decimal("55000"),
        mutation_intents=intents,
    )
    runtime = tmp_path / config.journal_path
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(json.dumps(journal.to_dict()), encoding="utf-8")
    protective_engine = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=env,
        http_get=_public_time,
        authenticated_request=transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=ProtectiveLifecyclePersistence,
    )
    service = SupervisedRecoveryService(
        repo_root=tmp_path,
        env=env,
        protective_engine=protective_engine,
        persistence_factory=ProtectiveLifecyclePersistence,
    )
    request = SupervisedRecoveryRequest(**_request(correlation_id=str(state.create_correlation_id), dry_run=False))
    return service, request, runtime, database_engine


def _completed_recovery_service(tmp_path: Path, transport: ReconcileOnlyTransport):
    service, request, runtime, database_engine = _real_recovery_service(
        tmp_path, "TAKE_PROFIT_DELETE", transport
    )
    persistence = ProtectiveLifecyclePersistence(env=service.env)
    persistence.ensure_available()
    journal = service.protective_engine._load_existing_journal_strict(
        service.protective_engine.load_config("configs/binance_futures_testnet_protective_orders.json"),
        PAIR_ID,
        STOP_ID,
        TP_ID,
    )
    state = persistence.check_consistency(journal, PAIR_ID, STOP_ID, TP_ID).state
    assert state is not None
    persistence.confirm_delete(state, "TAKE_PROFIT", "ABSENT", complete=False)
    persistence.prepare_cancel(state, "STOP", Decimal("0.001"), Decimal("50000"))
    persistence.mark_cancel_transmitted(state, "STOP")
    persistence.confirm_delete(state, "STOP", "ABSENT", complete=True)
    persistence.close()
    for intent in journal.mutation_intents:
        if intent.mutation_kind == "DELETE":
            intent.resolved = True
            intent.reconciliation_state = "ABSENT"
            intent.reconciliation_reason = "Exact prior proof."
    journal.mutation_intents.append(_intent("STOP", kind="DELETE", resolved=True))
    journal.mutation_intents[-1].reconciliation_state = "ABSENT"
    journal.phase = "RECOVERY_COMPLETE"
    journal.recovery_required = False
    journal.entries.extend(
        [
            {"created_at": "2026-01-01T00:00:01+00:00", "phase": "TAKE_PROFIT_CANCELED", "details": {"status": "ABSENT"}},
            {"created_at": "2026-01-01T00:00:02+00:00", "phase": "STOP_CANCELED", "details": {"status": "ABSENT"}},
        ]
    )
    runtime.write_text(json.dumps(journal.to_dict()), encoding="utf-8")
    return service, request, runtime, database_engine


@pytest.mark.parametrize(
    ("stage", "present"),
    [
        ("STOP_CREATE", {STOP_ID}),
        ("TAKE_PROFIT_CREATE", {STOP_ID, TP_ID}),
        ("TAKE_PROFIT_DELETE", {STOP_ID}),
    ],
)
def test_real_recovery_engine_is_exact_get_only_for_ambiguous_mutations(tmp_path: Path, stage, present) -> None:
    transport = ReconcileOnlyTransport(present)
    service, request, runtime, database_engine = _real_recovery_service(tmp_path, stage, transport)

    result = service.run(request)

    assert result["recovery_executed"] is True
    assert transport.calls
    assert {method for method, _ in transport.calls} == {"GET"}
    assert {client_id for _, client_id in transport.calls} <= {STOP_ID, TP_ID}
    assert not (runtime.parent / "protective.lock").exists()
    with Session(database_engine) as session:
        identities = list(session.scalars(select(ExchangeOrderIdentityORM)).all())
        assert len({item.client_algo_id for item in identities}) == len(identities)
    database_engine.dispose()


def test_active_orders_without_persisted_delete_intents_are_not_cancelled(tmp_path: Path) -> None:
    transport = ReconcileOnlyTransport({STOP_ID, TP_ID})
    service, request, runtime, database_engine = _real_recovery_service(tmp_path, "TAKE_PROFIT_CREATE", transport)

    result = service.run(request)

    assert result["stop_result"] == result["take_profit_result"] == "NEW"
    assert all(method == "GET" for method, _ in transport.calls)
    assert not (runtime.parent / "protective.lock").exists()
    database_engine.dispose()


@pytest.mark.parametrize("failure", ["timeout", "identity"])
def test_real_recovery_ambiguity_or_identity_conflict_fails_closed_and_releases_lock(tmp_path: Path, failure) -> None:
    transport = ReconcileOnlyTransport(
        {STOP_ID},
        fail_client_id=STOP_ID if failure == "timeout" else None,
        mismatch=failure == "identity",
    )
    service, request, runtime, database_engine = _real_recovery_service(tmp_path, "STOP_CREATE", transport)

    with pytest.raises(Exception) as caught:
        service.run(request)

    assert getattr(caught.value, "code", None) in {"RECOVERY_REQUIRED", "RECOVERY_FAILED"}
    assert {method for method, _ in transport.calls} == {"GET"}
    assert not (runtime.parent / "protective.lock").exists()
    payload = json.loads(runtime.read_text(encoding="utf-8"))
    assert payload["recovery_required"] is True
    database_engine.dispose()


def test_real_service_rejects_journal_only_unresolved_state_immutably(tmp_path: Path) -> None:
    transport = ReconcileOnlyTransport(set())
    service, request, runtime, database_engine = _real_recovery_service(tmp_path, "STOP_CREATE", transport)
    with Session(database_engine) as session, session.begin():
        for model in (RecoveryEventORM, AuditEventORM, ExchangeOrderIdentityORM, ProtectivePairORM, ExecutionIntentORM):
            session.query(model).delete()

    _assert_rejected_state_unchanged(service, request, runtime, database_engine, transport)
    database_engine.dispose()


def test_real_service_rejects_db_only_unresolved_state_immutably(tmp_path: Path) -> None:
    transport = ReconcileOnlyTransport(set())
    service, request, runtime, database_engine = _real_recovery_service(tmp_path, "STOP_CREATE", transport)
    runtime.unlink()

    _assert_rejected_state_unchanged(service, request, runtime, database_engine, transport, "RECOVERY_JOURNAL_NOT_FOUND")
    database_engine.dispose()


@pytest.mark.parametrize(
    ("field", "wrong_value", "expected_code"),
    [
        ("correlation_id", "99999999-9999-4999-8999-999999999999", "RECOVERY_OWNERSHIP_MISMATCH"),
        ("pair_id", "44444444-4444-4444-8444-444444444444", "RECOVERY_JOURNAL_UNTRUSTED"),
    ],
    ids=("wrong-correlation", "wrong-pair"),
)
def test_real_service_rejects_wrong_ownership_without_transport_or_mutation(
    tmp_path: Path, field: str, wrong_value: str, expected_code: str
) -> None:
    transport = ReconcileOnlyTransport(set())
    service, request, runtime, database_engine = _real_recovery_service(tmp_path, "STOP_CREATE", transport)
    request_payload = _request(correlation_id=request.correlation_id, dry_run=False)
    request_payload[field] = wrong_value
    journal_before = runtime.read_bytes()
    database_before = _stable_database_snapshot(database_engine)

    app = create_app()
    app.dependency_overrides[get_supervised_recovery_service] = lambda: service
    response = TestClient(app).post("/api/v1/live/recovery/run", json=request_payload)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == expected_code
    assert response.json()["detail"]["details"] == {}
    assert PAIR_ID not in response.text
    assert request.correlation_id not in response.text
    assert wrong_value not in response.text
    assert "traceback" not in response.text.lower()
    assert transport.calls == []
    assert runtime.read_bytes() == journal_before
    assert json.loads(runtime.read_text(encoding="utf-8"))["recovery_required"] is True
    assert _stable_database_snapshot(database_engine) == database_before
    assert not (runtime.parent / "protective.lock").exists()
    database_engine.dispose()


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("client_id", "RECOVERY_JOURNAL_UNTRUSTED"),
        ("unsupported_phase", "RECOVERY_JOURNAL_UNTRUSTED"),
        ("journal_true_db_false", "RECOVERY_STATE_CONFLICT"),
        ("journal_false_db_true", "RECOVERY_STATE_CONFLICT"),
        ("missing_identity", "RECOVERY_STATE_CONFLICT"),
        ("invalid_identity_status", "RECOVERY_STATE_CONFLICT"),
    ],
)
def test_real_service_rejects_untrusted_or_malformed_projection_immutably(
    tmp_path: Path, mutation: str, expected_code: str
) -> None:
    stage = "STOP_CREATE"
    present = set()
    transport = ReconcileOnlyTransport(present)
    if mutation in {"missing_identity", "invalid_identity_status"}:
        service, request, runtime, database_engine = _completed_recovery_service(tmp_path, transport)
    else:
        service, request, runtime, database_engine = _real_recovery_service(tmp_path, stage, transport)
    payload = json.loads(runtime.read_text(encoding="utf-8"))
    if mutation == "client_id":
        payload["stop_client_algo_id"] = "smcbot-protect-sl-mismatch"
        runtime.write_text(json.dumps(payload), encoding="utf-8")
    elif mutation == "unsupported_phase":
        payload["phase"] = "UNSUPPORTED_SUPERVISED_PHASE"
        runtime.write_text(json.dumps(payload), encoding="utf-8")
    elif mutation == "journal_true_db_false":
        with Session(database_engine) as session, session.begin():
            pair = session.scalar(select(ProtectivePairORM))
            pair.recovery_required = False
    elif mutation == "journal_false_db_true":
        payload["phase"] = "STOP_CREATE_CREATE_CONFIRMED"
        payload["recovery_required"] = False
        payload["mutation_intents"][0]["resolved"] = True
        payload["mutation_intents"][0]["reconciliation_state"] = "PRESENT"
        payload["mutation_intents"][0]["reconciliation_reason"] = "Exact prior proof."
        runtime.write_text(json.dumps(payload), encoding="utf-8")
    elif mutation == "missing_identity":
        with Session(database_engine) as session, session.begin():
            identity = session.scalar(
                select(ExchangeOrderIdentityORM).where(ExchangeOrderIdentityORM.leg_type == "STOP")
            )
            session.delete(identity)
    else:
        with Session(database_engine) as session, session.begin():
            identity = session.scalar(
                select(ExchangeOrderIdentityORM).where(ExchangeOrderIdentityORM.leg_type == "STOP")
            )
            identity.status = "HOSTILE_UNKNOWN"

    _assert_rejected_state_unchanged(service, request, runtime, database_engine, transport, expected_code)
    database_engine.dispose()


def test_real_service_rejects_multiple_unresolved_pairs_immutably(tmp_path: Path) -> None:
    transport = ReconcileOnlyTransport(set())
    service, request, runtime, database_engine = _real_recovery_service(tmp_path, "STOP_CREATE", transport)
    persistence = ProtectiveLifecyclePersistence(env=service.env)
    persistence.ensure_available()
    position = BinanceFuturesTestnetProtectivePosition(
        position_amt=Decimal("0.001"), mark_price=Decimal("50000"), notional=Decimal("50"), direction="LONG"
    )
    preview = BinanceFuturesTestnetProtectivePreview(
        pair_id="33333333-3333-4333-8333-333333333333",
        position_direction="LONG",
        position_amount=Decimal("0.001"),
        protective_side="SELL",
        stop_client_algo_id="smcbot-protect-sl-second",
        take_profit_client_algo_id="smcbot-protect-tp-second",
        stop_trigger=Decimal("45000"),
        take_profit_trigger=Decimal("55000"),
        transmission_ready=True,
    )
    persistence.prepare_lifecycle(
        preview.pair_id, preview.stop_client_algo_id, preview.take_profit_client_algo_id, position, preview
    )
    persistence.close()

    _assert_rejected_state_unchanged(service, request, runtime, database_engine, transport, "RECOVERY_STATE_CONFLICT")
    database_engine.dispose()


def test_real_service_rejects_completed_lifecycle_immutably(tmp_path: Path) -> None:
    transport = ReconcileOnlyTransport(set())
    service, request, runtime, database_engine = _completed_recovery_service(tmp_path, transport)

    _assert_rejected_state_unchanged(service, request, runtime, database_engine, transport, "RECOVERY_NOT_REQUIRED")
    database_engine.dispose()


@pytest.mark.parametrize("failure_kind", ["CREATE", "DELETE"])
def test_real_service_catches_up_definitive_projection_with_exact_get_only(tmp_path: Path, failure_kind: str) -> None:
    service, request, runtime, database_engine, setup_transport, recovery_transport = _projection_gap_service(
        tmp_path, failure_kind
    )
    before_identity_count = len(_stable_database_snapshot(database_engine)["exchange_order_identities"])

    result = service.run(request)

    assert result["recovery_executed"] is True
    assert recovery_transport.calls
    assert {method for method, _ in recovery_transport.calls} == {"GET"}
    assert {client_id for _, client_id in recovery_transport.calls} <= {STOP_ID, TP_ID}
    assert all(method not in {"POST", "DELETE"} for method, _ in recovery_transport.calls)
    after = _stable_database_snapshot(database_engine)
    assert len(after["exchange_order_identities"]) >= before_identity_count
    assert len({row[4] for row in after["exchange_order_identities"]}) == len(after["exchange_order_identities"])
    assert json.loads(runtime.read_text(encoding="utf-8"))["recovery_required"] is False
    assert not (runtime.parent / "protective.lock").exists()
    assert any(method == "POST" for method, _ in setup_transport.calls)
    database_engine.dispose()


@pytest.mark.parametrize(
    "hostile_marker",
    [
        "postgresql://user:secret@host/db",
        "connectionString=secret",
        "SELECT * FROM execution_intents",
        "Traceback (most recent call last)",
        "X-MBX-APIKEY=secret",
        "signed-url=https://secret",
        "rawResponse=secret",
    ],
)
def test_real_service_persistence_failure_after_lock_is_sanitized_and_immutable(
    tmp_path: Path, hostile_marker: str
) -> None:
    transport = ReconcileOnlyTransport({STOP_ID})
    service, request, runtime, database_engine = _real_recovery_service(tmp_path, "STOP_CREATE", transport)
    journal_before = runtime.read_bytes()
    database_before = _stable_database_snapshot(database_engine)

    class HostilePersistenceFailure(ProtectiveLifecyclePersistence):
        def check_consistency(self, *args, **kwargs):
            try:
                raise RuntimeError(hostile_marker)
            except RuntimeError as exc:
                raise ProtectivePersistenceError("PERSISTENCE_CONSISTENCY_UNAVAILABLE") from exc

    service.protective_engine.persistence_factory = HostilePersistenceFailure
    app = create_app()
    app.dependency_overrides[get_supervised_recovery_service] = lambda: service
    response = TestClient(app).post("/api/v1/live/recovery/run", json=_request(
        correlation_id=request.correlation_id, dry_run=False
    ))

    assert response.status_code == 502
    assert response.json() == {
        "detail": {"code": "RECOVERY_FAILED", "message": "Recovery did not complete.", "details": {}}
    }
    assert hostile_marker.lower() not in response.text.lower()
    assert transport.calls == []
    assert runtime.read_bytes() == journal_before
    assert _stable_database_snapshot(database_engine) == database_before
    assert hostile_marker.lower() not in json.dumps(database_before).lower()
    assert not (runtime.parent / "protective.lock").exists()
    database_engine.dispose()


def test_real_service_optimistic_lock_conflict_after_exact_get_releases_lock_without_retry(tmp_path: Path) -> None:
    transport = ReconcileOnlyTransport({STOP_ID})
    service, request, runtime, database_engine = _real_recovery_service(tmp_path, "STOP_CREATE", transport)

    class StaleVersionPersistence(ProtectiveLifecyclePersistence):
        def confirm_create(self, state, label, order):
            try:
                with self._transaction() as session:
                    repository = SqlAlchemyProtectivePairRepository(session)
                    pair = self._require_pair(repository, state.pair_id)
                    with Session(self._engine) as competing, competing.begin():
                        current = competing.get(ProtectivePairORM, pair.id)
                        current.version += 1
                    repository.update_state(pair.id, pair.version, "STOP_ACTIVE", recovery_required=False)
            except OptimisticLockError as exc:
                raise ProtectivePersistenceError("PERSISTENCE_VERSION_CONFLICT", after_transport=True) from exc

    service.protective_engine.persistence_factory = StaleVersionPersistence
    with pytest.raises(Exception) as caught:
        service.run(request)

    assert getattr(caught.value, "code", None) == "RECOVERY_REQUIRED"
    assert transport.calls == [("GET", STOP_ID)]
    assert all(method not in {"POST", "DELETE"} for method, _ in transport.calls)
    assert not (runtime.parent / "protective.lock").exists()
    assert json.loads(runtime.read_text(encoding="utf-8"))["recovery_required"] is True
    with Session(database_engine) as session:
        assert session.scalar(select(ExchangeOrderIdentityORM)) is None
        pair = session.scalar(select(ProtectivePairORM))
        assert pair.recovery_required is True
    database_engine.dispose()
