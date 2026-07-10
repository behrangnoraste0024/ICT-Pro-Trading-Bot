from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.diagnostics.btc_futures_read_only_feed_engine import BTCFuturesReadOnlyFeedEngine
from models.btc_futures_read_only_feed import BTCFuturesFundingInfo, BTCFuturesMarkPrice, BTCFuturesReadOnlyCandle
from tests.test_btc_paper_account_engine import _write_account_configs


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _futures_config(**overrides) -> dict[str, Any]:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "exchange": "binance",
        "market_type": "futures",
        "futures_contract_type": "USDT_PERPETUAL",
        "exchange_symbol": "BTCUSDT",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "live_market_feed_config_path": "configs/btc_live_market_feed.json",
        "paper_account_config_path": "configs/btc_paper_account.json",
        "primary_timeframe": "15m",
        "confirmation_timeframe": "1h",
        "primary_limit": 500,
        "confirmation_limit": 500,
        "closed_candles_only": True,
        "dry_run_only": True,
        "feed_enabled": False,
        "allow_public_futures_market_data_fetch": True,
        "allow_public_futures_mark_price_fetch": True,
        "allow_public_futures_funding_fetch": True,
        "allow_private_api": False,
        "allow_api_key_usage": False,
        "allow_trading_api": False,
        "allow_account_data": False,
        "allow_balance_fetch": False,
        "allow_position_fetch": False,
        "allow_order_submission": False,
        "allow_order_cancellation": False,
        "allow_real_position_creation": False,
        "allow_paper_position_creation": False,
        "allow_leverage": False,
        "allow_leverage_simulation": False,
        "allow_liquidation_modeling": False,
        "allow_paper_trade_persistence": False,
        "allow_executable_trade_creation": False,
        "allow_runner_state_mutation": False,
        "allow_execution_state_mutation": False,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_live_market_feed_config_pass": True,
        "require_paper_account_config_pass": True,
        "require_kill_switch_enabled": True,
        "request_timeout_seconds": 10,
        "max_fetch_retries": 1,
        "min_primary_candles": 100,
        "min_confirmation_candles": 100,
        "observation_mode": "fetch_once",
        "status_export_dir": "reports/futures_read_only_feed",
    }
    values.update(overrides)
    return values


def _write_futures_configs(tmp_path: Path, *, futures: dict[str, Any] | None = None, **kwargs) -> Path:
    _write_account_configs(tmp_path, **kwargs)
    path = tmp_path / "configs" / "btc_futures_read_only_feed.json"
    _write_json(path, _futures_config(**(futures or {})))
    return path


class _Adapter:
    def __init__(self, *, candle_fail: bool = False, funding_fail: bool = False, mark_fail: bool = False, candles: int = 101) -> None:
        self.candle_fail = candle_fail
        self.funding_fail = funding_fail
        self.mark_fail = mark_fail
        self.candles = candles

    def fetch_ohlcv(self, exchange_symbol: str, timeframe: str, limit: int, timeout_seconds: int) -> list[BTCFuturesReadOnlyCandle]:
        if self.candle_fail:
            raise RuntimeError("network unavailable")
        return [
            BTCFuturesReadOnlyCandle(
                timestamp=f"2026-01-01T00:{i % 60:02d}:00+00:00",
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.0 + i,
                volume=1.0,
            )
            for i in range(self.candles)
        ]

    def fetch_mark_price(self, exchange_symbol: str, timeout_seconds: int) -> BTCFuturesMarkPrice:
        if self.mark_fail:
            raise RuntimeError("mark unavailable")
        return BTCFuturesMarkPrice(symbol=exchange_symbol, mark_price=101.5, index_price=101.4, funding_rate=0.0001, next_funding_time="2026-01-01T08:00:00+00:00")

    def fetch_funding_info(self, exchange_symbol: str, timeout_seconds: int) -> BTCFuturesFundingInfo:
        if self.funding_fail:
            raise RuntimeError("funding unavailable")
        return BTCFuturesFundingInfo(symbol=exchange_symbol, funding_rate=0.0001, funding_time="2026-01-01T00:00:00+00:00")


def _engine(tmp_path: Path, adapter: _Adapter | None = None) -> BTCFuturesReadOnlyFeedEngine:
    return BTCFuturesReadOnlyFeedEngine(repo_root=tmp_path, market_data_adapter=adapter or _Adapter(), now_provider=lambda: "2026-01-01T00:00:00+00:00")


