from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.live_control_plane_routes import get_operator_status_service
from api.operator_status_service import OperatorStatusService


SECRET_MARKERS = (
    "unit-test-secret",
    "rawResponse",
    "traceback",
    "SELECT * FROM",
    "postgresql://",
    "X-MBX-APIKEY",
    "signed-url",
    "signature",
)


class MutatingDependency:
    def __init__(self) -> None:
        self.mutations: list[str] = []

    def engage(self):
        self.mutations.append("engage")
        raise AssertionError("mutation path must not be called")

    def release(self):
        self.mutations.append("release")
        raise AssertionError("mutation path must not be called")

    def run(self):
        self.mutations.append("run")
        raise AssertionError("mutation path must not be called")

    def issue(self):
        self.mutations.append("issue")
        raise AssertionError("permit mutation path must not be called")

    def consume(self):
        self.mutations.append("consume")
        raise AssertionError("permit mutation path must not be called")

    def revoke(self):
        self.mutations.append("revoke")
        raise AssertionError("permit mutation path must not be called")


class FakeLiveService(MutatingDependency):
    def __init__(
        self,
        *,
        environment: str = "BINANCE_FUTURES_TESTNET",
        symbol: str = "BTCUSDT",
        recovery_required: bool = False,
        recovery_available: bool = True,
        readiness_status: str = "READY",
        validation_gate: str = "PASS",
        active_lock: bool = False,
        safety_available: bool = True,
        readiness_available: bool = True,
    ) -> None:
        super().__init__()
        self.environment = environment
        self.symbol = symbol
        self._recovery_required = recovery_required
        self._recovery_available = recovery_available
        self._readiness_status = readiness_status
        self._validation_gate = validation_gate
        self._active_lock = active_lock
        self._safety_available = safety_available
        self._readiness_available = readiness_available

    def safety_status(self):
        if not self._safety_available:
            raise RuntimeError("postgresql://unit-test-secret SELECT * FROM rawResponse traceback")
        return {
            "environment": self.environment,
            "symbol": self.symbol,
            "live_trading_enabled": False,
            "automatic_execution_enabled": False,
            "kill_switch_engaged": True,
            "credentials_configured": False,
            "active_lock": self._active_lock,
            "recovery_required": self._recovery_required,
            "production_endpoint_allowed": self.environment != "BINANCE_FUTURES_TESTNET",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

    def recovery_status(self):
        if not self._recovery_available:
            raise RuntimeError("X-MBX-APIKEY unit-test-secret signed-url")
        return {
            "required": self._recovery_required,
            "reason": "SECRET_DETAIL_SHOULD_NOT_LEAK" if self._recovery_required else None,
            "pair_id": "pair-secret" if self._recovery_required else None,
            "phase": "RECOVERY_REQUIRED" if self._recovery_required else None,
            "active_lock": self._active_lock,
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

    def readiness(self):
        if not self._readiness_available:
            raise RuntimeError("traceback unit-test-secret signed-url")
        return {
            "status": self._readiness_status,
            "symbol": self.symbol,
            "checks_passed": 1,
            "checks_warning": 0,
            "checks_failed": 0 if self._readiness_status == "READY" else 1,
            "validation_gate": self._validation_gate,
            "blocking_reasons": ["rawResponse SECRET_DETAIL_SHOULD_NOT_LEAK"],
            "updated_at": "2026-01-01T00:00:00+00:00",
        }


class PayloadLiveService(FakeLiveService):
    def __init__(self, *, safety_payload: Any = None, recovery_payload: Any = None, readiness_payload: Any = None) -> None:
        super().__init__()
        self.safety_payload = safety_payload
        self.recovery_payload = recovery_payload
        self.readiness_payload = readiness_payload

    def safety_status(self):
        if self.safety_payload is not None:
            return self.safety_payload
        return super().safety_status()

    def recovery_status(self):
        if self.recovery_payload is not None:
            return self.recovery_payload
        return super().recovery_status()

    def readiness(self):
        if self.readiness_payload is not None:
            return self.readiness_payload
        return super().readiness()


class FakeKillSwitchService(MutatingDependency):
    def __init__(self, *, state: str = "RELEASED", available: bool = True) -> None:
        super().__init__()
        self.state = state
        self.available = available

    def status(self):
        if not self.available:
            raise RuntimeError("databaseUrl unit-test-secret SELECT * FROM")
        return {
            "accepted": True,
            "environment": "BINANCE_FUTURES_TESTNET",
            "symbol": "BTCUSDT",
            "state": self.state,
            "changed": False,
            "version": 1,
            "updated_at": "2026-01-01T00:00:00+00:00",
            "blocking_code": None,
        }


class PayloadKillSwitchService(FakeKillSwitchService):
    def __init__(self, payload: Any) -> None:
        super().__init__()
        self.payload = payload

    def status(self):
        return self.payload


class FakePersistenceService(MutatingDependency):
    def __init__(self, *, configured: bool = True, reachable: bool = True, schema_ready: bool = True, available: bool = True) -> None:
        super().__init__()
        self.configured = configured
        self.reachable = reachable
        self.schema_ready = schema_ready
        self.available = available

    def status(self):
        if not self.available:
            raise RuntimeError("connectionString unit-test-secret rawResponse")
        return {
            "configured": self.configured,
            "reachable": self.reachable,
            "schema_ready": self.schema_ready,
            "migration_revision": "000000000000" if self.schema_ready else None,
            "read_only": True,
            "source_of_truth": False,
            "updated_at": "2026-01-01T00:00:00+00:00",
        }


class PayloadPersistenceService(FakePersistenceService):
    def __init__(self, payload: Any) -> None:
        super().__init__()
        self.payload = payload

    def status(self):
        return self.payload


@dataclass
class ServiceBundle:
    live: FakeLiveService
    kill_switch: FakeKillSwitchService
    persistence: FakePersistenceService

    def operator(self) -> OperatorStatusService:
        return OperatorStatusService(
            live_service=self.live,
            kill_switch_service=self.kill_switch,
            persistence_service=self.persistence,
        )


def _bundle(
    *,
    live: FakeLiveService | None = None,
    kill_switch: FakeKillSwitchService | None = None,
    persistence: FakePersistenceService | None = None,
) -> ServiceBundle:
    return ServiceBundle(
        live=live or FakeLiveService(),
        kill_switch=kill_switch or FakeKillSwitchService(),
        persistence=persistence or FakePersistenceService(),
    )


def _status(**kwargs) -> dict[str, Any]:
    return _bundle(**kwargs).operator().status()


def _valid_safety_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "environment": "BINANCE_FUTURES_TESTNET",
        "symbol": "BTCUSDT",
        "active_lock": False,
        "production_endpoint_allowed": False,
        "automatic_execution_enabled": False,
    }
    payload.update(overrides)
    return payload


def _assert_no_sensitive_payload(payload: dict[str, Any]) -> None:
    body = json.dumps(payload)
    lower = body.lower()
    for marker in SECRET_MARKERS:
        assert marker not in body
        assert marker.lower() not in lower
    assert "SECRET_DETAIL_SHOULD_NOT_LEAK" not in body


def test_operator_status_ready_aggregate_returns_ready() -> None:
    assert FakeLiveService().safety_status()["symbol"] == "BTCUSDT"

    result = _status()

    assert result["overall_status"] == "READY"
    assert result["environment"] == "BINANCE_FUTURES_TESTNET"
    assert result["symbol"] == "BTCUSDT"
    assert result["kill_switch_state"] == "RELEASED"
    assert result["kill_switch_available"] is True
    assert result["recovery_required"] is False
    assert result["recovery_available"] is True
    assert result["persistence_configured"] is True
    assert result["persistence_reachable"] is True
    assert result["persistence_schema_ready"] is True
    assert result["readiness_status"] == "READY"
    assert result["validation_gate"] == "PASS"
    assert result["active_lock"] is False
    assert result["warnings"] == []
    assert result["updated_at"].endswith("+00:00")


def test_operator_status_kill_switch_not_released_returns_blocked() -> None:
    result = _status(kill_switch=FakeKillSwitchService(state="ENGAGED"))

    assert result["overall_status"] == "BLOCKED"
    assert result["warnings"] == [
        {
            "code": "KILL_SWITCH_NOT_RELEASED",
            "severity": "BLOCKING",
            "message": "Kill switch is not released.",
            "source": "kill_switch",
        }
    ]


def test_operator_status_kill_switch_unavailable_returns_unavailable() -> None:
    result = _status(kill_switch=FakeKillSwitchService(available=False))

    assert result["overall_status"] == "UNAVAILABLE"
    assert result["kill_switch_available"] is False
    assert result["warnings"][0]["code"] == "KILL_SWITCH_UNAVAILABLE"
    _assert_no_sensitive_payload(result)


def test_operator_status_recovery_required_returns_blocked() -> None:
    result = _status(live=FakeLiveService(recovery_required=True))

    assert result["overall_status"] == "BLOCKED"
    assert result["recovery_required"] is True
    assert any(warning["code"] == "RECOVERY_REQUIRED" for warning in result["warnings"])
    _assert_no_sensitive_payload(result)


def test_operator_status_recovery_unavailable_returns_unavailable() -> None:
    result = _status(live=FakeLiveService(recovery_available=False))

    assert result["overall_status"] == "UNAVAILABLE"
    assert result["recovery_available"] is False
    assert any(warning["code"] == "RECOVERY_STATUS_UNAVAILABLE" for warning in result["warnings"])
    _assert_no_sensitive_payload(result)


def test_operator_status_persistence_unconfigured_does_not_return_ready() -> None:
    result = _status(persistence=FakePersistenceService(configured=False, reachable=False, schema_ready=False))

    assert result["overall_status"] == "BLOCKED"
    assert any(warning["code"] == "PERSISTENCE_UNCONFIGURED" for warning in result["warnings"])


def test_operator_status_persistence_unreachable_returns_unavailable() -> None:
    result = _status(persistence=FakePersistenceService(configured=True, reachable=False, schema_ready=False))

    assert result["overall_status"] == "UNAVAILABLE"
    assert any(warning["code"] == "PERSISTENCE_UNAVAILABLE" for warning in result["warnings"])


def test_operator_status_schema_not_ready_never_returns_ready() -> None:
    result = _status(persistence=FakePersistenceService(configured=True, reachable=True, schema_ready=False))

    assert result["overall_status"] == "BLOCKED"
    assert any(warning["code"] == "PERSISTENCE_SCHEMA_NOT_READY" for warning in result["warnings"])


def test_operator_status_readiness_not_ready_returns_blocked() -> None:
    result = _status(live=FakeLiveService(readiness_status="BLOCKED"))

    assert result["overall_status"] == "BLOCKED"
    assert any(warning["code"] == "READINESS_NOT_READY" for warning in result["warnings"])


def test_operator_status_validation_gate_not_pass_returns_blocked() -> None:
    result = _status(live=FakeLiveService(validation_gate="FAIL"))

    assert result["overall_status"] == "BLOCKED"
    assert any(warning["code"] == "VALIDATION_GATE_NOT_PASS" for warning in result["warnings"])


def test_operator_status_active_lock_returns_blocked() -> None:
    result = _status(live=FakeLiveService(active_lock=True))

    assert result["overall_status"] == "BLOCKED"
    assert result["active_lock"] is True
    assert any(warning["code"] == "ACTIVE_LOCK_PRESENT" for warning in result["warnings"])


def test_operator_status_multiple_warnings_are_deterministic_and_unique() -> None:
    result = _status(
        live=FakeLiveService(recovery_required=True, active_lock=True, readiness_status="BLOCKED", validation_gate="FAIL"),
        kill_switch=FakeKillSwitchService(state="ENGAGED"),
        persistence=FakePersistenceService(configured=True, reachable=True, schema_ready=False),
    )

    warning_pairs = [(warning["code"], warning["source"]) for warning in result["warnings"]]
    assert warning_pairs == [
        ("KILL_SWITCH_NOT_RELEASED", "kill_switch"),
        ("RECOVERY_REQUIRED", "recovery"),
        ("PERSISTENCE_SCHEMA_NOT_READY", "persistence"),
        ("READINESS_NOT_READY", "readiness"),
        ("VALIDATION_GATE_NOT_PASS", "readiness"),
        ("ACTIVE_LOCK_PRESENT", "lock"),
    ]
    assert len(warning_pairs) == len(set(warning_pairs))


def test_operator_status_unexpected_service_exception_is_sanitized_unavailable() -> None:
    result = _status(live=FakeLiveService(safety_available=False, readiness_available=False))

    assert result["overall_status"] == "UNAVAILABLE"
    assert any(warning["code"] == "OPERATOR_STATUS_UNAVAILABLE" for warning in result["warnings"])
    _assert_no_sensitive_payload(result)


def test_operator_status_scope_violations_cannot_return_ready() -> None:
    production = _status(live=FakeLiveService(environment="BINANCE_PRODUCTION"))
    non_btc = _status(live=FakeLiveService(symbol="ETHUSDT"))

    assert production["overall_status"] == "UNAVAILABLE"
    assert any(warning["code"] == "OPERATOR_STATUS_UNAVAILABLE" for warning in production["warnings"])
    assert non_btc["overall_status"] == "UNAVAILABLE"
    assert any(warning["code"] == "OPERATOR_STATUS_UNAVAILABLE" for warning in non_btc["warnings"])


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        ("rawResponse unit-test-secret", "OPERATOR_STATUS_UNAVAILABLE"),
        (_valid_safety_payload(active_lock="false"), "OPERATOR_STATUS_UNAVAILABLE"),
    ],
)
def test_operator_status_malformed_safety_payloads_return_unavailable(payload: Any, expected_code: str) -> None:
    result = _status(live=PayloadLiveService(safety_payload=payload))

    assert result["overall_status"] == "UNAVAILABLE"
    assert any(warning["code"] == expected_code and warning["source"] == "safety" for warning in result["warnings"])
    _assert_no_sensitive_payload(result)


