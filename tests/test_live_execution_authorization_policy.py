from __future__ import annotations

from dataclasses import replace
import json
import logging
from pathlib import Path

import pytest

from infrastructure.observability.operational_metrics import OperationalCounterRegistry
from infrastructure.persistence import live_execution_authorization_policy as authorization_policy_module
from infrastructure.persistence.kill_switch_gate import KillSwitchGateError
from infrastructure.persistence.live_execution_authorization_policy import (
    SAFETY_DENIAL_COUNTER,
    LiveExecutionAuthorizationPolicy,
)
from infrastructure.persistence.kill_switch_persistence import KillSwitchPersistence
from models.live_execution_authorization import LiveExecutionAuthorizationContext, LiveExecutionOperation
from tests.kill_switch_test_support import durable_state_env


class _Gate:
    def __init__(self, code: str | None = None) -> None:
        self.code = code
        self.calls = 0

    def require_released(self) -> None:
        self.calls += 1
        if self.code:
            raise KillSwitchGateError(self.code)


class _Persistence:
    unresolved = False
    failure: Exception | None = None
    query_failure: Exception | None = None
    constructor_failure: Exception | None = None
    close_failure: Exception | None = None
    opens = 0
    closes = 0
    ensures = 0
    queries = 0

    def __init__(self, **kwargs) -> None:
        if self.constructor_failure:
            raise self.constructor_failure
        type(self).opens += 1

    def ensure_available(self) -> None:
        type(self).ensures += 1
        if self.failure:
            raise self.failure

    def has_unresolved_recovery(self, current_pair_id=None) -> bool:
        type(self).queries += 1
        if self.query_failure:
            raise self.query_failure
        if self.failure:
            raise self.failure
        return self.unresolved

    def close(self) -> None:
        type(self).closes += 1
        if self.close_failure:
            raise self.close_failure


@pytest.fixture(autouse=True)
def _reset_persistence() -> None:
    _Persistence.unresolved = False
    _Persistence.failure = None
    _Persistence.query_failure = None
    _Persistence.constructor_failure = None
    _Persistence.close_failure = None
    _Persistence.opens = 0
    _Persistence.closes = 0
    _Persistence.ensures = 0
    _Persistence.queries = 0


def _context(**overrides) -> LiveExecutionAuthorizationContext:
    values = {
        "operation": LiveExecutionOperation.PROTECTIVE_CREATE,
        "environment": "TESTNET",
        "symbol": "BTCUSDT",
        "live_trading_enabled": True,
        "dry_run": False,
        "confirmation_verified": True,
        "credentials_configured": True,
    }
    values.update(overrides)
    return LiveExecutionAuthorizationContext(**values)


def _policy(gate: _Gate | None = None) -> LiveExecutionAuthorizationPolicy:
    return LiveExecutionAuthorizationPolicy(
        env={},
        kill_switch_gate=gate or _Gate(),
        persistence_factory=_Persistence,
    )


def _policy_with_registry(registry: OperationalCounterRegistry) -> LiveExecutionAuthorizationPolicy:
    return LiveExecutionAuthorizationPolicy(
        env={},
        kill_switch_gate=_Gate(),
        persistence_factory=_Persistence,
        operational_counter_registry=registry,
    )


def _denial_records(caplog: pytest.LogCaptureFixture) -> list[dict]:
    records = []
    for record in caplog.records:
        if record.name == "ict_tradingbot.observability":
            records.append(json.loads(record.getMessage()))
    return records


@pytest.mark.parametrize("operation", list(LiveExecutionOperation))
def test_supported_operations_are_allowed(operation: LiveExecutionOperation) -> None:
    decision = _policy().evaluate(_context(operation=operation))
    assert decision.allowed is True
    assert decision.code == "AUTHORIZED"
    assert decision.operation == operation.value
    assert _Persistence.opens == _Persistence.closes == 2


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"environment": "PRODUCTION"}, "TESTNET_ONLY"),
        ({"symbol": "ETHUSDT"}, "BTCUSDT_ONLY"),
        ({"live_trading_enabled": False}, "LIVE_TRADING_DISABLED"),
        ({"dry_run": True}, "DRY_RUN_ACTIVE"),
        ({"confirmation_verified": False}, "CONFIRMATION_REQUIRED"),
        ({"credentials_configured": False}, "CREDENTIALS_UNAVAILABLE"),
    ],
)
def test_independent_policy_denials_are_deterministic(changes: dict, code: str) -> None:
    decision = _policy().evaluate(_context(**changes))
    assert decision.allowed is False
    assert decision.code == code
    assert "secret" not in decision.message.lower()


