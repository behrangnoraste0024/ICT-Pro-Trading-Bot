from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.diagnostics.btc_futures_risk_model_engine import BTCFuturesRiskModelEngine
from models.btc_futures_read_only_feed import (
    BTCFuturesFundingInfo,
    BTCFuturesMarkPrice,
    BTCFuturesReadOnlyFeedResult,
    BTCFuturesReadOnlyFeedStatus,
)
from models.btc_futures_risk_model import BTCFuturesRiskScenarioInput
from tests.test_btc_futures_read_only_feed_engine import _write_futures_configs


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _risk_config(**overrides) -> dict[str, Any]:
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
        "paper_account_config_path": "configs/btc_paper_account.json",
        "risk_model_enabled": False,
        "simulation_only": True,
        "dry_run_only": True,
        "model_name": "simplified_isolated_linear_v1",
        "model_accuracy": "APPROXIMATE_CONSERVATIVE",
        "exchange_exact_liquidation": False,
        "margin_mode": "isolated",
        "position_mode": "one_way",
        "allowed_leverage": [1, 2, 3, 5],
        "default_leverage": 2,
        "max_leverage": 5,
        "default_scenario_side": "LONG",
        "default_notional": 1000.0,
        "default_stop_loss_distance_pct": 2.0,
        "default_take_profit_distance_pct": 3.0,
        "maintenance_margin_rate": 0.004,
        "liquidation_fee_reserve_rate": 0.002,
        "additional_safety_buffer_rate": 0.005,
        "min_liquidation_distance_pct": 5.0,
        "warning_liquidation_distance_pct": 10.0,
        "max_initial_margin_pct_of_account_equity": 20.0,
        "max_notional_pct_of_account_equity": 100.0,
        "allow_public_futures_market_data_fetch": True,
        "allow_public_mark_price_fetch": True,
        "allow_public_funding_fetch": True,
        "allow_leverage_simulation": True,
        "allow_liquidation_modeling": True,
        "allow_margin_calculation": True,
        "allow_funding_estimation": True,
        "allow_scenario_comparison": True,
        "allow_real_leverage_change": False,
        "allow_exchange_margin_mode_change": False,
        "allow_private_api": False,
        "allow_api_key_usage": False,
        "allow_trading_api": False,
        "allow_account_data": False,
        "allow_balance_fetch": False,
        "allow_position_fetch": False,
        "allow_order_submission": False,
        "allow_order_cancellation": False,
        "allow_real_position_creation": False,
        "allow_paper_futures_position_creation": False,
        "allow_paper_trade_persistence": False,
        "allow_executable_trade_creation": False,
        "allow_paper_account_state_mutation": False,
        "allow_runner_state_mutation": False,
        "allow_execution_state_mutation": False,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_futures_feed_config_pass": True,
        "require_paper_account_config_pass": True,
        "require_kill_switch_enabled": True,
        "funding_periods_to_estimate": 3,
        "report_export_dir": "reports/futures_risk_model",
    }
    values.update(overrides)
    return values


def _write_risk_configs(tmp_path: Path, *, risk: dict[str, Any] | None = None, **kwargs) -> Path:
    _write_futures_configs(tmp_path, **kwargs)
    path = tmp_path / "configs" / "btc_futures_risk_model.json"
    _write_json(path, _risk_config(**(risk or {})))
    return path


class _FakeFuturesFeedEngine:
    def __init__(self, status: str = "PASS") -> None:
        self.status = status

    def validate(self, *args, **kwargs):
        from models.btc_futures_read_only_feed import BTCFuturesReadOnlyValidationReport

        return BTCFuturesReadOnlyValidationReport(status=self.status)

    def fetch_once(self, *args, **kwargs) -> BTCFuturesReadOnlyFeedResult:
        return BTCFuturesReadOnlyFeedResult(
            status=BTCFuturesReadOnlyFeedStatus.PASS.value,
            primary_latest_close=64000.0,
            primary_candles=499,
            mark_price=BTCFuturesMarkPrice(symbol="BTCUSDT", mark_price=63800.0, funding_rate=0.0001),
            funding_info=BTCFuturesFundingInfo(symbol="BTCUSDT", funding_rate=0.0001),
            public_futures_market_data_fetch_used=True,
        )


