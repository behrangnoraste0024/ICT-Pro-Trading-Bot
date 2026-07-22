from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import re
from uuid import UUID, uuid4

from models.live_execution_authorization import LiveExecutionOperation

PERMIT_ENVIRONMENT = "TESTNET"
PERMIT_SYMBOL = "BTCUSDT"
LIVE_EXECUTION_PERMIT_SCHEMA_VERSION = "1.0"

PERMIT_RESULT_CODES = {
    "PERMIT_ISSUED",
    "PERMIT_CONSUMED",
    "PERMIT_REVOKED",
    "PERMIT_EXPIRED",
    "PERMIT_DENIED",
    "PERMIT_NOT_FOUND",
    "PERMIT_INVALID",
    "PERMIT_ALREADY_CONSUMED",
    "PERMIT_ALREADY_REVOKED",
    "PERMIT_ALREADY_EXPIRED",
    "PERMIT_SCOPE_MISMATCH",
    "PERMIT_SUBJECT_MISMATCH",
    "PERMIT_FINGERPRINT_MISMATCH",
    "PERMIT_VERSION_CONFLICT",
    "PERMIT_CONSUMPTION_CORRELATION_CONFLICT",
    "PERMIT_DUPLICATE_ACTIVE",
    "PERMIT_CONFIRMATION_REQUIRED",
    "PERMIT_TTL_INVALID",
    "PERMIT_UNAVAILABLE",
}

PERMIT_REVOCATION_REASON_CODES = {
    "OPERATOR_REVOKED",
    "SUPERSEDED",
    "SECURITY_INVALIDATION",
}

PERMIT_SUBJECT_TYPES = {"PROTECTIVE_LEG", "CLIENT_ORDER"}
PERMIT_ID_PATTERN = re.compile(r"^permit-[0-9a-f]{32}$")
PERMIT_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PERMIT_CANONICAL_TEXT_PATTERN = re.compile(r"^[A-Za-z0-9._:@/\-]{1,128}$")
PERMIT_ISSUED_BY_PATTERN = re.compile(r"^[A-Za-z0-9._:@\-]{1,96}$")


class LiveExecutionPermitState(StrEnum):
    ISSUED = "ISSUED"
    CONSUMED = "CONSUMED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class LiveExecutionPermitError(ValueError):
    def __init__(self, code: str = "PERMIT_INVALID") -> None:
        super().__init__(code)
        self.code = code


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def generate_permit_id() -> str:
    return f"permit-{uuid4().hex}"


def validate_permit_id(value: str) -> str:
    if not isinstance(value, str) or PERMIT_ID_PATTERN.fullmatch(value) is None:
        raise LiveExecutionPermitError("PERMIT_INVALID")
    return value


def validate_request_fingerprint(value: str) -> str:
    if not isinstance(value, str) or PERMIT_FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise LiveExecutionPermitError("PERMIT_INVALID")
    return value


def validate_subject_type(value: str) -> str:
    if not isinstance(value, str) or value not in PERMIT_SUBJECT_TYPES:
        raise LiveExecutionPermitError("PERMIT_INVALID")
    return value


def validate_canonical_text(value: str, *, max_length: int = 128) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise LiveExecutionPermitError("PERMIT_INVALID")
    if PERMIT_CANONICAL_TEXT_PATTERN.fullmatch(value) is None:
        raise LiveExecutionPermitError("PERMIT_INVALID")
    return value


def validate_issued_by(value: str) -> str:
    if not isinstance(value, str) or PERMIT_ISSUED_BY_PATTERN.fullmatch(value) is None:
        raise LiveExecutionPermitError("PERMIT_INVALID")
    return value


def validate_aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise LiveExecutionPermitError("PERMIT_INVALID")
    return value.astimezone(UTC)


def validate_operation(value: LiveExecutionOperation | str) -> LiveExecutionOperation:
    if isinstance(value, LiveExecutionOperation):
        return value
    if isinstance(value, str):
        try:
            return LiveExecutionOperation(value)
        except ValueError as exc:
            raise LiveExecutionPermitError("PERMIT_INVALID") from exc
    raise LiveExecutionPermitError("PERMIT_INVALID")


