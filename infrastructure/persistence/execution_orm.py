from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator, Uuid


class AwareDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("timezone-aware datetime required")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class PreciseDecimal(TypeDecorator):
    impl = Numeric(38, 18)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(96))
        return dialect.type_descriptor(Numeric(38, 18))

    def process_bind_param(self, value: Decimal | str | int | float | None, dialect) -> str | Decimal | None:
        if value is None:
            return None
        decimal = Decimal(str(value))
        if dialect.name == "sqlite":
            return format(decimal, "f")
        return decimal

    def process_result_value(self, value: Any, dialect) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))


class AuditMetadataJSON(TypeDecorator):
    """JSON for SQLite tests and JSONB for PostgreSQL persistence."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class ExecutionPersistenceBase(DeclarativeBase):
    pass


class KillSwitchStateORM(ExecutionPersistenceBase):
    __tablename__ = "kill_switch_states"

    id: Mapped[Any] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    scope: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index("ix_kill_switch_states_scope", "scope"),
        Index("ix_kill_switch_states_updated_at", "updated_at"),
    )


class LiveExecutionPermitORM(ExecutionPersistenceBase):
    __tablename__ = "live_execution_permits"

    id: Mapped[Any] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    permit_id: Mapped[str] = mapped_column(String(96), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    issued_by: Mapped[str] = mapped_column(String(96), nullable=False)
    revocation_reason_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    consumption_correlation_id: Mapped[Any | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("permit_id", name="uq_live_execution_permits_permit_id"),
        UniqueConstraint("consumption_correlation_id", name="uq_live_execution_permits_consumption_correlation_id"),
        CheckConstraint("state IN ('ISSUED', 'CONSUMED', 'REVOKED', 'EXPIRED')", name="ck_live_execution_permits_state"),
        CheckConstraint("expires_at > issued_at", name="ck_live_execution_permits_expiry_order"),
        CheckConstraint("version >= 1", name="ck_live_execution_permits_version"),
        CheckConstraint(
            "((state = 'ISSUED' AND consumed_at IS NULL AND revoked_at IS NULL AND expired_at IS NULL AND consumption_correlation_id IS NULL AND revocation_reason_code IS NULL) "
            "OR (state = 'CONSUMED' AND consumed_at IS NOT NULL AND consumption_correlation_id IS NOT NULL AND revoked_at IS NULL AND expired_at IS NULL AND revocation_reason_code IS NULL) "
            "OR (state = 'REVOKED' AND revoked_at IS NOT NULL AND revocation_reason_code IS NOT NULL AND consumed_at IS NULL AND expired_at IS NULL AND consumption_correlation_id IS NULL) "
            "OR (state = 'EXPIRED' AND expired_at IS NOT NULL AND consumed_at IS NULL AND revoked_at IS NULL AND consumption_correlation_id IS NULL AND revocation_reason_code IS NULL))",
            name="ck_live_execution_permits_state_timestamps",
        ),
        Index("ix_live_execution_permits_permit_id", "permit_id"),
        Index("ix_live_execution_permits_request_fingerprint", "request_fingerprint"),
        Index("ix_live_execution_permits_state", "state"),
        Index("ix_live_execution_permits_expires_at", "expires_at"),
        Index("ix_live_execution_permits_subject", "subject_type", "subject_id"),
        Index("ix_live_execution_permits_operation_scope", "operation", "environment", "symbol"),
        Index("ix_live_execution_permits_consumption_correlation_id", "consumption_correlation_id"),
        Index(
            "uq_live_execution_permits_active_match",
            "environment",
            "symbol",
            "operation",
            "subject_type",
            "subject_id",
            "request_fingerprint",
            unique=True,
            sqlite_where=text("state = 'ISSUED'"),
            postgresql_where=text("state = 'ISSUED'"),
        ),
    )


class ExecutionIntentORM(ExecutionPersistenceBase):
    __tablename__ = "execution_intents"

    id: Mapped[Any] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    correlation_id: Mapped[Any] = mapped_column(Uuid(as_uuid=True), nullable=False, unique=True)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    intent_type: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_quantity: Mapped[Decimal | None] = mapped_column(PreciseDecimal, nullable=True)
    requested_price: Mapped[Decimal | None] = mapped_column(PreciseDecimal, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    protective_pairs: Mapped[list["ProtectivePairORM"]] = relationship(back_populates="execution_intent")

    __table_args__ = (
        Index("ix_execution_intents_correlation_id", "correlation_id"),
        Index("ix_execution_intents_state", "state"),
        Index("ix_execution_intents_created_at", "created_at"),
    )


class ProtectivePairORM(ExecutionPersistenceBase):
    __tablename__ = "protective_pairs"

    id: Mapped[Any] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    pair_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    correlation_id: Mapped[Any] = mapped_column(Uuid(as_uuid=True), nullable=False)
    execution_intent_id: Mapped[Any] = mapped_column(Uuid(as_uuid=True), ForeignKey("execution_intents.id", ondelete="RESTRICT"), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    position_side: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(PreciseDecimal, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    recovery_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    blocking_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    execution_intent: Mapped[ExecutionIntentORM] = relationship(back_populates="protective_pairs")
    order_identities: Mapped[list["ExchangeOrderIdentityORM"]] = relationship(back_populates="protective_pair")
    recovery_events: Mapped[list["RecoveryEventORM"]] = relationship(back_populates="protective_pair")

    __table_args__ = (
        Index("ix_protective_pairs_correlation_id", "correlation_id"),
        Index("ix_protective_pairs_pair_id", "pair_id"),
        Index("ix_protective_pairs_state", "state"),
        Index("ix_protective_pairs_created_at", "created_at"),
    )


class ExchangeOrderIdentityORM(ExecutionPersistenceBase):
    __tablename__ = "exchange_order_identities"

    id: Mapped[Any] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    protective_pair_id: Mapped[Any] = mapped_column(Uuid(as_uuid=True), ForeignKey("protective_pairs.id", ondelete="RESTRICT"), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    leg_type: Mapped[str] = mapped_column(String(16), nullable=False)
    client_algo_id: Mapped[str] = mapped_column(String(80), nullable=False)
    exchange_algo_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    exchange_order_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_price: Mapped[Decimal | None] = mapped_column(PreciseDecimal, nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    protective_pair: Mapped[ProtectivePairORM] = relationship(back_populates="order_identities")

    __table_args__ = (
        UniqueConstraint("environment", "symbol", "client_algo_id", name="uq_exchange_order_identity_client_algo"),
        UniqueConstraint("protective_pair_id", "leg_type", name="uq_exchange_order_identity_pair_leg"),
        Index("ix_exchange_order_identities_client_algo_id", "client_algo_id"),
        Index("ix_exchange_order_identities_state", "status"),
        Index("ix_exchange_order_identities_created_at", "created_at"),
    )


class RecoveryEventORM(ExecutionPersistenceBase):
    __tablename__ = "recovery_events"

    id: Mapped[Any] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    correlation_id: Mapped[Any] = mapped_column(Uuid(as_uuid=True), nullable=False)
    protective_pair_id: Mapped[Any | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("protective_pairs.id", ondelete="RESTRICT"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)

    protective_pair: Mapped[ProtectivePairORM | None] = relationship(back_populates="recovery_events")

    __table_args__ = (
        Index("ix_recovery_events_correlation_id", "correlation_id"),
        Index("ix_recovery_events_created_at", "created_at"),
    )


class AuditEventORM(ExecutionPersistenceBase):
    __tablename__ = "audit_events"

    id: Mapped[Any] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    correlation_id: Mapped[Any | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(AuditMetadataJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)

    __table_args__ = (
        Index("ix_audit_events_correlation_id", "correlation_id"),
        Index("ix_audit_events_created_at", "created_at"),
    )
