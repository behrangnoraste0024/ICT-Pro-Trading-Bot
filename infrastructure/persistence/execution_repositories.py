from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import case, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from infrastructure.persistence.execution_orm import (
    AuditEventORM,
    ExchangeOrderIdentityORM,
    ExecutionIntentORM,
    KillSwitchStateORM,
    LiveExecutionPermitORM,
    ProtectivePairORM,
    RecoveryEventORM,
)
from models.execution_persistence import (
    AuditEvent,
    DuplicateIdentityError,
    EXECUTION_INTENT_STATES,
    ExchangeOrderIdentity,
    ExecutionIntent,
    ForbiddenAuditMetadataError,
    OptimisticLockError,
    PersistenceValidationError,
    PROTECTIVE_PAIR_STATES,
    ProtectivePair,
    RecoveryEvent,
    ensure_aware_utc,
    utc_now,
    validate_leg_type,
    validate_state,
)
from models.kill_switch_state import KILL_SWITCH_STATES, KillSwitchState
from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit import LiveExecutionPermit, LiveExecutionPermitState

FORBIDDEN_METADATA_KEYS = {
    "apikey",
    "apisecret",
    "secret",
    "signature",
    "signedurl",
    "authorization",
    "auth",
    "headers",
    "authenticatedheaders",
    "rawresponse",
    "rawexchangeresponse",
    "exchangeresponse",
    "credentiallength",
    "xmbxapikey",
}


def _utc(value: datetime) -> datetime:
    return ensure_aware_utc(value)


