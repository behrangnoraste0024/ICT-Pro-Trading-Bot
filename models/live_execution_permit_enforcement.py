from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Iterator, Mapping
from uuid import UUID

from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit import (
    PERMIT_ENVIRONMENT,
    PERMIT_SYMBOL,
    LiveExecutionPermitError,
    validate_permit_id,
    validate_request_fingerprint,
)

PERMIT_GATE_CODES = {
    "PERMIT_REQUIRED",
    "PERMIT_REFERENCE_INVALID",
    "PERMIT_REQUEST_INVALID",
    "PERMIT_CONSUMED_NO_TRANSPORT",
    "PERMIT_GATE_UNAVAILABLE",
    "KILL_SWITCH_ENGAGED",
    "KILL_SWITCH_STATE_UNAVAILABLE",
    "RECOVERY_REQUIRED",
    "LIVE_TRADING_DISABLED",
    "DRY_RUN_ACTIVE",
    "CONFIRMATION_REQUIRED",
    "CREDENTIALS_UNAVAILABLE",
    "PERSISTENCE_UNAVAILABLE",
    "EXECUTION_POLICY_UNAVAILABLE",
    "UNSUPPORTED_EXECUTION_OPERATION",
    "TESTNET_ONLY",
    "BTCUSDT_ONLY",
    "PERMIT_NOT_FOUND",
    "PERMIT_ALREADY_CONSUMED",
    "PERMIT_ALREADY_REVOKED",
    "PERMIT_ALREADY_EXPIRED",
    "PERMIT_SCOPE_MISMATCH",
    "PERMIT_SUBJECT_MISMATCH",
    "PERMIT_FINGERPRINT_MISMATCH",
    "PERMIT_VERSION_CONFLICT",
    "PERMIT_CONSUMPTION_CORRELATION_CONFLICT",
    "PERMIT_INVALID",
    "PERMIT_UNAVAILABLE",
}

PERMIT_GATE_MESSAGES = {
    "PERMIT_REQUIRED": "A durable one-time live execution permit is required.",
    "PERMIT_REFERENCE_INVALID": "The live execution permit reference is invalid.",
    "PERMIT_REQUEST_INVALID": "The live execution permit request is invalid.",
    "PERMIT_CONSUMED_NO_TRANSPORT": "Permit was consumed but mutation transport was blocked.",
    "PERMIT_GATE_UNAVAILABLE": "Live execution permit gate is unavailable.",
    "KILL_SWITCH_ENGAGED": "Durable kill switch blocks exchange mutation.",
    "KILL_SWITCH_STATE_UNAVAILABLE": "Durable kill-switch state is unavailable.",
    "RECOVERY_REQUIRED": "Unresolved recovery blocks fresh exchange mutation.",
    "LIVE_TRADING_DISABLED": "Live mutation mode is disabled.",
    "DRY_RUN_ACTIVE": "Dry-run mode blocks exchange mutation.",
    "CONFIRMATION_REQUIRED": "Verified explicit confirmation is required.",
    "CREDENTIALS_UNAVAILABLE": "Testnet credentials are unavailable.",
    "PERSISTENCE_UNAVAILABLE": "Execution persistence is unavailable.",
    "EXECUTION_POLICY_UNAVAILABLE": "Execution authorization context is unavailable.",
    "UNSUPPORTED_EXECUTION_OPERATION": "Execution operation is not supported.",
    "TESTNET_ONLY": "Only the Binance Futures Testnet environment is authorized.",
    "BTCUSDT_ONLY": "Only BTCUSDT is authorized.",
    "PERMIT_NOT_FOUND": "Permit was not found.",
    "PERMIT_ALREADY_CONSUMED": "Permit is already consumed.",
    "PERMIT_ALREADY_REVOKED": "Permit is already revoked.",
    "PERMIT_ALREADY_EXPIRED": "Permit is expired.",
    "PERMIT_SCOPE_MISMATCH": "Permit scope does not match the mutation.",
    "PERMIT_SUBJECT_MISMATCH": "Permit subject does not match the mutation.",
    "PERMIT_FINGERPRINT_MISMATCH": "Permit fingerprint does not match the mutation.",
    "PERMIT_VERSION_CONFLICT": "Permit version conflict.",
    "PERMIT_CONSUMPTION_CORRELATION_CONFLICT": "Permit consumption correlation conflict.",
    "PERMIT_INVALID": "Permit is invalid.",
    "PERMIT_UNAVAILABLE": "Permit is unavailable.",
}