def _engine(tmp_path: Path, feed: _FakeFuturesFeedEngine | None = None) -> BTCFuturesRiskModelEngine:
    return BTCFuturesRiskModelEngine(repo_root=tmp_path, futures_feed_engine=feed or _FakeFuturesFeedEngine(), now_provider=lambda: "2026-01-01T00:00:00+00:00")


def _scenario(**overrides) -> BTCFuturesRiskScenarioInput:
    values = {"side": "LONG", "entry_price": 64000.0, "mark_price": 63800.0, "stop_loss": 62000.0, "take_profit": 67000.0, "notional_value": 1000.0, "leverage": 3, "account_equity": 10000.0, "funding_rate": 0.0001, "funding_periods": 3, "source": "test"}
    values.update(overrides)
    return BTCFuturesRiskScenarioInput(**values)


def test_default_repo_risk_model_config_validates_pass() -> None:
    report = BTCFuturesRiskModelEngine().validate()

    assert report.status == "PASS"
    assert report.config is not None
    assert report.config.risk_model_enabled is False


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("simulation_only", False, "simulation_only"),
        ("dry_run_only", False, "dry_run_only"),
        ("exchange_exact_liquidation", True, "exchange_exact_liquidation"),
        ("model_accuracy", "EXACT", "model_accuracy"),
        ("margin_mode", "cross", "margin_mode"),
        ("position_mode", "hedge", "position_mode"),
        ("max_leverage", 10, "max_leverage"),
        ("allowed_leverage", [0, 2], "allowed_leverage"),
        ("default_leverage", 4, "default_leverage"),
        ("allow_real_leverage_change", True, "allow_real_leverage_change"),
        ("allow_exchange_margin_mode_change", True, "allow_exchange_margin_mode_change"),
        ("allow_private_api", True, "allow_private_api"),
        ("allow_api_key_usage", True, "allow_api_key_usage"),
        ("allow_trading_api", True, "allow_trading_api"),
        ("allow_account_data", True, "allow_account_data"),
        ("allow_balance_fetch", True, "allow_balance_fetch"),
        ("allow_position_fetch", True, "allow_position_fetch"),
        ("allow_order_submission", True, "allow_order_submission"),
        ("allow_order_cancellation", True, "allow_order_cancellation"),
        ("allow_real_position_creation", True, "allow_real_position_creation"),
        ("allow_paper_futures_position_creation", True, "allow_paper_futures_position_creation"),
        ("allow_paper_trade_persistence", True, "allow_paper_trade_persistence"),
        ("allow_executable_trade_creation", True, "allow_executable_trade_creation"),
        ("allow_paper_account_state_mutation", True, "allow_paper_account_state_mutation"),
        ("allow_runner_state_mutation", True, "allow_runner_state_mutation"),
        ("allow_execution_state_mutation", True, "allow_execution_state_mutation"),
        ("symbol", "ETH/USDT", "symbol"),
        ("exchange_symbol", "ETHUSDT", "exchange_symbol"),
        ("market_type", "spot", "market_type"),
        ("futures_contract_type", "COIN_PERP", "futures_contract_type"),
        ("report_export_dir", "../bad", "report_export_dir"),
    ],
)
def test_dangerous_risk_model_config_fails(tmp_path: Path, field: str, value: Any, issue: str) -> None:
    path = _write_risk_configs(tmp_path, risk={field: value})

    report = _engine(tmp_path).validate(str(path))

    assert report.status == "FAIL"
    assert issue in {item.name for item in report.issues}


