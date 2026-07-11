from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.diagnostics.btc_futures_paper_position_engine import BTCFuturesPaperPositionEngine
from models.btc_futures_read_only_feed import (
    BTCFuturesFundingInfo,
    BTCFuturesMarkPrice,
    BTCFuturesReadOnlyFeedResult,
    BTCFuturesReadOnlyFeedStatus,
)
from tests.test_btc_futures_risk_model_engine import _write_json, _write_risk_configs


def _paper_position_config(**overrides) -> dict[str, Any]:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "exchange_symbol": "BTCUSDT",
        "exchange": "binance",
        "market_type": "futures",
        "futures_contract_type": "USDT_PERPETUAL",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "futures_read_only_feed_config_path": "configs/btc_futures_read_only_feed.json",
        "futures_risk_model_config_path": "configs/btc_futures_risk_model.json",
        "spot_paper_account_config_path": "configs/btc_paper_account.json",
        "position_simulation_enabled": False,
        "simulation_only": True,
        "dry_run_only": True,
        "margin_mode": "isolated",
        "position_mode": "one_way",
        "max_open_positions": 1,
        "allowed_leverage": [1, 2, 3, 5],
        "default_leverage": 2,
        "max_leverage": 5,
        "initial_account_balance": 10000.0,
        "account_currency": "USDT",
        "default_notional": 1000.0,
        "min_notional": 10.0,
        "max_notional_pct_of_equity": 100.0,
        "max_initial_margin_pct_of_equity": 20.0,
        "minimum_risk_reward": 1.5,
        "max_daily_realized_loss_pct": 2.0,
        "max_account_drawdown_pct": 5.0,
        "max_trades_per_day": 3,
        "taker_fee_rate": 0.0004,
        "liquidation_fee_rate": 0.002,
        "default_funding_periods": 1,
        "require_risk_model_pass": True,
        "require_stop_before_liquidation": True,
        "require_stop_loss": True,
        "require_take_profit": True,
        "auto_close_on_stop_loss": True,
        "auto_close_on_take_profit": True,
        "auto_close_on_simulated_liquidation": True,
        "liquidation_trigger_precedence": True,
        "closed_position_retention_in_state": 0,
        "allow_public_mark_price_fetch": True,
        "allow_public_funding_fetch": True,
        "allow_local_futures_state_write": True,
        "allow_local_futures_ledger_write": True,
        "allow_local_virtual_order_creation": True,
        "allow_local_paper_futures_position_creation": True,
        "allow_local_mark_to_market": True,
        "allow_local_funding_application": True,
        "allow_local_position_close": True,
        "allow_local_simulated_liquidation": True,
        "allow_local_futures_state_reset": True,
        "allow_private_api": False,
        "allow_api_key_usage": False,
        "allow_trading_api": False,
        "allow_account_data": False,
        "allow_balance_fetch": False,
        "allow_position_fetch": False,
        "allow_real_order_submission": False,
        "allow_order_cancellation": False,
        "allow_real_position_creation": False,
        "allow_exchange_paper_position_creation": False,
        "allow_testnet_order_submission": False,
        "allow_exchange_leverage_change": False,
        "allow_exchange_margin_mode_change": False,
        "allow_spot_paper_account_state_mutation": False,
        "allow_runner_state_mutation": False,
        "allow_execution_state_mutation": False,
        "allow_exchange_state_mutation": False,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_futures_feed_config_pass": True,
        "require_futures_risk_model_config_pass": True,
        "require_spot_paper_account_config_pass": True,
        "require_kill_switch_enabled": True,
        "state_path": "reports/futures_paper_position/state.json",
        "ledger_path": "reports/futures_paper_position/ledger.jsonl",
        "report_export_dir": "reports/futures_paper_position",
        "lock_path": "reports/futures_paper_position/state.lock",
        "state_lock_timeout_seconds": 1,
    }
    values.update(overrides)
    return values


def _write_configs(tmp_path: Path, **overrides) -> Path:
    _write_risk_configs(tmp_path)
    path = tmp_path / "configs" / "btc_futures_paper_position.json"
    _write_json(path, _paper_position_config(**overrides))
    return path


class _FakeFuturesFeedEngine:
    def validate(self, *args, **kwargs):
        from models.btc_futures_read_only_feed import BTCFuturesReadOnlyValidationReport

        return BTCFuturesReadOnlyValidationReport(status="PASS")

    def fetch_once(self, *args, **kwargs):
        return BTCFuturesReadOnlyFeedResult(
            status=BTCFuturesReadOnlyFeedStatus.PASS.value,
            primary_latest_close=64000.0,
            mark_price=BTCFuturesMarkPrice(symbol="BTCUSDT", mark_price=65000.0, funding_rate=0.0001),
            funding_info=BTCFuturesFundingInfo(symbol="BTCUSDT", funding_rate=0.0001),
            public_futures_mark_price_fetch_used=True,
            public_futures_funding_fetch_used=True,
        )


