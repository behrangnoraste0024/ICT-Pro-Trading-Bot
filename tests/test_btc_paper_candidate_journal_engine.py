from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.diagnostics.btc_paper_candidate_journal_engine import BTCPaperCandidateJournalEngine
from models.btc_paper_trade_candidate import (
    BTCPaperTradeCandidate,
    BTCPaperTradeCandidateResult,
    BTCPaperTradeCandidateValidationReport,
)
from tests.test_btc_paper_trade_candidate_engine import _trade_candidate_config, _write_trade_candidate_configs


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _journal_config(**overrides) -> dict[str, Any]:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "signal_evaluation_config_path": "configs/btc_paper_signal_evaluation.json",
        "trade_candidate_config_path": "configs/btc_paper_trade_candidate.json",
        "dry_run_only": True,
        "allow_journal_write": True,
        "allow_executable_trade_creation": False,
        "allow_paper_trade_persistence": False,
        "allow_position_creation": False,
        "allow_order_submission": False,
        "allow_exchange_connection": False,
        "allow_state_mutation": False,
        "journal_format": "jsonl",
        "journal_dir": "reports/paper_candidate_journal",
        "journal_file_name": "btc_paper_candidate_journal.jsonl",
        "max_entries_to_read": 50,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_signal_config_pass": True,
        "require_trade_candidate_config_pass": True,
        "require_kill_switch_enabled": True,
    }
    values.update(overrides)
    return values


def _write_journal_configs(
    tmp_path: Path,
    *,
    runtime: dict[str, Any] | None = None,
    monitoring: dict[str, Any] | None = None,
    runner: dict[str, Any] | None = None,
    signal: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
    journal: dict[str, Any] | None = None,
) -> Path:
    _write_trade_candidate_configs(tmp_path, runtime=runtime, monitoring=monitoring, runner=runner, signal=signal, candidate=candidate)
    path = tmp_path / "configs" / "btc_paper_candidate_journal.json"
    _write_json(path, _journal_config(**(journal or {})))
    return path


class _FakeTradeCandidateEngine:
    def __init__(self, result: BTCPaperTradeCandidateResult | None = None, report_status: str = "PASS") -> None:
        self.result = result or _candidate_result(candidate_created=False, status="WARNING")
        self.report_status = report_status

    def validate(self, config_path: str = "configs/btc_paper_trade_candidate.json", expected_profile: str = "balanced_smc_decision_065") -> BTCPaperTradeCandidateValidationReport:
        return BTCPaperTradeCandidateValidationReport(config_path=config_path, status=self.report_status, diagnostics={})

    def simulate(self, config_path: str = "configs/btc_paper_trade_candidate.json", expected_profile: str = "balanced_smc_decision_065") -> BTCPaperTradeCandidateResult:
        return self.result


def _candidate_result(*, candidate_created: bool, status: str = "PASS") -> BTCPaperTradeCandidateResult:
    candidate = None
    decision = "NO_CANDIDATE_SCORE_TOO_LOW"
    reason = "Signal score is below the trade candidate threshold."
    if candidate_created:
        candidate = BTCPaperTradeCandidate(
            candidate_id="BTC-DRYRUN-1",
            created_at="2026-01-01T00:00:00+00:00",
            symbol="BTC/USDT",
            strategy_profile="balanced_smc_decision_065",
            direction="LONG",
            entry_price=100.0,
            stop_loss=99.0,
            take_profit=101.5,
            risk_reward=1.5,
            signal_score=0.8,
            signal_threshold=0.65,
            account_currency="USDT",
            starting_equity=10000.0,
            risk_per_trade_pct=0.005,
            estimated_risk_amount=50.0,
            estimated_position_size=50.0,
            estimated_notional=5000.0,
            max_candidate_notional=2500.0,
        )
        decision = "CANDIDATE_CREATED_DRY_RUN"
        reason = "Non-executable dry-run trade candidate created."
    return BTCPaperTradeCandidateResult(
        status=status,
        decision=decision,
        candidate_created=candidate_created,
        candidate=candidate,
        signal_decision="APPROVED_DRY_RUN" if candidate_created else "WARNING_DRY_RUN",
        signal_score=0.8 if candidate_created else 0.4,
        signal_threshold=0.65,
        reason=reason,
        runtime_config_status="PASS",
        monitoring_config_status="PASS",
        runner_config_status="PASS",
        signal_config_status="PASS",
        dry_run_only=True,
        executable_trade_created=False,
        paper_trade_persisted=False,
        position_created=False,
        order_submitted=False,
        exchange_connected=False,
        state_mutated=False,
        safety_summary={"kill_switch_enabled": True},
    )


def _engine(tmp_path: Path, result: BTCPaperTradeCandidateResult | None = None, report_status: str = "PASS") -> BTCPaperCandidateJournalEngine:
    return BTCPaperCandidateJournalEngine(
        repo_root=tmp_path,
        trade_candidate_engine=_FakeTradeCandidateEngine(result=result, report_status=report_status),
        now_provider=lambda: "2026-01-01T00:00:00+00:00",
    )


