from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from models.btc_paper_monitoring import (
    BTCPaperMonitoringConfig,
    BTCPaperMonitoringIssue,
    BTCPaperMonitoringStatus,
    BTCPaperMonitoringValidationReport,
)


class BTCPaperMonitoringEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        runtime_config_engine: BTCPaperRuntimeConfigEngine | None = None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.runtime_config_engine = runtime_config_engine or BTCPaperRuntimeConfigEngine(repo_root=self.repo_root)

    def validate(
        self,
        config_path: str = "configs/btc_paper_monitoring.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCPaperMonitoringValidationReport:
        path = self._resolve(config_path)
        issues: list[BTCPaperMonitoringIssue] = []
        diagnostics: dict[str, Any] = {"runtime_config_status": "UNKNOWN"}
        config: BTCPaperMonitoringConfig | None = None
        if not path.exists():
            issues.append(self._issue("config_missing", "FAIL", "BTC paper monitoring config is missing.", {"config_path": str(path)}))
            return self._report(config_path, config, issues, diagnostics)
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("config JSON must be an object")
            config = BTCPaperMonitoringConfig(**{**BTCPaperMonitoringConfig().to_dict(), **loaded})
        except Exception as exc:
            issues.append(self._issue("config_invalid", "FAIL", f"BTC paper monitoring config could not be loaded: {exc}", {"config_path": str(path)}))
            return self._report(config_path, config, issues, diagnostics)

        self._validate_values(config, expected_profile, issues, diagnostics)
        return self._report(config_path, config, issues, diagnostics)

    def build_status(
        self,
        config_path: str = "configs/btc_paper_monitoring.json",
        expected_profile: str = "balanced_smc_decision_065",
        validation_gate_status: str = "UNKNOWN",
    ) -> BTCPaperMonitoringStatus:
        report = self.validate(config_path=config_path, expected_profile=expected_profile)
        config = report.config or BTCPaperMonitoringConfig()
        runtime_report = None
        if report.config is not None:
            runtime_report = self.runtime_config_engine.validate(
                config_path=config.runtime_config_path,
                expected_profile=expected_profile,
            )
        runtime_config = getattr(runtime_report, "config", None)
        monitoring_status = "READY" if report.status == "PASS" else "WARNING" if report.status == "WARNING" else "BLOCKED"
        return BTCPaperMonitoringStatus(
            created_at=self._now(),
            project_scope=config.project_scope,
            symbol=config.symbol,
            strategy_profile=config.strategy_profile,
            monitoring_status=monitoring_status,
            runtime_config_status=report.diagnostics.get("runtime_config_status", "UNKNOWN"),
            validation_gate_status=validation_gate_status,
            paper_execution_enabled=bool(getattr(runtime_config, "paper_execution_enabled", False)),
            live_trading_enabled=bool(getattr(runtime_config, "live_trading_enabled", False)),
            order_submission_enabled=bool(getattr(runtime_config, "order_submission_enabled", False)),
            dry_run=bool(getattr(runtime_config, "dry_run", True)),
            kill_switch_enabled=bool(getattr(runtime_config, "kill_switch_enabled", True)),
            last_heartbeat_at=None,
            last_signal_at=None,
            last_error_at=None,
            consecutive_errors=0,
            notes=["No paper runner is active yet; this is a pre-runner monitoring readiness status."],
            issues=list(report.issues),
        )

    def _validate_values(
        self,
        config: BTCPaperMonitoringConfig,
        expected_profile: str,
        issues: list[BTCPaperMonitoringIssue],
        diagnostics: dict[str, Any],
    ) -> None:
        self._expect(config.project_scope == "BTC_ONLY", issues, "project_scope", "project_scope must be BTC_ONLY.", {"project_scope": config.project_scope})
        self._expect(config.symbol == "BTC/USDT", issues, "symbol", "symbol must be BTC/USDT.", {"symbol": config.symbol})
        self._expect(config.strategy_profile == expected_profile, issues, "strategy_profile", f"strategy_profile must be {expected_profile}.", {"strategy_profile": config.strategy_profile, "expected_profile": expected_profile})
        self._expect(config.enabled, issues, "enabled", "monitoring enabled must be true.")
        self._expect(config.monitoring_only, issues, "monitoring_only", "monitoring_only must be true; this release must not execute trades.")
        self._expect(not config.paper_execution_expected, issues, "paper_execution_expected", "paper_execution_expected must be false.")
        self._expect(not config.live_trading_expected, issues, "live_trading_expected", "live_trading_expected must be false.")
        self._expect(not config.order_submission_expected, issues, "order_submission_expected", "order_submission_expected must be false.")
        self._expect(30 <= int(config.heartbeat_stale_after_seconds) <= 600, issues, "heartbeat_stale_after_seconds", "heartbeat_stale_after_seconds must be between 30 and 600.", {"heartbeat_stale_after_seconds": config.heartbeat_stale_after_seconds})
        self._expect(5 <= int(config.signal_stale_after_minutes) <= 240, issues, "signal_stale_after_minutes", "signal_stale_after_minutes must be between 5 and 240.", {"signal_stale_after_minutes": config.signal_stale_after_minutes})
        self._expect(1 <= int(config.validation_gate_stale_after_hours) <= 72, issues, "validation_gate_stale_after_hours", "validation_gate_stale_after_hours must be between 1 and 72.", {"validation_gate_stale_after_hours": config.validation_gate_stale_after_hours})
        self._expect(1 <= int(config.runtime_config_stale_after_hours) <= 72, issues, "runtime_config_stale_after_hours", "runtime_config_stale_after_hours must be between 1 and 72.", {"runtime_config_stale_after_hours": config.runtime_config_stale_after_hours})
        self._expect(1 <= int(config.max_consecutive_errors) <= 10, issues, "max_consecutive_errors", "max_consecutive_errors must be between 1 and 10.", {"max_consecutive_errors": config.max_consecutive_errors})
        self._expect(config.require_kill_switch_visible, issues, "require_kill_switch_visible", "require_kill_switch_visible must be true.")
        self._expect(config.require_execution_state_visible, issues, "require_execution_state_visible", "require_execution_state_visible must be true.")
        self._expect(config.require_runtime_config_visible, issues, "require_runtime_config_visible", "require_runtime_config_visible must be true.")
        self._expect(config.require_validation_gate_status_visible, issues, "require_validation_gate_status_visible", "require_validation_gate_status_visible must be true.")
        self._validate_status_export_dir(config.status_export_dir, issues)
        self._validate_runtime_config(config, expected_profile, issues, diagnostics)

    def _validate_runtime_config(
        self,
        config: BTCPaperMonitoringConfig,
        expected_profile: str,
        issues: list[BTCPaperMonitoringIssue],
        diagnostics: dict[str, Any],
    ) -> None:
        runtime_path = self._resolve(config.runtime_config_path)
        if not runtime_path.exists():
            diagnostics["runtime_config_status"] = "FAIL"
            issues.append(self._issue("runtime_config_missing", "FAIL", "BTC paper runtime config is missing.", {"runtime_config_path": str(runtime_path)}))
            return
        runtime_report = self.runtime_config_engine.validate(
            config_path=config.runtime_config_path,
            expected_profile=expected_profile,
        )
        diagnostics["runtime_config_status"] = runtime_report.status
        diagnostics["runtime_config_issue_count"] = runtime_report.issue_count
        diagnostics["runtime_config_issues"] = [issue.to_dict() for issue in runtime_report.issues]
        if runtime_report.status != "PASS":
            issues.append(
                self._issue(
                    "runtime_config_validation",
                    "FAIL",
                    "BTC paper runtime config must validate PASS before monitoring readiness can pass.",
                    {"runtime_config_status": runtime_report.status, "issues": diagnostics["runtime_config_issues"]},
                )
            )

    def _validate_status_export_dir(self, value: str, issues: list[BTCPaperMonitoringIssue]) -> None:
        path = Path(value)
        if path.is_absolute():
            issues.append(self._issue("status_export_dir", "FAIL", "status_export_dir must be a safe relative path under reports/paper_monitoring.", {"status_export_dir": value}))
            return
        parts = path.parts
        safe = len(parts) >= 2 and parts[0] == "reports" and parts[1] == "paper_monitoring" and ".." not in parts
        self._expect(safe, issues, "status_export_dir", "status_export_dir must be under reports/paper_monitoring.", {"status_export_dir": value})

    def _expect(
        self,
        condition: bool,
        issues: list[BTCPaperMonitoringIssue],
        name: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message, details))

    def _report(
        self,
        config_path: str,
        config: BTCPaperMonitoringConfig | None,
        issues: list[BTCPaperMonitoringIssue],
        diagnostics: dict[str, Any],
    ) -> BTCPaperMonitoringValidationReport:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        status = "FAIL" if failures else "WARNING" if warnings else "PASS"
        return BTCPaperMonitoringValidationReport(
            config_path=config_path,
            created_at=self._now(),
            status=status,
            issue_count=len(issues),
            warning_count=warnings,
            fail_count=failures,
            config=config,
            issues=issues,
            diagnostics=diagnostics,
        )

    def _resolve(self, path_text: str) -> Path:
        path = Path(path_text)
        if not path.is_absolute():
            path = self.repo_root / path
        return path

    def _issue(
        self,
        name: str,
        severity: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> BTCPaperMonitoringIssue:
        return BTCPaperMonitoringIssue(name=name, severity=severity, message=message, details=details or {})

    def _now(self) -> str:
        return datetime.now(UTC).replace(microsecond=0).isoformat()