def _safe_flush(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise DuplicateIdentityError("duplicate or invalid persistence identity") from exc
    except SQLAlchemyError:
        session.rollback()
        raise


def _sanitize_key(key: str) -> str:
    return "".join(ch for ch in key.casefold() if ch.isalnum())


def _is_forbidden_metadata_key(key: str) -> bool:
    normalized = _sanitize_key(key)
    return (
        normalized in FORBIDDEN_METADATA_KEYS
        or "apikey" in normalized
        or "secret" in normalized
        or "signature" in normalized
        or "authorization" in normalized
        or "headers" in normalized
        or ("signed" in normalized and "url" in normalized)
        or ("raw" in normalized and "response" in normalized)
        or ("exchange" in normalized and "response" in normalized)
        or ("credential" in normalized and "length" in normalized)
    )


def sanitize_audit_metadata(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ForbiddenAuditMetadataError("audit metadata keys must be strings")
            if _is_forbidden_metadata_key(key):
                raise ForbiddenAuditMetadataError(f"forbidden audit metadata key: {key}")
            cleaned[key] = sanitize_audit_metadata(nested)
        return cleaned
    if isinstance(value, list):
        return [sanitize_audit_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_audit_metadata(item) for item in value]
    if isinstance(value, (str, int, float, bool)):
        return deepcopy(value)
    raise PersistenceValidationError("audit metadata values must be JSON-compatible")


class ExecutionIntentRepository(ABC):
    @abstractmethod
    def create(self, intent: ExecutionIntent) -> ExecutionIntent: ...

    @abstractmethod
    def get_by_id(self, intent_id: UUID) -> ExecutionIntent | None: ...

    @abstractmethod
    def get_by_correlation_id(self, correlation_id: UUID) -> ExecutionIntent | None: ...

    @abstractmethod
    def update_state(self, intent_id: UUID, expected_version: int, state: str, failure_code: str | None = None) -> ExecutionIntent: ...


class ProtectivePairRepository(ABC):
    @abstractmethod
    def create(self, pair: ProtectivePair) -> ProtectivePair: ...

    @abstractmethod
    def get_by_id(self, pair_id: UUID) -> ProtectivePair | None: ...

    @abstractmethod
    def get_by_pair_id(self, pair_id: str) -> ProtectivePair | None: ...

    @abstractmethod
    def update_state(self, pair_id: UUID, expected_version: int, state: str, recovery_required: bool | None = None, blocking_reason: str | None = None) -> ProtectivePair: ...


class ExchangeOrderIdentityRepository(ABC):
    @abstractmethod
    def create(self, identity: ExchangeOrderIdentity) -> ExchangeOrderIdentity: ...

    @abstractmethod
    def get_by_client_algo_id(self, environment: str, symbol: str, client_algo_id: str) -> ExchangeOrderIdentity | None: ...

    @abstractmethod
    def update_status(self, identity_id: UUID, expected_version: int, status: str) -> ExchangeOrderIdentity: ...

    @abstractmethod
    def list_by_protective_pair_id(self, protective_pair_id: UUID, limit: int, offset: int = 0) -> list[ExchangeOrderIdentity]: ...


class RecoveryEventRepository(ABC):
    """Append-only repository contract; database triggers/permissions are future work."""
    @abstractmethod
    def append(self, event: RecoveryEvent) -> RecoveryEvent: ...

    @abstractmethod
    def list_by_protective_pair_id(self, protective_pair_id: UUID, limit: int, offset: int = 0) -> list[RecoveryEvent]: ...


class AuditEventRepository(ABC):
    """Append-only repository contract; database triggers/permissions are future work."""
    @abstractmethod
    def append(self, event: AuditEvent) -> AuditEvent: ...

    @abstractmethod
    def list_by_correlation_id(self, correlation_id: UUID, limit: int, offset: int = 0) -> list[AuditEvent]: ...




class LiveExecutionPermitRepository(ABC):
    @abstractmethod
    def create_issued(self, permit: LiveExecutionPermit) -> LiveExecutionPermit: ...

    @abstractmethod
    def get_by_id(self, permit_id: UUID) -> LiveExecutionPermit | None: ...

    @abstractmethod
    def get_by_permit_id(self, permit_id: str) -> LiveExecutionPermit | None: ...

    @abstractmethod
    def find_consumed_by_correlation_id(self, consumption_correlation_id: UUID) -> LiveExecutionPermit | None: ...

    @abstractmethod
    def list_by_subject(self, environment: str, symbol: str, subject_type: str, subject_id: str, limit: int) -> list[LiveExecutionPermit]: ...

    @abstractmethod
    def expire_due_active_match(self, environment: str, symbol: str, operation: LiveExecutionOperation, subject_type: str, subject_id: str, request_fingerprint: str, now: datetime, limit: int = 100) -> list[LiveExecutionPermit]: ...

    @abstractmethod
    def consume_if_issued(self, permit_id: str, expected_version: int, operation: LiveExecutionOperation, environment: str, symbol: str, subject_type: str, subject_id: str, request_fingerprint: str, consumption_correlation_id: UUID, now: datetime) -> LiveExecutionPermit: ...

    @abstractmethod
    def revoke_if_issued(self, permit_id: str, expected_version: int, reason_code: str, now: datetime) -> LiveExecutionPermit: ...

    @abstractmethod
    def expire_if_issued(self, permit_id: str, expected_version: int, now: datetime) -> LiveExecutionPermit: ...

class KillSwitchStateRepository(ABC):
    @abstractmethod
    def create(self, state: KillSwitchState) -> KillSwitchState: ...

    @abstractmethod
    def get_by_scope(self, scope: str) -> KillSwitchState | None: ...

    @abstractmethod
    def update_state(self, state_id: UUID, expected_version: int, state: str) -> KillSwitchState: ...


def _validate_pagination(limit: int, offset: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise PersistenceValidationError("limit must be between 1 and 100")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise PersistenceValidationError("offset must be zero or greater")


def _execution_intent_from_orm(row: ExecutionIntentORM) -> ExecutionIntent:
    return ExecutionIntent(id=row.id, correlation_id=row.correlation_id, environment=row.environment, symbol=row.symbol, intent_type=row.intent_type, state=row.state, requested_quantity=row.requested_quantity, requested_price=row.requested_price, failure_code=row.failure_code, created_at=_utc(row.created_at), updated_at=_utc(row.updated_at), version=row.version)


def _protective_pair_from_orm(row: ProtectivePairORM) -> ProtectivePair:
    return ProtectivePair(id=row.id, pair_id=row.pair_id, correlation_id=row.correlation_id, execution_intent_id=row.execution_intent_id, environment=row.environment, symbol=row.symbol, position_side=row.position_side, direction=row.direction, quantity=row.quantity, state=row.state, recovery_required=row.recovery_required, blocking_reason=row.blocking_reason, created_at=_utc(row.created_at), updated_at=_utc(row.updated_at), version=row.version)


def _exchange_order_identity_from_orm(row: ExchangeOrderIdentityORM) -> ExchangeOrderIdentity:
    return ExchangeOrderIdentity(id=row.id, protective_pair_id=row.protective_pair_id, environment=row.environment, symbol=row.symbol, leg_type=row.leg_type, client_algo_id=row.client_algo_id, exchange_algo_id=row.exchange_algo_id, exchange_order_id=row.exchange_order_id, status=row.status, trigger_price=row.trigger_price, created_at=_utc(row.created_at), updated_at=_utc(row.updated_at), version=row.version)


def _recovery_event_from_orm(row: RecoveryEventORM) -> RecoveryEvent:
    return RecoveryEvent(id=row.id, correlation_id=row.correlation_id, protective_pair_id=row.protective_pair_id, event_type=row.event_type, from_state=row.from_state, to_state=row.to_state, reason_code=row.reason_code, result=row.result, created_at=_utc(row.created_at))


def _audit_event_from_orm(row: AuditEventORM) -> AuditEvent:
    return AuditEvent(id=row.id, correlation_id=row.correlation_id, category=row.category, action=row.action, environment=row.environment, symbol=row.symbol, result=row.result, error_code=row.error_code, metadata_json=deepcopy(row.metadata_json), created_at=_utc(row.created_at))




def _live_execution_permit_from_orm(row: LiveExecutionPermitORM) -> LiveExecutionPermit:
    return LiveExecutionPermit(
        id=row.id,
        permit_id=row.permit_id,
        operation=row.operation,
        environment=row.environment,
        symbol=row.symbol,
        request_fingerprint=row.request_fingerprint,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        state=row.state,
        issued_at=_utc(row.issued_at),
        expires_at=_utc(row.expires_at),
        consumed_at=None if row.consumed_at is None else _utc(row.consumed_at),
        revoked_at=None if row.revoked_at is None else _utc(row.revoked_at),
        expired_at=None if row.expired_at is None else _utc(row.expired_at),
        issued_by=row.issued_by,
        revocation_reason_code=row.revocation_reason_code,
        consumption_correlation_id=row.consumption_correlation_id,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        version=row.version,
    )

def _kill_switch_state_from_orm(row: KillSwitchStateORM) -> KillSwitchState:
    return KillSwitchState(
        id=row.id,
        scope=row.scope,
        environment=row.environment,
        symbol=row.symbol,
        state=row.state,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        version=row.version,
    )


class SqlAlchemyExecutionIntentRepository(ExecutionIntentRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, intent: ExecutionIntent) -> ExecutionIntent:
        validate_state(intent.state, EXECUTION_INTENT_STATES)
        row = ExecutionIntentORM(**intent.__dict__)
        self.session.add(row)
        _safe_flush(self.session)
        return _execution_intent_from_orm(row)

    def get_by_id(self, intent_id: UUID) -> ExecutionIntent | None:
        row = self.session.get(ExecutionIntentORM, intent_id)
        return None if row is None else _execution_intent_from_orm(row)

    def get_by_correlation_id(self, correlation_id: UUID) -> ExecutionIntent | None:
        row = self.session.scalar(select(ExecutionIntentORM).where(ExecutionIntentORM.correlation_id == correlation_id))
        return None if row is None else _execution_intent_from_orm(row)

    def update_state(self, intent_id: UUID, expected_version: int, state: str, failure_code: str | None = None) -> ExecutionIntent:
        validate_state(state, EXECUTION_INTENT_STATES)
        result = self.session.execute(
            update(ExecutionIntentORM)
            .where(ExecutionIntentORM.id == intent_id, ExecutionIntentORM.version == expected_version)
            .values(state=state, failure_code=failure_code, updated_at=utc_now(), version=ExecutionIntentORM.version + 1)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise OptimisticLockError("execution intent version conflict")
        self.session.expire_all()
        row = self.session.scalar(select(ExecutionIntentORM).where(ExecutionIntentORM.id == intent_id).execution_options(populate_existing=True))
        if row is None:
            raise OptimisticLockError("execution intent refresh conflict")
        return _execution_intent_from_orm(row)




class SqlAlchemyLiveExecutionPermitRepository(LiveExecutionPermitRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_issued(self, permit: LiveExecutionPermit) -> LiveExecutionPermit:
        if permit.state != LiveExecutionPermitState.ISSUED:
            raise PersistenceValidationError("permit create requires ISSUED state")
        row = LiveExecutionPermitORM(
            id=permit.id,
            permit_id=permit.permit_id,
            operation=permit.operation.value,
            environment=permit.environment,
            symbol=permit.symbol,
            request_fingerprint=permit.request_fingerprint,
            subject_type=permit.subject_type,
            subject_id=permit.subject_id,
            state=permit.state.value,
            issued_at=permit.issued_at,
            expires_at=permit.expires_at,
            consumed_at=permit.consumed_at,
            revoked_at=permit.revoked_at,
            expired_at=permit.expired_at,
            issued_by=permit.issued_by,
            revocation_reason_code=permit.revocation_reason_code,
            consumption_correlation_id=permit.consumption_correlation_id,
            created_at=permit.created_at,
            updated_at=permit.updated_at,
            version=permit.version,
        )
        self.session.add(row)
        _safe_flush(self.session)
        return _live_execution_permit_from_orm(row)

    def get_by_id(self, permit_id: UUID) -> LiveExecutionPermit | None:
        row = self.session.get(LiveExecutionPermitORM, permit_id)
        return None if row is None else _live_execution_permit_from_orm(row)

    def get_by_permit_id(self, permit_id: str) -> LiveExecutionPermit | None:
        row = self.session.scalar(select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == permit_id))
        return None if row is None else _live_execution_permit_from_orm(row)

    def find_consumed_by_correlation_id(self, consumption_correlation_id: UUID) -> LiveExecutionPermit | None:
        row = self.session.scalar(
            select(LiveExecutionPermitORM)
            .where(
                LiveExecutionPermitORM.consumption_correlation_id == consumption_correlation_id,
                LiveExecutionPermitORM.state == LiveExecutionPermitState.CONSUMED.value,
            )
            .order_by(LiveExecutionPermitORM.consumed_at.asc(), LiveExecutionPermitORM.id.asc())
            .limit(1)
        )
        return None if row is None else _live_execution_permit_from_orm(row)

    def get_active_match(self, environment: str, symbol: str, operation: LiveExecutionOperation, subject_type: str, subject_id: str, request_fingerprint: str) -> LiveExecutionPermit | None:
        row = self.session.scalar(
            select(LiveExecutionPermitORM)
            .where(
                LiveExecutionPermitORM.environment == environment,
                LiveExecutionPermitORM.symbol == symbol,
                LiveExecutionPermitORM.operation == operation.value,
                LiveExecutionPermitORM.subject_type == subject_type,
                LiveExecutionPermitORM.subject_id == subject_id,
                LiveExecutionPermitORM.request_fingerprint == request_fingerprint,
                LiveExecutionPermitORM.state == LiveExecutionPermitState.ISSUED.value,
            )
            .order_by(LiveExecutionPermitORM.issued_at.asc(), LiveExecutionPermitORM.id.asc())
        )
        return None if row is None else _live_execution_permit_from_orm(row)

    def list_by_subject(self, environment: str, symbol: str, subject_type: str, subject_id: str, limit: int) -> list[LiveExecutionPermit]:
        _validate_pagination(limit, 0)
        statement = (
            select(LiveExecutionPermitORM)
            .where(
                LiveExecutionPermitORM.environment == environment,
                LiveExecutionPermitORM.symbol == symbol,
                LiveExecutionPermitORM.subject_type == subject_type,
                LiveExecutionPermitORM.subject_id == subject_id,
            )
            .order_by(LiveExecutionPermitORM.created_at.asc(), LiveExecutionPermitORM.id.asc())
            .limit(limit)
        )
        return [_live_execution_permit_from_orm(row) for row in self.session.scalars(statement).all()]

    def expire_due_active_match(self, environment: str, symbol: str, operation: LiveExecutionOperation, subject_type: str, subject_id: str, request_fingerprint: str, now: datetime, limit: int = 100) -> list[LiveExecutionPermit]:
        _validate_pagination(limit, 0)
        rows = list(
            self.session.scalars(
                select(LiveExecutionPermitORM)
                .where(
                    LiveExecutionPermitORM.environment == environment,
                    LiveExecutionPermitORM.symbol == symbol,
                    LiveExecutionPermitORM.operation == operation.value,
                    LiveExecutionPermitORM.subject_type == subject_type,
                    LiveExecutionPermitORM.subject_id == subject_id,
                    LiveExecutionPermitORM.request_fingerprint == request_fingerprint,
                    LiveExecutionPermitORM.state == LiveExecutionPermitState.ISSUED.value,
                    LiveExecutionPermitORM.expires_at <= now,
                )
                .order_by(LiveExecutionPermitORM.expires_at.asc(), LiveExecutionPermitORM.id.asc())
                .limit(limit)
            ).all()
        )
        expired: list[LiveExecutionPermit] = []
        for row in rows:
            expired.append(self.expire_if_issued(row.permit_id, row.version, now))
        return expired

    def consume_if_issued(self, permit_id: str, expected_version: int, operation: LiveExecutionOperation, environment: str, symbol: str, subject_type: str, subject_id: str, request_fingerprint: str, consumption_correlation_id: UUID, now: datetime) -> LiveExecutionPermit:
        result = self.session.execute(
            update(LiveExecutionPermitORM)
            .where(
                LiveExecutionPermitORM.permit_id == permit_id,
                LiveExecutionPermitORM.version == expected_version,
                LiveExecutionPermitORM.state == LiveExecutionPermitState.ISSUED.value,
                LiveExecutionPermitORM.expires_at > now,
                LiveExecutionPermitORM.operation == operation.value,
                LiveExecutionPermitORM.environment == environment,
                LiveExecutionPermitORM.symbol == symbol,
                LiveExecutionPermitORM.subject_type == subject_type,
                LiveExecutionPermitORM.subject_id == subject_id,
                LiveExecutionPermitORM.request_fingerprint == request_fingerprint,
                LiveExecutionPermitORM.consumption_correlation_id.is_(None),
            )
            .values(
                state=LiveExecutionPermitState.CONSUMED.value,
                consumed_at=now,
                consumption_correlation_id=consumption_correlation_id,
                updated_at=now,
                version=LiveExecutionPermitORM.version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise OptimisticLockError("live execution permit consume conflict")
        self.session.expire_all()
        row = self.session.scalar(select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == permit_id).execution_options(populate_existing=True))
        if row is None:
            raise OptimisticLockError("live execution permit refresh conflict")
        return _live_execution_permit_from_orm(row)

    def revoke_if_issued(self, permit_id: str, expected_version: int, reason_code: str, now: datetime) -> LiveExecutionPermit:
        result = self.session.execute(
            update(LiveExecutionPermitORM)
            .where(
                LiveExecutionPermitORM.permit_id == permit_id,
                LiveExecutionPermitORM.version == expected_version,
                LiveExecutionPermitORM.state == LiveExecutionPermitState.ISSUED.value,
            )
            .values(
                state=LiveExecutionPermitState.REVOKED.value,
                revoked_at=now,
                revocation_reason_code=reason_code,
                updated_at=now,
                version=LiveExecutionPermitORM.version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise OptimisticLockError("live execution permit revoke conflict")
        self.session.expire_all()
        row = self.session.scalar(select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == permit_id).execution_options(populate_existing=True))
        if row is None:
            raise OptimisticLockError("live execution permit refresh conflict")
        return _live_execution_permit_from_orm(row)

    def expire_if_issued(self, permit_id: str, expected_version: int, now: datetime) -> LiveExecutionPermit:
        result = self.session.execute(
            update(LiveExecutionPermitORM)
            .where(
                LiveExecutionPermitORM.permit_id == permit_id,
                LiveExecutionPermitORM.version == expected_version,
                LiveExecutionPermitORM.state == LiveExecutionPermitState.ISSUED.value,
            )
            .values(
                state=LiveExecutionPermitState.EXPIRED.value,
                expired_at=now,
                updated_at=now,
                version=LiveExecutionPermitORM.version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise OptimisticLockError("live execution permit expire conflict")
        self.session.expire_all()
        row = self.session.scalar(select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == permit_id).execution_options(populate_existing=True))
        if row is None:
            raise OptimisticLockError("live execution permit refresh conflict")
        return _live_execution_permit_from_orm(row)


class SqlAlchemyKillSwitchStateRepository(KillSwitchStateRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, state: KillSwitchState) -> KillSwitchState:
        if state.state not in KILL_SWITCH_STATES:
            raise PersistenceValidationError("unsupported kill switch state")
        row = KillSwitchStateORM(**state.__dict__)
        self.session.add(row)
        _safe_flush(self.session)
        return _kill_switch_state_from_orm(row)

    def get_by_scope(self, scope: str) -> KillSwitchState | None:
        row = self.session.scalar(select(KillSwitchStateORM).where(KillSwitchStateORM.scope == scope))
        return None if row is None else _kill_switch_state_from_orm(row)

    def update_state(self, state_id: UUID, expected_version: int, state: str) -> KillSwitchState:
        if state not in KILL_SWITCH_STATES:
            raise PersistenceValidationError("unsupported kill switch state")
        result = self.session.execute(
            update(KillSwitchStateORM)
            .where(KillSwitchStateORM.id == state_id, KillSwitchStateORM.version == expected_version)
            .values(state=state, updated_at=utc_now(), version=KillSwitchStateORM.version + 1)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise OptimisticLockError("kill switch state version conflict")
        self.session.expire_all()
        row = self.session.scalar(
            select(KillSwitchStateORM)
            .where(KillSwitchStateORM.id == state_id)
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise OptimisticLockError("kill switch state refresh conflict")
        return _kill_switch_state_from_orm(row)


class SqlAlchemyProtectivePairRepository(ProtectivePairRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, pair: ProtectivePair) -> ProtectivePair:
        validate_state(pair.state, PROTECTIVE_PAIR_STATES)
        row = ProtectivePairORM(**pair.__dict__)
        self.session.add(row)
        _safe_flush(self.session)
        return _protective_pair_from_orm(row)

    def get_by_id(self, pair_id: UUID) -> ProtectivePair | None:
        row = self.session.get(ProtectivePairORM, pair_id)
        return None if row is None else _protective_pair_from_orm(row)

    def get_by_pair_id(self, pair_id: str) -> ProtectivePair | None:
        row = self.session.scalar(select(ProtectivePairORM).where(ProtectivePairORM.pair_id == pair_id))
        return None if row is None else _protective_pair_from_orm(row)

    def update_state(self, pair_id: UUID, expected_version: int, state: str, recovery_required: bool | None = None, blocking_reason: str | None = None) -> ProtectivePair:
        validate_state(state, PROTECTIVE_PAIR_STATES)
        values: dict[str, Any] = {
            "state": state,
            "blocking_reason": blocking_reason,
            "updated_at": utc_now(),
            "version": ProtectivePairORM.version + 1,
        }
        if recovery_required is not None:
            values["recovery_required"] = recovery_required
        result = self.session.execute(
            update(ProtectivePairORM)
            .where(ProtectivePairORM.id == pair_id, ProtectivePairORM.version == expected_version)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise OptimisticLockError("protective pair version conflict")
        self.session.expire_all()
        row = self.session.scalar(select(ProtectivePairORM).where(ProtectivePairORM.id == pair_id).execution_options(populate_existing=True))
        if row is None:
            raise OptimisticLockError("protective pair refresh conflict")
        return _protective_pair_from_orm(row)


class SqlAlchemyExchangeOrderIdentityRepository(ExchangeOrderIdentityRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, identity: ExchangeOrderIdentity) -> ExchangeOrderIdentity:
        validate_leg_type(identity.leg_type)
        row = ExchangeOrderIdentityORM(**identity.__dict__)
        self.session.add(row)
        _safe_flush(self.session)
        return _exchange_order_identity_from_orm(row)

    def get_by_client_algo_id(self, environment: str, symbol: str, client_algo_id: str) -> ExchangeOrderIdentity | None:
        row = self.session.scalar(select(ExchangeOrderIdentityORM).where(ExchangeOrderIdentityORM.environment == environment, ExchangeOrderIdentityORM.symbol == symbol, ExchangeOrderIdentityORM.client_algo_id == client_algo_id))
        return None if row is None else _exchange_order_identity_from_orm(row)

    def update_status(self, identity_id: UUID, expected_version: int, status: str) -> ExchangeOrderIdentity:
        result = self.session.execute(
            update(ExchangeOrderIdentityORM)
            .where(ExchangeOrderIdentityORM.id == identity_id, ExchangeOrderIdentityORM.version == expected_version)
            .values(status=status, updated_at=utc_now(), version=ExchangeOrderIdentityORM.version + 1)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise OptimisticLockError("exchange order identity version conflict")
        self.session.expire_all()
        row = self.session.scalar(select(ExchangeOrderIdentityORM).where(ExchangeOrderIdentityORM.id == identity_id).execution_options(populate_existing=True))
        if row is None:
            raise OptimisticLockError("exchange order identity refresh conflict")
        return _exchange_order_identity_from_orm(row)

    def list_by_protective_pair_id(self, protective_pair_id: UUID, limit: int, offset: int = 0) -> list[ExchangeOrderIdentity]:
        _validate_pagination(limit, offset)
        statement = (
            select(ExchangeOrderIdentityORM)
            .where(ExchangeOrderIdentityORM.protective_pair_id == protective_pair_id)
            .order_by(
                case((ExchangeOrderIdentityORM.leg_type == "STOP", 0), else_=1),
                ExchangeOrderIdentityORM.created_at.asc(),
                ExchangeOrderIdentityORM.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return [_exchange_order_identity_from_orm(row) for row in self.session.scalars(statement).all()]


class SqlAlchemyRecoveryEventRepository(RecoveryEventRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(self, event: RecoveryEvent) -> RecoveryEvent:
        row = RecoveryEventORM(**event.__dict__)
        self.session.add(row)
        _safe_flush(self.session)
        return _recovery_event_from_orm(row)

    def list_by_protective_pair_id(self, protective_pair_id: UUID, limit: int, offset: int = 0) -> list[RecoveryEvent]:
        _validate_pagination(limit, offset)
        statement = (
            select(RecoveryEventORM)
            .where(RecoveryEventORM.protective_pair_id == protective_pair_id)
            .order_by(RecoveryEventORM.created_at.asc(), RecoveryEventORM.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return [_recovery_event_from_orm(row) for row in self.session.scalars(statement).all()]


class SqlAlchemyAuditEventRepository(AuditEventRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(self, event: AuditEvent) -> AuditEvent:
        sanitized = sanitize_audit_metadata(event.metadata_json)
        row = AuditEventORM(id=event.id, correlation_id=event.correlation_id, category=event.category, action=event.action, environment=event.environment, symbol=event.symbol, result=event.result, error_code=event.error_code, metadata_json=sanitized, created_at=event.created_at)
        self.session.add(row)
        _safe_flush(self.session)
        return _audit_event_from_orm(row)

    def list_by_correlation_id(self, correlation_id: UUID, limit: int, offset: int = 0) -> list[AuditEvent]:
        _validate_pagination(limit, offset)
        statement = (
            select(AuditEventORM)
            .where(AuditEventORM.correlation_id == correlation_id)
            .order_by(AuditEventORM.created_at.asc(), AuditEventORM.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return [_audit_event_from_orm(row) for row in self.session.scalars(statement).all()]
