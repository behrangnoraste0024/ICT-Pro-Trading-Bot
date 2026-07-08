from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.diagnostics.btc_paper_signal_evaluation_engine import BTCPaperSignalEvaluationEngine


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _candles(count: int = 1000) -> list[dict]:
    return [
        {"timestamp": i, "open": 100 + i * 0.1, "high": 101 + i * 0.1, "low": 99 + i * 0.1, "close": 100 + i * 0.1, "volume": 1}
        for i in range(count)
    ]


def _runtime_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "exchange": "binance",
        "strategy_profile": "balanced_smc_decision_065",
        "sample_scope": "required_full",
        "primary_timeframe": "15m",
        "confirmation_timeframe": "1h",
        "enabled": False,
        "paper_execution_enabled": False,
        "live_trading_enabled": False,
        "order_submission_enabled": False,
        "dry_run": True,
        "kill_switch_enabled": True,
        "account_currency": "USDT",
        "starting_equity": 10000.0,
        "risk_per_trade_pct": 0.005,
        "max_risk_per_trade_pct": 0.01,
        "max_daily_loss_pct": 0.02,
        "max_total_drawdown_pct": 0.05,
        "max_open_positions": 1,
        "max_trades_per_day": 3,
        "min_trade_interval_minutes": 15,
        "max_position_notional_pct": 0.25,
        "min_risk_reward": 1.5,
        "require_stop_loss": True,
        "require_take_profit": True,
        "allow_long": True,
        "allow_short": True,
    }
    values.update(overrides)
    return values


def _monitoring_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "enabled": True,
        "monitoring_only": True,
        "paper_execution_expected": False,
        "live_trading_expected": False,
        "order_submission_expected": False,
        "heartbeat_stale_after_seconds": 120,
        "signal_stale_after_minutes": 60,
        "validation_gate_stale_after_hours": 24,
        "runtime_config_stale_after_hours": 24,
        "max_consecutive_errors": 3,
        "require_kill_switch_visible": True,
        "require_execution_state_visible": True,
        "require_runtime_config_visible": True,
        "require_validation_gate_status_visible": True,
        "require_last_signal_visible": False,
        "status_export_dir": "reports/paper_monitoring",
    }
    values.update(overrides)
    return values


def _runner_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_enabled": False,
        "dry_run_only": True,
        "allow_signal_generation": False,
        "allow_paper_trade_creation": False,
        "allow_order_submission": False,
        "allow_exchange_connection": False,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_kill_switch_enabled": True,
        "heartbeat_interval_seconds": 30,
        "state_export_dir": "reports/paper_runner",
    }
    values.update(overrides)
    return values


def _signal_config(tmp_path: Path, **overrides) -> dict:
    fixture = tmp_path / "fixtures" / "btcusdt_15m_1000.json"
    confirmation = tmp_path / "fixtures" / "btcusdt_1h_1000.json"
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "sample_name": "btcusdt_15m_1000",
        "fixture_path": str(fixture),
        "confirmation_sample_name": "btcusdt_1h_1000",
        "confirmation_fixture_path": str(confirmation),
        "evaluation_mode": "latest_closed_candle",
        "dry_run_only": True,
        "allow_trade_creation": False,
        "allow_order_submission": False,
        "allow_exchange_connection": False,
        "allow_state_mutation": False,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_validation_baseline": True,
        "require_kill_switch_enabled": True,
        "min_candles": 1000,
        "max_evaluation_window": 500,
        "decision_threshold": 0.65,
        "status_export_dir": "reports/paper_signal_evaluation",
    }
    values.update(overrides)
    return values


def _write_configs(tmp_path: Path, *, runtime: dict | None = None, monitoring: dict | None = None, runner: dict | None = None, signal: dict | None = None, candle_count: int = 1000) -> Path:
    _write_json(tmp_path / "configs" / "btc_paper_runtime.json", _runtime_config(**(runtime or {})))
    _write_json(tmp_path / "configs" / "btc_paper_monitoring.json", _monitoring_config(**(monitoring or {})))
    _write_json(tmp_path / "configs" / "btc_paper_runner.json", _runner_config(**(runner or {})))
    config = signal or _signal_config(tmp_path)
    _write_json(Path(config["fixture_path"]), _candles(candle_count))
    _write_json(Path(config["confirmation_fixture_path"]), _candles(candle_count))
    path = tmp_path / "configs" / "btc_paper_signal_evaluation.json"
    _write_json(path, config)
    return path


