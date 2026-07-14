from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

EXECUTION_INTENT_STATES = {
    "PENDING",
    "PERSISTED",
    "TRANSMITTED",
    "RECONCILING",
    "COMPLETED",
    "RECOVERY_REQUIRED",
    "FAILED_SAFE",
}

PROTECTIVE_PAIR_STATES = {
    "PENDING",
    "STOP_ACTIVE",
    "PAIR_ACTIVE",
    "CANCEL_PENDING",
    "RECOVERY_REQUIRED",
    "RECOVERED",
    "COMPLETED",
    "FAILED_SAFE",
}

EXCHANGE_ORDER_LEG_TYPES = {"STOP", "TAKE_PROFIT"}


class PersistenceValidationError(ValueError):
    pass


class DuplicateIdentityError(RuntimeError):
    pass


class OptimisticLockError(RuntimeError):
    pass


class ForbiddenAuditMetadataError(PersistenceValidationError):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def validate_state(value: str, allowed: set[str], field_name: str = "state") -> str:
    if not isinstance(value, str) or value not in allowed:
        raise PersistenceValidationError(f"unknown {field_name}: {value}")
    return value


def validate_leg_type(value: str) -> str:
    return validate_state(value, EXCHANGE_ORDER_LEG_TYPES, "leg_type")


@dataclass(frozen=True)
class ExecutionIntent:
    environment: str
    symbol: str
    intent_type: str
    state: str
    correlation_id: UUID = field(default_factory=uuid4)
    id: UUID = field(default_factory=uuid4)
    requested_quantity: Decimal | None = None
    requested_price: Decimal | None = None
    failure_code: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1

    def __post_init__(self) -> None:
        validate_state(self.state, EXECUTION_INTENT_STATES)


@dataclass(frozen=True)
class ProtectivePair:
    pair_id: str
    correlation_id: UUID
    execution_intent_id: UUID
    environment: str
    symbol: str
    position_side: str
    direction: str
    quantity: Decimal
    state: str
    id: UUID = field(default_factory=uuid4)
    recovery_required: bool = False
    blocking_reason: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1

    def __post_init__(self) -> None:
        validate_state(self.state, PROTECTIVE_PAIR_STATES)


@dataclass(frozen=True)
class ExchangeOrderIdentity:
    protective_pair_id: UUID
    environment: str
    symbol: str
    leg_type: str
    client_algo_id: str
    status: str
    id: UUID = field(default_factory=uuid4)
    exchange_algo_id: str | None = None
    exchange_order_id: str | None = None
    trigger_price: Decimal | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1

    def __post_init__(self) -> None:
        validate_leg_type(self.leg_type)


@dataclass(frozen=True)
class RecoveryEvent:
    correlation_id: UUID
    event_type: str
    result: str
    id: UUID = field(default_factory=uuid4)
    protective_pair_id: UUID | None = None
    from_state: str | None = None
    to_state: str | None = None
    reason_code: str | None = None
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class AuditEvent:
    category: str
    action: str
    environment: str
    result: str
    id: UUID = field(default_factory=uuid4)
    correlation_id: UUID | None = None
    symbol: str | None = None
    error_code: str | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=utc_now)
