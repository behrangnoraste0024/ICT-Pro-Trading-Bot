from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.live_control_plane_routes import (
    get_kill_switch_control_service,
    get_live_control_plane_service,
    get_live_execution_permit_status_service,
    get_operator_status_service,
)
import api.live_control_plane_service as service_module
from api.live_control_plane_service import LiveControlPlaneHTTPError, LiveControlPlaneService
from engine.diagnostics.btc_paper_readiness_engine import BTCPaperReadinessEngine
from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import BinanceLifecycleHTTPResponse
from models.binance_futures_testnet_protective_orders import BinanceFuturesTestnetProtectiveJournal, BinanceFuturesTestnetProtectiveOrdersConfig
from models.binance_futures_testnet_read_only import BinanceFuturesTestnetReadOnlyConfig, BinanceFuturesTestnetPositionSummary


class FakeService:
    def safety_status(self):
        return {
            "environment": "BINANCE_FUTURES_TESTNET",
            "live_trading_enabled": False,
            "automatic_execution_enabled": False,
            "kill_switch_engaged": True,
            "credentials_configured": True,
            "active_lock": False,
            "recovery_required": False,
            "production_endpoint_allowed": False,
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

    def readiness(self):
        return {
            "status": "READY",
            "symbol": "BTCUSDT",
            "checks_passed": 3,
            "checks_warning": 0,
            "checks_failed": 0,
            "validation_gate": "PASS",
            "blocking_reasons": [],
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

    def position(self, symbol: str):
        if symbol != "BTCUSDT":
            raise LiveControlPlaneHTTPError(400, "INVALID_SYMBOL", "Only BTCUSDT is supported.")
        return {
            "symbol": "BTCUSDT",
            "position_side": "BOTH",
            "direction": "LONG",
            "quantity": "0.001",
            "entry_price": "60000",
            "break_even_price": "60001",
            "mark_price": "60100",
            "notional_usdt": "60.1",
            "unrealized_pnl": "1.2",
            "liquidation_price": "50000",
            "has_open_position": True,
            "source": "binance_futures_testnet_read_only",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

    def protective_orders_current(self):
        return {
            "state": "NONE",
            "pair_id": None,
            "recovery_required": False,
            "blocking_reason": None,
            "active_lock": False,
            "stop": None,
            "take_profit": None,
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

    def recovery_status(self):
        return {
            "required": False,
            "reason": None,
            "pair_id": None,
            "phase": None,
            "active_lock": False,
            "updated_at": "2026-01-01T00:00:00+00:00",
        }



class FakeKillSwitchService:
    def status(self):
        return {
            "accepted": True,
            "environment": "BINANCE_FUTURES_TESTNET",
            "symbol": "BTCUSDT",
            "state": "RELEASED",
            "changed": False,
            "version": 2,
            "updated_at": "2026-01-01T00:00:00+00:00",
            "blocking_code": None,
        }

    def engage(self):
        return {
            "accepted": True,
            "environment": "BINANCE_FUTURES_TESTNET",
            "symbol": "BTCUSDT",
            "state": "ENGAGED",
            "changed": True,
            "version": 1,
            "updated_at": "2026-01-01T00:00:00+00:00",
            "blocking_code": None,
        }

    def release(self):
        return {
            "accepted": True,
            "environment": "BINANCE_FUTURES_TESTNET",
            "symbol": "BTCUSDT",
            "state": "RELEASED",
            "changed": True,
            "version": 2,
            "updated_at": "2026-01-01T00:00:00+00:00",
            "blocking_code": None,
        }


class FakeOperatorStatusService:
    def __init__(self) -> None:
        self.mutation_calls = []

    def status(self):
        return {
            "environment": "BINANCE_FUTURES_TESTNET",
            "symbol": "BTCUSDT",
            "overall_status": "READY",
            "kill_switch_state": "RELEASED",
            "kill_switch_available": True,
            "recovery_required": False,
            "recovery_available": True,
            "persistence_configured": True,
            "persistence_reachable": True,
            "persistence_schema_ready": True,
            "readiness_status": "READY",
            "validation_gate": "PASS",
            "active_lock": False,
            "warnings": [],
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

    def engage(self):
        self.mutation_calls.append("engage")
        raise AssertionError("operator status must not mutate")

    def release(self):
        self.mutation_calls.append("release")
        raise AssertionError("operator status must not mutate")


class FakePermitStatusService:
    def status(self, permit_id: str):
        return {
            "permit_id": permit_id,
            "operation": "PROTECTIVE_CREATE",
            "environment": "TESTNET",
            "symbol": "BTCUSDT",
            "state": "ISSUED",
            "effective_expired": False,
            "expires_at": "2026-01-01T00:05:00+00:00",
            "issued_at": "2026-01-01T00:00:00+00:00",
            "consumed_at": None,
            "revoked_at": None,
            "revocation_reason": None,
            "version": 1,
            "updated_at": "2026-01-01T00:00:00+00:00",
        }


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_live_control_plane_service] = lambda: FakeService()
    app.dependency_overrides[get_kill_switch_control_service] = lambda: FakeKillSwitchService()
    app.dependency_overrides[get_operator_status_service] = lambda: FakeOperatorStatusService()
    app.dependency_overrides[get_live_execution_permit_status_service] = lambda: FakePermitStatusService()
    return TestClient(app)


def test_live_control_plane_routes_allow_only_recovery_and_kill_switch_mutations(client: TestClient) -> None:
    expected = {
        "/api/v1/live/safety/status",
        "/api/v1/live/readiness",
        "/api/v1/live/positions/{symbol}",
        "/api/v1/live/protective-orders/current",
        "/api/v1/live/recovery/status",
        "/api/v1/live/operator/status",
        "/api/v1/live/recovery/run",
        "/api/v1/live/kill-switch/status",
        "/api/v1/live/kill-switch/engage",
        "/api/v1/live/kill-switch/release",
        "/api/v1/live/persistence/status",
        "/api/v1/live/execution-intents/{correlation_id}",
        "/api/v1/live/protective-pairs/{pair_id}",
        "/api/v1/live/protective-pairs/{pair_id}/orders",
        "/api/v1/live/protective-pairs/{pair_id}/events",
        "/api/v1/live/execution-permits/{permit_id}",
    }
    app_paths = {path: set(methods) for path, methods in client.get("/openapi.json").json()["paths"].items() if path.startswith("/api/v1/live")}
    assert set(app_paths) == expected
    mutation_paths = {
        "/api/v1/live/recovery/run",
        "/api/v1/live/kill-switch/engage",
        "/api/v1/live/kill-switch/release",
    }
    assert all(app_paths[path] == {"post"} for path in mutation_paths)
    assert all(methods == {"get"} for path, methods in app_paths.items() if path not in mutation_paths)
    for path in [
        "/api/v1/live/safety/status",
        "/api/v1/live/readiness",
        "/api/v1/live/positions/BTCUSDT",
        "/api/v1/live/protective-orders/current",
        "/api/v1/live/recovery/status",
        "/api/v1/live/kill-switch/status",
        "/api/v1/live/operator/status",
        "/api/v1/live/execution-permits/permit-00000000000000000000000000000001",
    ]:
        for method in (client.post, client.put, client.patch, client.delete):
            assert method(path).status_code == 405


def test_routes_return_sanitized_payloads_without_secrets(client: TestClient) -> None:
    for path in [
        "/api/v1/live/safety/status",
        "/api/v1/live/readiness",
        "/api/v1/live/positions/BTCUSDT",
        "/api/v1/live/protective-orders/current",
        "/api/v1/live/recovery/status",
        "/api/v1/live/kill-switch/status",
        "/api/v1/live/operator/status",
        "/api/v1/live/execution-permits/permit-00000000000000000000000000000001",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        body = json.dumps(response.json())
        assert "unit-test-secret" not in body
        assert "signature" not in body.lower()
        assert "X-MBX-APIKEY" not in body
        assert "raw_response" not in body


def test_route_errors_are_sanitized(client: TestClient) -> None:
    response = client.get("/api/v1/live/positions/ETHUSDT")
    assert response.status_code == 400
    assert response.json()["detail"] == {"code": "INVALID_SYMBOL", "message": "Only BTCUSDT is supported.", "details": {}}


def _write_configs(root: Path, *, read_only_config: BinanceFuturesTestnetReadOnlyConfig | None = None, protective_config: BinanceFuturesTestnetProtectiveOrdersConfig | None = None) -> None:
    config_dir = root / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "binance_futures_testnet_read_only.json").write_text(json.dumps((read_only_config or BinanceFuturesTestnetReadOnlyConfig()).to_dict()), encoding="utf-8")
    (config_dir / "binance_futures_testnet_protective_orders.json").write_text(json.dumps((protective_config or BinanceFuturesTestnetProtectiveOrdersConfig()).to_dict()), encoding="utf-8")


class FakeReadinessEngine:
    def __init__(self, status="READY") -> None:
        self.called = False
        self.status = status

    def build_report(self, **kwargs):
        self.called = True
        checks = [SimpleNamespace(name="official_validation_gate", status="PASS" if self.status == "READY" else "FAIL", severity="REQUIRED", message="gate")]
        return SimpleNamespace(readiness_status=self.status, passed_checks=1 if self.status == "READY" else 0, warning_checks=0, failed_checks=0 if self.status == "READY" else 1, checks=checks, created_at="2026-01-01T00:00:00+00:00")


class RecordingDefaultReadinessEngine:
    instances = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.called = False
        RecordingDefaultReadinessEngine.instances.append(self)

    def build_report(self, **kwargs):
        self.called = True
        checks = [SimpleNamespace(name="official_validation_gate", status="PASS", severity="REQUIRED", message="gate")]
        return SimpleNamespace(readiness_status="READY", passed_checks=1, warning_checks=0, failed_checks=0, checks=checks, created_at="2026-01-01T00:00:00+00:00")


class FakeReadOnlyEngine:
    def __init__(self, root: Path, result) -> None:
        self.repo_root = root
        self.result = result
        self.called = False

    def load_config(self, path: str):
        return BinanceFuturesTestnetReadOnlyConfig(**json.loads((self.repo_root / path).read_text(encoding="utf-8")))

    def fetch_position_risk(self, symbol="BTCUSDT", confirmation=None, config_path="configs/binance_futures_testnet_read_only.json", expected_profile="balanced_smc_decision_065"):
        self.called = True
        assert confirmation == "CONFIRM_TESTNET_READ_ONLY"
        return self.result


def _service(root: Path, *, env=None, read_only_engine=None, readiness_engine=None, protective_engine=None) -> LiveControlPlaneService:
    return LiveControlPlaneService(repo_root=root, env=env or {}, read_only_engine=read_only_engine, readiness_engine=readiness_engine, protective_engine=protective_engine)


def test_safety_status_disabled_by_default_reports_credentials_lock_and_recovery(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    lock = tmp_path / "data/runtime/binance_futures_testnet_protective_orders/protective.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("locked", encoding="utf-8")
    journal = BinanceFuturesTestnetProtectiveJournal(pair_id="pair-001", stop_client_algo_id="smcbot-protect-sl-001", take_profit_client_algo_id="smcbot-protect-tp-001", phase="RECOVERY_REQUIRED", recovery_required=True, baseline_available=False, entries=[], mutation_intents=[])
    (lock.parent / "protective.json").write_text(json.dumps(journal.to_dict()), encoding="utf-8")
    service = _service(tmp_path, env={"BINANCE_FUTURES_TESTNET_API_KEY": "key", "BINANCE_FUTURES_TESTNET_API_SECRET": "secret"})

    result = service.safety_status()

    assert result["live_trading_enabled"] is False
    assert result["automatic_execution_enabled"] is False
    assert result["kill_switch_engaged"] is True
    assert result["credentials_configured"] is True
    assert result["active_lock"] is True
    assert result["recovery_required"] is True
    assert result["production_endpoint_allowed"] is False


def test_readiness_reuses_readiness_engine_for_ready_and_blocked_states(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    ready_engine = FakeReadinessEngine("READY")
    service = _service(tmp_path, readiness_engine=ready_engine)
    ready = service.readiness()
    assert ready_engine.called is True
    assert ready["status"] == "READY"
    assert ready["validation_gate"] == "PASS"

    blocked = _service(tmp_path, readiness_engine=FakeReadinessEngine("BLOCKED")).readiness()
    assert blocked["status"] == "BLOCKED"
    assert blocked["checks_failed"] == 1
    assert blocked["blocking_reasons"] == ["gate"]


def test_default_readiness_engine_does_not_hard_code_gate_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    RecordingDefaultReadinessEngine.instances = []
    monkeypatch.setattr(service_module, "BTCPaperReadinessEngine", RecordingDefaultReadinessEngine)

    service = _service(tmp_path)
    result = service.readiness()

    assert result["validation_gate"] == "PASS"
    assert RecordingDefaultReadinessEngine.instances
    assert "gate_runner" not in RecordingDefaultReadinessEngine.instances[0].kwargs


def test_real_nonzero_validation_gate_result_is_blocked_not_pass(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    readiness_engine = BTCPaperReadinessEngine(repo_root=tmp_path, env={}, gate_runner=lambda **kwargs: 1)

    result = _service(tmp_path, readiness_engine=readiness_engine).readiness()

    assert result["validation_gate"] == "FAIL"
    assert result["status"] != "READY"
    assert "Official BTC validation gate failed." in result["blocking_reasons"]


def test_unavailable_validation_gate_is_sanitized_and_not_reported_as_pass(tmp_path: Path) -> None:
    _write_configs(tmp_path)

    def unavailable_gate(**kwargs):
        raise RuntimeError("SUPER_SECRET_GATE_INTERNAL_DETAILS")

    readiness_engine = BTCPaperReadinessEngine(repo_root=tmp_path, env={}, gate_runner=unavailable_gate)

    result = _service(tmp_path, readiness_engine=readiness_engine).readiness()

    body = json.dumps(result)
    assert result["validation_gate"] == "FAIL"
    assert result["status"] != "READY"
    assert "Official BTC validation gate failed or is unavailable." in result["blocking_reasons"]
    assert "SUPER_SECRET_GATE_INTERNAL_DETAILS" not in body


def test_position_valid_btc_read_returns_sanitized_fields(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    position = BinanceFuturesTestnetPositionSummary(symbol="BTCUSDT", position_side="BOTH", position_amount=0.001, has_open_position=True, entry_price=60000, break_even_price=60001, mark_price=60100, unrealized_profit=1.2, liquidation_price=50000, notional=60.1)
    fake_engine = FakeReadOnlyEngine(tmp_path, SimpleNamespace(status="PASS", position_summary=position))
    service = _service(tmp_path, env={"BINANCE_FUTURES_TESTNET_API_KEY": "key", "BINANCE_FUTURES_TESTNET_API_SECRET": "secret"}, read_only_engine=fake_engine)

    result = service.position("BTCUSDT")

    assert fake_engine.called is True
    assert result["symbol"] == "BTCUSDT"
    assert result["direction"] == "LONG"
    assert result["quantity"] == "0.001"
    assert result["has_open_position"] is True
    assert "raw" not in json.dumps(result).lower()


def test_zero_position_returns_http_style_no_open_position_payload(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    position = BinanceFuturesTestnetPositionSummary(symbol="BTCUSDT", position_amount=0.0, has_open_position=False)
    service = _service(tmp_path, env={"BINANCE_FUTURES_TESTNET_API_KEY": "key", "BINANCE_FUTURES_TESTNET_API_SECRET": "secret"}, read_only_engine=FakeReadOnlyEngine(tmp_path, SimpleNamespace(status="PASS", position_summary=position)))

    result = service.position("BTCUSDT")

    assert result["has_open_position"] is False
    assert result["direction"] is None
    assert result["quantity"] == "0"


def test_position_missing_credentials_fails_before_transport(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    fake_engine = FakeReadOnlyEngine(tmp_path, SimpleNamespace(status="PASS", position_summary=BinanceFuturesTestnetPositionSummary()))
    service = _service(tmp_path, env={}, read_only_engine=fake_engine)

    with pytest.raises(LiveControlPlaneHTTPError) as exc:
        service.position("BTCUSDT")

    assert exc.value.status_code == 503
    assert exc.value.code == "CREDENTIALS_NOT_CONFIGURED"
    assert fake_engine.called is False


def test_position_rejects_non_btc_symbol_and_production_host(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    service = _service(tmp_path, env={"BINANCE_FUTURES_TESTNET_API_KEY": "key", "BINANCE_FUTURES_TESTNET_API_SECRET": "secret"})
    with pytest.raises(LiveControlPlaneHTTPError) as exc:
        service.position("ETHUSDT")
    assert exc.value.status_code == 400

    prod_config = BinanceFuturesTestnetReadOnlyConfig(rest_base_url="https://fapi.binance.com", allow_production_endpoint=True)
    _write_configs(tmp_path, read_only_config=prod_config)
    with pytest.raises(LiveControlPlaneHTTPError) as prod_exc:
        service.position("BTCUSDT")
    assert prod_exc.value.status_code == 403


def test_protective_state_no_journal_valid_journal_unresolved_and_malformed_are_read_only(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    service = _service(tmp_path)
    runtime = tmp_path / "data/runtime/binance_futures_testnet_protective_orders"
    result = service.protective_orders_current()
    assert result["state"] == "NONE"

    runtime.mkdir(parents=True, exist_ok=True)
    journal_path = runtime / "protective.json"
    active = BinanceFuturesTestnetProtectiveJournal(pair_id="pair-001", stop_client_algo_id="smcbot-protect-sl-001", take_profit_client_algo_id="smcbot-protect-tp-001", phase="PRECHECK_STARTED", recovery_required=False, baseline_available=True, baseline_position_amount="0.001", baseline_position_direction="LONG", stop_trigger="45000", take_profit_trigger="55000", entries=[], mutation_intents=[])
    journal_path.write_text(json.dumps(active.to_dict()), encoding="utf-8")
    before = journal_path.read_bytes()
    active_result = service.protective_orders_current()
    assert active_result["state"] == "ACTIVE"
    assert active_result["stop"]["client_algo_id"] == "smcbot-protect-sl-001"
    assert journal_path.read_bytes() == before

    data = active.to_dict()
    data["recovery_required"] = True
    data["phase"] = "RECOVERY_REQUIRED"
    journal_path.write_text(json.dumps(data), encoding="utf-8")
    unresolved = service.protective_orders_current()
    assert unresolved["state"] == "RECOVERY_REQUIRED"
    assert unresolved["recovery_required"] is True

    journal_path.write_bytes(b"{not-json")
    malformed_before = journal_path.read_bytes()
    malformed = service.protective_orders_current()
    assert malformed["state"] == "UNKNOWN"
    assert malformed["recovery_required"] is True
    assert journal_path.read_bytes() == malformed_before


def test_recovery_status_reports_required_state_without_invoking_recovery(tmp_path: Path) -> None:
    _write_configs(tmp_path)
    runtime = tmp_path / "data/runtime/binance_futures_testnet_protective_orders"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "protective.lock").write_text("locked", encoding="utf-8")
    journal = BinanceFuturesTestnetProtectiveJournal(pair_id="pair-001", stop_client_algo_id="smcbot-protect-sl-001", take_profit_client_algo_id="smcbot-protect-tp-001", phase="RECOVERY_REQUIRED", recovery_required=True, baseline_available=False, entries=[], mutation_intents=[])
    (runtime / "protective.json").write_text(json.dumps(journal.to_dict()), encoding="utf-8")
    service = _service(tmp_path)

    result = service.recovery_status()

    assert result["required"] is True
    assert result["pair_id"] == "pair-001"
    assert result["phase"] == "RECOVERY_REQUIRED"
    assert result["active_lock"] is True


def test_api_registers_only_approved_control_mutation_routes(client: TestClient) -> None:
    route_dump = json.dumps({path: sorted(methods) for path, methods in client.get("/openapi.json").json()["paths"].items() if path.startswith("/api/v1/live")})
    assert route_dump.count('"post"') == 3
    assert '"/api/v1/live/kill-switch/engage": ["post"]' in route_dump
    assert '"/api/v1/live/kill-switch/release": ["post"]' in route_dump
    assert '"/api/v1/live/recovery/run": ["post"]' in route_dump
    assert "put" not in route_dump
    assert "patch" not in route_dump
    assert "delete" not in route_dump