def test_dependency_failures_block_risk_model_config(tmp_path: Path) -> None:
    cases = [
        ("runtime", {"runtime": {"live_trading_enabled": True}}, "runtime_config_validation"),
        ("monitoring", {"monitoring": {"live_trading_expected": True}}, "monitoring_config_validation"),
        ("runner", {"runner": {"allow_order_submission": True}}, "runner_config_validation"),
        ("feed", {}, "futures_feed_config_validation"),
        ("account", {"account": {"allow_real_order_submission": True}}, "paper_account_config_validation"),
        ("kill", {"runtime": {"kill_switch_enabled": False}}, "kill_switch_enabled"),
    ]
    for name, kwargs, expected_issue in cases:
        root = tmp_path / name
        path = _write_risk_configs(root, **kwargs)
        feed = _FakeFuturesFeedEngine(status="FAIL") if name == "feed" else _FakeFuturesFeedEngine()
        report = _engine(root, feed).validate(str(path))
        assert expected_issue in {issue.name for issue in report.issues}


@pytest.mark.parametrize("leverage", [1, 2, 3, 5])
def test_long_scenario_calculates_margin_and_liquidation_below_entry(tmp_path: Path, leverage: int) -> None:
    path = _write_risk_configs(tmp_path)

    result = _engine(tmp_path).analyze_scenario(_scenario(leverage=leverage), str(path))

    assert result.calculation is not None
    assert result.calculation.quantity == pytest.approx(1000.0 / 64000.0)
    assert result.calculation.initial_margin == pytest.approx(1000.0 / leverage)
    assert result.calculation.estimated_liquidation_price < 64000.0
    assert result.exchange_exact_liquidation is False
    assert result.model_accuracy == "APPROXIMATE_CONSERVATIVE"


def test_short_scenario_calculates_liquidation_above_entry_and_pnl(tmp_path: Path) -> None:
    path = _write_risk_configs(tmp_path)

    result = _engine(tmp_path).analyze_scenario(_scenario(side="SHORT", mark_price=64200.0, stop_loss=66000.0, take_profit=61000.0), str(path))

    assert result.calculation is not None
    assert result.calculation.estimated_liquidation_price > 64000.0
    assert result.calculation.unrealized_pnl_at_mark == pytest.approx((64000.0 - 64200.0) * (1000.0 / 64000.0))


def test_formula_outputs_and_funding_direction(tmp_path: Path) -> None:
    path = _write_risk_configs(tmp_path)

    long_positive = _engine(tmp_path).analyze_scenario(_scenario(funding_rate=0.0001), str(path)).calculation
    short_positive = _engine(tmp_path).analyze_scenario(_scenario(side="SHORT", mark_price=64200, stop_loss=66000, take_profit=61000, funding_rate=0.0001), str(path)).calculation
    long_negative = _engine(tmp_path).analyze_scenario(_scenario(funding_rate=-0.0001), str(path)).calculation
    short_negative = _engine(tmp_path).analyze_scenario(_scenario(side="SHORT", mark_price=64200, stop_loss=66000, take_profit=61000, funding_rate=-0.0001), str(path)).calculation

    assert long_positive is not None
    assert long_positive.maintenance_margin_at_mark == pytest.approx((1000 / 64000) * 63800 * 0.004)
    assert long_positive.liquidation_fee_reserve_at_mark == pytest.approx((1000 / 64000) * 63800 * 0.002)
    assert long_positive.funding_payment_per_period == pytest.approx(-0.1)
    assert long_positive.total_funding_estimate == pytest.approx(-0.3)
    assert short_positive is not None and short_positive.funding_payment_per_period == pytest.approx(0.1)
    assert long_negative is not None and long_negative.funding_payment_per_period == pytest.approx(0.1)
    assert short_negative is not None and short_negative.funding_payment_per_period == pytest.approx(-0.1)


@pytest.mark.parametrize(
    "scenario",
    [
        _scenario(leverage=9),
        _scenario(side="BAD"),
        _scenario(entry_price=0),
        _scenario(notional_value=0),
        _scenario(account_equity=0),
        _scenario(stop_loss=65000),
        _scenario(take_profit=63000),
        _scenario(side="SHORT", stop_loss=63000, take_profit=61000),
        _scenario(side="SHORT", stop_loss=66000, take_profit=65000),
    ],
)
def test_invalid_scenarios_fail(tmp_path: Path, scenario: BTCFuturesRiskScenarioInput) -> None:
    path = _write_risk_configs(tmp_path)

    result = _engine(tmp_path).analyze_scenario(scenario, str(path))

    assert result.status == "FAIL"


