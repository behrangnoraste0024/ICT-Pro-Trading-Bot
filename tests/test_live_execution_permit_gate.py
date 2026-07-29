from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest

from infrastructure.persistence.live_execution_permit_persistence import (
    ISSUE_CONFIRMATION,
    LiveExecutionPermitPersistence,
    LiveExecutionPermitPersistenceError,
)
from infrastructure.security.live_execution_permit_gate import LiveExecutionPermitGate
from infrastructure.security.live_execution_request_fingerprint import (
    LiveExecutionRequestFingerprint,
    build_live_execution_request_fingerprint,
)
from models.live_execution_authorization import LiveExecutionAuthorizationDecision, LiveExecutionOperation
from models.live_execution_permit import LiveExecutionPermit, LiveExecutionPermitState, utc_now
from models.live_execution_permit_enforcement import LiveExecutionPermitGateError, LiveExecutionPermitReference
from tests.kill_switch_test_support import durable_state_env

CORRELATION_ID = UUID("11111111-1111-4111-8111-111111111111")


def _fingerprint(subject: str = "order-001"):
    return build_live_execution_request_fingerprint(
        {
            "schema_version": "1.0",
            "operation": "ORDER_LIFECYCLE_CANCEL",
            "environment": "TESTNET",
            "symbol": "BTCUSDT",
            "client_order_id": subject,
        }
    )


def _issue(env: dict[str, str], fingerprint=None):
    svc = LiveExecutionPermitPersistence(env=env)
    svc.ensure_available()
    try:
        return svc.issue(
            fingerprint or _fingerprint(),
            ttl_seconds=300,
            issued_by="operator-1",
            confirmation=ISSUE_CONFIRMATION,
        )
    finally:
        svc.close()


def _show(env: dict[str, str], permit_id: str):
    svc = LiveExecutionPermitPersistence(env=env)
    svc.ensure_available()
    try:
        permit, _ = svc.show(permit_id)
        return permit
    finally:
        svc.close()


def test_gate_consumes_exact_issued_permit_once() -> None:
    env = durable_state_env("RELEASED")
    fingerprint = _fingerprint()
    permit = _issue(env, fingerprint)
    gate = LiveExecutionPermitGate(env=env, correlation_id_provider=lambda: CORRELATION_ID)

    receipt = gate.authorize_and_consume(
        operation=LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL,
        fingerprint=fingerprint,
        permit_reference=LiveExecutionPermitReference(permit.permit_id, permit.version),
        confirmation_verified=True,
        credentials_configured=True,
        runtime_config_path=env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
    )

    assert receipt.permit_id == permit.permit_id
    assert receipt.previous_version == 1
    assert receipt.consumed_version == 2
    assert receipt.consumption_correlation_id == CORRELATION_ID
    stored = _show(env, permit.permit_id)
    assert stored.state == LiveExecutionPermitState.CONSUMED
    assert stored.version == 2


def test_gate_requires_reference_before_authorization_or_persistence() -> None:
    class ForbiddenPolicy:
        def authorize(self, *args, **kwargs):
            raise AssertionError("authorization should not run without a permit reference")

    def forbidden_factory(*args, **kwargs):
        raise AssertionError("persistence should not open without a permit reference")

    gate = LiveExecutionPermitGate(authorization_policy=ForbiddenPolicy(), permit_persistence_factory=forbidden_factory, env={})

    with pytest.raises(LiveExecutionPermitGateError) as exc:
        gate.authorize_and_consume(
            operation=LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL,
            fingerprint=_fingerprint(),
            permit_reference=None,
            confirmation_verified=True,
            credentials_configured=True,
            runtime_config_path="configs/btc_paper_runtime.json",
        )

    assert exc.value.code == "PERMIT_REQUIRED"