def test_default_repo_futures_read_only_config_validates_pass() -> None:
    report = BTCFuturesReadOnlyFeedEngine().validate()

    assert report.status == "PASS"
    assert report.config is not None
    assert report.config.feed_enabled is False


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("dry_run_only", False, "dry_run_only"),
        ("market_type", "spot", "market_type"),
        ("futures_contract_type", "COIN_PERPETUAL", "futures_contract_type"),
        ("allow_private_api", True, "allow_private_api"),
        ("allow_api_key_usage", True, "allow_api_key_usage"),
        ("allow_trading_api", True, "allow_trading_api"),
        ("allow_account_data", True, "allow_account_data"),
        ("allow_balance_fetch", True, "allow_balance_fetch"),
        ("allow_position_fetch", True, "allow_position_fetch"),
        ("allow_order_submission", True, "allow_order_submission"),
        ("allow_order_cancellation", True, "allow_order_cancellation"),
        ("allow_real_position_creation", True, "allow_real_position_creation"),
        ("allow_paper_position_creation", True, "allow_paper_position_creation"),
        ("allow_leverage", True, "allow_leverage"),
        ("allow_leverage_simulation", True, "allow_leverage_simulation"),
        ("allow_liquidation_modeling", True, "allow_liquidation_modeling"),
        ("allow_paper_trade_persistence", True, "allow_paper_trade_persistence"),
        ("allow_executable_trade_creation", True, "allow_executable_trade_creation"),
        ("allow_runner_state_mutation", True, "allow_runner_state_mutation"),
        ("allow_execution_state_mutation", True, "allow_execution_state_mutation"),
        ("symbol", "ETH/USDT", "symbol"),
        ("exchange_symbol", "ETHUSDT", "exchange_symbol"),
        ("exchange", "kraken", "exchange"),
        ("primary_timeframe", "5m", "primary_timeframe"),
        ("confirmation_timeframe", "4h", "confirmation_timeframe"),
        ("strategy_profile", "research_baseline", "strategy_profile"),
        ("status_export_dir", "../outside", "status_export_dir"),
    ],
)
def test_dangerous_futures_config_fails(tmp_path: Path, field: str, value: Any, issue: str) -> None:
    path = _write_futures_configs(tmp_path, futures={field: value})

    report = _engine(tmp_path).validate(str(path))

    assert report.status == "FAIL"
    assert issue in {item.name for item in report.issues}


def test_dependency_failures_block_futures_config(tmp_path: Path) -> None:
    cases = [
        ("runtime", {"runtime": {"live_trading_enabled": True}}, "runtime_config_validation"),
        ("monitoring", {"monitoring": {"live_trading_expected": True}}, "monitoring_config_validation"),
        ("runner", {"runner": {"allow_order_submission": True}}, "runner_config_validation"),
        ("live", {"live": {"allow_order_submission": True}}, "live_market_feed_config_validation"),
        ("account", {"account": {"allow_real_order_submission": True}}, "paper_account_config_validation"),
        ("kill", {"runtime": {"kill_switch_enabled": False}}, "kill_switch_enabled"),
    ]
    for name, kwargs, expected_issue in cases:
        root = tmp_path / name
        path = _write_futures_configs(root, **kwargs)
        report = _engine(root).validate(str(path))
        assert expected_issue in {issue.name for issue in report.issues}


def test_fetch_once_with_mocked_public_adapter_returns_pass_and_safe_flags(tmp_path: Path) -> None:
    path = _write_futures_configs(tmp_path)

    result = _engine(tmp_path).fetch_once(str(path))

    assert result.status == "PASS"
    assert result.primary_candles == 100
    assert result.confirmation_candles == 100
    assert result.mark_price is not None
    assert result.funding_info is not None
    assert result.public_futures_market_data_fetch_used is True
    assert result.private_api_used is False
    assert result.api_key_used is False
    assert result.trading_api_used is False
    assert result.account_data_used is False
    assert result.balance_fetch_used is False
    assert result.position_fetch_used is False
    assert result.order_submitted is False
    assert result.order_cancelled is False
    assert result.real_position_created is False
    assert result.paper_position_created is False
    assert result.leverage_used is False
    assert result.leverage_simulation_used is False
    assert result.liquidation_modeling_used is False
    assert result.executable_trade_created is False
    assert result.exchange_connected_for_trading is False
    assert result.runner_state_mutated is False
    assert result.execution_state_mutated is False


def test_fetch_once_funding_unavailable_returns_warning(tmp_path: Path) -> None:
    path = _write_futures_configs(tmp_path)

    result = _engine(tmp_path, _Adapter(funding_fail=True)).fetch_once(str(path))

    assert result.status == "WARNING"
    assert result.mark_price is not None
    assert "public_futures_funding_fetch_failed" in {issue.name for issue in result.issues}


def test_fetch_once_candle_failure_returns_safe_fail(tmp_path: Path) -> None:
    path = _write_futures_configs(tmp_path)

    result = _engine(tmp_path, _Adapter(candle_fail=True)).fetch_once(str(path))

    assert result.status == "FAIL"
    assert "public_futures_market_data_fetch_failed" in {issue.name for issue in result.issues}
    assert result.private_api_used is False
    assert result.order_submitted is False
    assert result.leverage_used is False


def test_observe_once_is_read_only_and_never_invokes_futures_trade_pipeline(tmp_path: Path) -> None:
    path = _write_futures_configs(tmp_path)

    result = _engine(tmp_path).observe_once(str(path))

    assert result.status == "PASS"
    assert result.paper_position_created is False
    assert result.leverage_used is False
    assert result.leverage_simulation_used is False
    assert result.liquidation_modeling_used is False
    assert result.private_api_used is False
    assert result.api_key_used is False
    assert result.trading_api_used is False
    assert result.account_data_used is False
    assert result.order_submitted is False
    assert result.order_cancelled is False
    assert result.real_position_created is False
    assert result.exchange_connected_for_trading is False
    assert result.runner_state_mutated is False
    assert result.execution_state_mutated is False
    assert result.metadata["futures_trade_pipeline_invoked"] is False