@pytest.mark.parametrize(
    "payload",
    [
        "databaseUrl unit-test-secret",
        {"environment": "BINANCE_FUTURES_TESTNET", "symbol": "BTCUSDT"},
        {"environment": "BINANCE_FUTURES_TESTNET", "symbol": "BTCUSDT", "state": "DISABLED"},
    ],
)
def test_operator_status_malformed_kill_switch_payloads_return_unavailable(payload: Any) -> None:
    result = _status(kill_switch=PayloadKillSwitchService(payload))

    assert result["overall_status"] == "UNAVAILABLE"
    assert result["kill_switch_available"] is False
    assert any(warning["code"] == "KILL_SWITCH_UNAVAILABLE" and warning["source"] == "kill_switch" for warning in result["warnings"])
    _assert_no_sensitive_payload(result)


@pytest.mark.parametrize(
    "payload",
    [
        "X-MBX-APIKEY unit-test-secret",
        {"required": "false", "active_lock": False},
    ],
)
def test_operator_status_malformed_recovery_payloads_return_unavailable(payload: Any) -> None:
    result = _status(live=PayloadLiveService(recovery_payload=payload))

    assert result["overall_status"] == "UNAVAILABLE"
    assert result["recovery_available"] is False
    assert any(warning["code"] == "RECOVERY_STATUS_UNAVAILABLE" and warning["source"] == "recovery" for warning in result["warnings"])
    _assert_no_sensitive_payload(result)


