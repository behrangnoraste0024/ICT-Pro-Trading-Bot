from __future__ import annotations

from typing import Any

from sqlalchemy import MetaData, Table, inspect, select

PERSISTENCE_REVISION = "20260714_0286"
REQUIRED_PERSISTENCE_TABLES = {
    "execution_intents",
    "protective_pairs",
    "exchange_order_identities",
    "recovery_events",
    "audit_events",
}


def validate_persistence_schema(connection: Any) -> bool:
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    if not REQUIRED_PERSISTENCE_TABLES.issubset(table_names) or not inspector.has_table("alembic_version"):
        return False
    version_table = Table("alembic_version", MetaData(), autoload_with=connection)
    revision = connection.scalar(select(version_table.c.version_num))
    return isinstance(revision, str) and revision == PERSISTENCE_REVISION