@dataclass(frozen=True)
class LiveExecutionPermitReference:
    permit_id: str
    expected_version: int

    def __post_init__(self) -> None:
        try:
            validate_permit_id(self.permit_id)
        except LiveExecutionPermitError as exc:
            raise ValueError("PERMIT_REFERENCE_INVALID") from exc
        if isinstance(self.expected_version, bool) or not isinstance(self.expected_version, int) or self.expected_version < 1:
            raise ValueError("PERMIT_REFERENCE_INVALID")


@dataclass(frozen=True)
class LiveExecutionUnsignedMutationRequest(Mapping[str, Any]):
    """One immutable unsigned request shared by fingerprinting and transport.

    Authentication fields are intentionally absent.  The exchange clients may
    add timestamp, recvWindow and signature only inside their signing boundary.
    Implementing ``Mapping`` keeps legacy consumers read-only compatible while
    preventing business-field edits after the final permit check.
    """

    operation: LiveExecutionOperation
    environment: str
    symbol: str
    subject_type: str
    subject_id: str
    fingerprint_context: Mapping[str, Any]
    transport_business_parameters: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.operation, LiveExecutionOperation):
            raise ValueError("PERMIT_REQUEST_INVALID")
        if self.environment != PERMIT_ENVIRONMENT or self.symbol != PERMIT_SYMBOL:
            raise ValueError("PERMIT_REQUEST_INVALID")
        if not isinstance(self.subject_type, str) or not self.subject_type:
            raise ValueError("PERMIT_REQUEST_INVALID")
        if not isinstance(self.subject_id, str) or not self.subject_id:
            raise ValueError("PERMIT_REQUEST_INVALID")
        if not isinstance(self.fingerprint_context, Mapping) or not isinstance(self.transport_business_parameters, Mapping):
            raise ValueError("PERMIT_REQUEST_INVALID")
        if self.operation in {
            LiveExecutionOperation.ORDER_LIFECYCLE_CREATE,
            LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE,
        }:
            reduce_only = self.fingerprint_context.get("reduce_only")
            if not isinstance(reduce_only, bool):
                raise ValueError("PERMIT_REQUEST_INVALID")
            transmitted_reduce_only = self.transport_business_parameters.get("reduceOnly")
            if transmitted_reduce_only is None:
                if reduce_only is not False:
                    raise ValueError("PERMIT_REQUEST_INVALID")
            elif str(transmitted_reduce_only).lower() != str(reduce_only).lower():
                raise ValueError("PERMIT_REQUEST_INVALID")
        object.__setattr__(self, "fingerprint_context", MappingProxyType(dict(self.fingerprint_context)))
        object.__setattr__(self, "transport_business_parameters", MappingProxyType(dict(self.transport_business_parameters)))

    def __getitem__(self, key: str) -> Any:
        return self.transport_business_parameters[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.transport_business_parameters)

    def __len__(self) -> int:
        return len(self.transport_business_parameters)

    def get(self, key: str, default: Any = None) -> Any:
        return self.transport_business_parameters.get(key, default)


@dataclass(frozen=True)
class LiveExecutionPermitConsumptionReceipt:
    permit_id: str
    operation: LiveExecutionOperation
    environment: str
    symbol: str
    subject_type: str
    subject_id: str
    request_fingerprint: str
    consumption_correlation_id: UUID
    previous_version: int
    consumed_version: int
    consumed_at: datetime

    def __post_init__(self) -> None:
        validate_permit_id(self.permit_id)
        if not isinstance(self.operation, LiveExecutionOperation):
            raise ValueError("PERMIT_REQUEST_INVALID")
        if self.environment != PERMIT_ENVIRONMENT or self.symbol != PERMIT_SYMBOL:
            raise ValueError("PERMIT_REQUEST_INVALID")
        validate_request_fingerprint(self.request_fingerprint)
        if not isinstance(self.consumption_correlation_id, UUID):
            raise ValueError("PERMIT_REQUEST_INVALID")
        if (
            isinstance(self.previous_version, bool)
            or isinstance(self.consumed_version, bool)
            or not isinstance(self.previous_version, int)
            or not isinstance(self.consumed_version, int)
            or self.consumed_version != self.previous_version + 1
        ):
            raise ValueError("PERMIT_REQUEST_INVALID")
        if not isinstance(self.consumed_at, datetime):
            raise ValueError("PERMIT_REQUEST_INVALID")


class LiveExecutionPermitGateError(RuntimeError):
    def __init__(self, code: str, permit_consumed: bool = False) -> None:
        fixed = code if code in PERMIT_GATE_CODES else "PERMIT_GATE_UNAVAILABLE"
        super().__init__(fixed)
        self.code = fixed
        self.message = PERMIT_GATE_MESSAGES[fixed]
        self.permit_consumed = bool(permit_consumed)

    def __str__(self) -> str:
        return self.code
