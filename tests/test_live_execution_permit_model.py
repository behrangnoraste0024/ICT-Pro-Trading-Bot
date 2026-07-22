from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit import LiveExecutionPermit, LiveExecutionPermitError, LiveExecutionPermitState

NOW = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
FINGERPRINT = "a" * 64
PERMIT_ID = "permit-" + "1" * 32


def _permit(**overrides) -> LiveExecutionPermit:
    values = {
        "permit_id": PERMIT_ID,
        "operation": LiveExecutionOperation.PROTECTIVE_CREATE,
        "environment": "TESTNET",
        "symbol": "BTCUSDT",
        "request_fingerprint": FINGERPRINT,
        "subject_type": "PROTECTIVE_LEG",
        "subject_id": "pair-1:STOP:client-1",
        "state": LiveExecutionPermitState.ISSUED,
        "issued_at": NOW,
        "expires_at": NOW + timedelta(minutes=5),
        "issued_by": "operator-1",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return LiveExecutionPermit(**values)


@pytest.mark.parametrize(
    "state,fields",
    [
        (LiveExecutionPermitState.ISSUED, {}),
        (LiveExecutionPermitState.CONSUMED, {"consumed_at": NOW, "consumption_correlation_id": uuid4()}),
        (LiveExecutionPermitState.REVOKED, {"revoked_at": NOW, "revocation_reason_code": "OPERATOR_REVOKED"}),
        (LiveExecutionPermitState.EXPIRED, {"expired_at": NOW}),
    ],
)
def test_live_execution_permit_accepts_valid_states(state: LiveExecutionPermitState, fields: dict) -> None:
    permit = _permit(state=state, **fields)
    assert permit.state == state
    with pytest.raises(FrozenInstanceError):
        permit.state = LiveExecutionPermitState.EXPIRED


@pytest.mark.parametrize(
    "field,value",
    [
        ("permit_id", "permit-XYZ"),
        ("request_fingerprint", "A" * 64),
        ("request_fingerprint", "a" * 63),
        ("environment", "PRODUCTION"),
        ("symbol", "ETHUSDT"),
        ("operation", "UNKNOWN"),
        ("subject_type", "WILDCARD"),
        ("subject_id", ""),
        ("subject_id", "bad subject"),
        ("issued_by", ""),
        ("issued_by", "operator secret"),
        ("version", 0),
        ("version", True),
    ],
)
def test_live_execution_permit_rejects_malformed_required_fields(field: str, value: object) -> None:
    with pytest.raises(LiveExecutionPermitError):
        _permit(**{field: value})


def test_live_execution_permit_rejects_naive_datetimes_and_bad_expiry_order() -> None:
    with pytest.raises(LiveExecutionPermitError):
        _permit(issued_at=datetime(2026, 7, 22, 12, 0))
    with pytest.raises(LiveExecutionPermitError):
        _permit(expires_at=NOW)


@pytest.mark.parametrize(
    "state,fields",
    [
        (LiveExecutionPermitState.ISSUED, {"consumed_at": NOW}),
        (LiveExecutionPermitState.CONSUMED, {"consumed_at": None, "consumption_correlation_id": uuid4()}),
        (LiveExecutionPermitState.CONSUMED, {"consumed_at": NOW, "consumption_correlation_id": None}),
        (LiveExecutionPermitState.REVOKED, {"revoked_at": None, "revocation_reason_code": "OPERATOR_REVOKED"}),
        (LiveExecutionPermitState.REVOKED, {"revoked_at": NOW, "revocation_reason_code": "FREE_TEXT"}),
        (LiveExecutionPermitState.EXPIRED, {"expired_at": None}),
        (LiveExecutionPermitState.EXPIRED, {"expired_at": NOW, "revoked_at": NOW}),
    ],
)
def test_live_execution_permit_rejects_illegal_state_timestamp_combinations(state: LiveExecutionPermitState, fields: dict) -> None:
    with pytest.raises(LiveExecutionPermitError):
        _permit(state=state, **fields)


def test_live_execution_permit_does_not_accept_arbitrary_secret_fields() -> None:
    with pytest.raises(TypeError):
        LiveExecutionPermit(
            permit_id=PERMIT_ID,
            operation=LiveExecutionOperation.PROTECTIVE_CREATE,
            environment="TESTNET",
            symbol="BTCUSDT",
            request_fingerprint=FINGERPRINT,
            subject_type="PROTECTIVE_LEG",
            subject_id="pair-1:STOP:client-1",
            state=LiveExecutionPermitState.ISSUED,
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
            issued_by="operator-1",
            api_secret="secret-token",
        )
