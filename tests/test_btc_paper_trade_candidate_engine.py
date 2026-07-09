from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.diagnostics.btc_paper_trade_candidate_engine import BTCPaperTradeCandidateEngine
from models.btc_paper_signal_evaluation import (
    BTCPaperSignalEvaluationConfig,
    BTCPaperSignalEvaluationResult,
    BTCPaperSignalEvaluationStatus,
    BTCPaperSignalEvaluationValidationReport,
)
from models.btc_paper_trade_candidate import BTCPaperTradeCandidateDecision
from tests.test_btc_paper_signal_evaluation_engine import (
    _monitoring_config,
    _runner_config,
    _runtime_config,
    _signal_config,
    _write_configs as _write_signal_configs,
)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _trade_candidate_config(**overrides) -> dict[str, Any]:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "signal_evaluation_config_path": "configs/btc_paper_signal_evaluation.json",
        "dry_run_only": True,
        "allow_candidate_creation": True,
        "allow_executable_trade_creation": False,
        "allow_paper_trade_persistence": False,
        "allow_position_creation": False,
        "allow_order_submission": False,
        "allow_exchange_connection": False,
        "allow_state_mutation": False,
        "require_signal_approved": True,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_signal_config_pass": True,
        "require_kill_switch_enabled": True,
        "min_signal_score": 0.65,
        "min_risk_reward": 1.5,
        "entry_price_source": "latest_close",
        "stop_loss_mode": "diagnostic_atr_like",
        "take_profit_mode": "fixed_rr",
        "diagnostic_stop_loss_pct": 0.01,
        "max_candidate_notional_pct": 0.25,
        "status_export_dir": "reports/paper_trade_candidates",
    }
    values.update(overrides)
    return values


def _write_trade_candidate_configs(
    tmp_path: Path,
    *,
    runtime: dict[str, Any] | None = None,
    monitoring: dict[str, Any] | None = None,
    runner: dict[str, Any] | None = None,
    signal: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
) -> Path:
    _write_signal_configs(tmp_path, runtime=runtime, monitoring=monitoring, runner=runner, signal=signal or _signal_config(tmp_path))
    path = tmp_path / "configs" / "btc_paper_trade_candidate.json"
    _write_json(path, _trade_candidate_config(**(candidate or {})))
    return path


class _FakeSignalEngine:
    def __init__(self, result: BTCPaperSignalEvaluationResult | None = None, report_status: str = "PASS") -> None:
        self.result = result or _signal_result()
        self.report_status = report_status

    def validate(self, config_path: str = "configs/btc_paper_signal_evaluation.json", expected_profile: str = "balanced_smc_decision_065") -> BTCPaperSignalEvaluationValidationReport:
        return BTCPaperSignalEvaluationValidationReport(
            config_path=config_path,
            status=self.report_status,
            config=BTCPaperSignalEvaluationConfig(strategy_profile=expected_profile),
            diagnostics={},
        )

    def evaluate(self, config_path: str = "configs/btc_paper_signal_evaluation.json", expected_profile: str = "balanced_smc_decision_065") -> BTCPaperSignalEvaluationResult:
        return self.result


def _signal_result(**overrides) -> BTCPaperSignalEvaluationResult:
    values = {
        "status": BTCPaperSignalEvaluationStatus.PASS.value,
        "decision": "APPROVED_DRY_RUN",
        "direction": "BULLISH",
        "score": 0.8,
        "threshold": 0.65,
        "reason": "approved",
        "setup_summary": {"latest_close": 100.0},
        "trade_created": False,
        "order_submitted": False,
        "exchange_connected": False,
        "state_mutated": False,
    }
    values.update(overrides)
    return BTCPaperSignalEvaluationResult(**values)


def test_default_repo_trade_candidate_config_validates_pass() -> None:
    report = BTCPaperTradeCandidateEngine().validate()

    assert report.status == "PASS"
    assert report.diagnostics["runtime_config_status"] == "PASS"
    assert report.diagnostics["monitoring_config_status"] == "PASS"
    assert report.diagnostics["runner_config_status"] == "PASS"
    assert report.diagnostics["signal_config_status"] == "PASS"


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
        ("min_risk_reward", 1.0, "min_risk_reward"),
        ("diagnostic_stop_loss_pct", 0.0, "diagnostic_stop_loss_pct"),
        ("max_candidate_notional_pct", 0.5, "max_candidate_notional_pct"),
        ("status_export_dir", "../outside", "status_export_dir"),
    ],
)
def test_dangerous_trade_candidate_config_fails(tmp_path: Path, field: str, value: Any, issue: str) -> None:
    path = _write_trade_candidate_configs(tmp_path, candidate={field: value})

    report = BTCPaperTradeCandidateEngine(repo_root=tmp_path).validate(str(path))

    assert report.status == "FAIL"
    assert issue in {item.name for item in report.issues}


