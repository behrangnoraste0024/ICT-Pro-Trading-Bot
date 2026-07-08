from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine


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
        "notes": "test",
    }
    values.update(overrides)
    return values


def _write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _write_configs(tmp_path: Path, *, runtime_overrides: dict | None = None, monitoring_overrides: dict | None = None) -> Path:
    _write_json(tmp_path / "configs" / "btc_paper_runtime.json", _runtime_config(**(runtime_overrides or {})))
    return _write_json(tmp_path / "configs" / "btc_paper_monitoring.json", _monitoring_config(**(monitoring_overrides or {})))


def _validate(tmp_path: Path, **overrides):
    path = _write_configs(tmp_path, monitoring_overrides=overrides)
    return BTCPaperMonitoringEngine(repo_root=tmp_path).validate(str(path))


def test_default_repo_config_validates_pass() -> None:
    report = BTCPaperMonitoringEngine().validate()

    assert report.status == "PASS"
    assert report.config is not None
    assert report.config.symbol == "BTC/USDT"
    assert report.diagnostics["runtime_config_status"] == "PASS"


def test_default_monitoring_status_is_ready_prerunner(tmp_path) -> None:
    _write_configs(tmp_path)

    status = BTCPaperMonitoringEngine(repo_root=tmp_path).build_status()

    assert status.monitoring_status == "READY"
    assert status.runtime_config_status == "PASS"
    assert status.paper_execution_enabled is False
    assert status.live_trading_enabled is False
    assert status.order_submission_enabled is False
    assert status.last_heartbeat_at is None


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("monitoring_only", False, "monitoring_only"),
        ("paper_execution_expected", True, "paper_execution_expected"),
        ("live_trading_expected", True, "live_trading_expected"),
        ("order_submission_expected", True, "order_submission_expected"),
        ("symbol", "ETH/USDT", "symbol"),
        ("strategy_profile", "research_baseline", "strategy_profile"),
        ("heartbeat_stale_after_seconds", 29, "heartbeat_stale_after_seconds"),
        ("heartbeat_stale_after_seconds", 601, "heartbeat_stale_after_seconds"),
        ("signal_stale_after_minutes", 4, "signal_stale_after_minutes"),
        ("signal_stale_after_minutes", 241, "signal_stale_after_minutes"),
        ("require_kill_switch_visible", False, "require_kill_switch_visible"),
        ("require_execution_state_visible", False, "require_execution_state_visible"),
        ("require_runtime_config_visible", False, "require_runtime_config_visible"),
        ("require_validation_gate_status_visible", False, "require_validation_gate_status_visible"),
        ("status_export_dir", "../outside", "status_export_dir"),
        ("status_export_dir", "reports/other", "status_export_dir"),
    ],
)
def test_dangerous_monitoring_settings_fail(tmp_path, field: str, value, issue: str) -> None:
    report = _validate(tmp_path, **{field: value})

    assert report.status == "FAIL"
    assert issue in {item.name for item in report.issues}


def test_missing_runtime_config_fails(tmp_path) -> None:
    path = _write_json(tmp_path / "configs" / "btc_paper_monitoring.json", _monitoring_config())

    report = BTCPaperMonitoringEngine(repo_root=tmp_path).validate(str(path))

    assert report.status == "FAIL"
    assert "runtime_config_missing" in {item.name for item in report.issues}


def test_runtime_config_validation_fail_blocks_monitoring(tmp_path) -> None:
    _write_configs(tmp_path, runtime_overrides={"live_trading_enabled": True})

    report = BTCPaperMonitoringEngine(repo_root=tmp_path).validate()

    assert report.status == "FAIL"
    assert "runtime_config_validation" in {item.name for item in report.issues}
