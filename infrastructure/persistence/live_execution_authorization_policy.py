from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from dataclasses import fields
from pathlib import Path
from typing import Callable

from infrastructure.observability.operational_metrics import OperationalCounterRegistry
from infrastructure.observability.structured_logging import build_structured_record, emit_structured_record
from infrastructure.persistence.kill_switch_gate import DurableKillSwitchGate, KillSwitchGateError
from infrastructure.persistence.kill_switch_persistence import KillSwitchPersistence
from infrastructure.persistence.live_execution_permit_persistence import record_order_test_policy_evaluation
from models.live_execution_authorization import (
    LiveExecutionAuthorizationContext,
    LiveExecutionAuthorizationDecision,
    LiveExecutionOperation,
)
from models.btc_paper_runtime_config import BTCPaperRuntimeConfig

SAFETY_DENIAL_COUNTER = "ict_tradingbot_safety_denials_total"


class LiveExecutionRuntimeProvider:
    """Strictly load only the typed runtime flags needed by mutation policy."""

    def __init__(self, repo_root: str | Path | None = None, env: dict[str, str] | None = None) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.env = os.environ if env is None else env

    def load(self, config_path: str) -> tuple[bool, bool]:
        override = self.env.get("ICT_LIVE_EXECUTION_RUNTIME_CONFIG")
        if override is not None and (type(override) is not str or not override.strip()):
            raise ValueError("runtime configuration override is invalid")
        path = Path(override if override is not None else config_path)
        if not path.is_absolute():
            path = self.repo_root / path
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("runtime configuration is invalid")
        allowed_fields = {field.name for field in fields(BTCPaperRuntimeConfig)}
        if any(type(key) is not str or key not in allowed_fields for key in payload):
            raise ValueError("runtime configuration contains unsupported fields")
        if set(("live_trading_enabled", "dry_run")) - payload.keys():
            raise ValueError("runtime configuration is incomplete")
        live = payload["live_trading_enabled"]
        dry_run = payload["dry_run"]
        if type(live) is not bool or type(dry_run) is not bool:
            raise ValueError("runtime authorization flags must be booleans")
        return live, dry_run