def test_safety_denial_emits_exact_structured_event_and_counter_once(caplog: pytest.LogCaptureFixture) -> None:
    registry = OperationalCounterRegistry()
    policy = _policy_with_registry(registry)
    caplog.set_level(logging.WARNING, logger="ict_tradingbot.observability")

    decision = policy.evaluate(_context(live_trading_enabled=False))

    assert decision.allowed is False
    assert decision.code == "LIVE_TRADING_DISABLED"
    assert registry.snapshot() == {SAFETY_DENIAL_COUNTER: 1}
    records = _denial_records(caplog)
    assert len(records) == 1
    record = records[0]
    assert record["event_name"] == "live_execution_authorization_denied"
    assert record["category"] == "safety_denial"
    assert record["severity"] == "WARNING"
    assert record["request_fingerprint"] is None
    assert record["context"] == {
        "decision_code": "LIVE_TRADING_DISABLED",
        "operation": LiveExecutionOperation.PROTECTIVE_CREATE.value,
        "policy_version": decision.policy_version,
    }
    assert set(record["context"]) == {"decision_code", "operation", "policy_version"}
    for prohibited in (
        "request_fingerprint",
        "permit_id",
        "order_id",
        "pair_id",
        "client_order_id",
        "correlation_id",
        "api_key",
        "api_secret",
        "signature",
        "authorization",
        "headers",
        "request_body",
        "sql",
        "traceback",
        "raw_exchange_response",
        "labels",
        "tags",
    ):
        assert prohibited not in record["context"]


def test_authorized_outcome_does_not_emit_denial_event_or_increment_counter(
    caplog: pytest.LogCaptureFixture,
) -> None:
    registry = OperationalCounterRegistry()
    policy = _policy_with_registry(registry)
    caplog.set_level(logging.WARNING, logger="ict_tradingbot.observability")

    decision = policy.evaluate(_context())

    assert decision.allowed is True
    assert decision.code == "AUTHORIZED"
    assert registry.snapshot() == {SAFETY_DENIAL_COUNTER: 0}
    assert _denial_records(caplog) == []