def _engine(tmp_path: Path) -> BTCFuturesPaperPositionEngine:
    return BTCFuturesPaperPositionEngine(repo_root=tmp_path, futures_feed_engine=_FakeFuturesFeedEngine(), now_provider=lambda: "2026-01-01T00:00:00+00:00")


def _open_long(engine: BTCFuturesPaperPositionEngine, path: Path):
    engine.initialize(str(path))
    return engine.open_position("LONG", 64000.0, 64000.0, 62000.0, 67000.0, 1000.0, 3, "open-1", str(path))


def test_default_repo_config_validates_pass() -> None:
    report = BTCFuturesPaperPositionEngine().validate()

    assert report.status == "PASS"
    assert report.config is not None
    assert report.config.position_simulation_enabled is False


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("position_simulation_enabled", False, None),
        ("simulation_only", False, "simulation_only"),
        ("dry_run_only", False, "dry_run_only"),
        ("margin_mode", "cross", "margin_mode"),
        ("position_mode", "hedge", "position_mode"),
        ("max_open_positions", 2, "max_open_positions"),
        ("max_leverage", 10, "max_leverage"),
        ("allowed_leverage", [1, 10], "allowed_leverage"),
        ("default_leverage", 4, "default_leverage"),
        ("initial_account_balance", 0, "initial_account_balance"),
        ("taker_fee_rate", -1, "taker_fee_rate"),
        ("state_path", "../state.json", "state_path"),
        ("ledger_path", "../ledger.jsonl", "ledger_path"),
        ("lock_path", "../state.lock", "lock_path"),
        ("report_export_dir", "../reports", "report_export_dir"),
        ("allow_private_api", True, "allow_private_api"),
        ("allow_api_key_usage", True, "allow_api_key_usage"),
        ("allow_trading_api", True, "allow_trading_api"),
        ("allow_account_data", True, "allow_account_data"),
        ("allow_balance_fetch", True, "allow_balance_fetch"),
        ("allow_position_fetch", True, "allow_position_fetch"),
        ("allow_real_order_submission", True, "allow_real_order_submission"),
        ("allow_order_cancellation", True, "allow_order_cancellation"),
        ("allow_real_position_creation", True, "allow_real_position_creation"),
        ("allow_exchange_paper_position_creation", True, "allow_exchange_paper_position_creation"),
        ("allow_testnet_order_submission", True, "allow_testnet_order_submission"),
        ("allow_exchange_leverage_change", True, "allow_exchange_leverage_change"),
        ("allow_exchange_margin_mode_change", True, "allow_exchange_margin_mode_change"),
        ("allow_spot_paper_account_state_mutation", True, "allow_spot_paper_account_state_mutation"),
        ("allow_runner_state_mutation", True, "allow_runner_state_mutation"),
        ("allow_execution_state_mutation", True, "allow_execution_state_mutation"),
        ("allow_exchange_state_mutation", True, "allow_exchange_state_mutation"),
        ("symbol", "ETH/USDT", "symbol"),
        ("exchange_symbol", "ETHUSDT", "exchange_symbol"),
        ("market_type", "spot", "market_type"),
        ("futures_contract_type", "COIN_PERP", "futures_contract_type"),
    ],
)
def test_config_validation_safety_rules(tmp_path: Path, field: str, value: Any, issue: str | None) -> None:
    path = _write_configs(tmp_path, **{field: value})

    report = _engine(tmp_path).validate(str(path))

    if issue is None:
        assert report.status == "PASS"
    else:
        assert report.status == "FAIL"
        assert issue in {item.name for item in report.issues}


def test_status_initialize_and_ledger(tmp_path: Path) -> None:
    path = _write_configs(tmp_path)
    engine = _engine(tmp_path)

    before = engine.status(str(path))
    init = engine.initialize(str(path))
    second = engine.initialize(str(path))
    summary = engine.ledger_summary(str(path))

    assert before.decision == "STATE_MISSING"
    assert init.status == "PASS"
    assert init.account_state is not None
    assert init.account_state.wallet_balance == 10000.0
    assert init.ledger_written is True
    assert second.decision == "STATE_ALREADY_INITIALIZED"
    assert summary.initialized_events == 1