def validate_state(value: LiveExecutionPermitState | str) -> LiveExecutionPermitState:
    if isinstance(value, LiveExecutionPermitState):
        return value
    if isinstance(value, str):
        try:
            return LiveExecutionPermitState(value)
        except ValueError as exc:
            raise LiveExecutionPermitError("PERMIT_INVALID") from exc
    raise LiveExecutionPermitError("PERMIT_INVALID")


@dataclass(frozen=True)
class LiveExecutionPermit:
    permit_id: str
    operation: LiveExecutionOperation
    environment: str
    symbol: str
    request_fingerprint: str
    subject_type: str
    subject_id: str
    state: LiveExecutionPermitState
    issued_at: datetime
    expires_at: datetime
    issued_by: str
    id: UUID = field(default_factory=uuid4)
    consumed_at: datetime | None = None
    revoked_at: datetime | None = None
    expired_at: datetime | None = None
    revocation_reason_code: str | None = None
    consumption_correlation_id: UUID | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise LiveExecutionPermitError("PERMIT_INVALID")
        operation = validate_operation(self.operation)
        state = validate_state(self.state)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "state", state)
        validate_permit_id(self.permit_id)
        if self.environment != PERMIT_ENVIRONMENT or self.symbol != PERMIT_SYMBOL:
            raise LiveExecutionPermitError("PERMIT_INVALID")
        validate_request_fingerprint(self.request_fingerprint)
        validate_subject_type(self.subject_type)
        validate_canonical_text(self.subject_id)
        validate_issued_by(self.issued_by)
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise LiveExecutionPermitError("PERMIT_INVALID")
        for field_name in ("issued_at", "expires_at", "created_at", "updated_at"):
            object.__setattr__(self, field_name, validate_aware_utc(getattr(self, field_name)))
        for field_name in ("consumed_at", "revoked_at", "expired_at"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, validate_aware_utc(value))
        if self.expires_at <= self.issued_at:
            raise LiveExecutionPermitError("PERMIT_INVALID")
        if self.revocation_reason_code is not None and self.revocation_reason_code not in PERMIT_REVOCATION_REASON_CODES:
            raise LiveExecutionPermitError("PERMIT_INVALID")
        if self.consumption_correlation_id is not None and not isinstance(self.consumption_correlation_id, UUID):
            raise LiveExecutionPermitError("PERMIT_INVALID")
        self._validate_state_timestamps()

    def _validate_state_timestamps(self) -> None:
        if self.state == LiveExecutionPermitState.ISSUED:
            if any(
                value is not None
                for value in (
                    self.consumed_at,
                    self.revoked_at,
                    self.expired_at,
                    self.consumption_correlation_id,
                    self.revocation_reason_code,
                )
            ):
                raise LiveExecutionPermitError("PERMIT_INVALID")
            return
        if self.state == LiveExecutionPermitState.CONSUMED:
            if (
                self.consumed_at is None
                or self.consumption_correlation_id is None
                or self.revoked_at is not None
                or self.expired_at is not None
                or self.revocation_reason_code is not None
            ):
                raise LiveExecutionPermitError("PERMIT_INVALID")
            return
        if self.state == LiveExecutionPermitState.REVOKED:
            if (
                self.revoked_at is None
                or self.revocation_reason_code not in PERMIT_REVOCATION_REASON_CODES
                or self.consumed_at is not None
                or self.expired_at is not None
                or self.consumption_correlation_id is not None
            ):
                raise LiveExecutionPermitError("PERMIT_INVALID")
            return
        if self.state == LiveExecutionPermitState.EXPIRED:
            if (
                self.expired_at is None
                or self.consumed_at is not None
                or self.revoked_at is not None
                or self.consumption_correlation_id is not None
                or self.revocation_reason_code is not None
            ):
                raise LiveExecutionPermitError("PERMIT_INVALID")
            return
        raise LiveExecutionPermitError("PERMIT_INVALID")
