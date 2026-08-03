from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from engine.diagnostics.binance_futures_testnet_protective_orders_engine import (
    BinanceFuturesTestnetProtectiveOrdersEngine,
    ProtectiveAbort,
)
from infrastructure.persistence.kill_switch_persistence import (
    KillSwitchPersistence,
    KillSwitchPersistenceError,
)
from infrastructure.persistence.protective_lifecycle_persistence import (
    ProtectiveLifecyclePersistence,
    ProtectivePersistenceError,
)

from .kill_switch_control_models import ENVIRONMENT, SYMBOL


@dataclass
class KillSwitchHTTPError(Exception):
    status_code: int
    code: str
    message: str


class KillSwitchControlService:
    """Durable Testnet/BTC-only kill-switch control with no exchange transport."""

    def __init__(
        self,
        repo_root: str | Path | None = None,
        env: dict[str, str] | None = None,
        protective_engine: BinanceFuturesTestnetProtectiveOrdersEngine | None = None,
        persistence_factory: Callable[..., KillSwitchPersistence] = KillSwitchPersistence,
        lifecycle_persistence_factory: Callable[..., ProtectiveLifecyclePersistence] = ProtectiveLifecyclePersistence,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.env = os.environ if env is None else env
        self.protective_engine = protective_engine or BinanceFuturesTestnetProtectiveOrdersEngine(
            repo_root=self.repo_root, env=self.env
        )
        self.persistence_factory = persistence_factory
        self.lifecycle_persistence_factory = lifecycle_persistence_factory

    def engage(self) -> dict[str, Any]:
        persistence = self.persistence_factory(env=self.env)
        try:
            persistence.ensure_available()
            state, changed = persistence.engage()
            return self._response(state, changed=changed)
        except KillSwitchPersistenceError as exc:
            raise self._persistence_error(exc) from exc
        finally:
            persistence.close()

    def status(self) -> dict[str, Any]:
        persistence = self.persistence_factory(env=self.env)
        try:
            persistence.ensure_available()
            state = persistence.current()
            if state is None or state.state not in {"ENGAGED", "RELEASED"}:
                raise self._error(503, "KILL_SWITCH_STATE_UNAVAILABLE")
            return self._response(state, changed=False)
        except KillSwitchHTTPError:
            raise
        except KillSwitchPersistenceError as exc:
            raise self._persistence_error(exc) from exc
        finally:
            persistence.close()

    def release(self) -> dict[str, Any]:
        persistence = self.persistence_factory(env=self.env)
        lock_path: Path | None = None
        lock_token: str | None = None
        lifecycle: ProtectiveLifecyclePersistence | None = None
        try:
            persistence.ensure_available()
            state = persistence.current()
            if state is None or state.state != "ENGAGED":
                raise self._error(409, "KILL_SWITCH_NOT_ENGAGED")
            config = self._safe_config()
            lock_path = self._resolve(config.lock_path)
            if lock_path.exists():
                raise self._error(409, "MUTATION_LOCK_ACTIVE")
            lock_token = self._acquire_lock(lock_path)
            lifecycle = self.lifecycle_persistence_factory(env=self.env)
            lifecycle.ensure_available()
            self._require_release_safe(persistence, lifecycle, config)
            updated = persistence.release(state.version)
            return self._response(updated, changed=True)
        except KillSwitchHTTPError:
            raise
        except KillSwitchPersistenceError as exc:
            raise self._persistence_error(exc) from exc
        except ProtectivePersistenceError as exc:
            unavailable = "UNAVAILABLE" in exc.code or "SCHEMA" in exc.code
            raise self._error(503 if unavailable else 409, "PERSISTENCE_UNAVAILABLE" if unavailable else "LIFECYCLE_STATE_CONFLICT") from exc
        except (OSError, json.JSONDecodeError, ProtectiveAbort, ValueError) as exc:
            raise self._error(409, "LIFECYCLE_STATE_CONFLICT") from exc
        except Exception as exc:
            raise self._error(503, "KILL_SWITCH_UNAVAILABLE") from exc
        finally:
            if lifecycle is not None:
                lifecycle.close()
            if lock_path is not None and lock_token is not None:
                self._release_lock(lock_path, lock_token)
            persistence.close()

    def _require_release_safe(
        self,
        persistence: KillSwitchPersistence,
        lifecycle: ProtectiveLifecyclePersistence,
        config: Any,
    ) -> None:
        if persistence.has_unresolved_protective_pair():
            raise self._error(409, "UNRESOLVED_PROTECTIVE_PAIR")
        journal_path = self._resolve(config.journal_path)
        if not journal_path.exists():
            return
        payload = json.loads(journal_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise self._error(409, "PROTECTIVE_JOURNAL_UNTRUSTED")
        pair_id = payload.get("pair_id")
        stop_id = payload.get("stop_client_algo_id")
        take_id = payload.get("take_profit_client_algo_id")
        if not all(isinstance(value, str) and value for value in (pair_id, stop_id, take_id)):
            raise self._error(409, "PROTECTIVE_JOURNAL_UNTRUSTED")
        journal = self.protective_engine._load_existing_journal_strict(config, pair_id, stop_id, take_id)
        if journal is None:
            raise self._error(409, "PROTECTIVE_JOURNAL_UNTRUSTED")
        if journal.recovery_required or any(not intent.resolved for intent in journal.mutation_intents):
            raise self._error(409, "RECOVERY_REQUIRED")
        consistency = lifecycle.check_consistency(journal, journal.pair_id, stop_id, take_id)
        if consistency.status != "ALREADY_COMPLETED":
            raise self._error(409, "LIFECYCLE_STATE_CONFLICT")

    def _safe_config(self):
        try:
            config = self.protective_engine.load_config("configs/binance_futures_testnet_protective_orders.json")
        except Exception as exc:
            raise self._error(503, "KILL_SWITCH_CONFIG_UNAVAILABLE") from exc
        if (
            config.testnet_only is not True
            or config.allow_production_endpoint is not False
            or config.project_scope != "BTC_ONLY"
        ):
            raise self._error(409, "KILL_SWITCH_SCOPE_FORBIDDEN")
        return config

    def _acquire_lock(self, path: Path) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        token = uuid4().hex
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise self._error(409, "MUTATION_LOCK_ACTIVE") from exc
        try:
            os.write(descriptor, token.encode("ascii"))
        finally:
            os.close(descriptor)
        return token

    @staticmethod
    def _release_lock(path: Path, token: str) -> None:
        try:
            if path.read_text(encoding="ascii") == token:
                path.unlink()
        except OSError:
            pass

    def _resolve(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else self.repo_root / path

    @staticmethod
    def _response(state, *, changed: bool) -> dict[str, Any]:
        return {
            "accepted": True,
            "environment": ENVIRONMENT,
            "symbol": SYMBOL,
            "state": state.state,
            "changed": changed,
            "version": state.version,
            "updated_at": state.updated_at.isoformat(),
            "blocking_code": None,
        }

    @staticmethod
    def _error(status_code: int, code: str) -> KillSwitchHTTPError:
        messages = {
            "KILL_SWITCH_NOT_ENGAGED": "Kill switch is not engaged.",
            "MUTATION_LOCK_ACTIVE": "A protective mutation lock is active.",
            "RECOVERY_REQUIRED": "Protective recovery remains required.",
            "UNRESOLVED_PROTECTIVE_PAIR": "An unresolved protective lifecycle exists.",
            "PROTECTIVE_JOURNAL_UNTRUSTED": "Protective journal is unavailable or untrusted.",
            "LIFECYCLE_STATE_CONFLICT": "Protective lifecycle state is inconsistent.",
            "KILL_SWITCH_SCOPE_FORBIDDEN": "Kill switch scope is forbidden.",
            "KILL_SWITCH_CONFIG_UNAVAILABLE": "Kill switch configuration is unavailable.",
            "PERSISTENCE_UNAVAILABLE": "Kill switch persistence is unavailable.",
            "KILL_SWITCH_VERSION_CONFLICT": "Kill switch state changed concurrently.",
            "KILL_SWITCH_PERSIST_FAILED": "Kill switch state could not be persisted.",
            "KILL_SWITCH_STATE_UNAVAILABLE": "Kill switch state is unavailable.",
            "KILL_SWITCH_UNAVAILABLE": "Kill switch control is unavailable.",
        }
        return KillSwitchHTTPError(status_code, code, messages[code])

    def _persistence_error(self, exc: KillSwitchPersistenceError) -> KillSwitchHTTPError:
        if exc.code in {"PERSISTENCE_UNAVAILABLE", "PERSISTENCE_SCHEMA_INVALID"}:
            return self._error(503, "PERSISTENCE_UNAVAILABLE")
        if exc.code == "KILL_SWITCH_NOT_ENGAGED":
            return self._error(409, exc.code)
        if exc.code == "KILL_SWITCH_VERSION_CONFLICT":
            return self._error(409, exc.code)
        return self._error(503, "KILL_SWITCH_PERSIST_FAILED")