def test_gate_authorization_denial_happens_before_persistence() -> None:
    env = durable_state_env("ENGAGED")

    def forbidden_factory(*args, **kwargs):
        raise AssertionError("persistence should not open when authorization blocks")

    gate = LiveExecutionPermitGate(env=env, permit_persistence_factory=forbidden_factory)

    with pytest.raises(LiveExecutionPermitGateError) as exc:
        gate.authorize_and_consume(
            operation=LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL,
            fingerprint=_fingerprint(),
            permit_reference=LiveExecutionPermitReference("permit-" + "a" * 32, 1),
            confirmation_verified=True,
            credentials_configured=True,
            runtime_config_path=env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
        )

    assert exc.value.code == "KILL_SWITCH_ENGAGED"


def test_gate_rejects_fingerprint_mismatch_without_consuming_permit() -> None:
    env = durable_state_env("RELEASED")
    issued_fingerprint = build_live_execution_request_fingerprint(
        {
            "schema_version": "1.0",
            "operation": "ORDER_LIFECYCLE_CREATE",
            "environment": "TESTNET",
            "symbol": "BTCUSDT",
            "client_order_id": "order-001",
            "side": "BUY",
            "position_side": "BOTH",
            "order_type": "LIMIT",
            "quantity": "0.001",
            "price": "50000",
            "time_in_force": "GTX",
            "reduce_only": False,
        }
    )
    requested_fingerprint = build_live_execution_request_fingerprint(
        {
            "schema_version": "1.0",
            "operation": "ORDER_LIFECYCLE_CREATE",
            "environment": "TESTNET",
            "symbol": "BTCUSDT",
            "client_order_id": "order-001",
            "side": "BUY",
            "position_side": "BOTH",
            "order_type": "LIMIT",
            "quantity": "0.001",
            "price": "50100",
            "time_in_force": "GTX",
            "reduce_only": False,
        }
    )
    permit = _issue(env, issued_fingerprint)
    gate = LiveExecutionPermitGate(env=env, correlation_id_provider=lambda: CORRELATION_ID)

    with pytest.raises(LiveExecutionPermitGateError) as exc:
        gate.authorize_and_consume(
            operation=LiveExecutionOperation.ORDER_LIFECYCLE_CREATE,
            fingerprint=requested_fingerprint,
            permit_reference=LiveExecutionPermitReference(permit.permit_id, permit.version),
            confirmation_verified=True,
            credentials_configured=True,
            runtime_config_path=env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
        )

    assert exc.value.code == "PERMIT_FINGERPRINT_MISMATCH"
    assert _show(env, permit.permit_id).state == LiveExecutionPermitState.ISSUED


def test_gate_rejects_reuse_after_successful_consumption() -> None:
    env = durable_state_env("RELEASED")
    fingerprint = _fingerprint()
    permit = _issue(env, fingerprint)
    gate = LiveExecutionPermitGate(env=env, correlation_id_provider=lambda: CORRELATION_ID)
    reference = LiveExecutionPermitReference(permit.permit_id, permit.version)

    gate.authorize_and_consume(
        operation=LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL,
        fingerprint=fingerprint,
        permit_reference=reference,
        confirmation_verified=True,
        credentials_configured=True,
        runtime_config_path=env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
    )

    with pytest.raises(LiveExecutionPermitGateError) as exc:
        gate.authorize_and_consume(
            operation=LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL,
            fingerprint=fingerprint,
            permit_reference=reference,
            confirmation_verified=True,
            credentials_configured=True,
            runtime_config_path=env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
        )

    assert exc.value.code == "PERMIT_ALREADY_CONSUMED"

