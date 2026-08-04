from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from infrastructure.persistence.live_execution_permit_persistence import (
    LiveExecutionPermitPersistence,
    LiveExecutionPermitPersistenceError,
)
from models.live_execution_permit import (
    PERMIT_ENVIRONMENT,
    PERMIT_SYMBOL,
    LiveExecutionPermitError,
    LiveExecutionPermitState,
    validate_operation,
    validate_permit_id,
    validate_state,
)


_UNAVAILABLE_CODE = "PERMIT_STATUS_UNAVAILABLE"
_UNAVAILABLE_MESSAGE = "Live execution permit status is unavailable."


@dataclass(frozen=True)
class LiveExecutionPermitStatusHTTPError(Exception):
    status_code: int
    code: str
    message: str


class LiveExecutionPermitStatusService:
    def __init__(
        self,
        *,
        env: dict[str, str] | None = None,
        persistence_factory: Callable[..., Any] = LiveExecutionPermitPersistence,
    ) -> None:
        self._env = env
        self._persistence_factory = persistence_factory

    def status(self, permit_id: str) -> dict[str, Any]:
        self._validate_permit_id_for_route(permit_id)
        persistence = self._persistence_factory(env=self._env) if self._env is not None else self._persistence_factory()
        try:
            ensure_available = getattr(persistence, "ensure_available", None)
            if callable(ensure_available):
                ensure_available()
            permit, effective_expired = persistence.show(permit_id)
        except LiveExecutionPermitPersistenceError as exc:
            raise self._map_persistence_error(exc) from exc
        except Exception as exc:
            raise LiveExecutionPermitStatusHTTPError(503, _UNAVAILABLE_CODE, _UNAVAILABLE_MESSAGE) from exc
        finally:
            close = getattr(persistence, "close", None)
            if callable(close):
                close()

        if permit is None:
            raise LiveExecutionPermitStatusHTTPError(404, "PERMIT_NOT_FOUND", "Live execution permit was not found.")

        return self._serialize_permit(permit, bool(effective_expired))

    @staticmethod
    def _validate_permit_id_for_route(permit_id: str) -> None:
        try:
            validate_permit_id(permit_id)
        except LiveExecutionPermitError as exc:
            raise LiveExecutionPermitStatusHTTPError(400, "INVALID_PERMIT_ID", "Permit identifier is invalid.") from exc

    @staticmethod
    def _map_persistence_error(exc: LiveExecutionPermitPersistenceError) -> LiveExecutionPermitStatusHTTPError:
        if exc.code == "PERMIT_INVALID":
            return LiveExecutionPermitStatusHTTPError(400, "INVALID_PERMIT_ID", "Permit identifier is invalid.")
        if exc.code == "PERMIT_NOT_FOUND":
            return LiveExecutionPermitStatusHTTPError(404, "PERMIT_NOT_FOUND", "Live execution permit was not found.")
        return LiveExecutionPermitStatusHTTPError(503, _UNAVAILABLE_CODE, _UNAVAILABLE_MESSAGE)

    def _serialize_permit(self, permit: Any, effective_expired: bool) -> dict[str, Any]:
        environment = self._required_string(getattr(permit, "environment", None))
        symbol = self._required_string(getattr(permit, "symbol", None))
        if environment != PERMIT_ENVIRONMENT or symbol != PERMIT_SYMBOL:
            if self._valid_scope_string(environment) and self._valid_scope_string(symbol):
                raise LiveExecutionPermitStatusHTTPError(
                    403,
                    "PERMIT_SCOPE_FORBIDDEN",
                    "Live execution permit scope is forbidden.",
                )
            raise LiveExecutionPermitStatusHTTPError(503, _UNAVAILABLE_CODE, _UNAVAILABLE_MESSAGE)

        try:
            operation = validate_operation(getattr(permit, "operation", None)).value
            persisted_state = validate_state(getattr(permit, "state", None))
        except LiveExecutionPermitError as exc:
            raise LiveExecutionPermitStatusHTTPError(503, _UNAVAILABLE_CODE, _UNAVAILABLE_MESSAGE) from exc

        state = persisted_state.value
        if persisted_state == LiveExecutionPermitState.ISSUED and effective_expired:
            state = LiveExecutionPermitState.EXPIRED.value
        effective_expired_value = bool(
            effective_expired
            or persisted_state == LiveExecutionPermitState.EXPIRED
            or state == LiveExecutionPermitState.EXPIRED.value
        )

        version = getattr(permit, "version", None)
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise LiveExecutionPermitStatusHTTPError(503, _UNAVAILABLE_CODE, _UNAVAILABLE_MESSAGE)

        return {
            "permit_id": self._validated_permit_id(getattr(permit, "permit_id", None)),
            "operation": operation,
            "environment": environment,
            "symbol": symbol,
            "state": state,
            "effective_expired": effective_expired_value,
            "expires_at": self._required_datetime(getattr(permit, "expires_at", None)),
            "issued_at": self._required_datetime(getattr(permit, "issued_at", None)),
            "consumed_at": self._optional_datetime(getattr(permit, "consumed_at", None)),
            "revoked_at": self._optional_datetime(getattr(permit, "revoked_at", None)),
            "revocation_reason": self._optional_reason(getattr(permit, "revocation_reason_code", None)),
            "version": version,
            "updated_at": self._required_datetime(getattr(permit, "updated_at", None)),
        }

    @staticmethod
    def _validated_permit_id(value: Any) -> str:
        try:
            return validate_permit_id(value)
        except LiveExecutionPermitError as exc:
            raise LiveExecutionPermitStatusHTTPError(503, _UNAVAILABLE_CODE, _UNAVAILABLE_MESSAGE) from exc

    @staticmethod
    def _required_string(value: Any) -> str:
        if not isinstance(value, str) or not value:
            raise LiveExecutionPermitStatusHTTPError(503, _UNAVAILABLE_CODE, _UNAVAILABLE_MESSAGE)
        return value

    @staticmethod
    def _valid_scope_string(value: str) -> bool:
        return bool(value) and value.replace("_", "").replace("-", "").replace("/", "").isalnum()

    @staticmethod
    def _required_datetime(value: Any) -> str:
        if not isinstance(value, datetime):
            raise LiveExecutionPermitStatusHTTPError(503, _UNAVAILABLE_CODE, _UNAVAILABLE_MESSAGE)
        return value.isoformat()

    @classmethod
    def _optional_datetime(cls, value: Any) -> str | None:
        if value is None:
            return None
        return cls._required_datetime(value)

    @staticmethod
    def _optional_reason(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str) and value.isupper() and 1 <= len(value) <= 64 and all(ch.isalnum() or ch == "_" for ch in value):
            return value
        raise LiveExecutionPermitStatusHTTPError(503, _UNAVAILABLE_CODE, _UNAVAILABLE_MESSAGE)
