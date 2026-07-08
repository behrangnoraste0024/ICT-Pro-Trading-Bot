from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine
from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from models.btc_paper_signal_evaluation import (
    BTCPaperSignalEvaluationConfig,
    BTCPaperSignalEvaluationDecision,
    BTCPaperSignalEvaluationIssue,
    BTCPaperSignalEvaluationResult,
    BTCPaperSignalEvaluationStatus,
    BTCPaperSignalEvaluationValidationReport,
)


class BTCPaperSignalEvaluationEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        runtime_config_engine: BTCPaperRuntimeConfigEngine | None = None,
        monitoring_engine: BTCPaperMonitoringEngine | None = None,
        runner_engine: BTCPaperRunnerEngine | None = None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.runtime_config_engine = runtime_config_engine or BTCPaperRuntimeConfigEngine(repo_root=self.repo_root)
        self.monitoring_engine = monitoring_engine or BTCPaperMonitoringEngine(repo_root=self.repo_root)
        self.runner_engine = runner_engine or BTCPaperRunnerEngine(repo_root=self.repo_root)

    def validate(
        self,
        config_path: str = "configs/btc_paper_signal_evaluation.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCPaperSignalEvaluationValidationReport:
        issues: list[BTCPaperSignalEvaluationIssue] = []
        diagnostics: dict[str, Any] = {
            "runtime_config_status": "UNKNOWN",
            "monitoring_config_status": "UNKNOWN",
            "runner_config_status": "UNKNOWN",
            "kill_switch_enabled": None,
        }
        config: BTCPaperSignalEvaluationConfig | None = None
        try:
            config = self.load_config(config_path)
        except Exception as exc:
            issues.append(self._issue("config_invalid", "FAIL", f"BTC paper signal evaluation config could not be loaded: {exc}", {"config_path": config_path}))
            return self._report(config_path, config, issues, diagnostics)
        self._validate_config_values(config, expected_profile, issues, diagnostics)
        return self._report(config_path, config, issues, diagnostics)

    def evaluate(
        self,
        config_path: str = "configs/btc_paper_signal_evaluation.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCPaperSignalEvaluationResult:
        report = self.validate(config_path=config_path, expected_profile=expected_profile)
        config = report.config or BTCPaperSignalEvaluationConfig()
        issues = list(report.issues)
        candle_count = 0
        confirmation_count = 0
        latest_timestamp = None
        confirmation_latest_timestamp = None
        direction = None
        score = None
        decision = BTCPaperSignalEvaluationDecision.ERROR.value
        status = report.status
        reason = "Signal evaluation safety validation failed."
        setup_summary: dict[str, Any] = {}
        if report.status != BTCPaperSignalEvaluationStatus.FAIL.value:
            candles = self._load_fixture(config.fixture_path, issues, "fixture_path")
            confirmation = self._load_fixture(config.confirmation_fixture_path, issues, "confirmation_fixture_path")
            if candles is not None:
                candle_count = len(candles)
                latest_timestamp = self._latest_timestamp(candles)
                if candle_count < config.min_candles:
                    issues.append(self._issue("min_candles", "FAIL", "Primary fixture has too few candles.", {"candle_count": candle_count, "min_candles": config.min_candles}))
            if confirmation is not None:
                confirmation_count = len(confirmation)
                confirmation_latest_timestamp = self._latest_timestamp(confirmation)
                if confirmation_count < config.min_candles:
                    issues.append(self._issue("confirmation_min_candles", "FAIL", "Confirmation fixture has too few candles.", {"candle_count": confirmation_count, "min_candles": config.min_candles}))
            if not any(issue.severity == "FAIL" for issue in issues) and candles is not None:
                window = candles.tail(min(config.max_evaluation_window, len(candles)))
                direction = self._infer_direction(window)
                score = self._score_window(window)
                setup_summary = {
                    "adapter": "latest_closed_candle_dry_run",
                    "window_candles": len(window),
                    "latest_close": self._float_value(window.iloc[-1].get("close")),
                    "direction_hint": direction,
                    "trade_pipeline_invoked": False,
                }
                decision, reason = self._decision(score, config.decision_threshold)
                status = BTCPaperSignalEvaluationStatus.PASS.value if decision != BTCPaperSignalEvaluationDecision.WARNING_DRY_RUN.value else BTCPaperSignalEvaluationStatus.WARNING.value
        if any(issue.severity == "FAIL" for issue in issues):
            status = BTCPaperSignalEvaluationStatus.FAIL.value
            decision = BTCPaperSignalEvaluationDecision.ERROR.value
            reason = "Signal evaluation failed safety or fixture validation."
        return BTCPaperSignalEvaluationResult(
            created_at=self._now(),
            project_scope=config.project_scope,
            symbol=config.symbol,
            strategy_profile=config.strategy_profile,
            sample_name=config.sample_name,
            confirmation_sample_name=config.confirmation_sample_name,
            evaluation_mode=config.evaluation_mode,
            status=status,
            decision=decision,
            candle_count=candle_count,
            confirmation_candle_count=confirmation_count,
            latest_timestamp=latest_timestamp,
            confirmation_latest_timestamp=confirmation_latest_timestamp,
            direction=direction,
            score=score,
            threshold=config.decision_threshold,
            reason=reason,
            setup_summary=setup_summary,
            safety_summary=self._safety_summary(config, report.diagnostics),
            runtime_config_status=str(report.diagnostics.get("runtime_config_status", "UNKNOWN")),
            monitoring_config_status=str(report.diagnostics.get("monitoring_config_status", "UNKNOWN")),
            runner_config_status=str(report.diagnostics.get("runner_config_status", "UNKNOWN")),
            dry_run_only=config.dry_run_only,
            trade_created=False,
            order_submitted=False,
            exchange_connected=False,
            state_mutated=False,
            issues=issues,
        )

    def load_config(self, config_path: str = "configs/btc_paper_signal_evaluation.json") -> BTCPaperSignalEvaluationConfig:
        path = self._resolve(config_path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("config JSON must be an object")
        return BTCPaperSignalEvaluationConfig(**{**BTCPaperSignalEvaluationConfig().to_dict(), **loaded})

    def _validate_config_values(
        self,
        config: BTCPaperSignalEvaluationConfig,
        expected_profile: str,
        issues: list[BTCPaperSignalEvaluationIssue],
        diagnostics: dict[str, Any],
    ) -> None:
        self._expect(config.project_scope == "BTC_ONLY", issues, "project_scope", "project_scope must be BTC_ONLY.", {"project_scope": config.project_scope})
        self._expect(config.symbol == "BTC/USDT", issues, "symbol", "symbol must be BTC/USDT.", {"symbol": config.symbol})
        self._expect(config.strategy_profile == expected_profile, issues, "strategy_profile", f"strategy_profile must be {expected_profile}.", {"strategy_profile": config.strategy_profile})
        self._expect(config.evaluation_mode == "latest_closed_candle", issues, "evaluation_mode", "evaluation_mode must be latest_closed_candle.", {"evaluation_mode": config.evaluation_mode})
        self._expect(config.dry_run_only, issues, "dry_run_only", "dry_run_only must be true.")
        self._expect(not config.allow_trade_creation, issues, "allow_trade_creation", "trade creation must remain disabled.")
        self._expect(not config.allow_order_submission, issues, "allow_order_submission", "order submission must remain disabled.")
        self._expect(not config.allow_exchange_connection, issues, "allow_exchange_connection", "exchange connection must remain disabled.")
        self._expect(not config.allow_state_mutation, issues, "allow_state_mutation", "state mutation must remain disabled.")
        self._expect(0.0 <= float(config.decision_threshold) <= 1.0, issues, "decision_threshold", "decision_threshold must be between 0.0 and 1.0.", {"decision_threshold": config.decision_threshold})
        self._expect(config.min_candles >= 1, issues, "min_candles", "min_candles must be positive.", {"min_candles": config.min_candles})
        self._expect(50 <= int(config.max_evaluation_window) <= int(config.min_candles), issues, "max_evaluation_window", "max_evaluation_window must be between 50 and min_candles.", {"max_evaluation_window": config.max_evaluation_window, "min_candles": config.min_candles})
        self._validate_status_export_dir(config.status_export_dir, issues)
        self._validate_fixture_path(config.fixture_path, issues, "fixture_path")
        self._validate_fixture_path(config.confirmation_fixture_path, issues, "confirmation_fixture_path")
        self._validate_runtime_config(config, expected_profile, issues, diagnostics)
        self._validate_monitoring_config(config, expected_profile, issues, diagnostics)
        self._validate_runner_config(config, expected_profile, issues, diagnostics)

    def _validate_runtime_config(self, config: BTCPaperSignalEvaluationConfig, expected_profile: str, issues: list[BTCPaperSignalEvaluationIssue], diagnostics: dict[str, Any]) -> None:
        report = self.runtime_config_engine.validate(config.runtime_config_path, expected_profile=expected_profile)
        diagnostics["runtime_config_status"] = report.status
        runtime_config = report.config
        diagnostics["kill_switch_enabled"] = bool(getattr(runtime_config, "kill_switch_enabled", False))
        if config.require_runtime_config_pass and report.status != "PASS":
            issues.append(self._issue("runtime_config_validation", "FAIL", "Runtime config must validate PASS.", {"runtime_config_status": report.status}))
        if runtime_config is not None and config.require_kill_switch_enabled:
            self._expect(runtime_config.kill_switch_enabled, issues, "kill_switch_enabled", "kill_switch_enabled must remain true.")

    def _validate_monitoring_config(self, config: BTCPaperSignalEvaluationConfig, expected_profile: str, issues: list[BTCPaperSignalEvaluationIssue], diagnostics: dict[str, Any]) -> None:
        report = self.monitoring_engine.validate(config.monitoring_config_path, expected_profile=expected_profile)
        diagnostics["monitoring_config_status"] = report.status
        if config.require_monitoring_config_pass and report.status != "PASS":
            issues.append(self._issue("monitoring_config_validation", "FAIL", "Monitoring config must validate PASS.", {"monitoring_config_status": report.status}))

    def _validate_runner_config(self, config: BTCPaperSignalEvaluationConfig, expected_profile: str, issues: list[BTCPaperSignalEvaluationIssue], diagnostics: dict[str, Any]) -> None:
        _, runner_issues, runner_diagnostics = self.runner_engine.validate_config(config.runner_config_path, expected_profile=expected_profile)
        fail_count = sum(1 for issue in runner_issues if issue.severity == "FAIL")
        diagnostics["runner_config_status"] = "FAIL" if fail_count else "PASS"
        diagnostics["runner_config_issues"] = [issue.to_dict() for issue in runner_issues]
        diagnostics["runner_diagnostics"] = runner_diagnostics
        if config.require_runner_config_pass and fail_count:
            issues.append(self._issue("runner_config_validation", "FAIL", "Runner config must validate PASS.", {"runner_fail_count": fail_count}))

    def _validate_fixture_path(self, value: str, issues: list[BTCPaperSignalEvaluationIssue], name: str) -> None:
        path = Path(value)
        if path.is_absolute():
            return
        parts = path.parts
        self._expect(len(parts) >= 2 and parts[0] == "data" and parts[1] == "historical" and ".." not in parts, issues, name, f"{name} must be under data/historical.", {name: value})

    def _validate_status_export_dir(self, value: str, issues: list[BTCPaperSignalEvaluationIssue]) -> None:
        path = Path(value)
        if path.is_absolute():
            issues.append(self._issue("status_export_dir", "FAIL", "status_export_dir must be a safe relative path under reports/paper_signal_evaluation.", {"status_export_dir": value}))
            return
        parts = path.parts
        self._expect(len(parts) >= 2 and parts[0] == "reports" and parts[1] == "paper_signal_evaluation" and ".." not in parts, issues, "status_export_dir", "status_export_dir must be under reports/paper_signal_evaluation.", {"status_export_dir": value})

    def _load_fixture(self, path_text: str, issues: list[BTCPaperSignalEvaluationIssue], name: str) -> pd.DataFrame | None:
        path = self._resolve(path_text)
        if not path.exists():
            issues.append(self._issue(name, "FAIL", f"{name} is missing.", {name: str(path)}))
            return None
        try:
            return pd.read_json(path)
        except Exception as exc:
            issues.append(self._issue(name, "FAIL", f"{name} could not be loaded: {exc}", {name: str(path)}))
            return None

    def _infer_direction(self, frame: pd.DataFrame) -> str:
        if frame.empty or "close" not in frame:
            return "NONE"
        first = self._float_value(frame.iloc[0].get("close"))
        last = self._float_value(frame.iloc[-1].get("close"))
        if first is None or last is None:
            return "NONE"
        if last > first:
            return "BULLISH"
        if last < first:
            return "BEARISH"
        return "RANGE"

    def _score_window(self, frame: pd.DataFrame) -> float | None:
        if frame.empty or "close" not in frame:
            return None
        closes = pd.to_numeric(frame["close"], errors="coerce").dropna()
        if closes.empty:
            return None
        change = abs(float(closes.iloc[-1]) - float(closes.iloc[0]))
        base = max(abs(float(closes.iloc[0])), 1.0)
        return round(min(change / base, 1.0), 4)

    def _decision(self, score: float | None, threshold: float) -> tuple[str, str]:
        if score is None:
            return BTCPaperSignalEvaluationDecision.NONE.value, "No score could be computed from the local fixture."
        if score >= threshold:
            return BTCPaperSignalEvaluationDecision.APPROVED_DRY_RUN.value, "Dry-run context score meets threshold; no execution action was taken."
        if score > 0:
            return BTCPaperSignalEvaluationDecision.WARNING_DRY_RUN.value, "Dry-run context exists but score is below threshold; no execution action was taken."
        return BTCPaperSignalEvaluationDecision.NONE.value, "No actionable dry-run signal context found."

    def _latest_timestamp(self, frame: pd.DataFrame) -> str | None:
        if frame.empty:
            return None
        for name in ("timestamp", "time", "datetime"):
            if name in frame.columns:
                value = frame.iloc[-1].get(name)
                return None if pd.isna(value) else str(value)
        return str(frame.index[-1])

    def _safety_summary(self, config: BTCPaperSignalEvaluationConfig, diagnostics: dict[str, Any]) -> dict[str, Any]:
        return {
            "dry_run_only": config.dry_run_only,
            "allow_trade_creation": config.allow_trade_creation,
            "allow_order_submission": config.allow_order_submission,
            "allow_exchange_connection": config.allow_exchange_connection,
            "allow_state_mutation": config.allow_state_mutation,
            "kill_switch_enabled": diagnostics.get("kill_switch_enabled"),
        }

    def _report(self, config_path: str, config: BTCPaperSignalEvaluationConfig | None, issues: list[BTCPaperSignalEvaluationIssue], diagnostics: dict[str, Any]) -> BTCPaperSignalEvaluationValidationReport:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        status = "FAIL" if failures else "WARNING" if warnings else "PASS"
        return BTCPaperSignalEvaluationValidationReport(
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

    def _expect(self, condition: bool, issues: list[BTCPaperSignalEvaluationIssue], name: str, message: str, details: dict[str, Any] | None = None) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message, details))

    def _issue(self, name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> BTCPaperSignalEvaluationIssue:
        return BTCPaperSignalEvaluationIssue(name=name, severity=severity, message=message, details=details or {})

    def _resolve(self, path_text: str) -> Path:
        path = Path(path_text)
        if not path.is_absolute():
            path = self.repo_root / path
        return path

    def _float_value(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _now(self) -> str:
        return datetime.now(UTC).replace(microsecond=0).isoformat()