GATE_PROVIDER_COUNTER_ROW_IDS = (
    "01_success",
    "02_missing_reference",
    "03_reference_wrong_type",
    "04_malformed_permit_id",
    "05_expected_version_bool",
    "06_expected_version_zero",
    "07_expected_version_negative",
    "08_invalid_fingerprint_object",
    "09_fingerprint_operation_mismatch",
    "10_fingerprint_environment_mismatch",
    "11_fingerprint_symbol_mismatch",
    "12_policy_confirmation_denied",
    "13_policy_credentials_denied",
    "14_persistence_factory_failure",
    "15_persistence_ensure_failure",
    "16_correlation_provider_failure",
    "17_correlation_provider_malformed_value",
    "18_consume_failure",
    "19_returned_permit_id_mismatch",
    "20_returned_operation_mismatch",
    "21_returned_environment_mismatch",
    "22_returned_symbol_mismatch",
    "23_returned_subject_type_mismatch",
    "24_returned_subject_id_mismatch",
    "25_returned_fingerprint_mismatch",
    "26_returned_correlation_mismatch",
    "27_returned_version_mismatch",
    "28_returned_state_or_consumed_record_invalid",
    "29_close_failure_after_consumption",
)


class _CountedPolicy:
    def __init__(self, counters: dict[str, int], events: list[str], denial_code: str | None = None) -> None:
        self._counters = counters
        self._events = events
        self._denial_code = denial_code

    def authorize(self, operation: LiveExecutionOperation, **kwargs: Any) -> LiveExecutionAuthorizationDecision:
        self._counters["policy_calls"] += 1
        self._events.append("policy")
        if self._denial_code is not None:
            return LiveExecutionAuthorizationDecision(False, self._denial_code, operation.value)
        return LiveExecutionAuthorizationDecision(True, "AUTHORIZED", operation.value)


class _CountedPersistence:
    def __init__(self, case: dict[str, Any], counters: dict[str, int], events: list[str], consumed: LiveExecutionPermit) -> None:
        self._case = case
        self._counters = counters
        self._events = events
        self._consumed = consumed

    def ensure_available(self) -> None:
        self._counters["ensure_calls"] += 1
        self._events.append("ensure")
        if self._case.get("ensure_failure"):
            raise RuntimeError("unavailable rawResponse secret")

    def consume(self, **kwargs: Any) -> LiveExecutionPermit:
        self._counters["consume_calls"] += 1
        self._events.append("consume")
        if self._case.get("consume_failure"):
            raise LiveExecutionPermitPersistenceError("PERMIT_UNAVAILABLE")
        return self._case.get("returned_permit", self._consumed)

    def close(self) -> None:
        self._counters["close_calls"] += 1
        self._events.append("close")
        if self._case.get("close_failure"):
            raise RuntimeError("close rawResponse secret")


def _matrix_fingerprint() -> LiveExecutionRequestFingerprint:
    return build_live_execution_request_fingerprint(
        {
            "schema_version": "1.0",
            "operation": "SIGNED_ORDER_TEST_CREATE",
            "environment": "TESTNET",
            "symbol": "BTCUSDT",
            "client_order_id": "gate-matrix-order-001",
            "side": "BUY",
            "position_side": "BOTH",
            "order_type": "LIMIT",
            "quantity": "0.001",
            "price": "50000",
            "time_in_force": "GTC",
            "reduce_only": False,
        }
    )


def _invalid_reference(permit_id: object, expected_version: object) -> LiveExecutionPermitReference:
    reference = object.__new__(LiveExecutionPermitReference)
    object.__setattr__(reference, "permit_id", permit_id)
    object.__setattr__(reference, "expected_version", expected_version)
    return reference


def _consumed_permit(
    fingerprint: LiveExecutionRequestFingerprint,
    correlation_id: UUID,
    *,
    permit_id: str = "permit-11111111111111111111111111111111",
    operation: LiveExecutionOperation | None = None,
    environment: str = "TESTNET",
    symbol: str = "BTCUSDT",
    subject_type: str | None = None,
    subject_id: str | None = None,
    request_fingerprint: str | None = None,
    state: LiveExecutionPermitState = LiveExecutionPermitState.CONSUMED,
    consumption_correlation_id: UUID | None = None,
    version: int = 2,
) -> LiveExecutionPermit:
    now = utc_now()
    if state == LiveExecutionPermitState.CONSUMED:
        consumed_at = now
        consumed_correlation = correlation_id if consumption_correlation_id is None else consumption_correlation_id
    else:
        consumed_at = None
        consumed_correlation = consumption_correlation_id
    return LiveExecutionPermit(
        permit_id=permit_id,
        operation=operation or fingerprint.operation,
        environment=environment,
        symbol=symbol,
        request_fingerprint=request_fingerprint or fingerprint.request_fingerprint,
        subject_type=subject_type or fingerprint.subject_type,
        subject_id=subject_id or fingerprint.subject_id,
        state=state,
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
        issued_by="operator-1",
        consumed_at=consumed_at,
        consumption_correlation_id=consumed_correlation,
        version=version,
    )