def test_risk_decision_rejections_and_warning(tmp_path: Path) -> None:
    margin_path = _write_risk_configs(tmp_path / "margin", risk={"max_initial_margin_pct_of_account_equity": 1.0})
    notional_path = _write_risk_configs(tmp_path / "notional", risk={"max_notional_pct_of_account_equity": 1.0})
    rr_path = _write_risk_configs(tmp_path / "rr")
    warning_path = _write_risk_configs(tmp_path / "warning", risk={"warning_liquidation_distance_pct": 90.0})

    margin = _engine(tmp_path / "margin").analyze_scenario(_scenario(), str(margin_path))
    notional = _engine(tmp_path / "notional").analyze_scenario(_scenario(), str(notional_path))
    bad_rr = _engine(tmp_path / "rr").analyze_scenario(_scenario(take_profit=65000), str(rr_path))
    warning = _engine(tmp_path / "warning").analyze_scenario(_scenario(), str(warning_path))

    assert margin.decision == "REJECT_MARGIN_LIMIT"
    assert notional.decision == "REJECT_NOTIONAL_LIMIT"
    assert bad_rr.decision == "REJECT_INVALID_RISK_REWARD"
    assert warning.status == "WARNING"


def test_safe_scenario_returns_pass_and_unsafe_flags_false(tmp_path: Path) -> None:
    path = _write_risk_configs(tmp_path)

    result = _engine(tmp_path).analyze_scenario(_scenario(), str(path))

    assert result.status == "PASS"
    assert result.private_api_used is False
    assert result.api_key_used is False
    assert result.trading_api_used is False
    assert result.account_data_used is False
    assert result.balance_fetch_used is False
    assert result.position_fetch_used is False
    assert result.exchange_leverage_changed is False
    assert result.exchange_margin_mode_changed is False
    assert result.order_submitted is False
    assert result.order_cancelled is False
    assert result.real_position_created is False
    assert result.paper_futures_position_created is False
    assert result.paper_trade_persisted is False
    assert result.executable_trade_created is False
    assert result.paper_account_state_mutated is False
    assert result.runner_state_mutated is False
    assert result.execution_state_mutated is False


def test_compare_leverage_rows_and_selection(tmp_path: Path) -> None:
    path = _write_risk_configs(tmp_path)

    result = _engine(tmp_path).compare_leverage(_scenario(leverage=1), str(path))

    assert [row.leverage for row in result.rows] == [1, 2, 3, 5]
    assert result.safest_leverage == 1
    assert result.highest_accepted_leverage in {1, 2, 3, 5}
    assert result.to_dict()["rows"][0]["leverage"] == 1


def test_analyze_live_uses_mocked_public_futures_data_only(tmp_path: Path) -> None:
    path = _write_risk_configs(tmp_path)

    result = _engine(tmp_path).analyze_live(side="LONG", notional=1000, account_equity=10000, leverage=3, config_path=str(path))

    assert result.public_market_data_used is True
    assert result.metadata["futures_feed_invoked"] is True
    assert result.metadata["futures_trade_pipeline_invoked"] is False
    assert result.metadata["paper_account_invoked"] is False
    assert result.paper_futures_position_created is False
    assert result.order_submitted is False
    assert result.exchange_leverage_changed is False


def test_analyze_live_public_fetch_failure_returns_safe_fail(tmp_path: Path) -> None:
    path = _write_risk_configs(tmp_path)

    class _FailFeed(_FakeFuturesFeedEngine):
        def fetch_once(self, *args, **kwargs):
            return BTCFuturesReadOnlyFeedResult(status="FAIL", public_futures_market_data_fetch_used=True)

    result = _engine(tmp_path, _FailFeed()).analyze_live(side="LONG", notional=1000, account_equity=10000, leverage=3, config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "DATA_FETCH_FAILED"
    assert result.order_submitted is False