def test_default_repo_candidate_journal_config_validates_pass() -> None:
    report = BTCPaperCandidateJournalEngine().validate()

    assert report.status == "PASS"
    assert report.diagnostics["runtime_config_status"] == "PASS"
    assert report.diagnostics["trade_candidate_config_status"] == "PASS"


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("dry_run_only", False, "dry_run_only"),
        ("allow_executable_trade_creation", True, "allow_executable_trade_creation"),
        ("allow_paper_trade_persistence", True, "allow_paper_trade_persistence"),
        ("allow_position_creation", True, "allow_position_creation"),
        ("allow_order_submission", True, "allow_order_submission"),
        ("allow_exchange_connection", True, "allow_exchange_connection"),
        ("allow_state_mutation", True, "allow_state_mutation"),
        ("symbol", "ETH/USDT", "symbol"),
        ("strategy_profile", "research_baseline", "strategy_profile"),
        ("journal_format", "json", "journal_format"),
        ("journal_dir", "../outside", "journal_dir"),
        ("journal_file_name", "../bad.jsonl", "journal_file_name"),
        ("journal_file_name", "bad.json", "journal_file_name"),
        ("max_entries_to_read", 0, "max_entries_to_read"),
        ("max_entries_to_read", 1001, "max_entries_to_read"),
    ],
)
def test_dangerous_journal_config_fails(tmp_path: Path, field: str, value: Any, issue: str) -> None:
    path = _write_journal_configs(tmp_path, journal={field: value})

    report = BTCPaperCandidateJournalEngine(repo_root=tmp_path).validate(str(path))

    assert report.status == "FAIL"
    assert issue in {item.name for item in report.issues}


def test_runtime_monitoring_runner_signal_candidate_or_kill_switch_fail_blocks(tmp_path: Path) -> None:
    cases = [
        ("runtime", {"runtime": {"live_trading_enabled": True}}, "runtime_config_validation"),
        ("monitoring", {"monitoring": {"live_trading_expected": True}}, "monitoring_config_validation"),
        ("runner", {"runner": {"allow_order_submission": True}}, "runner_config_validation"),
        ("signal", {"signal": None, "candidate": None}, "signal_config_validation"),
        ("candidate", {"candidate": {"allow_order_submission": True}}, "trade_candidate_config_validation"),
        ("kill", {"runtime": {"kill_switch_enabled": False}}, "kill_switch_enabled"),
    ]
    for name, kwargs, expected_issue in cases:
        root = tmp_path / name
        if name == "signal":
            from tests.test_btc_paper_signal_evaluation_engine import _signal_config

            kwargs["signal"] = _signal_config(root, allow_order_submission=True)
        path = _write_journal_configs(root, **kwargs)
        report = BTCPaperCandidateJournalEngine(repo_root=root).validate(str(path))
        assert expected_issue in {issue.name for issue in report.issues}


def test_simulate_and_record_low_score_candidate_writes_rejection_entry(tmp_path: Path) -> None:
    path = _write_journal_configs(tmp_path)
    journal_path = tmp_path / "reports" / "paper_candidate_journal" / "test.jsonl"

    result = _engine(tmp_path, _candidate_result(candidate_created=False, status="WARNING")).simulate_and_record(str(path), journal_path=str(journal_path))

    assert result.status == "WARNING"
    assert result.entry_written is True
    assert result.entry is not None
    assert result.entry.candidate_created is False
    assert result.entry.rejection_reason == "Signal score is below the trade candidate threshold."
    assert result.entry.order_submitted is False
    assert journal_path.exists()


def test_simulate_and_record_approved_candidate_writes_candidate_entry(tmp_path: Path) -> None:
    path = _write_journal_configs(tmp_path)
    journal_path = tmp_path / "reports" / "paper_candidate_journal" / "test.jsonl"

    result = _engine(tmp_path, _candidate_result(candidate_created=True)).simulate_and_record(str(path), journal_path=str(journal_path), runner_state="RUNNING")

    assert result.status == "PASS"
    assert result.entry_written is True
    assert result.entry is not None
    assert result.entry.candidate_created is True
    assert result.entry.candidate_id == "BTC-DRYRUN-1"
    assert result.entry.runner_state == "RUNNING"
    assert result.executable_trade_created is False
    assert result.paper_trade_persisted is False
    assert result.position_created is False
    assert result.order_submitted is False
    assert result.exchange_connected is False
    assert result.state_mutated is False


def test_simulate_and_record_fail_does_not_write(tmp_path: Path) -> None:
    path = _write_journal_configs(tmp_path)
    journal_path = tmp_path / "reports" / "paper_candidate_journal" / "test.jsonl"

    result = _engine(tmp_path, _candidate_result(candidate_created=False, status="FAIL")).simulate_and_record(str(path), journal_path=str(journal_path))

    assert result.status == "FAIL"
    assert result.entry_written is False
    assert not journal_path.exists()


def test_summary_handles_missing_journal(tmp_path: Path) -> None:
    path = _write_journal_configs(tmp_path)

    summary = _engine(tmp_path).summary(str(path), journal_path=str(tmp_path / "missing.jsonl"))

    assert summary.status == "WARNING"
    assert summary.total_entries_read == 0
    assert "journal_missing" in {issue.name for issue in summary.issues}


def test_summary_reads_entries_and_counts_created_rejected(tmp_path: Path) -> None:
    path = _write_journal_configs(tmp_path)
    engine = _engine(tmp_path)
    journal_path = tmp_path / "reports" / "paper_candidate_journal" / "test.jsonl"
    engine.simulate_and_record(str(path), journal_path=str(journal_path))
    engine.trade_candidate_engine = _FakeTradeCandidateEngine(_candidate_result(candidate_created=True))
    engine.simulate_and_record(str(path), journal_path=str(journal_path))

    summary = engine.summary(str(path), journal_path=str(journal_path))

    assert summary.total_entries_read == 2
    assert summary.candidate_created_count == 1
    assert summary.candidate_rejected_count == 1


def test_summary_skips_invalid_jsonl_line_with_warning(tmp_path: Path) -> None:
    path = _write_journal_configs(tmp_path)
    journal_path = tmp_path / "reports" / "paper_candidate_journal" / "test.jsonl"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_text("{bad json\n", encoding="utf-8")

    summary = _engine(tmp_path).summary(str(path), journal_path=str(journal_path))

    assert summary.status == "WARNING"
    assert "invalid_jsonl_line" in {issue.name for issue in summary.issues}