def _unsafe_permit(base: LiveExecutionPermit, **changes: Any) -> LiveExecutionPermit:
    permit = object.__new__(LiveExecutionPermit)
    for key, value in base.__dict__.items():
        object.__setattr__(permit, key, value)
    for key, value in changes.items():
        object.__setattr__(permit, key, value)
    return permit


def _gate_provider_counter_cases() -> list[dict[str, Any]]:
    fingerprint = _matrix_fingerprint()
    correlation_id = UUID("22222222-2222-4222-8222-222222222222")
    base_permit = _consumed_permit(fingerprint, correlation_id)
    different_correlation = UUID("33333333-3333-4333-8333-333333333333")
    cases = [
        {"id": "01_success", "events": ["policy", "factory", "ensure", "correlation", "consume", "close"]},
        {"id": "02_missing_reference", "reference": None, "code": "PERMIT_REQUIRED", "events": []},
        {"id": "03_reference_wrong_type", "reference": object(), "code": "PERMIT_REFERENCE_INVALID", "events": []},
        {
            "id": "04_malformed_permit_id",
            "reference": _invalid_reference("not-a-permit", 1),
            "code": "PERMIT_REFERENCE_INVALID",
            "events": [],
        },
        {
            "id": "05_expected_version_bool",
            "reference": _invalid_reference("permit-11111111111111111111111111111111", True),
            "code": "PERMIT_REFERENCE_INVALID",
            "events": [],
        },
        {
            "id": "06_expected_version_zero",
            "reference": _invalid_reference("permit-11111111111111111111111111111111", 0),
            "code": "PERMIT_REFERENCE_INVALID",
            "events": [],
        },
        {
            "id": "07_expected_version_negative",
            "reference": _invalid_reference("permit-11111111111111111111111111111111", -1),
            "code": "PERMIT_REFERENCE_INVALID",
            "events": [],
        },
        {"id": "08_invalid_fingerprint_object", "fingerprint": object(), "code": "PERMIT_REQUEST_INVALID", "events": []},
        {
            "id": "09_fingerprint_operation_mismatch",
            "fingerprint": replace(fingerprint, operation=LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL),
            "code": "PERMIT_REQUEST_INVALID",
            "events": [],
        },
        {
            "id": "10_fingerprint_environment_mismatch",
            "fingerprint": replace(fingerprint, environment="PRODUCTION"),
            "code": "PERMIT_REQUEST_INVALID",
            "events": [],
        },
        {
            "id": "11_fingerprint_symbol_mismatch",
            "fingerprint": replace(fingerprint, symbol="ETHUSDT"),
            "code": "PERMIT_REQUEST_INVALID",
            "events": [],
        },
        {"id": "12_policy_confirmation_denied", "confirmation_verified": False, "policy_code": "CONFIRMATION_REQUIRED", "code": "CONFIRMATION_REQUIRED", "events": ["policy"]},
        {"id": "13_policy_credentials_denied", "credentials_configured": False, "policy_code": "CREDENTIALS_UNAVAILABLE", "code": "CREDENTIALS_UNAVAILABLE", "events": ["policy"]},
        {"id": "14_persistence_factory_failure", "factory_failure": True, "code": "PERMIT_GATE_UNAVAILABLE", "events": ["policy", "factory"]},
        {"id": "15_persistence_ensure_failure", "ensure_failure": True, "code": "PERMIT_GATE_UNAVAILABLE", "events": ["policy", "factory", "ensure", "close"]},
        {"id": "16_correlation_provider_failure", "correlation_failure": True, "code": "PERMIT_GATE_UNAVAILABLE", "events": ["policy", "factory", "ensure", "correlation", "close"]},
        {"id": "17_correlation_provider_malformed_value", "correlation_value": "not-a-uuid", "code": "PERMIT_REQUEST_INVALID", "events": ["policy", "factory", "ensure", "correlation", "close"]},
        {"id": "18_consume_failure", "consume_failure": True, "code": "PERMIT_UNAVAILABLE", "events": ["policy", "factory", "ensure", "correlation", "consume", "close"]},
        {"id": "19_returned_permit_id_mismatch", "returned_permit": _consumed_permit(fingerprint, correlation_id, permit_id="permit-22222222222222222222222222222222"), "code": "PERMIT_CONSUMED_NO_TRANSPORT", "permit_consumed": True, "events": ["policy", "factory", "ensure", "correlation", "consume", "close"]},
        {"id": "20_returned_operation_mismatch", "returned_permit": _consumed_permit(fingerprint, correlation_id, operation=LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL), "code": "PERMIT_CONSUMED_NO_TRANSPORT", "permit_consumed": True, "events": ["policy", "factory", "ensure", "correlation", "consume", "close"]},
        {"id": "21_returned_environment_mismatch", "returned_permit": _unsafe_permit(base_permit, environment="PRODUCTION"), "code": "PERMIT_CONSUMED_NO_TRANSPORT", "permit_consumed": True, "events": ["policy", "factory", "ensure", "correlation", "consume", "close"]},
        {"id": "22_returned_symbol_mismatch", "returned_permit": _unsafe_permit(base_permit, symbol="ETHUSDT"), "code": "PERMIT_CONSUMED_NO_TRANSPORT", "permit_consumed": True, "events": ["policy", "factory", "ensure", "correlation", "consume", "close"]},
        {"id": "23_returned_subject_type_mismatch", "returned_permit": _consumed_permit(fingerprint, correlation_id, subject_type="PROTECTIVE_LEG"), "code": "PERMIT_CONSUMED_NO_TRANSPORT", "permit_consumed": True, "events": ["policy", "factory", "ensure", "correlation", "consume", "close"]},
        {"id": "24_returned_subject_id_mismatch", "returned_permit": _consumed_permit(fingerprint, correlation_id, subject_id="other-order"), "code": "PERMIT_CONSUMED_NO_TRANSPORT", "permit_consumed": True, "events": ["policy", "factory", "ensure", "correlation", "consume", "close"]},
        {"id": "25_returned_fingerprint_mismatch", "returned_permit": _consumed_permit(fingerprint, correlation_id, request_fingerprint="a" * 64), "code": "PERMIT_CONSUMED_NO_TRANSPORT", "permit_consumed": True, "events": ["policy", "factory", "ensure", "correlation", "consume", "close"]},
        {"id": "26_returned_correlation_mismatch", "returned_permit": _consumed_permit(fingerprint, correlation_id, consumption_correlation_id=different_correlation), "code": "PERMIT_CONSUMED_NO_TRANSPORT", "permit_consumed": True, "events": ["policy", "factory", "ensure", "correlation", "consume", "close"]},
        {"id": "27_returned_version_mismatch", "returned_permit": _consumed_permit(fingerprint, correlation_id, version=3), "code": "PERMIT_CONSUMED_NO_TRANSPORT", "permit_consumed": True, "events": ["policy", "factory", "ensure", "correlation", "consume", "close"]},
        {"id": "28_returned_state_or_consumed_record_invalid", "returned_permit": _consumed_permit(fingerprint, correlation_id, state=LiveExecutionPermitState.ISSUED), "code": "PERMIT_CONSUMED_NO_TRANSPORT", "permit_consumed": True, "events": ["policy", "factory", "ensure", "correlation", "consume", "close"]},
        {"id": "29_close_failure_after_consumption", "close_failure": True, "code": "PERMIT_CONSUMED_NO_TRANSPORT", "permit_consumed": True, "events": ["policy", "factory", "ensure", "correlation", "consume", "close"]},
    ]
    assert tuple(case["id"] for case in cases) == GATE_PROVIDER_COUNTER_ROW_IDS
    return cases