@pytest.mark.parametrize(
    "payload",
    [
        "connectionString unit-test-secret",
        {"configured": "false", "reachable": False, "schema_ready": False},
        {"configured": True, "reachable": 1, "schema_ready": False},
        {"configured": True, "reachable": True, "schema_ready": []},
    ],
)
def test_operator_status_malformed_persistence_payloads_return_unavailable(payload: Any) -> None:
    result = _status(persistence=PayloadPersistenceService(payload))

    assert result["overall_status"] == "UNAVAILABLE"
    assert result["persistence_configured"] is False
    assert result["persistence_reachable"] is False
    assert result["persistence_schema_ready"] is False
    assert any(warning["code"] == "PERSISTENCE_UNAVAILABLE" and warning["source"] == "persistence" for warning in result["warnings"])
    _assert_no_sensitive_payload(result)


@pytest.mark.parametrize(
    "payload",
    [
        "traceback unit-test-secret",
        {"status": "MAYBE", "symbol": "BTCUSDT", "validation_gate": "PASS"},
        {"status": "READY", "symbol": "BTCUSDT", "validation_gate": "MAYBE"},
    ],
)
def test_operator_status_malformed_readiness_payloads_return_unavailable(payload: Any) -> None:
    result = _status(live=PayloadLiveService(readiness_payload=payload))

    assert result["overall_status"] == "UNAVAILABLE"
    assert any(warning["code"] == "OPERATOR_STATUS_UNAVAILABLE" and warning["source"] == "readiness" for warning in result["warnings"])
    _assert_no_sensitive_payload(result)


