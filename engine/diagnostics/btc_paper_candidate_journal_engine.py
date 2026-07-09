from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine
from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from engine.diagnostics.btc_paper_signal_evaluation_engine import BTCPaperSignalEvaluationEngine
from engine.diagnostics.btc_paper_trade_candidate_engine import BTCPaperTradeCandidateEngine
from models.btc_paper_candidate_journal import (
    BTCPaperCandidateJournalAction,
    BTCPaperCandidateJournalConfig,
    BTCPaperCandidateJournalEntry,
    BTCPaperCandidateJournalIssue,
    BTCPaperCandidateJournalRecordResult,
    BTCPaperCandidateJournalStatus,
    BTCPaperCandidateJournalSummary,
    BTCPaperCandidateJournalValidationReport,
)


class BTCPaperCandidateJournalEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        runtime_config_engine: BTCPaperRuntimeConfigEngine | None = None,
        monitoring_engine: BTCPaperMonitoringEngine | None = None,
        runner_engine: BTCPaperRunnerEngine | None = None,
        signal_engine: BTCPaperSignalEvaluationEngine | None = None,
        trade_candidate_engine: BTCPaperTradeCandidateEngine | None = None,
        now_provider=None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.runtime_config_engine = runtime_config_engine or BTCPaperRuntimeConfigEngine(repo_root=self.repo_root)
        self.monitoring_engine = monitoring_engine or BTCPaperMonitoringEngine(repo_root=self.repo_root)
        self.runner_engine = runner_engine or BTCPaperRunnerEngine(repo_root=self.repo_root)
        self.signal_engine = signal_engine or BTCPaperSignalEvaluationEngine(repo_root=self.repo_root)
        self.trade_candidate_engine = trade_candidate_engine or BTCPaperTradeCandidateEngine(repo_root=self.repo_root)
        self.now_provider = now_provider

    def validate(
        self,
        config_path: str = "configs/btc_paper_candidate_journal.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCPaperCandidateJournalValidationReport:
        issues: list[BTCPaperCandidateJournalIssue] = []
        diagnostics: dict[str, Any] = {
            "runtime_config_status": "UNKNOWN",
            "monitoring_config_status": "UNKNOWN",
            "runner_config_status": "UNKNOWN",
            "signal_config_status": "UNKNOWN",
            "trade_candidate_config_status": "UNKNOWN",
            "kill_switch_enabled": None,
        }
        config: BTCPaperCandidateJournalConfig | None = None
        try:
            config = self.load_config(config_path)
        except Exception as exc:
            issues.append(self._issue("config_invalid", "FAIL", f"BTC paper candidate journal config could not be loaded: {exc}", {"config_path": config_path}))
            return self._report(config_path, config, issues, diagnostics)
        self._validate_config_values(config, expected_profile, issues, diagnostics)
        return self._report(config_path, config, issues, diagnostics)

    def simulate_and_record(
        self,
        config_path: str = "configs/btc_paper_candidate_journal.json",
        expected_profile: str = "balanced_smc_decision_065",
        journal_path: str | None = None,
        runner_state: str | None = None,
    ) -> BTCPaperCandidateJournalRecordResult:
        report = self.validate(config_path=config_path, expected_profile=expected_profile)
        config = report.config or BTCPaperCandidateJournalConfig()
        issues = list(report.issues)
        resolved_journal = self._journal_path(config, journal_path)
        entry = None
        status = BTCPaperCandidateJournalStatus.FAIL.value if report.status == "FAIL" else BTCPaperCandidateJournalStatus.WARNING.value
        reason = "Candidate journal config failed safety validation." if report.status == "FAIL" else "Trade candidate simulation did not complete."
        written = False
        if report.status != "FAIL":
            candidate_result = self.trade_candidate_engine.simulate(config.trade_candidate_config_path, expected_profile=expected_profile)
            issues.extend(self._from_candidate_issues(candidate_result.issues))
            entry = self.build_entry(config, report, candidate_result, runner_state=runner_state)
            status = candidate_result.status
            reason = "Candidate journal entry built from trade candidate dry-run."
            if candidate_result.status != "FAIL" and config.allow_journal_write:
                self._append_jsonl(resolved_journal, entry)
                written = True
                reason = "Candidate journal entry written."
            elif candidate_result.status == "FAIL":
                reason = "Trade candidate simulation failed; journal entry was not written."
        return BTCPaperCandidateJournalRecordResult(
            created_at=self._now(),
            status=status,
            action=BTCPaperCandidateJournalAction.SIMULATE_AND_RECORD.value,
            entry_written=written,
            journal_path=str(resolved_journal),
            entry=entry,
            reason=reason,
            dry_run_only=config.dry_run_only,
            executable_trade_created=False,
            paper_trade_persisted=False,
            position_created=False,
            order_submitted=False,
            exchange_connected=False,
            state_mutated=False,
            issues=issues,
        )

    def build_entry(
        self,
        config: BTCPaperCandidateJournalConfig,
        validation_report: BTCPaperCandidateJournalValidationReport,
        candidate_result: Any,
        runner_state: str | None = None,
    ) -> BTCPaperCandidateJournalEntry:
        candidate = getattr(candidate_result, "candidate", None)
        created_at = self._now()
        issues = self._from_candidate_issues(getattr(candidate_result, "issues", []))
        return BTCPaperCandidateJournalEntry(
            entry_id=f"BTC-JOURNAL-{created_at}",
            created_at=created_at,
            project_scope=config.project_scope,
            symbol=config.symbol,
            strategy_profile=config.strategy_profile,
            source="TRADE_CANDIDATE",
            runner_state=runner_state,
            signal_decision=getattr(candidate_result, "signal_decision", None),
            signal_status=getattr(candidate_result, "status", None),
            signal_score=getattr(candidate_result, "signal_score", None),
            signal_threshold=getattr(candidate_result, "signal_threshold", None),
            signal_direction=getattr(candidate, "direction", None),
            candidate_decision=getattr(candidate_result, "decision", None),
            candidate_status=getattr(candidate_result, "status", None),
            candidate_created=bool(getattr(candidate_result, "candidate_created", False)),
            candidate_id=getattr(candidate, "candidate_id", None),
            candidate_direction=getattr(candidate, "direction", None),
            candidate_entry_price=getattr(candidate, "entry_price", None),
            candidate_stop_loss=getattr(candidate, "stop_loss", None),
            candidate_take_profit=getattr(candidate, "take_profit", None),
            candidate_risk_reward=getattr(candidate, "risk_reward", None),
            rejection_reason=None if getattr(candidate_result, "candidate_created", False) else getattr(candidate_result, "reason", None),
            runtime_config_status=str(validation_report.diagnostics.get("runtime_config_status", "UNKNOWN")),
            monitoring_config_status=str(validation_report.diagnostics.get("monitoring_config_status", "UNKNOWN")),
            runner_config_status=str(validation_report.diagnostics.get("runner_config_status", "UNKNOWN")),
            signal_config_status=str(validation_report.diagnostics.get("signal_config_status", "UNKNOWN")),
            trade_candidate_config_status=str(validation_report.diagnostics.get("trade_candidate_config_status", "UNKNOWN")),
            dry_run_only=True,
            executable_trade_created=False,
            paper_trade_persisted=False,
            position_created=False,
            order_submitted=False,
            exchange_connected=False,
            state_mutated=False,
            safety_summary=dict(getattr(candidate_result, "safety_summary", {})),
            metadata={"candidate_reason": getattr(candidate_result, "reason", None)},
            issues=issues,
        )

    def summary(
        self,
        config_path: str = "configs/btc_paper_candidate_journal.json",
        expected_profile: str = "balanced_smc_decision_065",
        journal_path: str | None = None,
        max_entries: int | None = None,
    ) -> BTCPaperCandidateJournalSummary:
        report = self.validate(config_path=config_path, expected_profile=expected_profile)
        config = report.config or BTCPaperCandidateJournalConfig()
        path = self._journal_path(config, journal_path)
        limit = max_entries or config.max_entries_to_read
        issues = list(report.issues)
        if not path.exists():
            return self._summary(path, [], issues, BTCPaperCandidateJournalStatus.WARNING.value, "journal_missing")
        entries: list[BTCPaperCandidateJournalEntry] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                entries.append(self._entry_from_dict(data))
            except Exception as exc:
                issues.append(self._issue("invalid_jsonl_line", "WARNING", "Invalid journal JSONL line skipped.", {"line_number": line_number, "error": str(exc)}))
        return self._summary(path, entries[-limit:], issues)

    def load_config(self, config_path: str = "configs/btc_paper_candidate_journal.json") -> BTCPaperCandidateJournalConfig:
        path = self._resolve(config_path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("config JSON must be an object")
        return BTCPaperCandidateJournalConfig(**{**BTCPaperCandidateJournalConfig().to_dict(), **loaded})

    def _validate_config_values(self, config: BTCPaperCandidateJournalConfig, expected_profile: str, issues: list[BTCPaperCandidateJournalIssue], diagnostics: dict[str, Any]) -> None:
        self._expect(config.project_scope == "BTC_ONLY", issues, "project_scope", "project_scope must be BTC_ONLY.", {"project_scope": config.project_scope})
        self._expect(config.symbol == "BTC/USDT", issues, "symbol", "symbol must be BTC/USDT.", {"symbol": config.symbol})
        self._expect(config.strategy_profile == expected_profile, issues, "strategy_profile", f"strategy_profile must be {expected_profile}.", {"strategy_profile": config.strategy_profile})
        self._expect(config.dry_run_only, issues, "dry_run_only", "dry_run_only must be true.")
        self._expect(config.allow_journal_write in (True, False), issues, "allow_journal_write", "allow_journal_write must be boolean.")
        self._expect(not config.allow_executable_trade_creation, issues, "allow_executable_trade_creation", "executable trade creation must remain disabled.")
        self._expect(not config.allow_paper_trade_persistence, issues, "allow_paper_trade_persistence", "paper trade persistence must remain disabled.")
        self._expect(not config.allow_position_creation, issues, "allow_position_creation", "position creation must remain disabled.")
        self._expect(not config.allow_order_submission, issues, "allow_order_submission", "order submission must remain disabled.")
        self._expect(not config.allow_exchange_connection, issues, "allow_exchange_connection", "exchange connection must remain disabled.")
        self._expect(not config.allow_state_mutation, issues, "allow_state_mutation", "state mutation must remain disabled.")
        self._expect(config.journal_format == "jsonl", issues, "journal_format", "journal_format must be jsonl.", {"journal_format": config.journal_format})
        self._validate_journal_dir(config.journal_dir, issues)
        self._validate_journal_file_name(config.journal_file_name, issues)
        self._expect(1 <= int(config.max_entries_to_read) <= 1000, issues, "max_entries_to_read", "max_entries_to_read must be between 1 and 1000.", {"max_entries_to_read": config.max_entries_to_read})
        self._validate_runtime_config(config, expected_profile, issues, diagnostics)
        self._validate_monitoring_config(config, expected_profile, issues, diagnostics)
        self._validate_runner_config(config, expected_profile, issues, diagnostics)
        self._validate_signal_config(config, expected_profile, issues, diagnostics)
        self._validate_trade_candidate_config(config, expected_profile, issues, diagnostics)

    def _validate_runtime_config(self, config: BTCPaperCandidateJournalConfig, expected_profile: str, issues: list[BTCPaperCandidateJournalIssue], diagnostics: dict[str, Any]) -> None:
        report = self.runtime_config_engine.validate(config.runtime_config_path, expected_profile=expected_profile)
        diagnostics["runtime_config_status"] = report.status
        runtime_config = report.config
        diagnostics["kill_switch_enabled"] = bool(getattr(runtime_config, "kill_switch_enabled", False))
        if config.require_runtime_config_pass and report.status != "PASS":
            issues.append(self._issue("runtime_config_validation", "FAIL", "Runtime config must validate PASS.", {"runtime_config_status": report.status}))
        if runtime_config is not None and config.require_kill_switch_enabled:
            self._expect(runtime_config.kill_switch_enabled, issues, "kill_switch_enabled", "kill_switch_enabled must remain true.")

    def _validate_monitoring_config(self, config: BTCPaperCandidateJournalConfig, expected_profile: str, issues: list[BTCPaperCandidateJournalIssue], diagnostics: dict[str, Any]) -> None:
        report = self.monitoring_engine.validate(config.monitoring_config_path, expected_profile=expected_profile)
        diagnostics["monitoring_config_status"] = report.status
        if config.require_monitoring_config_pass and report.status != "PASS":
            issues.append(self._issue("monitoring_config_validation", "FAIL", "Monitoring config must validate PASS.", {"monitoring_config_status": report.status}))

    def _validate_runner_config(self, config: BTCPaperCandidateJournalConfig, expected_profile: str, issues: list[BTCPaperCandidateJournalIssue], diagnostics: dict[str, Any]) -> None:
        _, runner_issues, _ = self.runner_engine.validate_config(config.runner_config_path, expected_profile=expected_profile)
        fail_count = sum(1 for issue in runner_issues if issue.severity == "FAIL")
        diagnostics["runner_config_status"] = "FAIL" if fail_count else "PASS"
        if config.require_runner_config_pass and fail_count:
            issues.append(self._issue("runner_config_validation", "FAIL", "Runner config must validate PASS.", {"runner_fail_count": fail_count}))

    def _validate_signal_config(self, config: BTCPaperCandidateJournalConfig, expected_profile: str, issues: list[BTCPaperCandidateJournalIssue], diagnostics: dict[str, Any]) -> None:
        report = self.signal_engine.validate(config.signal_evaluation_config_path, expected_profile=expected_profile)
        diagnostics["signal_config_status"] = report.status
        if config.require_signal_config_pass and report.status != "PASS":
            issues.append(self._issue("signal_config_validation", "FAIL", "Signal evaluation config must validate PASS.", {"signal_config_status": report.status}))

    def _validate_trade_candidate_config(self, config: BTCPaperCandidateJournalConfig, expected_profile: str, issues: list[BTCPaperCandidateJournalIssue], diagnostics: dict[str, Any]) -> None:
        report = self.trade_candidate_engine.validate(config.trade_candidate_config_path, expected_profile=expected_profile)
        diagnostics["trade_candidate_config_status"] = report.status
        if config.require_trade_candidate_config_pass and report.status != "PASS":
            issues.append(self._issue("trade_candidate_config_validation", "FAIL", "Trade candidate config must validate PASS.", {"trade_candidate_config_status": report.status}))

    def _validate_journal_dir(self, value: str, issues: list[BTCPaperCandidateJournalIssue]) -> None:
        path = Path(value)
        if path.is_absolute():
            issues.append(self._issue("journal_dir", "FAIL", "journal_dir must be a safe relative path under reports/paper_candidate_journal.", {"journal_dir": value}))
            return
        parts = path.parts
        self._expect(len(parts) >= 2 and parts[0] == "reports" and parts[1] == "paper_candidate_journal" and ".." not in parts, issues, "journal_dir", "journal_dir must be under reports/paper_candidate_journal.", {"journal_dir": value})

    def _validate_journal_file_name(self, value: str, issues: list[BTCPaperCandidateJournalIssue]) -> None:
        path = Path(value)
        valid = len(path.parts) == 1 and value.endswith(".jsonl") and value not in (".jsonl", "")
        self._expect(valid, issues, "journal_file_name", "journal_file_name must be a safe .jsonl file name.", {"journal_file_name": value})

    def _append_jsonl(self, path: Path, entry: BTCPaperCandidateJournalEntry) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")

    def _entry_from_dict(self, data: dict[str, Any]) -> BTCPaperCandidateJournalEntry:
        issues = [BTCPaperCandidateJournalIssue(**issue) for issue in data.get("issues", []) if isinstance(issue, dict)]
        payload = {**BTCPaperCandidateJournalEntry().to_dict(), **data}
        payload["issues"] = issues
        return BTCPaperCandidateJournalEntry(**payload)

    def _summary(self, path: Path, entries: list[BTCPaperCandidateJournalEntry], issues: list[BTCPaperCandidateJournalIssue], status: str | None = None, missing_issue: str | None = None) -> BTCPaperCandidateJournalSummary:
        local_issues = list(issues)
        if missing_issue:
            local_issues.append(self._issue(missing_issue, "WARNING", "Journal file does not exist yet.", {"journal_path": str(path)}))
        warnings = sum(1 for issue in local_issues if issue.severity == "WARNING")
        failures = sum(1 for issue in local_issues if issue.severity == "FAIL")
        final_status = status or ("FAIL" if failures else "WARNING" if warnings else "PASS")
        return BTCPaperCandidateJournalSummary(
            created_at=self._now(),
            journal_path=str(path),
            status=final_status,
            total_entries_read=len(entries),
            candidate_created_count=sum(1 for entry in entries if entry.candidate_created),
            candidate_rejected_count=sum(1 for entry in entries if not entry.candidate_created),
            warning_count=sum(1 for entry in entries if entry.candidate_status == "WARNING") + warnings,
            fail_count=sum(1 for entry in entries if entry.candidate_status == "FAIL") + failures,
            latest_entry_at=None if not entries else entries[-1].created_at,
            entries=entries,
            issues=local_issues,
        )

    def _from_candidate_issues(self, candidate_issues: list[Any]) -> list[BTCPaperCandidateJournalIssue]:
        return [self._issue(getattr(issue, "name", "candidate_issue"), getattr(issue, "severity", "WARNING"), getattr(issue, "message", ""), getattr(issue, "details", {})) for issue in candidate_issues]

    def _journal_path(self, config: BTCPaperCandidateJournalConfig, journal_path: str | None = None) -> Path:
        if journal_path:
            return self._resolve(journal_path)
        return self._resolve(str(Path(config.journal_dir) / config.journal_file_name))

    def _report(self, config_path: str, config: BTCPaperCandidateJournalConfig | None, issues: list[BTCPaperCandidateJournalIssue], diagnostics: dict[str, Any]) -> BTCPaperCandidateJournalValidationReport:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        status = "FAIL" if failures else "WARNING" if warnings else "PASS"
        return BTCPaperCandidateJournalValidationReport(
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

    def _expect(self, condition: bool, issues: list[BTCPaperCandidateJournalIssue], name: str, message: str, details: dict[str, Any] | None = None) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message, details))

    def _issue(self, name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> BTCPaperCandidateJournalIssue:
        return BTCPaperCandidateJournalIssue(name=name, severity=severity, message=message, details=details or {})

    def _resolve(self, path_text: str) -> Path:
        path = Path(path_text)
        if not path.is_absolute():
            path = self.repo_root / path
        return path

    def _now(self) -> str:
        if self.now_provider is not None:
            return str(self.now_provider())
        return datetime.now(UTC).replace(microsecond=0).isoformat()