@pytest.mark.parametrize("case", _gate_provider_counter_cases(), ids=GATE_PROVIDER_COUNTER_ROW_IDS)
def test_gate_provider_counter_matrix(case: dict[str, Any]) -> None:
    counters = {
        "policy_calls": 0,
        "persistence_factory_calls": 0,
        "ensure_calls": 0,
        "correlation_provider_calls": 0,
        "consume_calls": 0,
        "close_calls": 0,
        "signing_calls": 0,
        "POST_calls": 0,
        "DELETE_calls": 0,
        "retry_calls": 0,
    }
    events: list[str] = []
    fingerprint = case.get("fingerprint", _matrix_fingerprint())
    permit_id = "permit-11111111111111111111111111111111"
    reference = case.get("reference", LiveExecutionPermitReference(permit_id, 1))
    correlation_id = UUID("22222222-2222-4222-8222-222222222222")
    consumed = _consumed_permit(fingerprint if isinstance(fingerprint, LiveExecutionRequestFingerprint) else _matrix_fingerprint(), correlation_id)

    def persistence_factory(**kwargs: Any) -> _CountedPersistence:
        counters["persistence_factory_calls"] += 1
        events.append("factory")
        if case.get("factory_failure"):
            raise RuntimeError("factory rawResponse secret")
        return _CountedPersistence(case, counters, events, consumed)

    def correlation_provider() -> object:
        counters["correlation_provider_calls"] += 1
        events.append("correlation")
        if case.get("correlation_failure"):
            raise RuntimeError("correlation signed-url secret")
        return case.get("correlation_value", correlation_id)

    gate = LiveExecutionPermitGate(
        authorization_policy=_CountedPolicy(counters, events, case.get("policy_code")),
        permit_persistence_factory=persistence_factory,
        correlation_id_provider=correlation_provider,
        env={},
    )

    expected_events = case["events"]
    if "code" not in case:
        receipt = gate.authorize_and_consume(
            operation=LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE,
            fingerprint=fingerprint,
            permit_reference=reference,
            confirmation_verified=case.get("confirmation_verified", True),
            credentials_configured=case.get("credentials_configured", True),
            runtime_config_path="configs/btc_paper_runtime.json",
        )
        assert receipt.permit_id == permit_id
        assert receipt.consumed_version == 2
    else:
        with pytest.raises(LiveExecutionPermitGateError) as exc:
            gate.authorize_and_consume(
                operation=LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE,
                fingerprint=fingerprint,
                permit_reference=reference,
                confirmation_verified=case.get("confirmation_verified", True),
                credentials_configured=case.get("credentials_configured", True),
                runtime_config_path="configs/btc_paper_runtime.json",
            )
        assert exc.value.code == case["code"]
        assert exc.value.permit_consumed is case.get("permit_consumed", False)

    assert events == expected_events
    assert counters["policy_calls"] == expected_events.count("policy")
    assert counters["persistence_factory_calls"] == expected_events.count("factory")
    assert counters["ensure_calls"] == expected_events.count("ensure")
    assert counters["correlation_provider_calls"] == expected_events.count("correlation")
    assert counters["consume_calls"] == expected_events.count("consume")
    assert counters["close_calls"] == expected_events.count("close")
    assert counters["signing_calls"] == 0
    assert counters["POST_calls"] == 0
    assert counters["DELETE_calls"] == 0
    assert counters["retry_calls"] == 0
