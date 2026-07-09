from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine
from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from engine.diagnostics.btc_paper_signal_evaluation_engine import BTCPaperSignalEvaluationEngine
from models.btc_paper_trade_candidate import (
    BTCPaperTradeCandidate,
    BTCPaperTradeCandidateConfig,
    BTCPaperTradeCandidateDecision,
    BTCPaperTradeCandidateIssue,
    BTCPaperTradeCandidateResult,
    BTCPaperTradeCandidateStatus,
    BTCPaperTradeCandidateValidationReport,
)


class BTCPaperTradeCandidateEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        runtime_config_engine: BTCPaperRuntimeConfigEngine | None = None,
        monitoring_engine: BTCPaperMonitoringEngine | None = None,
        runner_engine: BTCPaperRunnerEngine | None = None,
        signal_engine: BTCPaperSignalEvaluationEngine | None = None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.runtime_config_engine = runtime_config_engine or BTCPaperRuntimeConfigEngine(repo_root=self.repo_root)
        self.monitoring_engine = monitoring_engine or BTCPaperMonitoringEngine(repo_root=self.repo_root)
        self.runner_engine = runner_engine or BTCPaperRunnerEngine(repo_root=self.repo_root)
        self.signal_engine = signal_engine or BTCPaperSignalEvaluationEngine(repo_root=self.repo_root)

    def validate(
        self,
        config_path: str = "configs/btc_paper_trade_candidate.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCPaperTradeCandidateValidationReport:
        issues: list[BTCPaperTradeCandidateIssue] = []
        diagnostics: dict[str, Any] = {
            "runtime_config_status": "UNKNOWN",
            "monitoring_config_status": "UNKNOWN",
            "runner_config_status": "UNKNOWN",
            "signal_config_status": "UNKNOWN",
            "kill_switch_enabled": None,
        }
        config: BTCPaperTradeCandidateConfig | None = None
        try:
            config = self.load_config(config_path)
        except Exception as exc:
            issues.append(self._issue("config_invalid", "FAIL", f"BTC paper trade candidate config could not be loaded: {exc}", {"config_path": config_path}))
            return self._report(config_path, config, issues, diagnostics)
        self._validate_config_values(config, expected_profile, issues, diagnostics)
        return self._report(config_path, config, issues, diagnostics)

    def simulate(
        self,
        config_path: str = "configs/btc_paper_trade_candidate.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCPaperTradeCandidateResult:
        report = self.validate(config_path=config_path, expected_profile=expected_profile)
        config = report.config or BTCPaperTradeCandidateConfig()
        issues = list(report.issues)
        runtime_config = None
        if report.status != "FAIL":
            runtime_config = self.runtime_config_engine.validate(config.runtime_config_path, expected_profile=expected_profile).config
        signal_result = None
        candidate = None
        status = BTCPaperTradeCandidateStatus.FAIL.value if report.status == "FAIL" else BTCPaperTradeCandidateStatus.WARNING.value
        decision = BTCPaperTradeCandidateDecision.NO_CANDIDATE_CONFIG_UNSAFE.value if report.status == "FAIL" else BTCPaperTradeCandidateDecision.NO_CANDIDATE_SIGNAL_NOT_APPROVED.value
        reason = "Trade candidate config failed safety validation." if report.status == "FAIL" else "Signal is not approved for dry-run candidate creation."
        if report.status != "FAIL":
            signal_result = self.signal_engine.evaluate(config.signal_evaluation_config_path, expected_profile=expected_profile)
            if signal_result.status == "FAIL":
                issues.extend(self._from_signal_issues(signal_result.issues))
                status = BTCPaperTradeCandidateStatus.FAIL.value
                decision = BTCPaperTradeCandidateDecision.ERROR.value
                reason = "Signal evaluation failed; no trade candidate was created."
            elif signal_result.decision != "APPROVED_DRY_RUN":
                status = BTCPaperTradeCandidateStatus.WARNING.value
                decision = BTCPaperTradeCandidateDecision.NO_CANDIDATE_SIGNAL_NOT_APPROVED.value
                reason = "Signal evaluation did not approve a dry-run candidate."
                if signal_result.score is not None and signal_result.score < config.min_signal_score:
                    decision = BTCPaperTradeCandidateDecision.NO_CANDIDATE_SCORE_TOO_LOW.value
                    reason = "Signal score is below the trade candidate threshold."
            elif signal_result.score is None or signal_result.score < config.min_signal_score:
                status = BTCPaperTradeCandidateStatus.WARNING.value
                decision = BTCPaperTradeCandidateDecision.NO_CANDIDATE_SCORE_TOO_LOW.value
                reason = "Signal score is below the trade candidate threshold."
            else:
                candidate, candidate_issues = self._build_candidate(config, runtime_config, signal_result)
                issues.extend(candidate_issues)
                if candidate is None:
                    status = BTCPaperTradeCandidateStatus.WARNING.value
                    decision = BTCPaperTradeCandidateDecision.NO_CANDIDATE_SIGNAL_NOT_APPROVED.value
                    reason = "Approved signal did not contain enough diagnostic price/direction data."
                else:
                    status = BTCPaperTradeCandidateStatus.PASS.value
                    decision = BTCPaperTradeCandidateDecision.CANDIDATE_CREATED_DRY_RUN.value
                    reason = "Non-executable dry-run trade candidate created."
        return BTCPaperTradeCandidateResult(
            created_at=self._now(),
            project_scope=config.project_scope,
            symbol=config.symbol,
            strategy_profile=config.strategy_profile,
            status=status,
            decision=decision,
            candidate_created=candidate is not None,
            candidate=candidate,
            signal_decision=None if signal_result is None else signal_result.decision,
            signal_score=None if signal_result is None else signal_result.score,
            signal_threshold=config.min_signal_score,
            reason=reason,
            runtime_config_status=str(report.diagnostics.get("runtime_config_status", "UNKNOWN")),
            monitoring_config_status=str(report.diagnostics.get("monitoring_config_status", "UNKNOWN")),
            runner_config_status=str(report.diagnostics.get("runner_config_status", "UNKNOWN")),
            signal_config_status=str(report.diagnostics.get("signal_config_status", "UNKNOWN")),
            dry_run_only=config.dry_run_only,
            executable_trade_created=False,
            paper_trade_persisted=False,
            position_created=False,
            order_submitted=False,
            exchange_connected=False,
            state_mutated=False,
            safety_summary=self._safety_summary(config, report.diagnostics),
            issues=issues,
        )

    def load_config(self, config_path: str = "configs/btc_paper_trade_candidate.json") -> BTCPaperTradeCandidateConfig:
        path = self._resolve(config_path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("config JSON must be an object")
        return BTCPaperTradeCandidateConfig(**{**BTCPaperTradeCandidateConfig().to_dict(), **loaded})

    def _validate_config_values(self, config: BTCPaperTradeCandidateConfig, expected_profile: str, issues: list[BTCPaperTradeCandidateIssue], diagnostics: dict[str, Any]) -> None:
        self._expect(config.project_scope == "BTC_ONLY", issues, "project_scope", "project_scope must be BTC_ONLY.", {"project_scope": config.project_scope})
        self._expect(config.symbol == "BTC/USDT", issues, "symbol", "symbol must be BTC/USDT.", {"symbol": config.symbol})
        self._expect(config.strategy_profile == expected_profile, issues, "strategy_profile", f"strategy_profile must be {expected_profile}.", {"strategy_profile": config.strategy_profile})
        self._expect(config.dry_run_only, issues, "dry_run_only", "dry_run_only must be true.")
        self._expect(config.allow_candidate_creation in (True, False), issues, "allow_candidate_creation", "allow_candidate_creation must be boolean.")
        self._expect(not config.allow_executable_trade_creation, issues, "allow_executable_trade_creation", "executable trade creation must remain disabled.")
        self._expect(not config.allow_paper_trade_persistence, issues, "allow_paper_trade_persistence", "paper trade persistence must remain disabled.")
        self._expect(not config.allow_position_creation, issues, "allow_position_creation", "position creation must remain disabled.")
        self._expect(not config.allow_order_submission, issues, "allow_order_submission", "order submission must remain disabled.")
        self._expect(not config.allow_exchange_connection, issues, "allow_exchange_connection", "exchange connection must remain disabled.")
        self._expect(not config.allow_state_mutation, issues, "allow_state_mutation", "state mutation must remain disabled.")
        self._expect(0.0 <= float(config.min_signal_score) <= 1.0, issues, "min_signal_score", "min_signal_score must be between 0.0 and 1.0.", {"min_signal_score": config.min_signal_score})
        self._expect(float(config.min_risk_reward) >= 1.5, issues, "min_risk_reward", "min_risk_reward must be >= 1.5.", {"min_risk_reward": config.min_risk_reward})
        self._expect(0 < float(config.diagnostic_stop_loss_pct) <= 0.05, issues, "diagnostic_stop_loss_pct", "diagnostic_stop_loss_pct must be > 0 and <= 0.05.", {"diagnostic_stop_loss_pct": config.diagnostic_stop_loss_pct})
        self._expect(float(config.max_candidate_notional_pct) <= 0.30, issues, "max_candidate_notional_pct", "max_candidate_notional_pct must be <= 0.30.", {"max_candidate_notional_pct": config.max_candidate_notional_pct})
        self._expect(config.entry_price_source == "latest_close", issues, "entry_price_source", "entry_price_source must be latest_close.")
        self._expect(config.stop_loss_mode == "diagnostic_atr_like", issues, "stop_loss_mode", "stop_loss_mode must be diagnostic_atr_like.")
        self._expect(config.take_profit_mode == "fixed_rr", issues, "take_profit_mode", "take_profit_mode must be fixed_rr.")
        self._validate_status_export_dir(config.status_export_dir, issues)
        self._validate_runtime_config(config, expected_profile, issues, diagnostics)
        self._validate_monitoring_config(config, expected_profile, issues, diagnostics)
        self._validate_runner_config(config, expected_profile, issues, diagnostics)
        self._validate_signal_config(config, expected_profile, issues, diagnostics)

    def _validate_runtime_config(self, config: BTCPaperTradeCandidateConfig, expected_profile: str, issues: list[BTCPaperTradeCandidateIssue], diagnostics: dict[str, Any]) -> None:
        report = self.runtime_config_engine.validate(config.runtime_config_path, expected_profile=expected_profile)
        diagnostics["runtime_config_status"] = report.status
        runtime_config = report.config
        diagnostics["runtime_config"] = runtime_config
        diagnostics["kill_switch_enabled"] = bool(getattr(runtime_config, "kill_switch_enabled", False))
        if config.require_runtime_config_pass and report.status != "PASS":
            issues.append(self._issue("runtime_config_validation", "FAIL", "Runtime config must validate PASS.", {"runtime_config_status": report.status}))
        if runtime_config is not None:
            self._expect(float(config.min_risk_reward) >= float(runtime_config.min_risk_reward), issues, "min_risk_reward_runtime", "min_risk_reward must be >= runtime min_risk_reward.", {"min_risk_reward": config.min_risk_reward, "runtime_min_risk_reward": runtime_config.min_risk_reward})
            self._expect(float(config.max_candidate_notional_pct) <= float(runtime_config.max_position_notional_pct), issues, "max_candidate_notional_pct_runtime", "max_candidate_notional_pct must be <= runtime max_position_notional_pct.", {"max_candidate_notional_pct": config.max_candidate_notional_pct, "runtime_max_position_notional_pct": runtime_config.max_position_notional_pct})
            if config.require_kill_switch_enabled:
                self._expect(runtime_config.kill_switch_enabled, issues, "kill_switch_enabled", "kill_switch_enabled must remain true.")

    def _validate_monitoring_config(self, config: BTCPaperTradeCandidateConfig, expected_profile: str, issues: list[BTCPaperTradeCandidateIssue], diagnostics: dict[str, Any]) -> None:
        report = self.monitoring_engine.validate(config.monitoring_config_path, expected_profile=expected_profile)
        diagnostics["monitoring_config_status"] = report.status
        if config.require_monitoring_config_pass and report.status != "PASS":
            issues.append(self._issue("monitoring_config_validation", "FAIL", "Monitoring config must validate PASS.", {"monitoring_config_status": report.status}))

    def _validate_runner_config(self, config: BTCPaperTradeCandidateConfig, expected_profile: str, issues: list[BTCPaperTradeCandidateIssue], diagnostics: dict[str, Any]) -> None:
        _, runner_issues, _ = self.runner_engine.validate_config(config.runner_config_path, expected_profile=expected_profile)
        fail_count = sum(1 for issue in runner_issues if issue.severity == "FAIL")
        diagnostics["runner_config_status"] = "FAIL" if fail_count else "PASS"
        if config.require_runner_config_pass and fail_count:
            issues.append(self._issue("runner_config_validation", "FAIL", "Runner config must validate PASS.", {"runner_fail_count": fail_count}))

    def _validate_signal_config(self, config: BTCPaperTradeCandidateConfig, expected_profile: str, issues: list[BTCPaperTradeCandidateIssue], diagnostics: dict[str, Any]) -> None:
        report = self.signal_engine.validate(config.signal_evaluation_config_path, expected_profile=expected_profile)
        diagnostics["signal_config_status"] = report.status
        if config.require_signal_config_pass and report.status != "PASS":
            issues.append(self._issue("signal_config_validation", "FAIL", "Signal evaluation config must validate PASS.", {"signal_config_status": report.status}))

    def _build_candidate(self, config: BTCPaperTradeCandidateConfig, runtime_config: Any, signal_result: Any) -> tuple[BTCPaperTradeCandidate | None, list[BTCPaperTradeCandidateIssue]]:
        issues: list[BTCPaperTradeCandidateIssue] = []
        direction = str(signal_result.direction or "").upper()
        entry = self._float_value((signal_result.setup_summary or {}).get("latest_close"))
        score = self._float_value(signal_result.score)
        if direction not in ("BULLISH", "BUY", "LONG", "BEARISH", "SELL", "SHORT") or entry is None or entry <= 0 or score is None:
            return None, issues
        bullish = direction in ("BULLISH", "BUY", "LONG")
        stop = entry * (1 - config.diagnostic_stop_loss_pct) if bullish else entry * (1 + config.diagnostic_stop_loss_pct)
        per_unit_risk = abs(entry - stop)
        if per_unit_risk <= 0:
            return None, [self._issue("per_unit_risk", "FAIL", "Per-unit risk must be positive.")]
        take_profit = entry + per_unit_risk * config.min_risk_reward if bullish else entry - per_unit_risk * config.min_risk_reward
        starting_equity = float(getattr(runtime_config, "starting_equity", 0.0) or 0.0)
        risk_pct = float(getattr(runtime_config, "risk_per_trade_pct", 0.0) or 0.0)
        risk_amount = starting_equity * risk_pct
        position_size = risk_amount / per_unit_risk
        notional = position_size * entry
        max_notional = starting_equity * config.max_candidate_notional_pct
        if notional > max_notional and entry > 0:
            position_size = max_notional / entry
            notional = max_notional
            issues.append(self._issue("candidate_notional_capped", "WARNING", "Candidate notional was capped by diagnostic max_candidate_notional_pct.", {"max_candidate_notional": max_notional}))
        return BTCPaperTradeCandidate(
            candidate_id=f"BTC-DRYRUN-{self._now()}",
            created_at=self._now(),
            symbol=config.symbol,
            strategy_profile=config.strategy_profile,
            direction="LONG" if bullish else "SHORT",
            entry_price=self._round(entry),
            stop_loss=self._round(stop),
            take_profit=self._round(take_profit),
            risk_reward=self._round(config.min_risk_reward),
            signal_score=self._round(score),
            signal_threshold=self._round(config.min_signal_score),
            account_currency=str(getattr(runtime_config, "account_currency", "USDT")),
            starting_equity=self._round(starting_equity),
            risk_per_trade_pct=self._round(risk_pct),
            estimated_risk_amount=self._round(risk_amount),
            estimated_position_size=self._round(position_size),
            estimated_notional=self._round(notional),
            max_candidate_notional=self._round(max_notional),
            candidate_is_executable=False,
            candidate_is_persisted=False,
            candidate_opens_position=False,
            reason="Diagnostic candidate only; not executable.",
            metadata={"signal_decision": signal_result.decision, "signal_reason": signal_result.reason},
        ), issues

    def _from_signal_issues(self, signal_issues: list[Any]) -> list[BTCPaperTradeCandidateIssue]:
        return [self._issue(f"signal_{issue.name}", issue.severity, issue.message, issue.details) for issue in signal_issues]

    def _validate_status_export_dir(self, value: str, issues: list[BTCPaperTradeCandidateIssue]) -> None:
        path = Path(value)
        if path.is_absolute():
            issues.append(self._issue("status_export_dir", "FAIL", "status_export_dir must be a safe relative path under reports/paper_trade_candidates.", {"status_export_dir": value}))
            return
        parts = path.parts
        self._expect(len(parts) >= 2 and parts[0] == "reports" and parts[1] == "paper_trade_candidates" and ".." not in parts, issues, "status_export_dir", "status_export_dir must be under reports/paper_trade_candidates.", {"status_export_dir": value})

    def _safety_summary(self, config: BTCPaperTradeCandidateConfig, diagnostics: dict[str, Any]) -> dict[str, Any]:
        return {
            "dry_run_only": config.dry_run_only,
            "allow_candidate_creation": config.allow_candidate_creation,
            "allow_executable_trade_creation": config.allow_executable_trade_creation,
            "allow_paper_trade_persistence": config.allow_paper_trade_persistence,
            "allow_position_creation": config.allow_position_creation,
            "allow_order_submission": config.allow_order_submission,
            "allow_exchange_connection": config.allow_exchange_connection,
            "allow_state_mutation": config.allow_state_mutation,
            "kill_switch_enabled": diagnostics.get("kill_switch_enabled"),
        }

    def _report(self, config_path: str, config: BTCPaperTradeCandidateConfig | None, issues: list[BTCPaperTradeCandidateIssue], diagnostics: dict[str, Any]) -> BTCPaperTradeCandidateValidationReport:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        status = "FAIL" if failures else "WARNING" if warnings else "PASS"
        serializable_diagnostics = {key: value for key, value in diagnostics.items() if key != "runtime_config"}
        return BTCPaperTradeCandidateValidationReport(
            config_path=config_path,
            created_at=self._now(),
            status=status,
            issue_count=len(issues),
            warning_count=warnings,
            fail_count=failures,
            config=config,
            issues=issues,
            diagnostics=serializable_diagnostics,
        )

    def _expect(self, condition: bool, issues: list[BTCPaperTradeCandidateIssue], name: str, message: str, details: dict[str, Any] | None = None) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message, details))

    def _issue(self, name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> BTCPaperTradeCandidateIssue:
        return BTCPaperTradeCandidateIssue(name=name, severity=severity, message=message, details=details or {})

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

    def _round(self, value: float) -> float:
        return round(float(value), 8)

    def _now(self) -> str:
        return datetime.now(UTC).replace(microsecond=0).isoformat()
