from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from sqlalchemy import create_engine, or_, select
from sqlalchemy.orm import Session

from infrastructure.persistence.execution_orm import ProtectivePairORM
from infrastructure.persistence.execution_repositories import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyKillSwitchStateRepository,
)
from infrastructure.persistence.schema_contract import validate_persistence_schema
from models.execution_persistence import AuditEvent, OptimisticLockError
from models.kill_switch_state import KILL_SWITCH_SCOPE, KillSwitchState


ENVIRONMENT = "BINANCE_FUTURES_TESTNET"
SYMBOL = "BTCUSDT"
UNRESOLVED_PAIR_STATES = {"PENDING", "STOP_ACTIVE", "PAIR_ACTIVE", "CANCEL_PENDING", "RECOVERY_REQUIRED"}


class KillSwitchPersistenceError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class KillSwitchPersistence:
    """Durable, scoped kill-switch state with short transactions only."""

    def __init__(
        self,
        env: dict[str, str] | None = None,
        engine_factory: Callable[..., Any] = create_engine,
        session_factory: Callable[..., Session] = Session,
    ) -> None:
        self.env = os.environ if env is None else env
        self._engine_factory = engine_factory
        self._session_factory = session_factory
        self._engine: Any | None = None

    def ensure_available(self) -> None:
        url = self.env.get("ICT_DATABASE_URL") or self.env.get("DATABASE_URL")
        if not isinstance(url, str) or not url.strip():
            raise KillSwitchPersistenceError("PERSISTENCE_UNAVAILABLE")
        try:
            engine = self._engine_factory(url, future=True)
            with engine.connect() as connection:
                connection.execute(select(1)).scalar_one()
                if not validate_persistence_schema(connection):
                    raise KillSwitchPersistenceError("PERSISTENCE_SCHEMA_INVALID")
            self._engine = engine
        except KillSwitchPersistenceError:
            if "engine" in locals():
                engine.dispose()
            raise
        except Exception as exc:
            if "engine" in locals():
                engine.dispose()
            raise KillSwitchPersistenceError("PERSISTENCE_UNAVAILABLE") from exc

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def current(self) -> KillSwitchState | None:
        try:
            with self._session() as session:
                return SqlAlchemyKillSwitchStateRepository(session).get_by_scope(KILL_SWITCH_SCOPE)
        except KillSwitchPersistenceError:
            raise
        except Exception as exc:
            raise KillSwitchPersistenceError("PERSISTENCE_UNAVAILABLE") from exc

    def engage(self) -> tuple[KillSwitchState, bool]:
        try:
            with self._transaction() as session:
                states = SqlAlchemyKillSwitchStateRepository(session)
                current = states.get_by_scope(KILL_SWITCH_SCOPE)
                if current is not None and current.state == "ENGAGED":
                    return current, False
                if current is None:
                    updated = states.create(KillSwitchState(
                        scope=KILL_SWITCH_SCOPE,
                        environment=ENVIRONMENT,
                        symbol=SYMBOL,
                        state="ENGAGED",
                    ))
                else:
                    updated = states.update_state(current.id, current.version, "ENGAGED")
                SqlAlchemyAuditEventRepository(session).append(self._audit("KILL_SWITCH_ENGAGED"))
                return updated, True
        except KillSwitchPersistenceError:
            raise
        except OptimisticLockError as exc:
            raise KillSwitchPersistenceError("KILL_SWITCH_VERSION_CONFLICT") from exc
        except Exception as exc:
            raise KillSwitchPersistenceError("KILL_SWITCH_PERSIST_FAILED") from exc

    def release(self, expected_version: int) -> KillSwitchState:
        try:
            with self._transaction() as session:
                states = SqlAlchemyKillSwitchStateRepository(session)
                current = states.get_by_scope(KILL_SWITCH_SCOPE)
                if current is None or current.state != "ENGAGED":
                    raise KillSwitchPersistenceError("KILL_SWITCH_NOT_ENGAGED")
                updated = states.update_state(current.id, expected_version, "RELEASED")
                SqlAlchemyAuditEventRepository(session).append(self._audit("KILL_SWITCH_RELEASED"))
                return updated
        except KillSwitchPersistenceError:
            raise
        except OptimisticLockError as exc:
            raise KillSwitchPersistenceError("KILL_SWITCH_VERSION_CONFLICT") from exc
        except Exception as exc:
            raise KillSwitchPersistenceError("KILL_SWITCH_PERSIST_FAILED") from exc

    def has_unresolved_protective_pair(self) -> bool:
        try:
            with self._session() as session:
                row = session.scalar(
                    select(ProtectivePairORM.id)
                    .where(
                        ProtectivePairORM.environment == ENVIRONMENT,
                        ProtectivePairORM.symbol == SYMBOL,
                        or_(
                            ProtectivePairORM.state.in_(UNRESOLVED_PAIR_STATES),
                            ProtectivePairORM.recovery_required.is_(True),
                        ),
                    )
                    .limit(1)
                )
                return row is not None
        except Exception as exc:
            raise KillSwitchPersistenceError("PERSISTENCE_UNAVAILABLE") from exc

    @staticmethod
    def _audit(action: str) -> AuditEvent:
        return AuditEvent(
            category="KILL_SWITCH_CONTROL",
            action=action,
            environment=ENVIRONMENT,
            symbol=SYMBOL,
            result="PASS",
            metadata_json={"scope": KILL_SWITCH_SCOPE},
        )

    @contextmanager
    def _session(self) -> Iterator[Session]:
        if self._engine is None:
            raise KillSwitchPersistenceError("PERSISTENCE_UNAVAILABLE")
        session = self._session_factory(bind=self._engine, future=True, autoflush=False, expire_on_commit=False)
        try:
            yield session
        finally:
            session.close()

    @contextmanager
    def _transaction(self) -> Iterator[Session]:
        with self._session() as session:
            try:
                with session.begin():
                    yield session
            except Exception:
                session.rollback()
                raise
