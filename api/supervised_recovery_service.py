from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

from engine.diagnostics.binance_futures_testnet_protective_orders_engine import (
    BinanceFuturesTestnetProtectiveOrdersEngine,
    ProtectiveAbort,
)
from infrastructure.persistence.protective_lifecycle_persistence import (
    ProtectiveLifecyclePersistence,
    ProtectivePersistenceError,
)
from infrastructure.persistence.kill_switch_gate import DurableKillSwitchGate, KillSwitchGateError
from models.binance_futures_testnet_protective_orders import BinanceFuturesTestnetProtectiveJournal

from .supervised_recovery_models import CONFIRMATION, ENVIRONMENT, SYMBOL, SupervisedRecoveryRequest


@dataclass
class SupervisedRecoveryHTTPError(Exception):
    status_code: int
    code: str
    message: str


@dataclass(frozen=True)
class RecoveryEligibility:
    journal: BinanceFuturesTestnetProtectiveJournal
    persistence: ProtectiveLifecyclePersistence
    pair_state: str
    planned_actions: tuple[str, ...]


class SupervisedRecoveryService:
    """Operator gate around the existing exact protective recovery engine."""

    def __init__(
        self,
        repo_root: str | Path | None = None,
        env: dict[str, str] | None = None,
        protective_engine: BinanceFuturesTestnetProtectiveOrdersEngine | None = None,
        persistence_factory: Callable[..., ProtectiveLifecyclePersistence] = ProtectiveLifecyclePersistence,
        recovery_runner: Callable[..., Any] | None = None,
        kill_switch_gate: DurableKillSwitchGate | None = None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.env = os.environ if env is None else env
        self.protective_engine = protective_engine or BinanceFuturesTestnetProtectiveOrdersEngine(
            repo_root=self.repo_root, env=self.env
        )
        self.persistence_factory = persistence_factory
        self.recovery_runner = recovery_runner or self.protective_engine.recover_protective_pair
        self.kill_switch_gate = kill_switch_gate or DurableKillSwitchGate(env=self.env)

    def run(self, request: SupervisedRecoveryRequest) -> dict[str, Any]:
        eligibility = self._preflight(request)
        try:
            if request.dry_run:
                return self._response(request, eligibility, recovery_ready=True)
            self._require_credentials()
            result = self.recovery_runner(
                eligibility.journal.stop_client_algo_id,
                eligibility.journal.take_profit_client_algo_id,
                confirmation=self._config().recovery_confirmation_phrase,
                reconcile_only=True,
            )
            if getattr(result, "status", None) != "PASS":
                code = self._safe_result_code(getattr(result, "decision", None))
                status = 409 if code in {"RECOVERY_REQUIRED", "PERSISTENCE_STATE_MISMATCH"} else 502
                raise self._error(status, code)
            return self._response(
                request,
                eligibility,
                recovery_ready=True,
                recovery_executed=True,
                final_phase=getattr(result, "phase", None) or "RECOVERY_COMPLETE",
                final_pair_state="COMPLETED" if bool(getattr(result, "lifecycle_complete", False)) else None,
                recovery_required=bool(getattr(result, "recovery_required", False)),
                stop_result=self._order_result(getattr(result, "final_stop_order", None)),
                take_profit_result=self._order_result(getattr(result, "final_take_profit_order", None)),
            )
        finally:
            eligibility.persistence.close()

    def _preflight(self, request: SupervisedRecoveryRequest) -> RecoveryEligibility:
        if request.environment != ENVIRONMENT or request.symbol != SYMBOL or request.confirmation != CONFIRMATION:
            raise self._error(400, "RECOVERY_SCOPE_FORBIDDEN")
        if not self._kill_switch_engaged():
            raise self._error(423, "KILL_SWITCH_NOT_ENGAGED")
        config = self._config()
        if self._resolve(config.lock_path).exists():
            raise self._error(409, "RECOVERY_LOCKED")
        journal = self._load_journal(config, request.pair_id)
        persistence = self.persistence_factory(env=self.env)
        try:
            persistence.ensure_available()
            consistency = persistence.check_consistency(
                journal, request.pair_id, journal.stop_client_algo_id, journal.take_profit_client_algo_id
            )
            if consistency.status != "RECOVERY" or consistency.state is None:
                raise self._error(409, "RECOVERY_NOT_REQUIRED")
            if consistency.correlation_id != UUID(request.correlation_id):
                raise self._error(409, "RECOVERY_OWNERSHIP_MISMATCH")
            planned = self._planned_actions(persistence, consistency.state, journal)
            projection_gap = any(action.startswith("CATCH_UP_") for action in planned)
            if not journal.recovery_required and not projection_gap:
                raise self._error(409, "RECOVERY_NOT_REQUIRED")
            if consistency.pair_recovery_required != journal.recovery_required and not projection_gap:
                raise self._error(409, "RECOVERY_STATE_MISMATCH")
            if not planned:
                raise self._error(409, "RECOVERY_STATE_UNSUPPORTED")
            return RecoveryEligibility(
                journal=journal,
                persistence=persistence,
                pair_state=consistency.pair_state or "RECOVERY_REQUIRED",
                planned_actions=tuple(planned),
            )
        except SupervisedRecoveryHTTPError:
            persistence.close()
            raise
        except ProtectivePersistenceError as exc:
            persistence.close()
            unavailable = "UNAVAILABLE" in exc.code or "SCHEMA" in exc.code
            raise self._error(503 if unavailable else 409, "PERSISTENCE_UNAVAILABLE" if unavailable else "RECOVERY_STATE_CONFLICT") from exc
        except Exception as exc:
            persistence.close()
            raise self._error(503, "RECOVERY_PREFLIGHT_UNAVAILABLE") from exc

    def _load_journal(self, config: Any, pair_id: str) -> BinanceFuturesTestnetProtectiveJournal:
        path = self._resolve(config.journal_path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError
            stop_id = payload.get("stop_client_algo_id")
            take_id = payload.get("take_profit_client_algo_id")
            if not isinstance(stop_id, str) or not isinstance(take_id, str):
                raise ValueError
            journal = self.protective_engine._load_existing_journal_strict(config, pair_id, stop_id, take_id)
            if journal is None:
                raise FileNotFoundError
            return journal
        except FileNotFoundError as exc:
            raise self._error(404, "RECOVERY_JOURNAL_NOT_FOUND") from exc
        except (ProtectiveAbort, json.JSONDecodeError, OSError, ValueError) as exc:
            raise self._error(409, "RECOVERY_JOURNAL_UNTRUSTED") from exc

    def _planned_actions(self, persistence: ProtectiveLifecyclePersistence, state: Any, journal: Any) -> list[str]:
        actions: list[str] = []
        for intent in journal.mutation_intents:
            if not intent.resolved:
                actions.append(f"EXACT_GET_{intent.label}_{intent.mutation_kind}")
            elif persistence.needs_catch_up(state, intent):
                actions.append(f"CATCH_UP_{intent.label}_{intent.mutation_kind}")
        if journal.recovery_required and not actions:
            actions.extend(("EXACT_GET_STOP", "EXACT_GET_TAKE_PROFIT"))
        return actions

    def _kill_switch_engaged(self) -> bool:
        try:
            self.kill_switch_gate.require_engaged()
            return True
        except KillSwitchGateError:
            return False

    def _require_credentials(self) -> None:
        config = self._config()
        api_key = self.env.get(config.api_key_env_var)
        api_secret = self.env.get(config.api_secret_env_var)
        if not isinstance(api_key, str) or not api_key or not isinstance(api_secret, str) or not api_secret:
            raise self._error(503, "CREDENTIALS_NOT_CONFIGURED")

    def _config(self):
        try:
            return self.protective_engine.load_config("configs/binance_futures_testnet_protective_orders.json")
        except Exception as exc:
            raise self._error(503, "RECOVERY_CONFIG_UNAVAILABLE") from exc

    def _resolve(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else self.repo_root / path

    def _response(self, request: SupervisedRecoveryRequest, eligibility: RecoveryEligibility, **changes: Any) -> dict[str, Any]:
        response = {
            "accepted": True, "dry_run": bool(request.dry_run), "recovery_ready": False,
            "recovery_executed": False, "environment": ENVIRONMENT, "symbol": SYMBOL,
            "pair_id": request.pair_id, "correlation_id": request.correlation_id,
            "current_phase": eligibility.journal.phase, "final_phase": None,
            "pair_state": eligibility.pair_state, "final_pair_state": None,
            "recovery_required": bool(eligibility.journal.recovery_required),
            "planned_actions": list(eligibility.planned_actions), "stop_result": None,
            "take_profit_result": None, "blocking_code": None,
        }
        response.update(changes)
        return response

    @staticmethod
    def _order_result(order: Any) -> str:
        if order is None:
            return "ABSENT"
        status = getattr(order, "algo_status", None)
        return status if status in {"NEW", "CANCELED", "EXPIRED", "REJECTED"} else "UNKNOWN"

    @staticmethod
    def _safe_result_code(value: Any) -> str:
        allowed = {"RECOVERY_REQUIRED", "PERSISTENCE_STATE_MISMATCH", "CREDENTIALS_NOT_CONFIGURED", "OPERATION_BLOCKED"}
        return value if value in allowed else "RECOVERY_FAILED"

    @staticmethod
    def _error(status: int, code: str) -> SupervisedRecoveryHTTPError:
        messages = {
            "RECOVERY_SCOPE_FORBIDDEN": "Recovery scope or confirmation is forbidden.",
            "KILL_SWITCH_NOT_ENGAGED": "Recovery requires the kill switch to remain engaged.",
            "RECOVERY_LOCKED": "Protective recovery is already in progress.",
            "RECOVERY_NOT_REQUIRED": "The exact lifecycle does not require supervised recovery.",
            "RECOVERY_OWNERSHIP_MISMATCH": "Recovery ownership does not match.",
            "RECOVERY_STATE_MISMATCH": "Recovery state is inconsistent.",
            "RECOVERY_STATE_UNSUPPORTED": "Recovery state is not eligible.",
            "RECOVERY_JOURNAL_NOT_FOUND": "The exact recovery journal was not found.",
            "RECOVERY_JOURNAL_UNTRUSTED": "The recovery journal is unavailable or untrusted.",
            "PERSISTENCE_UNAVAILABLE": "Recovery persistence is unavailable.",
            "RECOVERY_STATE_CONFLICT": "Recovery persistence state is inconsistent.",
            "RECOVERY_PREFLIGHT_UNAVAILABLE": "Recovery preflight is unavailable.",
            "RECOVERY_CONFIG_UNAVAILABLE": "Recovery configuration is unavailable.",
            "CREDENTIALS_NOT_CONFIGURED": "Testnet recovery credentials are not configured.",
            "RECOVERY_REQUIRED": "Recovery remains required.",
            "PERSISTENCE_STATE_MISMATCH": "Recovery persistence state is inconsistent.",
            "OPERATION_BLOCKED": "Recovery was blocked safely.",
            "RECOVERY_FAILED": "Recovery did not complete.",
        }
        return SupervisedRecoveryHTTPError(status, code, messages.get(code, "Recovery request was blocked safely."))