@pytest.mark.parametrize(
    "payload",
    [
        _valid_safety_payload(symbol=None),
        _valid_safety_payload(symbol=""),
        _valid_safety_payload(symbol="ETHUSDT"),
        _valid_safety_payload(symbol="btcusdt"),
        _valid_safety_payload(symbol=0),
        _valid_safety_payload(symbol=True),
        _valid_safety_payload(symbol=[]),
        _valid_safety_payload(symbol={}),
        _valid_safety_payload(symbol=object()),
        _valid_safety_payload(symbol="ETHUSDT rawResponse unit-test-secret SELECT * FROM postgresql:// signed-url traceback"),
        {
            "environment": "BINANCE_FUTURES_TESTNET",
            "active_lock": True,
            "production_endpoint_allowed": True,
            "automatic_execution_enabled": True,
        },
    ],
)
def test_operator_status_malformed_safety_symbol_returns_unavailable_without_authoritative_values(payload: Any) -> None:
    result = _status(live=PayloadLiveService(safety_payload=payload))

    assert result["overall_status"] == "UNAVAILABLE"
    assert result["overall_status"] != "READY"
    assert result["overall_status"] != "BLOCKED"
    assert result["active_lock"] is False
    assert any(warning["code"] == "OPERATOR_STATUS_UNAVAILABLE" and warning["source"] == "safety" for warning in result["warnings"])
    assert all(warning["code"] != "ACTIVE_LOCK_PRESENT" for warning in result["warnings"])
    assert all(warning["code"] != "ENVIRONMENT_NOT_TESTNET" for warning in result["warnings"])
    _assert_no_sensitive_payload(result)


