from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timedelta
from typing import Any, Callable, Iterator
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from infrastructure.persistence.execution_repositories import SqlAlchemyAuditEventRepository, SqlAlchemyLiveExecutionPermitRepository
from infrastructure.persistence.schema_contract import validate_persistence_schema
from infrastructure.security.live_execution_request_fingerprint import LiveExecutionRequestFingerprint
from models.execution_persistence import AuditEvent, DuplicateIdentityError, OptimisticLockError
from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit import (
    PERMIT_ENVIRONMENT,
    PERMIT_REVOCATION_REASON_CODES,
    PERMIT_SYMBOL,
    LiveExecutionPermit,
    LiveExecutionPermitError,
    LiveExecutionPermitState,
    generate_permit_id,
    utc_now,
    validate_permit_id,
)

ISSUE_CONFIRMATION = "CONFIRM_TESTNET_ONE_TIME_EXECUTION_PERMIT"
REVOKE_CONFIRMATION = "CONFIRM_TESTNET_REVOKE_EXECUTION_PERMIT"
DEFAULT_TTL_SECONDS = 300
MIN_TTL_SECONDS = 30
MAX_TTL_SECONDS = 900
AUDIT_CATEGORY = "LIVE_EXECUTION_PERMIT"
AUDIT_METADATA_KEYS = {
    "permit_id",
    "operation",
    "environment",
    "symbol",
    "subject_type",
    "subject_id",
    "request_fingerprint",
    "state",
    "result",
    "code",
    "issued_at",
    "expires_at",
    "consumed_at",
    "revoked_at",
    "expired_at",
    "version",
    "consumption_correlation_id",
}
RUNTIME_EVIDENCE_EVENT_POLICY_EVALUATED = "POLICY_EVALUATED"
RUNTIME_EVIDENCE_EVENT_PERSISTENCE_OPENED = "PERSISTENCE_OPENED"
RUNTIME_EVIDENCE_EVENT_PERMIT_CONSUMED = "PERMIT_CONSUMED"
RUNTIME_EVIDENCE_EVENT_PERSISTENCE_COMMITTED = "PERSISTENCE_COMMITTED"
RUNTIME_EVIDENCE_EVENT_PERSISTENCE_CLOSED = "PERSISTENCE_CLOSED"
RUNTIME_EVIDENCE_EVENT_SIGNED = "SIGNED"
RUNTIME_EVIDENCE_EVENT_POST_ATTEMPTED = "POST_ATTEMPTED"
RUNTIME_EVIDENCE_EVENT_POST_COMPLETED = "POST_COMPLETED"
RUNTIME_EVIDENCE_ALLOWED_EVENTS = {
    RUNTIME_EVIDENCE_EVENT_POLICY_EVALUATED,
    RUNTIME_EVIDENCE_EVENT_PERSISTENCE_OPENED,
    RUNTIME_EVIDENCE_EVENT_PERMIT_CONSUMED,
    RUNTIME_EVIDENCE_EVENT_PERSISTENCE_COMMITTED,
    RUNTIME_EVIDENCE_EVENT_PERSISTENCE_CLOSED,
    RUNTIME_EVIDENCE_EVENT_SIGNED,
    RUNTIME_EVIDENCE_EVENT_POST_ATTEMPTED,
    RUNTIME_EVIDENCE_EVENT_POST_COMPLETED,
}
_RUNTIME_EVIDENCE_CAPTURE: ContextVar[dict[str, Any] | None] = ContextVar(
    "order_test_runtime_evidence_capture",
    default=None,
)


def begin_order_test_runtime_evidence_capture() -> Token[dict[str, Any] | None]:
    return _RUNTIME_EVIDENCE_CAPTURE.set(
        {
            "policy_evaluation_count": 0,
            "audit_record_count": 0,
            "recovery_required": None,
            "mutation_boundary_events": [],
        }
    )


def get_order_test_runtime_evidence() -> dict[str, Any] | None:
    capture = _RUNTIME_EVIDENCE_CAPTURE.get()
    if capture is None:
        return None
    return {
        "policy_evaluation_count": int(capture["policy_evaluation_count"]),
        "audit_record_count": int(capture["audit_record_count"]),
        "recovery_required": capture["recovery_required"],
        "mutation_boundary_events": list(capture["mutation_boundary_events"]),
    }


