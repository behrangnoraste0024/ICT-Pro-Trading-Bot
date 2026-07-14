"""add execution persistence foundation

Revision ID: 20260714_0286
Revises:
Create Date: 2026-07-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260714_0286"
down_revision = None
branch_labels = None
depends_on = None


def _uuid() -> sa.types.TypeEngine:
    return sa.Uuid(as_uuid=True)


def _numeric() -> sa.types.TypeEngine:
    return sa.Numeric(38, 18)


def _timestamp() -> sa.types.TypeEngine:
    return sa.DateTime(timezone=True)


def _metadata_json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "execution_intents",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("correlation_id", _uuid(), nullable=False, unique=True),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("intent_type", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("requested_quantity", _numeric(), nullable=True),
        sa.Column("requested_price", _numeric(), nullable=True),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", _timestamp(), nullable=False),
        sa.Column("updated_at", _timestamp(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_execution_intents_correlation_id", "execution_intents", ["correlation_id"])
    op.create_index("ix_execution_intents_state", "execution_intents", ["state"])
    op.create_index("ix_execution_intents_created_at", "execution_intents", ["created_at"])

    op.create_table(
        "protective_pairs",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("pair_id", sa.String(length=80), nullable=False, unique=True),
        sa.Column("correlation_id", _uuid(), nullable=False),
        sa.Column("execution_intent_id", _uuid(), sa.ForeignKey("execution_intents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("position_side", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("quantity", _numeric(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("recovery_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("blocking_reason", sa.String(length=256), nullable=True),
        sa.Column("created_at", _timestamp(), nullable=False),
        sa.Column("updated_at", _timestamp(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_protective_pairs_correlation_id", "protective_pairs", ["correlation_id"])
    op.create_index("ix_protective_pairs_pair_id", "protective_pairs", ["pair_id"])
    op.create_index("ix_protective_pairs_state", "protective_pairs", ["state"])
    op.create_index("ix_protective_pairs_created_at", "protective_pairs", ["created_at"])

    op.create_table(
        "exchange_order_identities",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("protective_pair_id", _uuid(), sa.ForeignKey("protective_pairs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("leg_type", sa.String(length=16), nullable=False),
        sa.Column("client_algo_id", sa.String(length=80), nullable=False),
        sa.Column("exchange_algo_id", sa.String(length=80), nullable=True),
        sa.Column("exchange_order_id", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trigger_price", _numeric(), nullable=True),
        sa.Column("created_at", _timestamp(), nullable=False),
        sa.Column("updated_at", _timestamp(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("environment", "symbol", "client_algo_id", name="uq_exchange_order_identity_client_algo"),
        sa.UniqueConstraint("protective_pair_id", "leg_type", name="uq_exchange_order_identity_pair_leg"),
    )
    op.create_index("ix_exchange_order_identities_client_algo_id", "exchange_order_identities", ["client_algo_id"])
    op.create_index("ix_exchange_order_identities_state", "exchange_order_identities", ["status"])
    op.create_index("ix_exchange_order_identities_created_at", "exchange_order_identities", ["created_at"])

    op.create_table(
        "recovery_events",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("correlation_id", _uuid(), nullable=False),
        sa.Column("protective_pair_id", _uuid(), sa.ForeignKey("protective_pairs.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("from_state", sa.String(length=32), nullable=True),
        sa.Column("to_state", sa.String(length=32), nullable=True),
        sa.Column("reason_code", sa.String(length=128), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("created_at", _timestamp(), nullable=False),
    )
    op.create_index("ix_recovery_events_correlation_id", "recovery_events", ["correlation_id"])
    op.create_index("ix_recovery_events_created_at", "recovery_events", ["created_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("correlation_id", _uuid(), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", _metadata_json(), nullable=True),
        sa.Column("created_at", _timestamp(), nullable=False),
    )
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_correlation_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_recovery_events_created_at", table_name="recovery_events")
    op.drop_index("ix_recovery_events_correlation_id", table_name="recovery_events")
    op.drop_table("recovery_events")
    op.drop_index("ix_exchange_order_identities_created_at", table_name="exchange_order_identities")
    op.drop_index("ix_exchange_order_identities_state", table_name="exchange_order_identities")
    op.drop_index("ix_exchange_order_identities_client_algo_id", table_name="exchange_order_identities")
    op.drop_table("exchange_order_identities")
    op.drop_index("ix_protective_pairs_created_at", table_name="protective_pairs")
    op.drop_index("ix_protective_pairs_state", table_name="protective_pairs")
    op.drop_index("ix_protective_pairs_pair_id", table_name="protective_pairs")
    op.drop_index("ix_protective_pairs_correlation_id", table_name="protective_pairs")
    op.drop_table("protective_pairs")
    op.drop_index("ix_execution_intents_created_at", table_name="execution_intents")
    op.drop_index("ix_execution_intents_state", table_name="execution_intents")
    op.drop_index("ix_execution_intents_correlation_id", table_name="execution_intents")
    op.drop_table("execution_intents")
