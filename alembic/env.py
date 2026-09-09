from __future__ import annotations

from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import create_engine, pool

from infrastructure.persistence.execution_orm import ExecutionPersistenceBase

config = context.config
if config.config_file_name is not None:
    fileConfig(
        config.config_file_name,
        disable_existing_loggers=False,
    )

target_metadata = ExecutionPersistenceBase.metadata


def _database_url() -> str:
    url = os.environ.get("ICT_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("ICT_DATABASE_URL or DATABASE_URL is required for migration execution.")
    return url


def run_migrations_offline() -> None:
    url = _database_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