def reset_order_test_runtime_evidence_capture(token: Token[dict[str, Any] | None]) -> None:
    _RUNTIME_EVIDENCE_CAPTURE.reset(token)


def record_order_test_runtime_evidence_event(event: str) -> None:
    capture = _RUNTIME_EVIDENCE_CAPTURE.get()
    if capture is None:
        return
    if event not in RUNTIME_EVIDENCE_ALLOWED_EVENTS:
        raise LiveExecutionPermitPersistenceError("PERMIT_UNAVAILABLE")
    capture["mutation_boundary_events"].append(event)


def record_order_test_policy_evaluation(*, recovery_required: bool | None) -> None:
    capture = _RUNTIME_EVIDENCE_CAPTURE.get()
    if capture is None:
        return
    capture["policy_evaluation_count"] += 1
    capture["recovery_required"] = recovery_required
    record_order_test_runtime_evidence_event(RUNTIME_EVIDENCE_EVENT_POLICY_EVALUATED)


def record_order_test_audit_record() -> None:
    capture = _RUNTIME_EVIDENCE_CAPTURE.get()
    if capture is None:
        return
    capture["audit_record_count"] += 1


class LiveExecutionPermitPersistenceError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class LiveExecutionPermitPersistence:
    def __init__(
        self,
        env: dict[str, str] | None = None,
        engine_factory: Callable[..., Any] = create_engine,
        session_factory: Callable[..., Session] = Session,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self.env = os.environ if env is None else env
        self._engine_factory = engine_factory
        self._session_factory = session_factory
        self._now_provider = now_provider
        self._engine: Any | None = None

    def ensure_available(self) -> None:
        url = self.env.get("ICT_DATABASE_URL") or self.env.get("DATABASE_URL")
        if not isinstance(url, str) or not url.strip():
            raise LiveExecutionPermitPersistenceError("PERMIT_UNAVAILABLE")
        try:
            engine = self._engine_factory(url, future=True)
            with engine.connect() as connection:
                connection.execute(select(1)).scalar_one()
                if not validate_persistence_schema(connection):
                    raise LiveExecutionPermitPersistenceError("PERMIT_UNAVAILABLE")
            self._engine = engine
            record_order_test_runtime_evidence_event(RUNTIME_EVIDENCE_EVENT_PERSISTENCE_OPENED)
        except LiveExecutionPermitPersistenceError:
            if "engine" in locals():
                engine.dispose()
            raise
        except Exception as exc:
            if "engine" in locals():
                engine.dispose()
            raise LiveExecutionPermitPersistenceError("PERMIT_UNAVAILABLE") from exc

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            record_order_test_runtime_evidence_event(RUNTIME_EVIDENCE_EVENT_PERSISTENCE_CLOSED)

    def issue(
        self,
        fingerprint: LiveExecutionRequestFingerprint,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        issued_by: str,
        confirmation: str,
    ) -> LiveExecutionPermit:
        if confirmation != ISSUE_CONFIRMATION:
            raise LiveExecutionPermitPersistenceError("PERMIT_CONFIRMATION_REQUIRED")
        ttl = self._validate_ttl(ttl_seconds)
        now = self._now_provider()
        expires_at = now + timedelta(seconds=ttl)
        try:
            with self._transaction() as session:
                repo = SqlAlchemyLiveExecutionPermitRepository(session)
                audit_repo = SqlAlchemyAuditEventRepository(session)
                active = repo.get_active_match(
                    fingerprint.environment,
                    fingerprint.symbol,
                    fingerprint.operation,
                    fingerprint.subject_type,
                    fingerprint.subject_id,
                    fingerprint.request_fingerprint,
                )
                if active is not None:
                    if active.expires_at > now:
                        raise LiveExecutionPermitPersistenceError("PERMIT_DUPLICATE_ACTIVE")
                    expired = repo.expire_if_issued(active.permit_id, active.version, now)
                    audit_repo.append(self._audit("PERMIT_EXPIRED", "PASS", expired))
                permit = LiveExecutionPermit(
                    permit_id=generate_permit_id(),
                    operation=fingerprint.operation,
                    environment=fingerprint.environment,
                    symbol=fingerprint.symbol,
                    request_fingerprint=fingerprint.request_fingerprint,
                    subject_type=fingerprint.subject_type,
                    subject_id=fingerprint.subject_id,
                    state=LiveExecutionPermitState.ISSUED,
                    issued_at=now,
                    expires_at=expires_at,
                    issued_by=issued_by,
                    created_at=now,
                    updated_at=now,
                )
                saved = repo.create_issued(permit)
                audit_repo.append(self._audit("PERMIT_ISSUED", "PASS", saved))
                return saved
        except LiveExecutionPermitPersistenceError:
            raise
        except DuplicateIdentityError as exc:
            raise LiveExecutionPermitPersistenceError("PERMIT_DUPLICATE_ACTIVE") from exc
        except LiveExecutionPermitError as exc:
            raise LiveExecutionPermitPersistenceError(exc.code) from exc
        except Exception as exc:
            raise LiveExecutionPermitPersistenceError("PERMIT_UNAVAILABLE") from exc

    def show(self, permit_id: str) -> tuple[LiveExecutionPermit | None, bool]:
        try:
            validate_permit_id(permit_id)
            with self._session() as session:
                permit = SqlAlchemyLiveExecutionPermitRepository(session).get_by_permit_id(permit_id)
                effective_expired = bool(
                    permit is not None
                    and permit.state == LiveExecutionPermitState.ISSUED
                    and permit.expires_at <= self._now_provider()
                )
                return permit, effective_expired
        except LiveExecutionPermitPersistenceError:
            raise
        except LiveExecutionPermitError as exc:
            raise LiveExecutionPermitPersistenceError(exc.code) from exc
        except Exception as exc:
            raise LiveExecutionPermitPersistenceError("PERMIT_UNAVAILABLE") from exc

    def revoke(self, permit_id: str, *, expected_version: int, reason_code: str, confirmation: str) -> LiveExecutionPermit:
        if confirmation != REVOKE_CONFIRMATION:
            raise LiveExecutionPermitPersistenceError("PERMIT_CONFIRMATION_REQUIRED")
        if reason_code not in PERMIT_REVOCATION_REASON_CODES:
            raise LiveExecutionPermitPersistenceError("PERMIT_INVALID")
        now = self._now_provider()
        permit = self._lookup_required(permit_id)
        if permit.state == LiveExecutionPermitState.CONSUMED:
            raise LiveExecutionPermitPersistenceError("PERMIT_ALREADY_CONSUMED")
        if permit.state == LiveExecutionPermitState.REVOKED:
            raise LiveExecutionPermitPersistenceError("PERMIT_ALREADY_REVOKED")
        if permit.state == LiveExecutionPermitState.EXPIRED:
            raise LiveExecutionPermitPersistenceError("PERMIT_ALREADY_EXPIRED")
        if permit.expires_at <= now:
            self.expire(permit_id, expected_version=expected_version, now=now)
            raise LiveExecutionPermitPersistenceError("PERMIT_ALREADY_EXPIRED")
        try:
            with self._transaction() as session:
                repo = SqlAlchemyLiveExecutionPermitRepository(session)
                audit_repo = SqlAlchemyAuditEventRepository(session)
                revoked = repo.revoke_if_issued(permit_id, expected_version, reason_code, now)
                audit_repo.append(self._audit("PERMIT_REVOKED", "PASS", revoked))
                return revoked
        except OptimisticLockError as exc:
            raise LiveExecutionPermitPersistenceError("PERMIT_VERSION_CONFLICT") from exc
        except LiveExecutionPermitError as exc:
            raise LiveExecutionPermitPersistenceError(exc.code) from exc
        except Exception as exc:
            raise LiveExecutionPermitPersistenceError("PERMIT_UNAVAILABLE") from exc

    def expire(self, permit_id: str, *, expected_version: int, now: datetime | None = None) -> LiveExecutionPermit:
        now = self._now_provider() if now is None else now
        try:
            with self._transaction() as session:
                repo = SqlAlchemyLiveExecutionPermitRepository(session)
                audit_repo = SqlAlchemyAuditEventRepository(session)
                expired = repo.expire_if_issued(permit_id, expected_version, now)
                audit_repo.append(self._audit("PERMIT_EXPIRED", "PASS", expired))
                return expired
        except OptimisticLockError as exc:
            raise LiveExecutionPermitPersistenceError("PERMIT_VERSION_CONFLICT") from exc
        except LiveExecutionPermitError as exc:
            raise LiveExecutionPermitPersistenceError(exc.code) from exc
        except Exception as exc:
            raise LiveExecutionPermitPersistenceError("PERMIT_UNAVAILABLE") from exc

    def consume(
        self,
        *,
        permit_id: str,
        expected_version: int,
        expected_operation: LiveExecutionOperation,
        expected_environment: str,
        expected_symbol: str,
        expected_subject_type: str,
        expected_subject_id: str,
        expected_request_fingerprint: str,
        consumption_correlation_id: UUID,
        now: datetime | None = None,
    ) -> LiveExecutionPermit:
        now = self._now_provider() if now is None else now
        try:
            with self._transaction(record_runtime_boundary=True) as session:
                repo = SqlAlchemyLiveExecutionPermitRepository(session)
                consumed = repo.consume_if_issued(
                    permit_id,
                    expected_version,
                    expected_operation,
                    expected_environment,
                    expected_symbol,
                    expected_subject_type,
                    expected_subject_id,
                    expected_request_fingerprint,
                    consumption_correlation_id,
                    now,
                )
                record_order_test_runtime_evidence_event(RUNTIME_EVIDENCE_EVENT_PERMIT_CONSUMED)
                SqlAlchemyAuditEventRepository(session).append(self._audit("PERMIT_CONSUMED", "PASS", consumed))
                record_order_test_audit_record()
                return consumed
        except OptimisticLockError:
            code = self._classify_consume_failure(
                permit_id,
                expected_operation,
                expected_environment,
                expected_symbol,
                expected_subject_type,
                expected_subject_id,
                expected_request_fingerprint,
                now,
            )
            raise LiveExecutionPermitPersistenceError(code) from None
        except IntegrityError:
            code = self._classify_consume_integrity_failure(permit_id, consumption_correlation_id)
            raise LiveExecutionPermitPersistenceError(code) from None
        except LiveExecutionPermitError as exc:
            raise LiveExecutionPermitPersistenceError(exc.code) from exc
        except Exception as exc:
            raise LiveExecutionPermitPersistenceError("PERMIT_UNAVAILABLE") from exc

    def _classify_consume_failure(
        self,
        permit_id: str,
        expected_operation: LiveExecutionOperation,
        expected_environment: str,
        expected_symbol: str,
        expected_subject_type: str,
        expected_subject_id: str,
        expected_request_fingerprint: str,
        now: datetime,
    ) -> str:
        permit = self._lookup_required(permit_id)
        if permit.state == LiveExecutionPermitState.CONSUMED:
            return "PERMIT_ALREADY_CONSUMED"
        if permit.state == LiveExecutionPermitState.REVOKED:
            return "PERMIT_ALREADY_REVOKED"
        if permit.state == LiveExecutionPermitState.EXPIRED:
            return "PERMIT_ALREADY_EXPIRED"
        if permit.expires_at <= now:
            self.expire(permit.permit_id, expected_version=permit.version, now=now)
            return "PERMIT_ALREADY_EXPIRED"
        if permit.operation != expected_operation or permit.environment != expected_environment or permit.symbol != expected_symbol:
            return "PERMIT_SCOPE_MISMATCH"
        if permit.subject_type != expected_subject_type or permit.subject_id != expected_subject_id:
            return "PERMIT_SUBJECT_MISMATCH"
        if permit.request_fingerprint != expected_request_fingerprint:
            return "PERMIT_FINGERPRINT_MISMATCH"
        return "PERMIT_VERSION_CONFLICT"

    def _classify_consume_integrity_failure(self, permit_id: str, consumption_correlation_id: UUID) -> str:
        try:
            validate_permit_id(permit_id)
            with self._session() as session:
                owner = SqlAlchemyLiveExecutionPermitRepository(session).find_consumed_by_correlation_id(consumption_correlation_id)
                if (
                    owner is not None
                    and owner.permit_id != permit_id
                    and owner.state == LiveExecutionPermitState.CONSUMED
                    and owner.consumption_correlation_id == consumption_correlation_id
                ):
                    return "PERMIT_CONSUMPTION_CORRELATION_CONFLICT"
                return "PERMIT_UNAVAILABLE"
        except LiveExecutionPermitError as exc:
            return exc.code
        except LiveExecutionPermitPersistenceError as exc:
            return exc.code
        except Exception:
            return "PERMIT_UNAVAILABLE"

    def _lookup_required(self, permit_id: str) -> LiveExecutionPermit:
        try:
            validate_permit_id(permit_id)
            with self._session() as session:
                permit = SqlAlchemyLiveExecutionPermitRepository(session).get_by_permit_id(permit_id)
                if permit is None:
                    raise LiveExecutionPermitPersistenceError("PERMIT_NOT_FOUND")
                return permit
        except LiveExecutionPermitPersistenceError:
            raise
        except LiveExecutionPermitError as exc:
            raise LiveExecutionPermitPersistenceError(exc.code) from exc
        except Exception as exc:
            raise LiveExecutionPermitPersistenceError("PERMIT_UNAVAILABLE") from exc

    @staticmethod
    def _validate_ttl(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not MIN_TTL_SECONDS <= value <= MAX_TTL_SECONDS:
            raise LiveExecutionPermitPersistenceError("PERMIT_TTL_INVALID")
        return value

    @staticmethod
    def _metadata(permit: LiveExecutionPermit, action: str) -> dict[str, Any]:
        metadata = {
            "permit_id": permit.permit_id,
            "operation": permit.operation.value,
            "environment": permit.environment,
            "symbol": permit.symbol,
            "subject_type": permit.subject_type,
            "subject_id": permit.subject_id,
            "request_fingerprint": permit.request_fingerprint,
            "state": permit.state.value,
            "result": action,
            "code": action,
            "issued_at": permit.issued_at.isoformat(),
            "expires_at": permit.expires_at.isoformat(),
            "consumed_at": None if permit.consumed_at is None else permit.consumed_at.isoformat(),
            "revoked_at": None if permit.revoked_at is None else permit.revoked_at.isoformat(),
            "expired_at": None if permit.expired_at is None else permit.expired_at.isoformat(),
            "version": permit.version,
            "consumption_correlation_id": None if permit.consumption_correlation_id is None else str(permit.consumption_correlation_id),
        }
        if set(metadata) != AUDIT_METADATA_KEYS:
            raise LiveExecutionPermitPersistenceError("PERMIT_UNAVAILABLE")
        return metadata

    @classmethod
    def _audit(cls, action: str, result: str, permit: LiveExecutionPermit) -> AuditEvent:
        return AuditEvent(
            category=AUDIT_CATEGORY,
            action=action,
            environment=PERMIT_ENVIRONMENT,
            symbol=PERMIT_SYMBOL,
            result=result,
            metadata_json=cls._metadata(permit, action),
            created_at=permit.updated_at,
        )

    @contextmanager
    def _session(self) -> Iterator[Session]:
        if self._engine is None:
            raise LiveExecutionPermitPersistenceError("PERMIT_UNAVAILABLE")
        session = self._session_factory(bind=self._engine, future=True, autoflush=False, expire_on_commit=False)
        try:
            yield session
        finally:
            session.close()

    @contextmanager
    def _transaction(self, *, record_runtime_boundary: bool = False) -> Iterator[Session]:
        with self._session() as session:
            try:
                with session.begin():
                    yield session
                if record_runtime_boundary:
                    record_order_test_runtime_evidence_event(RUNTIME_EVIDENCE_EVENT_PERSISTENCE_COMMITTED)
            except Exception:
                session.rollback()
                raise
