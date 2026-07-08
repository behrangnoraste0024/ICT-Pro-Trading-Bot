from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from models.btc_paper_runner import BTCPaperRunnerState, BTCPaperRunnerStatus


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
        "notes": "test",
    }
    values.update(overrides)
    return values


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_configs(tmp_path: Path, *, runtime: dict | None = None, monitoring: dict | None = None, runner: dict | None = None) -> None:
    _write_json(tmp_path / "configs" / "btc_paper_runtime.json", _runtime_config(**(runtime or {})))
    _write_json(tmp_path / "configs" / "btc_paper_monitoring.json", _monitoring_config(**(monitoring or {})))
    _write_json(tmp_path / "configs" / "btc_paper_runner.json", _runner_config(**(runner or {})))


def test_default_repo_runner_config_validates_pass() -> None:
    config, issues, diagnostics = BTCPaperRunnerEngine().validate_config()

    assert config is not None
    assert not any(issue.severity == "FAIL" for issue in issues)
    assert diagnostics["runtime_config_status"] == "PASS"
    assert diagnostics["monitoring_config_status"] == "PASS"


def test_default_status_is_created_and_safe() -> None:
    status = BTCPaperRunnerEngine().build_status()

    assert status.state == "CREATED"
    assert status.signal_generation_enabled is False
    assert status.paper_trade_creation_enabled is False
    assert status.order_submission_enabled is False
    assert status.exchange_connection_enabled is False


def test_lifecycle_transitions(tmp_path) -> None:
    _write_configs(tmp_path)
    engine = BTCPaperRunnerEngine(repo_root=tmp_path)

    ready = engine.apply("initialize")
    running = engine.apply("start", status=ready.status)
    paused = engine.apply("pause", status=running.status)
    resumed = engine.apply("resume", status=paused.status)
    stopped = engine.apply("stop", status=resumed.status)

    assert ready.accepted and ready.current_state == "READY"
    assert running.accepted and running.current_state == "RUNNING"
    assert paused.accepted and paused.current_state == "PAUSED"
    assert resumed.accepted and resumed.current_state == "RUNNING"
    assert stopped.accepted and stopped.current_state == "STOPPED"
    assert running.status.paper_trade_creation_enabled is False


def test_stop_from_paused(tmp_path) -> None:
    _write_configs(tmp_path)
    engine = BTCPaperRunnerEngine(repo_root=tmp_path)
    paused = BTCPaperRunnerStatus(state=BTCPaperRunnerState.PAUSED.value)

    result = engine.apply("stop", status=paused)

    assert result.accepted
    assert result.current_state == "STOPPED"


def test_heartbeat_updates_only_when_running_or_paused(tmp_path) -> None:
    _write_configs(tmp_path)
    engine = BTCPaperRunnerEngine(repo_root=tmp_path)

    running = engine.apply("heartbeat", status=BTCPaperRunnerStatus(state="RUNNING"))
    ready = engine.apply("heartbeat", status=BTCPaperRunnerStatus(state="READY"))

    assert running.accepted
    assert running.status.last_heartbeat_at is not None
    assert ready.accepted
    assert ready.status.last_heartbeat_at is None
    assert "ignored" in ready.message


def test_invalid_transition_rejected_without_crash(tmp_path) -> None:
    _write_configs(tmp_path)
    result = BTCPaperRunnerEngine(repo_root=tmp_path).apply("pause", status=BTCPaperRunnerStatus(state="READY"))

    assert result.accepted is False
    assert result.current_state == "READY"
    assert "pause is not valid" in result.message


def test_reset_error_moves_to_ready_when_safe(tmp_path) -> None:
    _write_configs(tmp_path)
    result = BTCPaperRunnerEngine(repo_root=tmp_path).apply("reset_error", status=BTCPaperRunnerStatus(state="ERROR", error_message="x", consecutive_errors=2))

    assert result.accepted
    assert result.current_state == "READY"
    assert result.status.error_message is None
    assert result.status.consecutive_errors == 0


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("dry_run_only", False, "dry_run_only"),
        ("allow_signal_generation", True, "allow_signal_generation"),
        ("allow_paper_trade_creation", True, "allow_paper_trade_creation"),
        ("allow_order_submission", True, "allow_order_submission"),
        ("allow_exchange_connection", True, "allow_exchange_connection"),
        ("symbol", "ETH/USDT", "symbol"),
        ("strategy_profile", "research_baseline", "strategy_profile"),
        ("heartbeat_interval_seconds", 9, "heartbeat_interval_seconds"),
        ("heartbeat_interval_seconds", 301, "heartbeat_interval_seconds"),
        ("state_export_dir", "../outside", "state_export_dir"),
    ],
)
def test_dangerous_runner_config_fails(tmp_path, field: str, value, issue: str) -> None:
    _write_configs(tmp_path, runner={field: value})

    _, issues, _ = BTCPaperRunnerEngine(repo_root=tmp_path).validate_config()

    assert issue in {item.name for item in issues if item.severity == "FAIL"}


def test_runtime_or_monitoring_fail_blocks_runner(tmp_path) -> None:
    _write_configs(tmp_path, runtime={"live_trading_enabled": True})
    _, runtime_issues, _ = BTCPaperRunnerEngine(repo_root=tmp_path).validate_config()
    _write_configs(tmp_path, monitoring={"live_trading_expected": True})
    _, monitoring_issues, _ = BTCPaperRunnerEngine(repo_root=tmp_path).validate_config()

    assert "runtime_config_validation" in {issue.name for issue in runtime_issues}
    assert "monitoring_config_validation" in {issue.name for issue in monitoring_issues}


def test_state_file_round_trip(tmp_path) -> None:
    _write_configs(tmp_path)
    engine = BTCPaperRunnerEngine(repo_root=tmp_path)
    state_path = "reports/paper_runner/state.json"
    status = engine.apply("start").status

    engine.save_state(status, state_path)
    loaded = engine.load_state(state_path)

    assert loaded.state == "RUNNING"
    assert (tmp_path / state_path).exists()
