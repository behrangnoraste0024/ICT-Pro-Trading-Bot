from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.diagnostics.btc_forward_test_loop_engine import BTCForwardTestLoopEngine
from models.btc_paper_candidate_journal import (
    BTCPaperCandidateJournalEntry,
    BTCPaperCandidateJournalRecordResult,
    BTCPaperCandidateJournalValidationReport,
)
from tests.test_btc_paper_candidate_journal_engine import _journal_config, _write_journal_configs
from tests.test_btc_paper_signal_evaluation_engine import _signal_config


def _write_json(path: Path, data: dict[str, Any] | list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _candles(count: int = 1000) -> list[dict[str, Any]]:
    return [
        {"timestamp": f"2026-01-01T00:{i % 60:02d}:00Z", "open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100 + i, "volume": 1}
        for i in range(count)
    ]


def _forward_config(**overrides) -> dict[str, Any]:
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
        "candidate_journal_config_path": "configs/btc_paper_candidate_journal.json",
        "fixture_path": "data/historical/btcusdt_15m_1000.json",
        "confirmation_fixture_path": "data/historical/btcusdt_1h_1000.json",
        "dry_run_only": True,
        "allow_forward_loop": True,
        "allow_journal_write": True,
        "allow_live_market_data": False,
        "allow_exchange_connection": False,
        "allow_order_submission": False,
        "allow_position_creation": False,
        "allow_paper_trade_persistence": False,
        "allow_executable_trade_creation": False,
        "allow_state_mutation": False,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_signal_config_pass": True,
        "require_trade_candidate_config_pass": True,
        "require_candidate_journal_config_pass": True,
        "require_kill_switch_enabled": True,
        "cycle_mode": "historical_cursor",
        "start_index": 500,
        "max_cycles": 5,
        "min_candles": 1000,
        "evaluation_window": 500,
        "cycle_interval_seconds": 0,
        "max_run_seconds": 60,
        "state_export_dir": "reports/forward_test",
        "report_export_dir": "reports/forward_test",
    }
    values.update(overrides)
    return values


def _write_forward_configs(tmp_path: Path, *, forward: dict[str, Any] | None = None, **kwargs) -> Path:
    _write_journal_configs(tmp_path, **kwargs)
    _write_json(tmp_path / "data" / "historical" / "btcusdt_15m_1000.json", _candles())
    _write_json(tmp_path / "data" / "historical" / "btcusdt_1h_1000.json", _candles())
    path = tmp_path / "configs" / "btc_forward_test_loop.json"
    _write_json(path, _forward_config(**(forward or {})))
    return path


class _FakeJournalEngine:
    def __init__(self, result: BTCPaperCandidateJournalRecordResult | None = None, report_status: str = "PASS") -> None:
        self.result = result or _journal_result(candidate_created=False, status="WARNING")
        self.report_status = report_status

    def validate(self, config_path: str = "configs/btc_paper_candidate_journal.json", expected_profile: str = "balanced_smc_decision_065") -> BTCPaperCandidateJournalValidationReport:
        return BTCPaperCandidateJournalValidationReport(config_path=config_path, status=self.report_status, diagnostics={})

    def simulate_and_record(self, config_path: str = "configs/btc_paper_candidate_journal.json", expected_profile: str = "balanced_smc_decision_065", journal_path: str | None = None, runner_state: str | None = None) -> BTCPaperCandidateJournalRecordResult:
        return self.result


def _journal_result(*, candidate_created: bool, status: str = "PASS") -> BTCPaperCandidateJournalRecordResult:
    entry = BTCPaperCandidateJournalEntry(
        entry_id="BTC-JOURNAL-1",
        created_at="2026-01-01T00:00:00+00:00",
        signal_status=status,
        signal_decision="APPROVED_DRY_RUN" if candidate_created else "WARNING_DRY_RUN",
        signal_score=0.8 if candidate_created else 0.4,
        signal_threshold=0.65,
        candidate_status=status,
        candidate_decision="CANDIDATE_CREATED_DRY_RUN" if candidate_created else "NO_CANDIDATE_SCORE_TOO_LOW",
        candidate_created=candidate_created,
        candidate_id="BTC-DRYRUN-1" if candidate_created else None,
        rejection_reason=None if candidate_created else "Signal score is below threshold.",
    )
    return BTCPaperCandidateJournalRecordResult(
        status=status,
        entry_written=status != "FAIL",
        journal_path="reports/paper_candidate_journal/test.jsonl",
        entry=entry,
        reason="journaled",
        executable_trade_created=False,
        paper_trade_persisted=False,
        position_created=False,
        order_submitted=False,
        exchange_connected=False,
        state_mutated=False,
    )


def _engine(tmp_path: Path, result: BTCPaperCandidateJournalRecordResult | None = None, report_status: str = "PASS") -> BTCForwardTestLoopEngine:
    return BTCForwardTestLoopEngine(
        repo_root=tmp_path,
        candidate_journal_engine=_FakeJournalEngine(result=result, report_status=report_status),
        now_provider=lambda: "2026-01-01T00:00:00+00:00",
    )


def test_default_repo_forward_config_validates_pass() -> None:
    report = BTCForwardTestLoopEngine().validate()

    assert report.status == "PASS"
    assert report.diagnostics["runtime_config_status"] == "PASS"
    assert report.diagnostics["candidate_journal_config_status"] == "PASS"


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("dry_run_only", False, "dry_run_only"),
        ("allow_live_market_data", True, "allow_live_market_data"),
        ("allow_exchange_connection", True, "allow_exchange_connection"),
        ("allow_order_submission", True, "allow_order_submission"),
        ("allow_position_creation", True, "allow_position_creation"),
        ("allow_paper_trade_persistence", True, "allow_paper_trade_persistence"),
        ("allow_executable_trade_creation", True, "allow_executable_trade_creation"),
        ("allow_state_mutation", True, "allow_state_mutation"),
        ("symbol", "ETH/USDT", "symbol"),
        ("strategy_profile", "research_baseline", "strategy_profile"),
        ("state_export_dir", "../outside", "state_export_dir"),
        ("report_export_dir", "../outside", "report_export_dir"),
        ("max_cycles", 101, "max_cycles"),
        ("cycle_interval_seconds", 1, "cycle_interval_seconds"),
    ],
)
def test_dangerous_forward_config_fails(tmp_path: Path, field: str, value: Any, issue: str) -> None:
    path = _write_forward_configs(tmp_path, forward={field: value})

    report = BTCForwardTestLoopEngine(repo_root=tmp_path).validate(str(path))

    assert report.status == "FAIL"
    assert issue in {item.name for item in report.issues}