def test_operator_status_valid_authoritative_unsafe_values_still_block() -> None:
    result = _status(
        live=FakeLiveService(recovery_required=True, active_lock=True, readiness_status="WARNING", validation_gate="WARNING"),
        kill_switch=FakeKillSwitchService(state="ENGAGED"),
        persistence=FakePersistenceService(configured=False, reachable=False, schema_ready=False),
    )

    assert result["overall_status"] == "BLOCKED"
    assert [warning["code"] for warning in result["warnings"]] == [
        "KILL_SWITCH_NOT_RELEASED",
        "RECOVERY_REQUIRED",
        "PERSISTENCE_UNCONFIGURED",
        "READINESS_NOT_READY",
        "VALIDATION_GATE_NOT_PASS",
        "ACTIVE_LOCK_PRESENT",
    ]


def test_operator_status_route_get_only_and_performs_no_mutation_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "BINANCE_FUTURES_TESTNET_API_KEY",
        "BINANCE_FUTURES_TESTNET_API_SECRET",
        "ICT_DATABASE_URL",
        "DATABASE_URL",
        "ICT_LIVE_EXECUTION_RUNTIME_CONFIG",
    ):
        monkeypatch.delenv(name, raising=False)
    bundle = _bundle()
    service = bundle.operator()
    app = create_app()
    app.dependency_overrides[get_operator_status_service] = lambda: service
    client = TestClient(app)

    response = client.get("/api/v1/live/operator/status")

    assert response.status_code == 200
    assert response.json()["overall_status"] == "READY"
    assert bundle.live.mutations == []
    assert bundle.kill_switch.mutations == []
    assert bundle.persistence.mutations == []
    for method in (client.post, client.put, client.patch, client.delete):
        assert method("/api/v1/live/operator/status").status_code == 405


def test_operator_status_route_sanitizes_unexpected_top_level_exception() -> None:
    class BrokenOperatorStatusService:
        def status(self):
            raise RuntimeError("postgresql://unit-test-secret rawResponse traceback X-MBX-APIKEY")

    app = create_app()
    app.dependency_overrides[get_operator_status_service] = lambda: BrokenOperatorStatusService()
    client = TestClient(app)

    response = client.get("/api/v1/live/operator/status")

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "OPERATOR_STATUS_UNAVAILABLE",
        "message": "Operator status is unavailable.",
        "details": {},
    }
    body = json.dumps(response.json())
    for marker in SECRET_MARKERS:
        assert marker.lower() not in body.lower()