def test_open_mark_funding_and_manual_close_updates_account(tmp_path: Path) -> None:
    path = _write_configs(tmp_path)
    engine = _engine(tmp_path)
    opened = _open_long(engine, path)
    marked = engine.mark_to_market(65000.0, "mark-1", str(path))
    funded = engine.apply_funding(0.0001, 1, "funding-1", str(path))
    closed = engine.close_position(66000.0, "MANUAL", "close-1", str(path))
    summary = engine.ledger_summary(str(path))

    assert opened.status == "PASS"
    assert opened.local_virtual_order_created is True
    assert opened.local_paper_futures_position_created is True
    assert opened.account_state is not None
    assert opened.account_state.wallet_balance == pytest.approx(9999.6)
    assert opened.account_state.margin_used == pytest.approx(333.333333)
    assert marked.position is not None
    assert marked.position.unrealized_pnl == pytest.approx(15.625)
    assert funded.local_funding_applied is True
    assert funded.account_state is not None
    assert funded.account_state.funding_pnl < 0
    assert closed.local_position_closed is True
    assert closed.account_state is not None
    assert closed.account_state.open_position is None
    assert closed.account_state.margin_used == 0
    assert closed.position is not None
    assert closed.position.realized_pnl == pytest.approx(31.25)
    assert summary.position_opened_events == 1
    assert summary.mark_events == 1
    assert summary.funding_events == 1
    assert summary.manual_close_events == 1


def test_short_mark_to_market_and_take_profit(tmp_path: Path) -> None:
    path = _write_configs(tmp_path)
    engine = _engine(tmp_path)
    engine.initialize(str(path))
    opened = engine.open_position("SHORT", 64000.0, 64000.0, 66000.0, 61000.0, 1000.0, 3, "short-open", str(path))
    marked = engine.mark_to_market(63000.0, "short-mark", str(path))
    closed = engine.mark_to_market(61000.0, "short-tp", str(path))

    assert opened.status == "PASS"
    assert marked.position is not None
    assert marked.position.unrealized_pnl > 0
    assert closed.decision == "POSITION_CLOSED_TAKE_PROFIT"
    assert closed.position is not None
    assert closed.position.status == "TAKE_PROFIT"


def test_stop_loss_liquidation_duplicate_and_reset(tmp_path: Path) -> None:
    path = _write_configs(tmp_path)
    engine = _engine(tmp_path)
    _open_long(engine, path)
    duplicate = engine.mark_to_market(65000.0, "same", str(path))
    duplicate_again = engine.mark_to_market(65100.0, "same", str(path))
    stopped = engine.mark_to_market(62000.0, "stop", str(path))
    reset_without_force = engine.reset(str(path), force=False)
    reset = engine.reset(str(path), force=True)

    assert duplicate.status == "PASS"
    assert duplicate_again.decision == "DUPLICATE_ACTION"
    assert stopped.decision == "POSITION_CLOSED_STOP_LOSS"
    assert reset_without_force.status == "WARNING"
    assert reset.decision == "RESET_COMPLETED"


def test_simulated_liquidation_precedence_and_lifecycle_are_local_only(tmp_path: Path) -> None:
    path = _write_configs(tmp_path)
    engine = _engine(tmp_path)
    opened = _open_long(engine, path)
    liq_price = opened.position.estimated_liquidation_price if opened.position else 43000
    liquidated = engine.mark_to_market(liq_price - 10, "liq", str(path))
    lifecycle = engine.simulate_lifecycle(str(path))

    assert liquidated.decision == "POSITION_LIQUIDATED_SIMULATED"
    assert liquidated.local_simulated_liquidation_applied is True
    assert lifecycle.status == "PASS"
    assert lifecycle.state_written is False
    assert lifecycle.ledger_written is False
    assert lifecycle.metadata["persistent_state_used"] is False


def test_live_mark_failure_does_not_mutate_state(tmp_path: Path) -> None:
    class FailingFeed(_FakeFuturesFeedEngine):
        def fetch_once(self, *args, **kwargs):
            return BTCFuturesReadOnlyFeedResult(status="FAIL", public_futures_mark_price_fetch_used=True)

    path = _write_configs(tmp_path)
    engine = BTCFuturesPaperPositionEngine(repo_root=tmp_path, futures_feed_engine=FailingFeed(), now_provider=lambda: "2026-01-01T00:00:00+00:00")
    _open_long(engine, path)
    before = json.loads((tmp_path / "reports" / "futures_paper_position" / "state.json").read_text(encoding="utf-8"))
    result = engine.mark_to_market_live("live-mark", str(path))
    after = json.loads((tmp_path / "reports" / "futures_paper_position" / "state.json").read_text(encoding="utf-8"))

    assert result.status == "FAIL"
    assert before == after
    assert result.private_api_used is False
    assert result.exchange_state_mutated is False


def test_all_unsafe_flags_remain_false(tmp_path: Path) -> None:
    path = _write_configs(tmp_path)
    engine = _engine(tmp_path)
    result = _open_long(engine, path)

    for name in (
        "private_api_used",
        "api_key_used",
        "trading_api_used",
        "account_data_used",
        "balance_fetch_used",
        "position_fetch_used",
        "real_order_submitted",
        "order_cancelled",
        "real_position_created",
        "exchange_paper_position_created",
        "testnet_order_submitted",
        "exchange_leverage_changed",
        "exchange_margin_mode_changed",
        "spot_paper_account_state_mutated",
        "runner_state_mutated",
        "execution_state_mutated",
        "exchange_state_mutated",
    ):
        assert getattr(result, name) is False