def test_default_repo_signal_config_validates_pass() -> None:
    report = BTCPaperSignalEvaluationEngine().validate()

    assert report.status == "PASS"
    assert report.diagnostics["runtime_config_status"] == "PASS"
    assert report.diagnostics["monitoring_config_status"] == "PASS"
    assert report.diagnostics["runner_config_status"] == "PASS"


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("dry_run_only", False, "dry_run_only"),
        ("allow_trade_creation", True, "allow_trade_creation"),
        ("allow_order_submission", True, "allow_order_submission"),
        ("allow_exchange_connection", True, "allow_exchange_connection"),
        ("allow_state_mutation", True, "allow_state_mutation"),
        ("symbol", "ETH/USDT", "symbol"),
        ("strategy_profile", "research_baseline", "strategy_profile"),
        ("status_export_dir", "../outside", "status_export_dir"),
    ],
)
def test_dangerous_signal_config_fails(tmp_path, field: str, value, issue: str) -> None:
    path = _write_configs(tmp_path, signal=_signal_config(tmp_path, **{field: value}))

    report = BTCPaperSignalEvaluationEngine(repo_root=tmp_path).validate(str(path))

    assert report.status == "FAIL"
    assert issue in {item.name for item in report.issues}


def test_runtime_monitoring_runner_or_kill_switch_fail_blocks(tmp_path) -> None:
    runtime_root = tmp_path / "runtime"
    monitoring_root = tmp_path / "monitoring"
    runner_root = tmp_path / "runner"
    kill_root = tmp_path / "kill"
    runtime_path = _write_configs(runtime_root, runtime={"live_trading_enabled": True})
    monitoring_path = _write_configs(monitoring_root, monitoring={"live_trading_expected": True})
    runner_path = _write_configs(runner_root, runner={"allow_order_submission": True})
    kill_path = _write_configs(kill_root, runtime={"kill_switch_enabled": False})

    assert "runtime_config_validation" in {issue.name for issue in BTCPaperSignalEvaluationEngine(repo_root=runtime_root).validate(str(runtime_path)).issues}
    assert "monitoring_config_validation" in {issue.name for issue in BTCPaperSignalEvaluationEngine(repo_root=monitoring_root).validate(str(monitoring_path)).issues}
    assert "runner_config_validation" in {issue.name for issue in BTCPaperSignalEvaluationEngine(repo_root=runner_root).validate(str(runner_path)).issues}
    assert "kill_switch_enabled" in {issue.name for issue in BTCPaperSignalEvaluationEngine(repo_root=kill_root).validate(str(kill_path)).issues}


def test_evaluate_uses_fixtures_and_never_executes(tmp_path) -> None:
    path = _write_configs(tmp_path)

    result = BTCPaperSignalEvaluationEngine(repo_root=tmp_path).evaluate(str(path))

    assert result.status in ("PASS", "WARNING")
    assert result.decision in ("NONE", "WARNING_DRY_RUN", "APPROVED_DRY_RUN")
    assert result.candle_count == 1000
    assert result.trade_created is False
    assert result.order_submitted is False
    assert result.exchange_connected is False
    assert result.state_mutated is False


def test_evaluate_missing_or_too_few_candles_fails(tmp_path) -> None:
    missing_root = tmp_path / "missing_case"
    few_root = tmp_path / "few_case"
    missing_config = _signal_config(missing_root, fixture_path=str(missing_root / "missing.json"))
    missing_path = _write_configs(missing_root, signal=missing_config)
    Path(missing_config["fixture_path"]).unlink()
    few_path = _write_configs(few_root, candle_count=10)

    assert BTCPaperSignalEvaluationEngine(repo_root=missing_root).evaluate(str(missing_path)).status == "FAIL"
    assert BTCPaperSignalEvaluationEngine(repo_root=few_root).evaluate(str(few_path)).status == "FAIL"
