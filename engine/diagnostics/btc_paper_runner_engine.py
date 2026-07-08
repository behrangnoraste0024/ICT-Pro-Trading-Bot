from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine
from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from models.btc_paper_runner import (
    BTCPaperRunnerAction,
    BTCPaperRunnerConfig,
    BTCPaperRunnerIssue,
    BTCPaperRunnerState,
    BTCPaperRunnerStatus,
    BTCPaperRunnerTransitionResult,
)


NO_EXECUTION_MESSAGE = "Dry-run lifecycle only. No signals, trades, orders, or exchange connections were executed."


class BTCPaperRunnerEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        runtime_config_engine: BTCPaperRuntimeConfigEngine | None = None,
        monitoring_engine: BTCPaperMonitoringEngine | None = None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.runtime_config_engine = runtime_config_engine or BTCPaperRuntimeConfigEngine(repo_root=self.repo_root)
        self.monitoring_engine = monitoring_engine or BTCPaperMonitoringEngine(repo_root=self.repo_root)

    def load_config(self, config_path: str = "configs/btc_paper_runner.json") -> BTCPaperRunnerConfig:
        path = self._resolve(config_path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("runner config JSON must be an object")
        return BTCPaperRunnerConfig(**{**BTCPaperRunnerConfig().to_dict(), **loaded})

    def validate_config(
        self,
        config_path: str = "configs/btc_paper_runner.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> tuple[BTCPaperRunnerConfig | None, list[BTCPaperRunnerIssue], dict[str, Any]]:
        issues: list[BTCPaperRunnerIssue] = []
        diagnostics: dict[str, Any] = {"runtime_config_status": "UNKNOWN", "monitoring_config_status": "UNKNOWN", "kill_switch_enabled": None}
        try:
            config = self.load_config(config_path)
        except Exception as exc:
            return None, [self._issue("config_invalid", "FAIL", f"BTC paper runner config could not be loaded: {exc}", {"config_path": config_path})], diagnostics
        self._validate_config_values(config, expected_profile, issues, diagnostics)
        return config, issues, diagnostics

    def build_status(
        self,
        config_path: str = "configs/btc_paper_runner.json",
        expected_profile: str = "balanced_smc_decision_065",
        state: BTCPaperRunnerStatus | None = None,
    ) -> BTCPaperRunnerStatus:
        config, issues, diagnostics = self.validate_config(config_path, expected_profile)
        config = config or BTCPaperRunnerConfig()
        now = self._now()
        base = state or BTCPaperRunnerStatus(created_at=now)
        return BTCPaperRunnerStatus(
            created_at=base.created_at or now,
            updated_at=now,
            project_scope=config.project_scope,
            symbol=config.symbol,
            strategy_profile=config.strategy_profile,
            state=base.state,
            previous_state=base.previous_state,
            last_action=base.last_action,
            last_heartbeat_at=base.last_heartbeat_at,
            started_at=base.started_at,
            stopped_at=base.stopped_at,
            paused_at=base.paused_at,
            resumed_at=base.resumed_at,
            error_message=base.error_message,
            consecutive_errors=base.consecutive_errors,
            dry_run_only=config.dry_run_only,
            runner_enabled=config.runner_enabled,
            signal_generation_enabled=config.allow_signal_generation,
            paper_trade_creation_enabled=config.allow_paper_trade_creation,
            order_submission_enabled=config.allow_order_submission,
            exchange_connection_enabled=config.allow_exchange_connection,
            runtime_config_status=str(diagnostics.get("runtime_config_status", "UNKNOWN")),
            monitoring_config_status=str(diagnostics.get("monitoring_config_status", "UNKNOWN")),
            kill_switch_enabled=bool(diagnostics.get("kill_switch_enabled", True)),
            notes=self._notes(config),
            issues=issues,
        )

    def apply(
        self,
        action: str,
        status: BTCPaperRunnerStatus | None = None,
        config_path: str = "configs/btc_paper_runner.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCPaperRunnerTransitionResult:
        action_value = self._normalize_action(action)
        current = self.build_status(config_path=config_path, expected_profile=expected_profile, state=status)
        previous_state = current.state
        if any(issue.severity == "FAIL" for issue in current.issues):
            return self._reject(action_value, current, "Runner config safety validation failed.")
        now = self._now()
        accepted = True
        message = NO_EXECUTION_MESSAGE
        next_state = current.state
        error_message = current.error_message
        consecutive_errors = current.consecutive_errors
        last_heartbeat_at = current.last_heartbeat_at
        started_at = current.started_at
        stopped_at = current.stopped_at
        paused_at = current.paused_at
        resumed_at = current.resumed_at

        if action_value == BTCPaperRunnerAction.STATUS.value:
            accepted = True
            message = "Status read only. " + NO_EXECUTION_MESSAGE
        elif action_value == BTCPaperRunnerAction.INITIALIZE.value:
            if current.state in (BTCPaperRunnerState.CREATED.value, BTCPaperRunnerState.STOPPED.value):
                next_state = BTCPaperRunnerState.READY.value
            else:
                accepted = False
                message = f"initialize is not valid from {current.state}."
        elif action_value == BTCPaperRunnerAction.START.value:
            if current.state == BTCPaperRunnerState.CREATED.value:
                next_state = BTCPaperRunnerState.RUNNING.value
                started_at = now
            elif current.state == BTCPaperRunnerState.READY.value:
                next_state = BTCPaperRunnerState.RUNNING.value
                started_at = now
            else:
                accepted = False
                message = f"start is not valid from {current.state}."
        elif action_value == BTCPaperRunnerAction.PAUSE.value:
            if current.state == BTCPaperRunnerState.RUNNING.value:
                next_state = BTCPaperRunnerState.PAUSED.value
                paused_at = now
            else:
                accepted = False
                message = f"pause is not valid from {current.state}."
        elif action_value == BTCPaperRunnerAction.RESUME.value:
            if current.state == BTCPaperRunnerState.PAUSED.value:
                next_state = BTCPaperRunnerState.RUNNING.value
                resumed_at = now
            else:
                accepted = False
                message = f"resume is not valid from {current.state}."
        elif action_value == BTCPaperRunnerAction.STOP.value:
            if current.state in (BTCPaperRunnerState.READY.value, BTCPaperRunnerState.RUNNING.value, BTCPaperRunnerState.PAUSED.value):
                next_state = BTCPaperRunnerState.STOPPED.value
                stopped_at = now
            else:
                accepted = False
                message = f"stop is not valid from {current.state}."
        elif action_value == BTCPaperRunnerAction.HEARTBEAT.value:
            if current.state in (BTCPaperRunnerState.RUNNING.value, BTCPaperRunnerState.PAUSED.value):
                last_heartbeat_at = now
                message = "Heartbeat recorded. " + NO_EXECUTION_MESSAGE
            else:
                message = f"Heartbeat ignored in {current.state}; runner is not active."
        elif action_value == BTCPaperRunnerAction.RESET_ERROR.value:
            if current.state == BTCPaperRunnerState.ERROR.value:
                next_state = BTCPaperRunnerState.READY.value
                error_message = None
                consecutive_errors = 0
            else:
                accepted = False
                message = f"reset_error is not valid from {current.state}."
        else:
            accepted = False
            message = f"Unknown action: {action}."

        updated = BTCPaperRunnerStatus(
            **{
                **current.to_dict(),
                "updated_at": now,
                "previous_state": previous_state if next_state != previous_state else current.previous_state,
                "state": next_state,
                "last_action": action_value,
                "last_heartbeat_at": last_heartbeat_at,
                "started_at": started_at,
                "stopped_at": stopped_at,
                "paused_at": paused_at,
                "resumed_at": resumed_at,
                "error_message": error_message,
                "consecutive_errors": consecutive_errors,
                "issues": current.issues,
            }
        )
        if accepted and message == NO_EXECUTION_MESSAGE and action_value == BTCPaperRunnerAction.START.value:
            message = "Runner moved to RUNNING. " + NO_EXECUTION_MESSAGE
        elif accepted and message == NO_EXECUTION_MESSAGE:
            message = f"{action_value.lower()} accepted. " + NO_EXECUTION_MESSAGE
        return BTCPaperRunnerTransitionResult(
            action=action_value,
            accepted=accepted,
            previous_state=previous_state,
            current_state=updated.state,
            status=updated,
            message=message,
            issues=list(updated.issues),
        )

    def load_state(self, state_file: str) -> BTCPaperRunnerStatus:
        path = self._safe_state_path(state_file)
        return BTCPaperRunnerStatus.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save_state(self, status: BTCPaperRunnerStatus, state_file: str) -> None:
        path = self._safe_state_path(state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(status.to_dict(), indent=2), encoding="utf-8")
        temp_path.replace(path)

    def _validate_config_values(
        self,
        config: BTCPaperRunnerConfig,
        expected_profile: str,
        issues: list[BTCPaperRunnerIssue],
        diagnostics: dict[str, Any],
    ) -> None:
        self._expect(config.project_scope == "BTC_ONLY", issues, "project_scope", "project_scope must be BTC_ONLY.", {"project_scope": config.project_scope})
        self._expect(config.symbol == "BTC/USDT", issues, "symbol", "symbol must be BTC/USDT.", {"symbol": config.symbol})
        self._expect(config.strategy_profile == expected_profile, issues, "strategy_profile", f"strategy_profile must be {expected_profile}.", {"strategy_profile": config.strategy_profile})
        self._expect(config.dry_run_only, issues, "dry_run_only", "dry_run_only must be true.")
        self._expect(not config.allow_signal_generation, issues, "allow_signal_generation", "signal generation must remain disabled.")
        self._expect(not config.allow_paper_trade_creation, issues, "allow_paper_trade_creation", "paper trade creation must remain disabled.")
        self._expect(not config.allow_order_submission, issues, "allow_order_submission", "order submission must remain disabled.")
        self._expect(not config.allow_exchange_connection, issues, "allow_exchange_connection", "exchange connections must remain disabled.")
        self._expect(10 <= int(config.heartbeat_interval_seconds) <= 300, issues, "heartbeat_interval_seconds", "heartbeat_interval_seconds must be between 10 and 300.", {"heartbeat_interval_seconds": config.heartbeat_interval_seconds})
        self._validate_state_export_dir(config.state_export_dir, issues)
        if not config.runner_enabled:
            issues.append(self._issue("runner_enabled", "INFO", "Runner config is disabled by default; lifecycle command is dry-run simulation only."))
        self._validate_runtime_config(config, expected_profile, issues, diagnostics)
        self._validate_monitoring_config(config, expected_profile, issues, diagnostics)

    def _validate_runtime_config(self, config: BTCPaperRunnerConfig, expected_profile: str, issues: list[BTCPaperRunnerIssue], diagnostics: dict[str, Any]) -> None:
        report = self.runtime_config_engine.validate(config.runtime_config_path, expected_profile=expected_profile)
        diagnostics["runtime_config_status"] = report.status
        runtime_config = report.config
        diagnostics["kill_switch_enabled"] = bool(getattr(runtime_config, "kill_switch_enabled", False))
        if config.require_runtime_config_pass and report.status != "PASS":
            issues.append(self._issue("runtime_config_validation", "FAIL", "Runtime config must validate PASS.", {"runtime_config_status": report.status}))
        if runtime_config is not None:
            self._expect(not runtime_config.paper_execution_enabled, issues, "paper_execution_enabled", "paper_execution_enabled must remain false.")
            self._expect(not runtime_config.live_trading_enabled, issues, "live_trading_enabled", "live_trading_enabled must remain false.")
            self._expect(not runtime_config.order_submission_enabled, issues, "order_submission_enabled", "order_submission_enabled must remain false.")
            self._expect(runtime_config.dry_run, issues, "dry_run", "dry_run must remain true.")
            if config.require_kill_switch_enabled:
                self._expect(runtime_config.kill_switch_enabled, issues, "kill_switch_enabled", "kill_switch_enabled must remain true.")

    def _validate_monitoring_config(self, config: BTCPaperRunnerConfig, expected_profile: str, issues: list[BTCPaperRunnerIssue], diagnostics: dict[str, Any]) -> None:
        report = self.monitoring_engine.validate(config.monitoring_config_path, expected_profile=expected_profile)
        diagnostics["monitoring_config_status"] = report.status
        if config.require_monitoring_config_pass and report.status != "PASS":
            issues.append(self._issue("monitoring_config_validation", "FAIL", "Monitoring config must validate PASS.", {"monitoring_config_status": report.status}))

    def _validate_state_export_dir(self, value: str, issues: list[BTCPaperRunnerIssue]) -> None:
        path = Path(value)
        if path.is_absolute():
            issues.append(self._issue("state_export_dir", "FAIL", "state_export_dir must be a safe relative path under reports/paper_runner.", {"state_export_dir": value}))
            return
        parts = path.parts
        self._expect(len(parts) >= 2 and parts[0] == "reports" and parts[1] == "paper_runner" and ".." not in parts, issues, "state_export_dir", "state_export_dir must be under reports/paper_runner.", {"state_export_dir": value})

    def _safe_state_path(self, state_file: str) -> Path:
        path = Path(state_file)
        if path.is_absolute():
            resolved = path
            try:
                relative = resolved.relative_to(self.repo_root)
            except ValueError as exc:
                raise ValueError("state-file must be under reports/paper_runner") from exc
        else:
            relative = path
            resolved = self.repo_root / path
        parts = relative.parts
        if len(parts) < 2 or parts[0] != "reports" or parts[1] != "paper_runner" or ".." in parts:
            raise ValueError("state-file must be under reports/paper_runner")
        return resolved

    def _reject(self, action: str, status: BTCPaperRunnerStatus, message: str) -> BTCPaperRunnerTransitionResult:
        return BTCPaperRunnerTransitionResult(
            action=action,
            accepted=False,
            previous_state=status.state,
            current_state=status.state,
            status=status,
            message=message,
            issues=list(status.issues),
        )

    def _normalize_action(self, action: str) -> str:
        return action.strip().replace("-", "_").upper()

    def _notes(self, config: BTCPaperRunnerConfig) -> list[str]:
        notes = [NO_EXECUTION_MESSAGE]
        if not config.runner_enabled:
            notes.append("Runner config is disabled by default; lifecycle command is dry-run simulation only.")
        if config.notes:
            notes.append(config.notes)
        return notes

    def _expect(self, condition: bool, issues: list[BTCPaperRunnerIssue], name: str, message: str, details: dict[str, Any] | None = None) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message, details))

    def _issue(self, name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> BTCPaperRunnerIssue:
        return BTCPaperRunnerIssue(name=name, severity=severity, message=message, details=details or {})

    def _resolve(self, path_text: str) -> Path:
        path = Path(path_text)
        if not path.is_absolute():
            path = self.repo_root / path
        return path

    def _now(self) -> str:
        return datetime.now(UTC).replace(microsecond=0).isoformat()
