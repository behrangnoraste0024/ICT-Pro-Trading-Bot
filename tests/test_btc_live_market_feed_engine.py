from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.diagnostics.btc_live_market_feed_engine import BTCLiveMarketFeedEngine
from models.btc_live_market_feed import BTCLiveMarketCandle
from tests.test_btc_forward_test_loop_engine import _write_forward_configs
from tests.test_btc_paper_signal_evaluation_engine import _signal_config


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _live_config(**overrides) -> dict[str, Any]:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "exchange": "binance",
        "market_type": "spot",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "signal_evaluation_config_path": "configs/btc_paper_signal_evaluation.json",
        "trade_candidate_config_path": "configs/btc_paper_trade_candidate.json",
        "candidate_journal_config_path": "configs/btc_paper_candidate_journal.json",
        "forward_test_config_path": "configs/btc_forward_test_loop.json",
        "primary_timeframe": "15m",
        "confirmation_timeframe": "1h",
        "primary_limit": 100,
        "confirmation_limit": 100,
        "closed_candles_only": True,
        "dry_run_only": True,
        "feed_enabled": False,
        "allow_public_market_data_fetch": True,
        "allow_private_api": False,
        "allow_api_key_usage": False,
        "allow_trading_api": False,
        "allow_account_data": False,
        "allow_balance_fetch": False,
        "allow_position_fetch": False,
        "allow_order_submission": False,
        "allow_order_cancellation": False,
        "allow_position_creation": False,
        "allow_paper_trade_persistence": False,
        "allow_executable_trade_creation": False,
        "allow_state_mutation": False,
        "allow_journal_write": True,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_signal_config_pass": True,
        "require_trade_candidate_config_pass": True,
        "require_candidate_journal_config_pass": True,
        "require_kill_switch_enabled": True,
        "request_timeout_seconds": 10,
        "max_fetch_retries": 0,
        "min_primary_candles": 100,
        "min_confirmation_candles": 100,
        "observation_mode": "fetch_once",
        "status_export_dir": "reports/live_market_feed",
    }
    values.update(overrides)
    return values


def _write_live_configs(tmp_path: Path, *, live: dict[str, Any] | None = None, **kwargs) -> Path:
    _write_forward_configs(tmp_path, **kwargs)
    path = tmp_path / "configs" / "btc_live_market_feed.json"
    _write_json(path, _live_config(**(live or {})))
    return path


class _Adapter:
    def __init__(self, candles: int = 101, fail: bool = False, step: float = 1.0) -> None:
        self.candles = candles
        self.fail = fail
        self.step = step

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int, timeout_seconds: int) -> list[BTCLiveMarketCandle]:
        if self.fail:
            raise RuntimeError("network unavailable")
        return [
            BTCLiveMarketCandle(
                timestamp=f"2026-01-01T00:{i % 60:02d}:00+00:00",
                open=100.0 + i * self.step,
                high=101.0 + i * self.step,
                low=99.0 + i * self.step,
                close=100.0 + i * self.step,
                volume=1.0,
            )
            for i in range(self.candles)
        ]


def _engine(tmp_path: Path, adapter: _Adapter | None = None) -> BTCLiveMarketFeedEngine:
    return BTCLiveMarketFeedEngine(repo_root=tmp_path, market_data_adapter=adapter or _Adapter(), now_provider=lambda: "2026-01-01T00:00:00+00:00")


def test_default_repo_live_market_feed_config_validates_pass() -> None:
    report = BTCLiveMarketFeedEngine().validate()

    assert report.status == "PASS"
    assert report.config is not None
    assert report.config.feed_enabled is False
    assert report.config.allow_public_market_data_fetch is True


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("dry_run_only", False, "dry_run_only"),
        ("allow_private_api", True, "allow_private_api"),
        ("allow_api_key_usage", True, "allow_api_key_usage"),
        ("allow_trading_api", True, "allow_trading_api"),
        ("allow_account_data", True, "allow_account_data"),
        ("allow_balance_fetch", True, "allow_balance_fetch"),
        ("allow_position_fetch", True, "allow_position_fetch"),
        ("allow_order_submission", True, "allow_order_submission"),
        ("allow_order_cancellation", True, "allow_order_cancellation"),
        ("allow_position_creation", True, "allow_position_creation"),
        ("allow_paper_trade_persistence", True, "allow_paper_trade_persistence"),
        ("allow_executable_trade_creation", True, "allow_executable_trade_creation"),
        ("allow_state_mutation", True, "allow_state_mutation"),
        ("symbol", "ETH/USDT", "symbol"),
        ("exchange", "kraken", "exchange"),
        ("primary_timeframe", "5m", "primary_timeframe"),
        ("confirmation_timeframe", "4h", "confirmation_timeframe"),
        ("strategy_profile", "research_baseline", "strategy_profile"),
        ("status_export_dir", "../outside", "status_export_dir"),
    ],
)
def test_dangerous_live_market_feed_config_fails(tmp_path: Path, field: str, value: Any, issue: str) -> None:
    path = _write_live_configs(tmp_path, live={field: value})

    report = _engine(tmp_path).validate(str(path))

    assert report.status == "FAIL"
    assert issue in {item.name for item in report.issues}


