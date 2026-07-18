from __future__ import annotations

import json
import tempfile
import weakref
from pathlib import Path

from sqlalchemy import Column, MetaData, String, Table, create_engine

from infrastructure.persistence.execution_orm import ExecutionPersistenceBase
from infrastructure.persistence.kill_switch_persistence import KillSwitchPersistence
from infrastructure.persistence.schema_contract import PERSISTENCE_REVISION


class _DurableStateEnvironment(dict[str, str]):
    __slots__ = ("__weakref__",)


def authorized_runtime_env(values: dict[str, str] | None = None) -> dict[str, str]:
    """Attach an explicit typed, temporary mutation runtime config for one test."""
    temporary_directory = tempfile.TemporaryDirectory(prefix="ict_live_execution_")
    runtime_path = Path(temporary_directory.name) / "runtime.json"
    runtime_path.write_text(
        json.dumps({"live_trading_enabled": True, "dry_run": False}),
        encoding="utf-8",
    )
    env = _DurableStateEnvironment(values or {})
    env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"] = str(runtime_path)
    weakref.finalize(env, temporary_directory.cleanup)
    return env


def durable_state_env(state: str = "RELEASED") -> dict[str, str]:
    """Return an isolated real SQLite persistence environment for mutation tests."""
    temporary_directory = tempfile.TemporaryDirectory(prefix="ict_kill_switch_")
    database_path = Path(temporary_directory.name) / "kill_switch.sqlite"
    url = f"sqlite:///{database_path}"
    engine = create_engine(url, future=True)
    persistence: KillSwitchPersistence | None = None
    env: _DurableStateEnvironment | None = None
    setup_completed = False
    try:
        ExecutionPersistenceBase.metadata.create_all(engine)
        metadata = MetaData()
        revision = Table("alembic_version", metadata, Column("version_num", String(64), primary_key=True))
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(revision.insert().values(version_num=PERSISTENCE_REVISION))
        env = _DurableStateEnvironment(
            ICT_DATABASE_URL=url,
            BINANCE_FUTURES_TESTNET_API_KEY="unit-test-key",
            BINANCE_FUTURES_TESTNET_API_SECRET="unit-test-secret",
        )
        runtime_path = Path(temporary_directory.name) / "live_execution_runtime.json"
        runtime_path.write_text(
            json.dumps({"live_trading_enabled": True, "dry_run": False}),
            encoding="utf-8",
        )
        env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"] = str(runtime_path)
        persistence = KillSwitchPersistence(env=env)
        persistence.ensure_available()
        persistence.engage()
        if state == "RELEASED":
            persistence.release(1)
        setup_completed = True
    finally:
        if persistence is not None:
            persistence.close()
        engine.dispose()
        if not setup_completed:
            temporary_directory.cleanup()
    assert env is not None
    weakref.finalize(env, temporary_directory.cleanup)
    return env