@pytest.mark.parametrize("failure_point", ["build", "emit", "register", "increment"])
def test_observability_failures_preserve_denial_decision(
    failure_point: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingRegistry:
        def register(self, name: str) -> None:
            if failure_point == "register":
                raise RuntimeError("signature=secret")

        def increment(self, name: str, amount: int = 1) -> int:
            if failure_point == "increment":
                raise RuntimeError("rawResponse secret")
            return amount

    if failure_point == "build":
        def fail_build(**kwargs):
            raise RuntimeError("postgresql://user:secret@host/db")

        monkeypatch.setattr(authorization_policy_module, "build_structured_record", fail_build)
    if failure_point == "emit":
        def fail_emit(record):
            raise RuntimeError("Authorization secret")

        monkeypatch.setattr(authorization_policy_module, "emit_structured_record", fail_emit)

    policy = LiveExecutionAuthorizationPolicy(
        env={},
        kill_switch_gate=_Gate(),
        persistence_factory=_Persistence,
        operational_counter_registry=FailingRegistry(),
    )

    decision = policy.evaluate(_context(live_trading_enabled=False))

    assert decision.allowed is False
    assert decision.code == "LIVE_TRADING_DISABLED"
    assert decision.operation == LiveExecutionOperation.PROTECTIVE_CREATE.value
    assert decision.message == LiveExecutionAuthorizationPolicy.SAFE_MESSAGES["LIVE_TRADING_DISABLED"]
    assert decision.policy_version == "1.0"


@pytest.mark.parametrize(
    "field,value",
    [
        ("live_trading_enabled", "true"),
        ("live_trading_enabled", 1),
        ("live_trading_enabled", None),
        ("dry_run", "false"),
        ("dry_run", 0),
        ("confirmation_verified", "true"),
        ("credentials_configured", 1),
    ],
)
def test_strict_boolean_violations_fail_closed(field: str, value: object) -> None:
    decision = _policy().evaluate(replace(_context(), **{field: value}))
    assert decision.allowed is False
    assert decision.code == "EXECUTION_POLICY_UNAVAILABLE"


def test_malformed_or_unknown_operation_fails_closed() -> None:
    assert _policy().evaluate(None).code == "EXECUTION_POLICY_UNAVAILABLE"
    malformed = replace(_context(), operation="ANY_MUTATION")
    assert _policy().evaluate(malformed).code == "UNSUPPORTED_EXECUTION_OPERATION"


@pytest.mark.parametrize(
    ("gate_code", "expected"),
    [
        ("KILL_SWITCH_ENGAGED", "KILL_SWITCH_ENGAGED"),
        ("KILL_SWITCH_STATE_UNAVAILABLE", "KILL_SWITCH_STATE_UNAVAILABLE"),
    ],
)
def test_durable_gate_denials_are_preserved(gate_code: str, expected: str) -> None:
    decision = _policy(_Gate(gate_code)).evaluate(_context())
    assert decision.allowed is False
    assert decision.code == expected


def test_unresolved_recovery_denies_fresh_mutation() -> None:
    _Persistence.unresolved = True
    decision = _policy().evaluate(_context())
    assert decision.allowed is False
    assert decision.code == "RECOVERY_REQUIRED"


@pytest.mark.parametrize("marker", ["postgresql://user:secret@", "connectionString", "SELECT * FROM", "traceback", "X-MBX-APIKEY", "signed-url", "rawResponse", "Authorization", "secret-token"])
def test_hostile_persistence_failures_are_sanitized(marker: str) -> None:
    _Persistence.failure = RuntimeError(marker)
    decision = _policy().evaluate(_context())
    rendered = str(decision.to_dict())
    assert decision.code == "PERSISTENCE_UNAVAILABLE"
    assert marker not in rendered
    assert _Persistence.opens == _Persistence.closes


def test_policy_evaluation_has_no_transport_or_mutation_side_effect_api() -> None:
    policy = _policy()
    decision = policy.evaluate(_context())
    assert decision.allowed
    assert not hasattr(policy, "authenticated_request")
    assert not hasattr(policy, "http_get")


def test_actual_policy_rechecks_runtime_state_instead_of_caching_allow() -> None:
    env = durable_state_env("RELEASED")
    policy = LiveExecutionAuthorizationPolicy(env=env)
    kwargs = dict(
        environment="TESTNET",
        symbol="BTCUSDT",
        confirmation_verified=True,
        credentials_configured=True,
    )

    assert policy.authorize(LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE, **kwargs).allowed
    runtime_path = Path(env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"])
    runtime_path.write_text(json.dumps({"live_trading_enabled": False, "dry_run": False}), encoding="utf-8")

    decision = policy.authorize(LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE, **kwargs)
    assert decision.allowed is False
    assert decision.code == "LIVE_TRADING_DISABLED"


def test_actual_policy_rechecks_durable_kill_switch_instead_of_caching_allow() -> None:
    env = durable_state_env("RELEASED")
    policy = LiveExecutionAuthorizationPolicy(env=env)
    kwargs = dict(
        environment="TESTNET",
        symbol="BTCUSDT",
        confirmation_verified=True,
        credentials_configured=True,
    )
    assert policy.authorize(LiveExecutionOperation.PROTECTIVE_CREATE, **kwargs).allowed

    persistence = KillSwitchPersistence(env=env)
    persistence.ensure_available()
    persistence.engage()
    persistence.close()

    decision = policy.authorize(LiveExecutionOperation.PROTECTIVE_CREATE, **kwargs)
    assert decision.allowed is False
    assert decision.code == "KILL_SWITCH_ENGAGED"


@pytest.mark.parametrize("marker", ["postgresql://user:secret@", "connectionString", "SELECT * FROM", "traceback", "X-MBX-APIKEY", "signed-url", "rawResponse", "Authorization", "secret-token"])
def test_hostile_runtime_provider_failures_are_sanitized(marker: str) -> None:
    class HostileRuntimeProvider:
        def load(self, config_path: str):
            raise RuntimeError(marker)

    policy = LiveExecutionAuthorizationPolicy(
        env={},
        runtime_provider=HostileRuntimeProvider(),
        kill_switch_gate=_Gate(),
        persistence_factory=_Persistence,
    )
    decision = policy.authorize(
        LiveExecutionOperation.PROTECTIVE_CREATE,
        environment="TESTNET",
        symbol="BTCUSDT",
        confirmation_verified=True,
        credentials_configured=True,
    )
    assert decision.code == "EXECUTION_POLICY_UNAVAILABLE"
    assert marker not in str(decision.to_dict())


@pytest.mark.parametrize("failure_point", ["factory", "ensure", "query", "close"])
def test_persistence_lifecycle_failures_are_contained_and_sanitized(failure_point: str) -> None:
    hostile = RuntimeError("postgresql://user:secret@host/db SELECT * FROM rawResponse")
    if failure_point == "factory":
        _Persistence.constructor_failure = hostile
    elif failure_point == "ensure":
        _Persistence.failure = hostile
    elif failure_point == "query":
        _Persistence.query_failure = hostile
    else:
        _Persistence.close_failure = hostile

    decision = _policy().evaluate(_context())

    assert decision.allowed is False
    assert decision.code == "PERSISTENCE_UNAVAILABLE"
    assert "secret" not in str(decision.to_dict()).lower()


def test_close_failure_after_otherwise_allowed_check_fails_closed() -> None:
    _Persistence.close_failure = RuntimeError("connectionString=secret")
    decision = _policy().evaluate(_context())
    assert decision.allowed is False
    assert decision.code == "PERSISTENCE_UNAVAILABLE"


def test_malformed_context_wins_before_unsupported_operation_and_providers() -> None:
    gate = _Gate("KILL_SWITCH_ENGAGED")
    context = replace(_context(), operation="ANY_MUTATION", dry_run="false")
    decision = _policy(gate).evaluate(context)
    assert decision.code == "EXECUTION_POLICY_UNAVAILABLE"
    assert gate.calls == 0
    assert _Persistence.opens == 0


@pytest.mark.parametrize(
    ("changes", "code", "persistence_calls", "gate_calls"),
    [
        ({"operation": "ANY_MUTATION", "environment": "PRODUCTION"}, "UNSUPPORTED_EXECUTION_OPERATION", 0, 0),
        ({"environment": "PRODUCTION", "symbol": "ETHUSDT"}, "TESTNET_ONLY", 0, 0),
        ({"symbol": "ETHUSDT"}, "BTCUSDT_ONLY", 0, 0),
    ],
)
def test_scope_and_operation_denials_short_circuit_later_providers(
    changes: dict,
    code: str,
    persistence_calls: int,
    gate_calls: int,
) -> None:
    gate = _Gate("KILL_SWITCH_ENGAGED")
    decision = _policy(gate).evaluate(replace(_context(), **changes))
    assert decision.code == code
    assert _Persistence.opens == persistence_calls
    assert gate.calls == gate_calls


def test_deterministic_first_denial_order_for_combined_failures() -> None:
    _Persistence.unresolved = True
    engaged = _Gate("KILL_SWITCH_ENGAGED")
    decision = _policy(engaged).evaluate(_context(live_trading_enabled=False, dry_run=True))
    assert decision.code == "KILL_SWITCH_ENGAGED"

    _Persistence.unresolved = True
    decision = _policy().evaluate(_context(live_trading_enabled=False, dry_run=True))
    assert decision.code == "RECOVERY_REQUIRED"

    _Persistence.unresolved = False
    decision = _policy().evaluate(
        _context(live_trading_enabled=False, dry_run=True, confirmation_verified=False, credentials_configured=False)
    )
    assert decision.code == "LIVE_TRADING_DISABLED"

    decision = _policy().evaluate(_context(dry_run=True, confirmation_verified=False, credentials_configured=False))
    assert decision.code == "DRY_RUN_ACTIVE"

    decision = _policy().evaluate(_context(confirmation_verified=False, credentials_configured=False))
    assert decision.code == "CONFIRMATION_REQUIRED"


@pytest.mark.parametrize(
    (
        "case",
        "expected",
        "expected_factory",
        "expected_ensure",
        "expected_close",
        "expected_gate",
        "expected_queries",
        "expected_runtime",
    ),
    [
        ("malformed_unsupported", "EXECUTION_POLICY_UNAVAILABLE", 0, 0, 0, 0, 0, 0),
        ("unsupported_environment", "UNSUPPORTED_EXECUTION_OPERATION", 0, 0, 0, 0, 0, 0),
        ("environment_persistence", "TESTNET_ONLY", 0, 0, 0, 0, 0, 0),
        ("symbol_persistence", "BTCUSDT_ONLY", 0, 0, 0, 0, 0, 0),
        ("persistence_kill", "PERSISTENCE_UNAVAILABLE", 1, 1, 1, 0, 0, 0),
        ("kill_recovery", "KILL_SWITCH_ENGAGED", 1, 1, 1, 1, 0, 0),
        ("recovery_live", "RECOVERY_REQUIRED", 2, 2, 2, 1, 1, 0),
        ("live_dry", "LIVE_TRADING_DISABLED", 2, 2, 2, 1, 1, 1),
        ("dry_confirmation", "DRY_RUN_ACTIVE", 2, 2, 2, 1, 1, 1),
        ("confirmation_credentials", "CONFIRMATION_REQUIRED", 2, 2, 2, 1, 1, 1),
    ],
)
def test_complete_combined_denial_precedence_and_provider_short_circuit(
    case: str,
    expected: str,
    expected_factory: int,
    expected_ensure: int,
    expected_close: int,
    expected_gate: int,
    expected_queries: int,
    expected_runtime: int,
) -> None:
    class RuntimeSpy:
        calls = 0

        def load(self, config_path: str):
            type(self).calls += 1
            if case == "live_dry":
                return False, True
            if case == "dry_confirmation":
                return True, True
            return True, False

    gate = _Gate("KILL_SWITCH_ENGAGED" if case in {"persistence_kill", "kill_recovery"} else None)
    if case in {"environment_persistence", "symbol_persistence", "persistence_kill"}:
        _Persistence.failure = RuntimeError("unavailable")
    if case in {"kill_recovery", "recovery_live"}:
        _Persistence.unresolved = True
    operation: object = "ANY_MUTATION" if case in {"malformed_unsupported", "unsupported_environment"} else LiveExecutionOperation.PROTECTIVE_CREATE
    environment = "PRODUCTION" if case in {"unsupported_environment", "environment_persistence"} else "TESTNET"
    symbol = "ETHUSDT" if case == "symbol_persistence" else "BTCUSDT"
    confirmation: object = False if case in {"dry_confirmation", "confirmation_credentials"} else True
    credentials: object = False if case == "confirmation_credentials" else True
    if case == "malformed_unsupported":
        credentials = "false"
    runtime = RuntimeSpy()
    policy = LiveExecutionAuthorizationPolicy(
        env={}, runtime_provider=runtime, kill_switch_gate=gate, persistence_factory=_Persistence
    )

    decision = policy.authorize(
        operation,
        environment=environment,
        symbol=symbol,
        confirmation_verified=confirmation,
        credentials_configured=credentials,
    )

    assert decision.code == expected
    assert _Persistence.opens == expected_factory
    assert _Persistence.ensures == expected_ensure
    assert _Persistence.closes == expected_close
    assert gate.calls == expected_gate
    assert _Persistence.queries == expected_queries
    assert runtime.calls == expected_runtime