def test_runtime_monitoring_runner_signal_or_kill_switch_fail_blocks(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    monitoring_root = tmp_path / "monitoring"
    runner_root = tmp_path / "runner"
    signal_root = tmp_path / "signal"
    kill_root = tmp_path / "kill"
    runtime_path = _write_trade_candidate_configs(runtime_root, runtime={"live_trading_enabled": True})
    monitoring_path = _write_trade_candidate_configs(monitoring_root, monitoring={"live_trading_expected": True})
    runner_path = _write_trade_candidate_configs(runner_root, runner={"allow_order_submission": True})
    signal_path = _write_trade_candidate_configs(signal_root, signal=_signal_config(signal_root, allow_order_submission=True))
    kill_path = _write_trade_candidate_configs(kill_root, runtime={"kill_switch_enabled": False})

    assert "runtime_config_validation" in {issue.name for issue in BTCPaperTradeCandidateEngine(repo_root=runtime_root).validate(str(runtime_path)).issues}
    assert "monitoring_config_validation" in {issue.name for issue in BTCPaperTradeCandidateEngine(repo_root=monitoring_root).validate(str(monitoring_path)).issues}
    assert "runner_config_validation" in {issue.name for issue in BTCPaperTradeCandidateEngine(repo_root=runner_root).validate(str(runner_path)).issues}
    assert "signal_config_validation" in {issue.name for issue in BTCPaperTradeCandidateEngine(repo_root=signal_root).validate(str(signal_path)).issues}
    assert "kill_switch_enabled" in {issue.name for issue in BTCPaperTradeCandidateEngine(repo_root=kill_root).validate(str(kill_path)).issues}


def test_simulate_low_score_signal_creates_no_candidate(tmp_path: Path) -> None:
    path = _write_trade_candidate_configs(tmp_path)
    engine = BTCPaperTradeCandidateEngine(repo_root=tmp_path, signal_engine=_FakeSignalEngine(_signal_result(score=0.4)))

    result = engine.simulate(str(path))

    assert result.status == "WARNING"
    assert result.decision == BTCPaperTradeCandidateDecision.NO_CANDIDATE_SCORE_TOO_LOW.value
    assert result.candidate_created is False
    assert result.paper_trade_persisted is False
    assert result.position_created is False
    assert result.order_submitted is False
    assert result.exchange_connected is False
    assert result.state_mutated is False


def test_simulate_approved_bullish_signal_creates_non_executable_long_candidate(tmp_path: Path) -> None:
    path = _write_trade_candidate_configs(tmp_path)
    engine = BTCPaperTradeCandidateEngine(repo_root=tmp_path, signal_engine=_FakeSignalEngine(_signal_result(direction="BULLISH", score=0.9)))

    result = engine.simulate(str(path))

    assert result.status == "PASS"
    assert result.decision == BTCPaperTradeCandidateDecision.CANDIDATE_CREATED_DRY_RUN.value
    assert result.candidate_created is True
    assert result.candidate is not None
    assert result.candidate.direction == "LONG"
    assert result.candidate.entry_price == 100.0
    assert result.candidate.stop_loss == 99.0
    assert result.candidate.take_profit == 101.5
    assert result.candidate.candidate_is_executable is False
    assert result.candidate.candidate_is_persisted is False
    assert result.candidate.candidate_opens_position is False
    assert result.paper_trade_persisted is False
    assert result.position_created is False
    assert result.order_submitted is False


def test_simulate_approved_bearish_signal_creates_non_executable_short_candidate(tmp_path: Path) -> None:
    path = _write_trade_candidate_configs(tmp_path)
    engine = BTCPaperTradeCandidateEngine(repo_root=tmp_path, signal_engine=_FakeSignalEngine(_signal_result(direction="BEARISH", score=0.9)))

    result = engine.simulate(str(path))

    assert result.candidate is not None
    assert result.candidate.direction == "SHORT"
    assert result.candidate.stop_loss == 101.0
    assert result.candidate.take_profit == 98.5
    assert result.executable_trade_created is False
    assert result.paper_trade_persisted is False
    assert result.position_created is False


def test_simulate_caps_candidate_notional_without_creating_position(tmp_path: Path) -> None:
    path = _write_trade_candidate_configs(tmp_path, candidate={"max_candidate_notional_pct": 0.01})
    engine = BTCPaperTradeCandidateEngine(repo_root=tmp_path, signal_engine=_FakeSignalEngine(_signal_result(score=0.9)))

    result = engine.simulate(str(path))

    assert result.candidate is not None
    assert result.candidate.estimated_notional == 100.0
    assert "candidate_notional_capped" in {issue.name for issue in result.issues}
    assert result.position_created is False
