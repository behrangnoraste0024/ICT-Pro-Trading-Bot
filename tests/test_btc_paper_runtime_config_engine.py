from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine


def _config(**overrides) -> dict:
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
        "notes": "test",
    }
    values.update(overrides)
    return values


def _write(path: Path, config: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _validate(tmp_path: Path, **overrides):
    path = _write(tmp_path / "configs" / "btc_paper_runtime.json", _config(**overrides))
    return BTCPaperRuntimeConfigEngine(repo_root=tmp_path).validate(str(path))


def test_default_repo_config_validates_pass() -> None:
    report = BTCPaperRuntimeConfigEngine().validate()

    assert report.status == "PASS"
    assert report.fail_count == 0
    assert report.config is not None
    assert report.config.symbol == "BTC/USDT"


def test_missing_config_returns_fail(tmp_path) -> None:
    report = BTCPaperRuntimeConfigEngine(repo_root=tmp_path).validate("configs/missing.json")

    assert report.status == "FAIL"
    assert report.issues[0].name == "config_missing"


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("live_trading_enabled", True, "live_trading_enabled"),
        ("order_submission_enabled", True, "order_submission_enabled"),
        ("paper_execution_enabled", True, "paper_execution_enabled"),
        ("dry_run", False, "dry_run"),
        ("kill_switch_enabled", False, "kill_switch_enabled"),
        ("symbol", "ETH/USDT", "symbol"),
        ("strategy_profile", "research_baseline", "strategy_profile"),
        ("max_risk_per_trade_pct", 0.02, "max_risk_per_trade_pct"),
        ("max_daily_loss_pct", 0.04, "max_daily_loss_pct"),
        ("max_total_drawdown_pct", 0.11, "max_total_drawdown_pct"),
        ("max_open_positions", 2, "max_open_positions"),
        ("require_stop_loss", False, "require_stop_loss"),
        ("require_take_profit", False, "require_take_profit"),
        ("min_risk_reward", 1.49, "min_risk_reward"),
    ],
)
def test_dangerous_settings_fail(tmp_path, field: str, value, issue: str) -> None:
    report = _validate(tmp_path, **{field: value})

    assert report.status == "FAIL"
    assert issue in {item.name for item in report.issues}


def test_no_direction_allowed_fails(tmp_path) -> None:
    report = _validate(tmp_path, allow_long=False, allow_short=False)

    assert report.status == "FAIL"
    assert "direction_allowed" in {issue.name for issue in report.issues}


def test_enabled_true_is_warning_not_fail_when_execution_disabled(tmp_path) -> None:
    report = _validate(tmp_path, enabled=True)

    assert report.status == "WARNING"
    assert report.warning_count == 1
    assert report.fail_count == 0