class LiveExecutionAuthorizationPolicy:
    """Central, deterministic, side-effect-free authorization for exchange mutation."""

    SAFE_MESSAGES = {
        "AUTHORIZED": "Exchange mutation is authorized.",
        "EXECUTION_POLICY_UNAVAILABLE": "Execution authorization context is unavailable.",
        "UNSUPPORTED_EXECUTION_OPERATION": "Execution operation is not supported.",
        "TESTNET_ONLY": "Only the Binance Futures Testnet environment is authorized.",
        "BTCUSDT_ONLY": "Only BTCUSDT is authorized.",
        "PERSISTENCE_UNAVAILABLE": "Execution persistence is unavailable.",
        "KILL_SWITCH_ENGAGED": "Durable kill switch blocks exchange mutation.",
        "KILL_SWITCH_STATE_UNAVAILABLE": "Durable kill-switch state is unavailable.",
        "RECOVERY_REQUIRED": "Unresolved recovery blocks fresh exchange mutation.",
        "LIVE_TRADING_DISABLED": "Live mutation mode is disabled.",
        "DRY_RUN_ACTIVE": "Dry-run mode blocks exchange mutation.",
        "CONFIRMATION_REQUIRED": "Verified explicit confirmation is required.",
        "CREDENTIALS_UNAVAILABLE": "Testnet credentials are unavailable.",
    }

    def __init__(
        self,
        repo_root: str | Path | None = None,
        env: dict[str, str] | None = None,
        runtime_provider: LiveExecutionRuntimeProvider | None = None,
        kill_switch_gate: DurableKillSwitchGate | None = None,
        persistence_factory: Callable[..., KillSwitchPersistence] = KillSwitchPersistence,
        operational_counter_registry: OperationalCounterRegistry | None = None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.env = os.environ if env is None else env
        self.runtime_provider = runtime_provider or LiveExecutionRuntimeProvider(self.repo_root, self.env)
        self.kill_switch_gate = kill_switch_gate or DurableKillSwitchGate(env=self.env)
        self.persistence_factory = persistence_factory
        self.operational_counter_registry = operational_counter_registry or OperationalCounterRegistry()
        try:
            self.operational_counter_registry.register(SAFETY_DENIAL_COUNTER)
        except Exception:
            pass

    def authorize(
        self,
        operation: LiveExecutionOperation,
        *,
        environment: str,
        symbol: str,
        confirmation_verified: bool,
        credentials_configured: bool,
        runtime_config_path: str = "configs/btc_paper_runtime.json",
        current_pair_id: str | None = None,
    ) -> LiveExecutionAuthorizationDecision:
        operation_value = operation.value if isinstance(operation, LiveExecutionOperation) else None
        if not self._strict_request(
            operation,
            environment,
            symbol,
            confirmation_verified,
            credentials_configured,
            current_pair_id,
        ):
            return self._record_order_test_authorization_evidence(
                self._deny("EXECUTION_POLICY_UNAVAILABLE", operation_value),
                recovery_required=None,
            )
        if operation_value is None:
            return self._record_order_test_authorization_evidence(
                self._deny("UNSUPPORTED_EXECUTION_OPERATION", None),
                recovery_required=None,
            )
        if environment != "TESTNET":
            return self._record_order_test_authorization_evidence(
                self._deny("TESTNET_ONLY", operation_value),
                recovery_required=None,
            )
        if symbol != "BTCUSDT":
            return self._record_order_test_authorization_evidence(
                self._deny("BTCUSDT_ONLY", operation_value),
                recovery_required=None,
            )

        available, _ = self._use_persistence(lambda persistence: None)
        if not available:
            return self._record_order_test_authorization_evidence(
                self._deny("PERSISTENCE_UNAVAILABLE", operation_value),
                recovery_required=None,
            )
        kill_switch_denial = self._kill_switch_denial(operation_value)
        if kill_switch_denial is not None:
            return self._record_order_test_authorization_evidence(
                kill_switch_denial,
                recovery_required=None,
            )
        available, unresolved = self._use_persistence(
            lambda persistence: persistence.has_unresolved_recovery(current_pair_id)
        )
        if not available:
            return self._record_order_test_authorization_evidence(
                self._deny("PERSISTENCE_UNAVAILABLE", operation_value),
                recovery_required=None,
            )
        if unresolved:
            return self._record_order_test_authorization_evidence(
                self._deny("RECOVERY_REQUIRED", operation_value),
                recovery_required=True,
            )

        try:
            live, dry_run = self.runtime_provider.load(runtime_config_path)
        except Exception:
            return self._record_order_test_authorization_evidence(
                self._deny("EXECUTION_POLICY_UNAVAILABLE", operation_value),
                recovery_required=False,
            )
        if type(live) is not bool or type(dry_run) is not bool:
            return self._record_order_test_authorization_evidence(
                self._deny("EXECUTION_POLICY_UNAVAILABLE", operation_value),
                recovery_required=False,
            )
        return self._record_order_test_authorization_evidence(
            self._evaluate_flags(
                operation_value,
                live,
                dry_run,
                confirmation_verified,
                credentials_configured,
            ),
            recovery_required=False,
        )

    def authorize_preflight(
        self,
        operation: LiveExecutionOperation,
        *,
        environment: str,
        symbol: str,
        confirmation_verified: bool,
        credentials_configured: bool,
        runtime_config_path: str = "configs/btc_paper_runtime.json",
    ) -> LiveExecutionAuthorizationDecision:
        """Authorize a fresh mutation preflight with the complete durable policy."""
        return self.authorize(
            operation,
            environment=environment,
            symbol=symbol,
            confirmation_verified=confirmation_verified,
            credentials_configured=credentials_configured,
            runtime_config_path=runtime_config_path,
        )

    def evaluate(self, context: object) -> LiveExecutionAuthorizationDecision:
        if not isinstance(context, LiveExecutionAuthorizationContext):
            return self._deny("EXECUTION_POLICY_UNAVAILABLE", None)
        if not self._strict_context(context):
            operation = context.operation.value if isinstance(context.operation, LiveExecutionOperation) else None
            return self._deny("EXECUTION_POLICY_UNAVAILABLE", operation)
        operation = context.operation.value if isinstance(context.operation, LiveExecutionOperation) else None
        if operation is None:
            return self._deny("UNSUPPORTED_EXECUTION_OPERATION", None)
        if context.environment != "TESTNET":
            return self._deny("TESTNET_ONLY", operation)
        if context.symbol != "BTCUSDT":
            return self._deny("BTCUSDT_ONLY", operation)

        available, _ = self._use_persistence(lambda persistence: None)
        if not available:
            return self._deny("PERSISTENCE_UNAVAILABLE", operation)
        kill_switch_denial = self._kill_switch_denial(operation)
        if kill_switch_denial is not None:
            return kill_switch_denial
        available, unresolved = self._use_persistence(
            lambda persistence: persistence.has_unresolved_recovery(context.current_pair_id)
        )
        if not available:
            return self._deny("PERSISTENCE_UNAVAILABLE", operation)
        if unresolved:
            return self._deny("RECOVERY_REQUIRED", operation)
        return self._evaluate_flags(
            operation,
            context.live_trading_enabled,
            context.dry_run,
            context.confirmation_verified,
            context.credentials_configured,
        )

    def _use_persistence(self, action: Callable[[KillSwitchPersistence], object]) -> tuple[bool, object | None]:
        persistence: KillSwitchPersistence | None = None
        result: object | None = None
        failed = False
        try:
            persistence = self.persistence_factory(env=self.env)
            persistence.ensure_available()
            result = action(persistence)
        except Exception:
            failed = True
        finally:
            if persistence is not None:
                try:
                    persistence.close()
                except Exception:
                    failed = True
        return (not failed, result if not failed else None)

    def _kill_switch_denial(self, operation: str) -> LiveExecutionAuthorizationDecision | None:
        try:
            self.kill_switch_gate.require_released()
        except KillSwitchGateError as exc:
            code = exc.code if exc.code in {"KILL_SWITCH_ENGAGED", "KILL_SWITCH_STATE_UNAVAILABLE"} else "KILL_SWITCH_STATE_UNAVAILABLE"
            return self._deny(code, operation)
        except Exception:
            return self._deny("KILL_SWITCH_STATE_UNAVAILABLE", operation)
        return None

    def _evaluate_flags(
        self,
        operation: str,
        live_trading_enabled: bool,
        dry_run: bool,
        confirmation_verified: bool,
        credentials_configured: bool,
    ) -> LiveExecutionAuthorizationDecision:
        if not live_trading_enabled:
            return self._deny("LIVE_TRADING_DISABLED", operation)
        if dry_run:
            return self._deny("DRY_RUN_ACTIVE", operation)
        if not confirmation_verified:
            return self._deny("CONFIRMATION_REQUIRED", operation)
        if not credentials_configured:
            return self._deny("CREDENTIALS_UNAVAILABLE", operation)
        return LiveExecutionAuthorizationDecision(True, "AUTHORIZED", operation, message=self.SAFE_MESSAGES["AUTHORIZED"])

    @staticmethod
    def _strict_request(
        operation: object,
        environment: object,
        symbol: object,
        confirmation_verified: object,
        credentials_configured: object,
        current_pair_id: object,
    ) -> bool:
        return (
            isinstance(operation, (LiveExecutionOperation, str))
            and type(environment) is str
            and type(symbol) is str
            and type(confirmation_verified) is bool
            and type(credentials_configured) is bool
            and (current_pair_id is None or (type(current_pair_id) is str and bool(current_pair_id)))
        )

    @staticmethod
    def _strict_context(context: LiveExecutionAuthorizationContext) -> bool:
        return (
            isinstance(context.operation, (LiveExecutionOperation, str))
            and type(context.environment) is str
            and type(context.symbol) is str
            and type(context.live_trading_enabled) is bool
            and type(context.dry_run) is bool
            and type(context.confirmation_verified) is bool
            and type(context.credentials_configured) is bool
            and (context.current_pair_id is None or (type(context.current_pair_id) is str and bool(context.current_pair_id)))
        )

    def _deny(self, code: str, operation: str | None) -> LiveExecutionAuthorizationDecision:
        decision = LiveExecutionAuthorizationDecision(False, code, operation, message=self.SAFE_MESSAGES[code])
        self._observe_denial(decision)
        return decision

    def _observe_denial(self, decision: LiveExecutionAuthorizationDecision) -> None:
        context = {
            "decision_code": decision.code,
            "operation": decision.operation,
            "policy_version": decision.policy_version,
        }
        try:
            record = build_structured_record(
                timestamp=datetime.now(UTC),
                severity="WARNING",
                event_name="live_execution_authorization_denied",
                category="safety_denial",
                context=context,
            )
            emit_structured_record(record)
        except Exception:
            pass
        try:
            self.operational_counter_registry.increment(SAFETY_DENIAL_COUNTER, 1)
        except Exception:
            pass

    @staticmethod
    def _record_order_test_authorization_evidence(
        decision: LiveExecutionAuthorizationDecision,
        *,
        recovery_required: bool | None,
    ) -> LiveExecutionAuthorizationDecision:
        record_order_test_policy_evaluation(recovery_required=recovery_required)
        return decision
