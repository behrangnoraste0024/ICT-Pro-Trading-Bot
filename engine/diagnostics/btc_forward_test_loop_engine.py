from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.diagnostics.btc_paper_candidate_journal_engine import BTCPaperCandidateJournalEngine
from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine
from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from engine.diagnostics.btc_paper_signal_evaluation_engine import BTCPaperSignalEvaluationEngine
from engine.diagnostics.btc_paper_trade_candidate_engine import BTCPaperTradeCandidateEngine
from models.btc_forward_test_loop import (
    BTCForwardTestConfig,
    BTCForwardTestCycleDecision,
    BTCForwardTestCycleResult,
    BTCForwardTestIssue,
    BTCForwardTestRunResult,
    BTCForwardTestState,
    BTCForwardTestStatus,
    BTCForwardTestValidationReport,
)


class BTCForwardTestLoopEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        runtime_config_engine: BTCPaperRuntimeConfigEngine | None = None,
        monitoring_engine: BTCPaperMonitoringEngine | None = None,
        runner_engine: BTCPaperRunnerEngine | None = None,
        signal_engine: BTCPaperSignalEvaluationEngine | None = None,
        trade_candidate_engine: BTCPaperTradeCandidateEngine | None = None,
        candidate_journal_engine: BTCPaperCandidateJournalEngine | None = None,
        now_provider=None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.runtime_config_engine = runtime_config_engine or BTCPaperRuntimeConfigEngine(repo_root=self.repo_root)
        self.monitoring_engine = monitoring_engine or BTCPaperMonitoringEngine(repo_root=self.repo_root)
        self.runner_engine = runner_engine or BTCPaperRunnerEngine(repo_root=self.repo_root)
        self.signal_engine = signal_engine or BTCPaperSignalEvaluationEngine(repo_root=self.repo_root)
        self.trade_candidate_engine = trade_candidate_engine or BTCPaperTradeCandidateEngine(repo_root=self.repo_root)
        self.candidate_journal_engine = candidate_journal_engine or BTCPaperCandidateJournalEngine(repo_root=self.repo_root)
        self.now_provider = now_provider

    def validate(
        self,
        config_path: str = "configs/btc_forward_test_loop.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCForwardTestValidationReport:
        issues: list[BTCForwardTestIssue] = []
        diagnostics: dict[str, Any] = {
            "runtime_config_status": "UNKNOWN",
            "monitoring_config_status": "UNKNOWN",
            "runner_config_status": "UNKNOWN",
            "signal_config_status": "UNKNOWN",
            "trade_candidate_config_status": "UNKNOWN",
            "candidate_journal_config_status": "UNKNOWN",
            "kill_switch_enabled": None,
        }
        config: BTCForwardTestConfig | None = None
        try:
            config = self.load_config(config_path)
        except Exception as exc:
            issues.append(self._issue("config_invalid", "FAIL", f"BTC forward test loop config could not be loaded: {exc}", {"config_path": config_path}))
            return self._report(config_path, config, issues, diagnostics)
        self._validate_config_values(config, expected_profile, issues, diagnostics)
        return self._report(config_path, config, issues, diagnostics)

    def run(
        self,
        config_path: str = "configs/btc_forward_test_loop.json",
        expected_profile: str = "balanced_smc_decision_065",
        cycles: int | None = None,
        start_index: int | None = None,
        state_file: str | None = None,
    ) -> BTCForwardTestRunResult:
        report = self.validate(config_path=config_path, expected_profile=expected_profile)
        config = report.config or BTCForwardTestConfig()
        issues = list(report.issues)
        requested = cycles or config.max_cycles
        start = start_index if start_index is not None else config.start_index
        if report.status == "FAIL":
            return self._run_result(config, report, requested, start, [], issues, "Forward test config failed safety validation.")
        candles, load_issues = self._load_candles(config.fixture_path, config.min_candles)
        issues.extend(load_issues)
        if load_issues:
            return self._run_result(config, report, requested, start, [], issues, "Forward test fixture data could not be loaded.")
        cycle_results: list[BTCForwardTestCycleResult] = []
        cursor = start
        for number in range(1, requested + 1):
            if cursor >= len(candles):
                issue = self._issue("cursor_out_of_range", "FAIL", "Forward-test cursor is outside available candles.", {"cursor_index": cursor, "candle_count": len(candles)})
                issues.append(issue)
                cycle_results.append(self._failed_cycle(config, number, cursor, [issue], "Cursor is outside available candles."))
                break
            cycle = self._run_cycle(config, report, number, cursor, candles[cursor])
            cycle_results.append(cycle)
            if any(issue.severity == "FAIL" for issue in cycle.issues):
                break
            cursor += 1
        result = self._run_result(config, report, requested, start, cycle_results, issues, "Forward test dry-run completed.")
        if state_file:
            self.save_state(self.state_from_result(result), state_file)
        return result

    def summary(self, state_file: str | None = None) -> BTCForwardTestState:
        if not state_file:
            return self._empty_state("No state file supplied.")
        path = self._resolve(state_file)
        if not path.exists():
            return self._empty_state("Forward test state file does not exist.")
        data = json.loads(path.read_text(encoding="utf-8"))
        return BTCForwardTestState(**{**BTCForwardTestState().to_dict(), **data})

    def reset_state(self, state_file: str | None = None) -> BTCForwardTestState:
        state = self._empty_state("Forward test state reset.")
        if state_file:
            path = self._resolve(state_file)
            if self._safe_forward_report_path(path):
                path.unlink(missing_ok=True)
        return state

    def state_from_result(self, result: BTCForwardTestRunResult) -> BTCForwardTestState:
        return BTCForwardTestState(
            created_at=result.created_at,
            updated_at=self._now(),
            project_scope=result.project_scope,
            symbol=result.symbol,
            strategy_profile=result.strategy_profile,
            last_cursor_index=result.end_index,
            last_cycle_at=None if not result.cycles else result.cycles[-1].created_at,
            total_cycles_completed=result.cycles_completed,
            total_candidates_created=result.candidates_created,
            total_candidates_rejected=result.candidates_rejected,
            total_journal_entries_written=result.journal_entries_written,
            last_status=result.status,
            last_reason=None if not result.issues else result.issues[-1].message,
            dry_run_only=True,
            executable_trade_created=False,
            paper_trade_persisted=False,
            position_created=False,
            order_submitted=False,
            exchange_connected=False,
            state_mutated=False,
        )

    def save_state(self, state: BTCForwardTestState, state_file: str) -> None:
        path = self._resolve(state_file)
        if not self._safe_forward_report_path(path):
            raise ValueError("state_file must be under reports/forward_test")
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
        temp_path.replace(path)

    def load_config(self, config_path: str = "configs/btc_forward_test_loop.json") -> BTCForwardTestConfig:
        path = self._resolve(config_path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("config JSON must be an object")
        return BTCForwardTestConfig(**{**BTCForwardTestConfig().to_dict(), **loaded})

    def _validate_config_values(self, config: BTCForwardTestConfig, expected_profile: str, issues: list[BTCForwardTestIssue], diagnostics: dict[str, Any]) -> None:
        self._expect(config.project_scope == "BTC_ONLY", issues, "project_scope", "project_scope must be BTC_ONLY.", {"project_scope": config.project_scope})
        self._expect(config.symbol == "BTC/USDT", issues, "symbol", "symbol must be BTC/USDT.", {"symbol": config.symbol})
        self._expect(config.strategy_profile == expected_profile, issues, "strategy_profile", f"strategy_profile must be {expected_profile}.", {"strategy_profile": config.strategy_profile})
        self._expect(config.dry_run_only, issues, "dry_run_only", "dry_run_only must be true.")
        self._expect(config.allow_forward_loop in (True, False), issues, "allow_forward_loop", "allow_forward_loop must be boolean.")
        self._expect(config.allow_journal_write in (True, False), issues, "allow_journal_write", "allow_journal_write must be boolean.")
        self._expect(not config.allow_live_market_data, issues, "allow_live_market_data", "live market data must remain disabled.")
        self._expect(not config.allow_exchange_connection, issues, "allow_exchange_connection", "exchange connection must remain disabled.")
        self._expect(not config.allow_order_submission, issues, "allow_order_submission", "order submission must remain disabled.")
        self._expect(not config.allow_position_creation, issues, "allow_position_creation", "position creation must remain disabled.")
        self._expect(not config.allow_paper_trade_persistence, issues, "allow_paper_trade_persistence", "paper trade persistence must remain disabled.")
        self._expect(not config.allow_executable_trade_creation, issues, "allow_executable_trade_creation", "executable trade creation must remain disabled.")
        self._expect(not config.allow_state_mutation, issues, "allow_state_mutation", "state mutation must remain disabled.")
        self._expect(config.cycle_mode == "historical_cursor", issues, "cycle_mode", "cycle_mode must be historical_cursor.", {"cycle_mode": config.cycle_mode})
        self._validate_historical_path(config.fixture_path, "fixture_path", issues)
        self._validate_historical_path(config.confirmation_fixture_path, "confirmation_fixture_path", issues)
        self._validate_forward_dir(config.state_export_dir, "state_export_dir", issues)
        self._validate_forward_dir(config.report_export_dir, "report_export_dir", issues)
        self._expect(1 <= int(config.max_cycles) <= 100, issues, "max_cycles", "max_cycles must be between 1 and 100.", {"max_cycles": config.max_cycles})
        self._expect(50 <= int(config.evaluation_window) <= int(config.min_candles), issues, "evaluation_window", "evaluation_window must be between 50 and min_candles.", {"evaluation_window": config.evaluation_window, "min_candles": config.min_candles})
        self._expect(int(config.start_index) >= int(config.evaluation_window), issues, "start_index", "start_index must be >= evaluation_window.", {"start_index": config.start_index, "evaluation_window": config.evaluation_window})
        self._expect(int(config.cycle_interval_seconds) == 0, issues, "cycle_interval_seconds", "cycle_interval_seconds must be 0 for this dry-run release.", {"cycle_interval_seconds": config.cycle_interval_seconds})
        self._expect(1 <= int(config.max_run_seconds) <= 300, issues, "max_run_seconds", "max_run_seconds must be between 1 and 300.", {"max_run_seconds": config.max_run_seconds})
        self._validate_runtime_config(config, expected_profile, issues, diagnostics)
        self._validate_monitoring_config(config, expected_profile, issues, diagnostics)
        self._validate_runner_config(config, expected_profile, issues, diagnostics)
        self._validate_signal_config(config, expected_profile, issues, diagnostics)
        self._validate_trade_candidate_config(config, expected_profile, issues, diagnostics)
        self._validate_candidate_journal_config(config, expected_profile, issues, diagnostics)

    def _validate_runtime_config(self, config: BTCForwardTestConfig, expected_profile: str, issues: list[BTCForwardTestIssue], diagnostics: dict[str, Any]) -> None:
        report = self.runtime_config_engine.validate(config.runtime_config_path, expected_profile=expected_profile)
        diagnostics["runtime_config_status"] = report.status
        runtime_config = report.config
        diagnostics["kill_switch_enabled"] = bool(getattr(runtime_config, "kill_switch_enabled", False))
        if config.require_runtime_config_pass and report.status != "PASS":
            issues.append(self._issue("runtime_config_validation", "FAIL", "Runtime config must validate PASS.", {"runtime_config_status": report.status}))
        if runtime_config is not None and config.require_kill_switch_enabled:
            self._expect(runtime_config.kill_switch_enabled, issues, "kill_switch_enabled", "kill_switch_enabled must remain true.")

    def _validate_monitoring_config(self, config: BTCForwardTestConfig, expected_profile: str, issues: list[BTCForwardTestIssue], diagnostics: dict[str, Any]) -> None:
        report = self.monitoring_engine.validate(config.monitoring_config_path, expected_profile=expected_profile)
        diagnostics["monitoring_config_status"] = report.status
        if config.require_monitoring_config_pass and report.status != "PASS":
            issues.append(self._issue("monitoring_config_validation", "FAIL", "Monitoring config must validate PASS.", {"monitoring_config_status": report.status}))

    def _validate_runner_config(self, config: BTCForwardTestConfig, expected_profile: str, issues: list[BTCForwardTestIssue], diagnostics: dict[str, Any]) -> None:
        _, runner_issues, _ = self.runner_engine.validate_config(config.runner_config_path, expected_profile=expected_profile)
        fail_count = sum(1 for issue in runner_issues if issue.severity == "FAIL")
        diagnostics["runner_config_status"] = "FAIL" if fail_count else "PASS"
        if config.require_runner_config_pass and fail_count:
            issues.append(self._issue("runner_config_validation", "FAIL", "Runner config must validate PASS.", {"runner_fail_count": fail_count}))

    def _validate_signal_config(self, config: BTCForwardTestConfig, expected_profile: str, issues: list[BTCForwardTestIssue], diagnostics: dict[str, Any]) -> None:
        report = self.signal_engine.validate(config.signal_evaluation_config_path, expected_profile=expected_profile)
        diagnostics["signal_config_status"] = report.status
        if config.require_signal_config_pass and report.status != "PASS":
            issues.append(self._issue("signal_config_validation", "FAIL", "Signal evaluation config must validate PASS.", {"signal_config_status": report.status}))

    def _validate_trade_candidate_config(self, config: BTCForwardTestConfig, expected_profile: str, issues: list[BTCForwardTestIssue], diagnostics: dict[str, Any]) -> None:
        report = self.trade_candidate_engine.validate(config.trade_candidate_config_path, expected_profile=expected_profile)
        diagnostics["trade_candidate_config_status"] = report.status
        if config.require_trade_candidate_config_pass and report.status != "PASS":
            issues.append(self._issue("trade_candidate_config_validation", "FAIL", "Trade candidate config must validate PASS.", {"trade_candidate_config_status": report.status}))

    def _validate_candidate_journal_config(self, config: BTCForwardTestConfig, expected_profile: str, issues: list[BTCForwardTestIssue], diagnostics: dict[str, Any]) -> None:
        report = self.candidate_journal_engine.validate(config.candidate_journal_config_path, expected_profile=expected_profile)
        diagnostics["candidate_journal_config_status"] = report.status
        if config.require_candidate_journal_config_pass and report.status != "PASS":
            issues.append(self._issue("candidate_journal_config_validation", "FAIL", "Candidate journal config must validate PASS.", {"candidate_journal_config_status": report.status}))

    def _run_cycle(self, config: BTCForwardTestConfig, report: BTCForwardTestValidationReport, cycle_number: int, cursor: int, candle: dict[str, Any]) -> BTCForwardTestCycleResult:
        journal_result = self.candidate_journal_engine.simulate_and_record(config.candidate_journal_config_path, expected_profile=config.strategy_profile)
        issues = self._from_journal_issues(journal_result.issues)
        entry = journal_result.entry
        candidate_created = bool(getattr(entry, "candidate_created", False))
        if journal_result.status == "FAIL":
            if not any(issue.severity == "FAIL" for issue in issues):
                issues.append(self._issue("forward_cycle_failed", "FAIL", "Forward-test cycle failed because candidate journal result failed.", {"journal_status": journal_result.status}))
            decision = BTCForwardTestCycleDecision.ERROR.value
        elif not journal_result.entry_written:
            decision = BTCForwardTestCycleDecision.NO_JOURNAL.value
        elif candidate_created:
            decision = BTCForwardTestCycleDecision.JOURNALED_CANDIDATE.value
        else:
            if journal_result.status == "WARNING" and not any(issue.severity == "WARNING" for issue in issues):
                issues.append(self._issue("forward_cycle_warning", "WARNING", "Forward-test cycle completed with a rejected or warning candidate journal result.", {"journal_status": journal_result.status}))
            decision = BTCForwardTestCycleDecision.JOURNALED_REJECTION.value
        return BTCForwardTestCycleResult(
            cycle_id=f"BTC-FWD-{self._now()}-{cycle_number}",
            created_at=self._now(),
            cycle_number=cycle_number,
            cursor_index=cursor,
            symbol=config.symbol,
            strategy_profile=config.strategy_profile,
            candle_timestamp=str(candle.get("timestamp")) if isinstance(candle, dict) and candle.get("timestamp") is not None else None,
            signal_status=None if entry is None else entry.signal_status,
            signal_decision=None if entry is None else entry.signal_decision,
            signal_score=None if entry is None else entry.signal_score,
            candidate_status=None if entry is None else entry.candidate_status,
            candidate_decision=None if entry is None else entry.candidate_decision,
            candidate_created=candidate_created,
            journal_entry_written=journal_result.entry_written,
            journal_entry_id=None if entry is None else entry.entry_id,
            cycle_decision=decision,
            reason=journal_result.reason,
            dry_run_only=True,
            live_market_data_used=False,
            executable_trade_created=False,
            paper_trade_persisted=False,
            position_created=False,
            order_submitted=False,
            exchange_connected=False,
            state_mutated=False,
            issues=issues,
            metadata={"journal_status": journal_result.status},
        )

    def _failed_cycle(self, config: BTCForwardTestConfig, number: int, cursor: int, issues: list[BTCForwardTestIssue], reason: str) -> BTCForwardTestCycleResult:
        return BTCForwardTestCycleResult(
            cycle_id=f"BTC-FWD-{self._now()}-{number}",
            created_at=self._now(),
            cycle_number=number,
            cursor_index=cursor,
            symbol=config.symbol,
            strategy_profile=config.strategy_profile,
            cycle_decision=BTCForwardTestCycleDecision.ERROR.value,
            reason=reason,
            issues=issues,
        )

    def _run_result(self, config: BTCForwardTestConfig, report: BTCForwardTestValidationReport, requested: int, start: int, cycles: list[BTCForwardTestCycleResult], issues: list[BTCForwardTestIssue], reason: str) -> BTCForwardTestRunResult:
        all_issues = list(issues)
        for cycle in cycles:
            all_issues.extend(cycle.issues)
        failures = sum(1 for issue in all_issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in all_issues if issue.severity == "WARNING")
        status = "FAIL" if failures else "WARNING" if warnings else "PASS"
        return BTCForwardTestRunResult(
            created_at=self._now(),
            project_scope=config.project_scope,
            symbol=config.symbol,
            strategy_profile=config.strategy_profile,
            status=status,
            cycles_requested=requested,
            cycles_completed=len([cycle for cycle in cycles if cycle.cycle_decision != BTCForwardTestCycleDecision.ERROR.value]),
            cycles_failed=len([cycle for cycle in cycles if cycle.cycle_decision == BTCForwardTestCycleDecision.ERROR.value]),
            candidates_created=sum(1 for cycle in cycles if cycle.candidate_created),
            candidates_rejected=sum(1 for cycle in cycles if not cycle.candidate_created and cycle.cycle_decision in (BTCForwardTestCycleDecision.JOURNALED_REJECTION.value, BTCForwardTestCycleDecision.NO_JOURNAL.value)),
            journal_entries_written=sum(1 for cycle in cycles if cycle.journal_entry_written),
            warnings=warnings,
            failures=failures,
            start_index=start,
            end_index=start if not cycles else cycles[-1].cursor_index,
            runtime_config_status=str(report.diagnostics.get("runtime_config_status", "UNKNOWN")),
            monitoring_config_status=str(report.diagnostics.get("monitoring_config_status", "UNKNOWN")),
            runner_config_status=str(report.diagnostics.get("runner_config_status", "UNKNOWN")),
            signal_config_status=str(report.diagnostics.get("signal_config_status", "UNKNOWN")),
            trade_candidate_config_status=str(report.diagnostics.get("trade_candidate_config_status", "UNKNOWN")),
            candidate_journal_config_status=str(report.diagnostics.get("candidate_journal_config_status", "UNKNOWN")),
            dry_run_only=True,
            live_market_data_used=False,
            executable_trade_created=False,
            paper_trade_persisted=False,
            position_created=False,
            order_submitted=False,
            exchange_connected=False,
            state_mutated=False,
            cycles=cycles,
            issues=all_issues,
            safety_summary={"reason": reason, "dry_run_only": True, "live_market_data_used": False},
        )

    def _load_candles(self, fixture_path: str, min_candles: int) -> tuple[list[dict[str, Any]], list[BTCForwardTestIssue]]:
        path = self._resolve(fixture_path)
        if not path.exists():
            return [], [self._issue("fixture_path", "FAIL", "fixture_path is missing.", {"fixture_path": str(path)})]
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return [], [self._issue("fixture_path_invalid", "FAIL", f"fixture_path could not be read: {exc}", {"fixture_path": str(path)})]
        if not isinstance(loaded, list):
            return [], [self._issue("fixture_path_invalid", "FAIL", "fixture_path must contain a JSON list.", {"fixture_path": str(path)})]
        if len(loaded) < min_candles:
            return [], [self._issue("min_candles", "FAIL", "fixture_path has too few candles.", {"candle_count": len(loaded), "min_candles": min_candles})]
        return [row for row in loaded if isinstance(row, dict)], []

    def _empty_state(self, reason: str) -> BTCForwardTestState:
        return BTCForwardTestState(created_at=self._now(), updated_at=self._now(), last_status=BTCForwardTestStatus.WARNING.value, last_reason=reason)

    def _validate_historical_path(self, value: str, name: str, issues: list[BTCForwardTestIssue]) -> None:
        path = Path(value)
        if path.is_absolute():
            issues.append(self._issue(name, "FAIL", f"{name} must be a safe relative path under data/historical.", {name: value}))
            return
        parts = path.parts
        self._expect(len(parts) >= 2 and parts[0] == "data" and parts[1] == "historical" and ".." not in parts and value.endswith(".json"), issues, name, f"{name} must be under data/historical.", {name: value})

    def _validate_forward_dir(self, value: str, name: str, issues: list[BTCForwardTestIssue]) -> None:
        path = Path(value)
        if path.is_absolute():
            issues.append(self._issue(name, "FAIL", f"{name} must be a safe relative path under reports/forward_test.", {name: value}))
            return
        parts = path.parts
        self._expect(len(parts) >= 2 and parts[0] == "reports" and parts[1] == "forward_test" and ".." not in parts, issues, name, f"{name} must be under reports/forward_test.", {name: value})

    def _safe_forward_report_path(self, path: Path) -> bool:
        try:
            return path.resolve().is_relative_to((self.repo_root / "reports" / "forward_test").resolve())
        except AttributeError:
            return str(path.resolve()).startswith(str((self.repo_root / "reports" / "forward_test").resolve()))

    def _from_journal_issues(self, journal_issues: list[Any]) -> list[BTCForwardTestIssue]:
        return [self._issue(getattr(issue, "name", "journal_issue"), getattr(issue, "severity", "WARNING"), getattr(issue, "message", ""), getattr(issue, "details", {})) for issue in journal_issues]

    def _report(self, config_path: str, config: BTCForwardTestConfig | None, issues: list[BTCForwardTestIssue], diagnostics: dict[str, Any]) -> BTCForwardTestValidationReport:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        status = "FAIL" if failures else "WARNING" if warnings else "PASS"
        return BTCForwardTestValidationReport(
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

    def _expect(self, condition: bool, issues: list[BTCForwardTestIssue], name: str, message: str, details: dict[str, Any] | None = None) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message, details))

    def _issue(self, name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> BTCForwardTestIssue:
        return BTCForwardTestIssue(name=name, severity=severity, message=message, details=details or {})

    def _resolve(self, path_text: str) -> Path:
        path = Path(path_text)
        if not path.is_absolute():
            path = self.repo_root / path
        return path

    def _now(self) -> str:
        if self.now_provider is not None:
            return str(self.now_provider())
        return datetime.now(UTC).replace(microsecond=0).isoformat()