def test_dependency_failures_block_live_market_feed_config(tmp_path: Path) -> None:
    cases = [
        ("runtime", {"runtime": {"live_trading_enabled": True}}, "runtime_config_validation"),
        ("monitoring", {"monitoring": {"live_trading_expected": True}}, "monitoring_config_validation"),
        ("runner", {"runner": {"allow_order_submission": True}}, "runner_config_validation"),
        ("signal", {"signal": {"allow_order_submission": True}}, "signal_config_validation"),
        ("candidate", {"candidate": {"allow_order_submission": True}}, "trade_candidate_config_validation"),
        ("journal", {"journal": {"allow_order_submission": True}}, "candidate_journal_config_validation"),
        ("kill", {"runtime": {"kill_switch_enabled": False}}, "kill_switch_enabled"),
    ]
    for name, kwargs, expected_issue in cases:
        root = tmp_path / name
        if name == "signal":
            kwargs["signal"] = _signal_config(root, allow_order_submission=True)
        path = _write_live_configs(root, **kwargs)
        report = _engine(root).validate(str(path))
        assert expected_issue in {issue.name for issue in report.issues}


def test_fetch_once_with_mocked_public_adapter_returns_pass_and_safe_flags(tmp_path: Path) -> None:
    path = _write_live_configs(tmp_path)

    result = _engine(tmp_path).fetch_once(str(path))

    assert result.status == "PASS"
    assert result.primary_candles == 100
    assert result.confirmation_candles == 100
    assert result.public_market_data_fetch_used is True
    assert result.private_api_used is False
    assert result.api_key_used is False
    assert result.trading_api_used is False
    assert result.account_data_used is False
    assert result.order_submitted is False
    assert result.exchange_connected_for_trading is False


def test_fetch_once_adapter_failure_returns_safe_fail(tmp_path: Path) -> None:
    path = _write_live_configs(tmp_path)

    result = _engine(tmp_path, _Adapter(fail=True)).fetch_once(str(path))

    assert result.status == "FAIL"
    assert "public_market_data_fetch_failed" in {issue.name for issue in result.issues}
    assert result.private_api_used is False
    assert result.order_submitted is False
    assert result.exchange_connected_for_trading is False


def test_observe_once_low_score_is_warning_and_non_executable(tmp_path: Path) -> None:
    path = _write_live_configs(tmp_path, live={"allow_journal_write": False})

    result = _engine(tmp_path, _Adapter(step=0.001)).observe_once(str(path))

    assert result.status == "WARNING"
    assert result.candidate_created is False
    assert result.journal_entry_written is False
    assert result.executable_trade_created is False
    assert result.paper_trade_persisted is False
    assert result.position_created is False
    assert result.order_submitted is False
    assert result.order_cancelled is False
    assert result.exchange_connected_for_trading is False
    assert result.state_mutated is False


def test_observe_once_approved_candidate_is_still_non_executable_and_can_journal(tmp_path: Path) -> None:
    path = _write_live_configs(tmp_path)

    result = _engine(tmp_path, _Adapter(step=2.0)).observe_once(str(path), journal=True)

    journal_path = tmp_path / "reports" / "live_market_feed" / "btc_live_market_observations.jsonl"
    assert result.status == "PASS"
    assert result.candidate_created is True
    assert result.journal_entry_written is True
    assert journal_path.exists()
    assert result.executable_trade_created is False
    assert result.paper_trade_persisted is False
    assert result.position_created is False
    assert result.order_submitted is False
    assert result.state_mutated is False


def test_observe_once_no_journal_suppresses_journal_write(tmp_path: Path) -> None:
    path = _write_live_configs(tmp_path)

    result = _engine(tmp_path, _Adapter(step=2.0)).observe_once(str(path), journal=False)

    assert result.status == "PASS"
    assert result.journal_entry_written is False
    assert not (tmp_path / "reports" / "live_market_feed" / "btc_live_market_observations.jsonl").exists()
