"""add durable live execution permits

Revision ID: 20260722_0292
Revises: 20260717_0290
Create Date: 2026-07-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260722_0292"
down_revision = "20260717_0290"
branch_labels = None
depends_on = None


def _uuid() -> sa.types.TypeEngine:
    return sa.Uuid(as_uuid=True)


def _timestamp() -> sa.types.TypeEngine:
    return sa.DateTime(timezone=True)


def _active_predicate():
    return sa.text("state = 'ISSUED'")


def upgrade() -> None:
    op.create_table(
        "live_execution_permits",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("permit_id", sa.String(length=96), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("subject_type", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("issued_at", _timestamp(), nullable=False),
        sa.Column("expires_at", _timestamp(), nullable=False),
        sa.Column("consumed_at", _timestamp(), nullable=True),
        sa.Column("revoked_at", _timestamp(), nullable=True),
        sa.Column("expired_at", _timestamp(), nullable=True),
        sa.Column("issued_by", sa.String(length=96), nullable=False),
        sa.Column("revocation_reason_code", sa.String(length=128), nullable=True),
        sa.Column("consumption_correlation_id", _uuid(), nullable=True),
        sa.Column("created_at", _timestamp(), nullable=False),
        sa.Column("updated_at", _timestamp(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("permit_id", name="uq_live_execution_permits_permit_id"),
        sa.UniqueConstraint("consumption_correlation_id", name="uq_live_execution_permits_consumption_correlation_id"),
        sa.CheckConstraint("state IN ('ISSUED', 'CONSUMED', 'REVOKED', 'EXPIRED')", name="ck_live_execution_permits_state"),
        sa.CheckConstraint("expires_at > issued_at", name="ck_live_execution_permits_expiry_order"),
        sa.CheckConstraint("version >= 1", name="ck_live_execution_permits_version"),
        sa.CheckConstraint(
            "((state = 'ISSUED' AND consumed_at IS NULL AND revoked_at IS NULL AND expired_at IS NULL AND consumption_correlation_id IS NULL AND revocation_reason_code IS NULL) "
            "OR (state = 'CONSUMED' AND consumed_at IS NOT NULL AND consumption_correlation_id IS NOT NULL AND revoked_at IS NULL AND expired_at IS NULL AND revocation_reason_code IS NULL) "
            "OR (state = 'REVOKED' AND revoked_at IS NOT NULL AND revocation_reason_code IS NOT NULL AND consumed_at IS NULL AND expired_at IS NULL AND consumption_correlation_id IS NULL) "
            "OR (state = 'EXPIRED' AND expired_at IS NOT NULL AND consumed_at IS NULL AND revoked_at IS NULL AND consumption_correlation_id IS NULL AND revocation_reason_code IS NULL))",
            name="ck_live_execution_permits_state_timestamps",
        ),
    )
    op.create_index("ix_live_execution_permits_permit_id", "live_execution_permits", ["permit_id"])
    op.create_index("ix_live_execution_permits_request_fingerprint", "live_execution_permits", ["request_fingerprint"])
    op.create_index("ix_live_execution_permits_state", "live_execution_permits", ["state"])
    op.create_index("ix_live_execution_permits_expires_at", "live_execution_permits", ["expires_at"])
    op.create_index("ix_live_execution_permits_subject", "live_execution_permits", ["subject_type", "subject_id"])
    op.create_index("ix_live_execution_permits_operation_scope", "live_execution_permits", ["operation", "environment", "symbol"])
    op.create_index("ix_live_execution_permits_consumption_correlation_id", "live_execution_permits", ["consumption_correlation_id"])
    op.create_index(
        "uq_live_execution_permits_active_match",
        "live_execution_permits",
        ["environment", "symbol", "operation", "subject_type", "subject_id", "request_fingerprint"],
        unique=True,
        postgresql_where=_active_predicate(),
        sqlite_where=_active_predicate(),
    )


def downgrade() -> None:
    op.drop_index("uq_live_execution_permits_active_match", table_name="live_execution_permits")
    op.drop_index("ix_live_execution_permits_consumption_correlation_id", table_name="live_execution_permits")
    op.drop_index("ix_live_execution_permits_operation_scope", table_name="live_execution_permits")
    op.drop_index("ix_live_execution_permits_subject", table_name="live_execution_permits")
    op.drop_index("ix_live_execution_permits_expires_at", table_name="live_execution_permits")
    op.drop_index("ix_live_execution_permits_state", table_name="live_execution_permits")
    op.drop_index("ix_live_execution_permits_request_fingerprint", table_name="live_execution_permits")
    op.drop_index("ix_live_execution_permits_permit_id", table_name="live_execution_permits")
    op.drop_table("live_execution_permits")