def test_dependency_config_failures_block_forward_config(tmp_path: Path) -> None:
    cases = [
        ("runtime", {"runtime": {"live_trading_enabled": True}}, "runtime_config_validation"),
        ("monitoring", {"monitoring": {"live_trading_expected": True}}, "monitoring_config_validation"),
        ("runner", {"runner": {"allow_order_submission": True}}, "runner_config_validation"),
        ("signal", {"signal": None}, "signal_config_validation"),
        ("candidate", {"candidate": {"allow_order_submission": True}}, "trade_candidate_config_validation"),
        ("journal", {"journal": {"allow_order_submission": True}}, "candidate_journal_config_validation"),
        ("kill", {"runtime": {"kill_switch_enabled": False}}, "kill_switch_enabled"),
    ]
    for name, kwargs, expected_issue in cases:
        root = tmp_path / name
        if name == "signal":
            kwargs["signal"] = _signal_config(root, allow_order_submission=True)
        path = _write_forward_configs(root, **kwargs)
        report = BTCForwardTestLoopEngine(repo_root=root).validate(str(path))
        assert expected_issue in {issue.name for issue in report.issues}


def test_run_low_score_candidate_completes_rejected_cycles(tmp_path: Path) -> None:
    path = _write_forward_configs(tmp_path)

    result = _engine(tmp_path, _journal_result(candidate_created=False, status="WARNING")).run(str(path), cycles=3)

    assert result.status == "WARNING"
    assert result.cycles_completed == 3
    assert result.candidates_rejected == 3
    assert result.journal_entries_written == 3
    assert result.live_market_data_used is False
    assert result.order_submitted is False


def test_run_approved_candidate_counts_created(tmp_path: Path) -> None:
    path = _write_forward_configs(tmp_path)

    result = _engine(tmp_path, _journal_result(candidate_created=True)).run(str(path), cycles=2)

    assert result.status == "PASS"
    assert result.cycles_completed == 2
    assert result.candidates_created == 2
    assert result.executable_trade_created is False
    assert result.paper_trade_persisted is False
    assert result.position_created is False
    assert result.exchange_connected is False
    assert result.state_mutated is False


def test_run_stops_safely_on_fail(tmp_path: Path) -> None:
    path = _write_forward_configs(tmp_path)

    result = _engine(tmp_path, _journal_result(candidate_created=False, status="FAIL")).run(str(path), cycles=3)

    assert result.status == "FAIL"
    assert result.cycles_failed == 1
    assert len(result.cycles) == 1


def test_run_with_state_file_writes_local_diagnostic_state(tmp_path: Path) -> None:
    path = _write_forward_configs(tmp_path)
    state_path = tmp_path / "reports" / "forward_test" / "state.json"

    result = _engine(tmp_path, _journal_result(candidate_created=True)).run(str(path), cycles=2, state_file=str(state_path))
    state = _engine(tmp_path).summary(str(state_path))

    assert result.status == "PASS"
    assert state_path.exists()
    assert state.total_cycles_completed == 2
    assert state.total_candidates_created == 2


def test_summary_missing_state_and_reset_are_safe(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    state_path = tmp_path / "reports" / "forward_test" / "state.json"

    missing = engine.summary(str(state_path))
    reset = engine.reset_state(str(state_path))

    assert missing.last_status == "WARNING"
    assert reset.last_status == "WARNING"
    assert not state_path.exists()
