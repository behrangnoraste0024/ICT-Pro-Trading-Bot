"""add durable kill switch state

Revision ID: 20260717_0290
Revises: 20260714_0286
Create Date: 2026-07-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260717_0290"
down_revision = "20260714_0286"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kill_switch_states",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("scope", sa.String(length=96), nullable=False, unique=True),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_kill_switch_states_scope", "kill_switch_states", ["scope"])
    op.create_index("ix_kill_switch_states_updated_at", "kill_switch_states", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_kill_switch_states_updated_at", table_name="kill_switch_states")
    op.drop_index("ix_kill_switch_states_scope", table_name="kill_switch_states")
    op.drop_table("kill_switch_states")
