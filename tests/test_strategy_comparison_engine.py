from __future__ import annotations

import pytest

from models.cost_diagnostics import CostDiagnostics
from models.decision_filter_simulation import DecisionFilterBucket, DecisionFilterSimulationResult
from models.entry_followthrough_diagnostics import EntryFollowthroughDiagnostics
from models.rolling_backtest_result import RollingBacktestResult
from models.regime_direction_diagnostics import RegimeDirectionDiagnostics
from models.sl_tp_outcome_diagnostics import SLTPOutcomeDiagnostics
from models.strategy_comparison import StrategyComparisonReport, StrategyComparisonRow, StrategyConfigSpec
from models.trade_outcome_diagnostics import TradeOutcomeDiagnostics, TradeOutcomeRecord
import engine.backtest.strategy_comparison_engine as strategy_module
from engine.backtest.strategy_comparison_engine import (
    StrategyComparisonEngine,
    build_decision_gate_profile_with_cost_specs,
    build_direction_modes_recent_50_fixed_1_5r_specs,
    build_default_strategy_specs,
    build_exit_modes_recent_50_specs,
    build_long_strict_recent_50_fixed_1_5r_specs,
    build_recommended_profile_specs,
    build_recommended_profile_with_cost_specs,
    build_regime_direction_recent_50_fixed_1_5r_specs,
    build_trend_direction_recent_50_fixed_1_5r_specs,
    direction_quality_preset_config,
)


FIXTURE_PATH = "tests/fixtures/btcusdt_100_candles.json"


def _result_with_trades() -> RollingBacktestResult:
    result = RollingBacktestResult(
        total_windows=10,
        processed_windows=8,
        skipped_windows=2,
        failed_windows=0,
        min_candles=5,
        total_paper_trades=3,
        closed_trades=3,
        open_trades=0,
        wins=2,
        losses=1,
        win_rate=66.67,
        net_pnl=150,
        average_pnl=50,
        max_drawdown=25,
        ignored_contexts=0,
        opened_trades=3,
        duplicate_signals_skipped=4,
    )
    result.trade_outcome_diagnostics = TradeOutcomeDiagnostics(
        trades=[
            TradeOutcomeRecord(1, "LONG", "PAPER_CLOSED_TP", pnl=100, result="WIN"),
            TradeOutcomeRecord(2, "SHORT", "PAPER_CLOSED_SL", pnl=-50, result="LOSS"),
            TradeOutcomeRecord(3, "SHORT", "PAPER_CLOSED_TP", pnl=100, result="WIN"),
        ],
        total_trades=3,
        closed_trades=3,
        wins=2,
        losses=1,
        win_rate=66.67,
        net_pnl=150,
        average_pnl=50,
        average_win=100,
        average_loss=-50,
        largest_win=100,
        largest_loss=-50,
        average_rr=1.5,
        average_setup_score=90,
    )
    result.sl_tp_outcome_diagnostics = SLTPOutcomeDiagnostics(
        total_trades=3,
        fast_loss_count=1,
        no_follow_through_loss_count=2,
        high_rr_loss_count=1,
    )
    result.entry_followthrough_diagnostics = EntryFollowthroughDiagnostics(
        total_trades=3,
        next_candle_continuation_count=2,
        next_candle_rejection_count=1,
    )
    result.regime_direction_diagnostics = RegimeDirectionDiagnostics(
        long_in_bearish_count=1,
        long_in_bearish_pnl=-25,
        short_in_bullish_count=2,
        short_in_bullish_pnl=-50,
    )
    return result


def _bucket(
    name: str,
    total_trades: int,
    wins: int,
    losses: int,
    gross_net_pnl: float,
    net_pnl_after_costs: float,
) -> DecisionFilterBucket:
    return DecisionFilterBucket(
        name=name,
        decision_values=[name.upper()],
        total_trades=total_trades,
        wins=wins,
        losses=losses,
        win_rate=round((wins / total_trades) * 100, 2) if total_trades else 0.0,
        gross_net_pnl=gross_net_pnl,
        total_cost=gross_net_pnl - net_pnl_after_costs,
        net_pnl_after_costs=net_pnl_after_costs,
        average_pnl=gross_net_pnl / total_trades if total_trades else 0.0,
        average_net_pnl_after_costs=net_pnl_after_costs / total_trades if total_trades else 0.0,
        max_drawdown=12.5,
        profit_factor=1.8,
        average_execution_quality=0.72,
        average_decision_score=0.81,
    )


def _result_with_decision_filter_buckets() -> RollingBacktestResult:
    result = _result_with_trades()
    result.decision_filter_simulation = DecisionFilterSimulationResult(
        buckets=[
            _bucket("all_trades", 3, 2, 1, 150, 132.5),
            _bucket("approve_only", 1, 1, 0, 90, 85),
            _bucket("warning_only", 1, 0, 1, -20, -22),
            _bucket("approve_or_warning", 2, 1, 1, 70, 63),
        ]
    )
    return result


def test_strategy_config_spec_string_contains_modes() -> None:
    spec = StrategyConfigSpec("recent", "recent_50", "fixed_1_5r", 1.5)

    assert str(spec) == "recent_50|fixed_1_5r|min_rr=1.5|dir=all"


def test_strategy_config_spec_string_includes_auto_trend_fallback() -> None:
    spec = StrategyConfigSpec("recent", "recent_50", "fixed_1_5r", 1.5, "auto_trend", "block")

    assert str(spec) == "recent_50|fixed_1_5r|min_rr=1.5|dir=auto_trend|trend_fallback=block"


def test_strategy_config_spec_string_includes_regime_fields() -> None:
    spec = StrategyConfigSpec(
        "recent",
        "recent_50",
        "fixed_1_5r",
        1.5,
        "regime_trend",
        "all",
        "rolling_return",
        50,
        0.01,
        "block",
    )

    assert str(spec) == (
        "recent_50|fixed_1_5r|min_rr=1.5|dir=regime_trend|"
        "regime=rolling_return|lookback=50|thr=0.01|regime_fb=block"
    )


def test_strategy_config_spec_string_includes_direction_quality_fields() -> None:
    spec = StrategyConfigSpec(
        "recent",
        "recent_50",
        "fixed_1_5r",
        1.5,
        direction_quality_mode="long_strict",
        strict_long_preset="regime_known_displacement",
    )

    assert str(spec) == (
        "recent_50|fixed_1_5r|min_rr=1.5|dir=all|"
        "dq=long_strict|long_preset=regime_known_displacement"
    )


def test_strategy_config_spec_string_includes_decision_filter_when_active() -> None:
    spec = StrategyConfigSpec(
        "recent",
        "recent_50",
        "fixed_1_5r",
        1.5,
        decision_filter_mode="approve_only",
    )

    assert str(spec) == "recent_50|fixed_1_5r|min_rr=1.5|dir=all|decision=approve_only"


def test_strategy_comparison_row_string_contains_name_and_pnl() -> None:
    row = StrategyComparisonRow("recent_50|fixed_1_5r|min_rr=1.5|dir=all", rank=1, total_trades=10, net_pnl=500.98)

    assert "#1 recent_50|fixed_1_5r|min_rr=1.5|dir=all" in str(row)
    assert "pnl=500.98" in str(row)


def test_strategy_report_sorted_by_net_pnl_descending() -> None:
    report = StrategyComparisonReport(
        fixture=FIXTURE_PATH,
        min_candles=50,
        strategies=[
            StrategyComparisonRow("low", net_pnl=-1),
            StrategyComparisonRow("high", net_pnl=10),
        ],
    )

    assert [row.strategy_name for row in report.sorted_by("net_pnl")] == ["high", "low"]


def test_strategy_report_sorted_by_net_pnl_after_costs_descending() -> None:
    report = StrategyComparisonReport(
        fixture=FIXTURE_PATH,
        min_candles=50,
        strategies=[
            StrategyComparisonRow("gross_high", net_pnl=10, net_pnl_after_costs=1),
            StrategyComparisonRow("net_high", net_pnl=5, net_pnl_after_costs=4),
        ],
    )

    assert [row.strategy_name for row in report.sorted_by("net_pnl_after_costs")] == ["net_high", "gross_high"]


def test_best_row_drawdown_prefers_lower() -> None:
    report = StrategyComparisonReport(
        fixture=FIXTURE_PATH,
        min_candles=50,
        strategies=[
            StrategyComparisonRow("wide", max_drawdown=100),
            StrategyComparisonRow("tight", max_drawdown=10),
        ],
    )

    assert report.best_row("max_drawdown", prefer_lower=True).strategy_name == "tight"


def test_profit_factor_handles_wins_and_losses() -> None:
    row = StrategyComparisonEngine().row_from_result(
        StrategyConfigSpec("spec", "recent_50", "fixed_1_5r", 1.5),
        _result_with_trades(),
    )

    assert row.profit_factor == 4
    assert row.average_loss == -50


def test_row_from_result_populates_cost_fields() -> None:
    result = _result_with_trades()
    result.cost_diagnostics = CostDiagnostics(
        cost_model="percent",
        commission_pct=0.0004,
        slippage_pct=0.0002,
        spread_pct=0.0001,
        total_trades=3,
        closed_trades=3,
        gross_net_pnl=150,
        total_commission_cost=10,
        total_slippage_cost=5,
        total_spread_cost=2.5,
        total_cost=17.5,
        net_pnl_after_costs=132.5,
        average_cost_per_trade=5.8333333333,
        average_net_pnl_after_costs=44.1666666667,
        cost_to_gross_profit_ratio=0.0875,
    )

    row = StrategyComparisonEngine().row_from_result(
        StrategyConfigSpec(
            "spec",
            "recent_50",
            "fixed_1_5r",
            1.5,
            cost_model="percent",
            commission_pct=0.0004,
            slippage_pct=0.0002,
            spread_pct=0.0001,
        ),
        result,
    )

    assert row.cost_model == "percent"
    assert row.gross_net_pnl == 150
    assert row.total_cost == 17.5
    assert row.net_pnl_after_costs == 132.5


def test_decision_filter_off_preserves_unfiltered_strategy_metrics() -> None:
    result = _result_with_decision_filter_buckets()

    row = StrategyComparisonEngine().row_from_result(
        StrategyConfigSpec("spec", "recent_50", "fixed_1_5r", 1.5, decision_filter_mode="off"),
        result,
    )

    assert row.decision_filter_mode == "off"
    assert row.decision_filtered is False
    assert row.decision_filter_bucket is None
    assert row.total_trades == result.total_paper_trades
    assert row.wins == result.wins
    assert row.losses == result.losses
    assert row.net_pnl == result.net_pnl


def test_approve_only_decision_filter_uses_approve_bucket_metrics() -> None:
    row = StrategyComparisonEngine().row_from_result(
        StrategyConfigSpec("spec", "recent_50", "fixed_1_5r", 1.5, decision_filter_mode="approve_only"),
        _result_with_decision_filter_buckets(),
    )

    assert row.decision_filtered is True
    assert row.decision_filter_bucket == "approve_only"
    assert row.total_trades == 1
    assert row.wins == 1
    assert row.losses == 0
    assert row.net_pnl == 90
    assert row.gross_net_pnl == 90
    assert row.total_cost == 5
    assert row.net_pnl_after_costs == 85
    assert row.average_execution_quality == 0.72
    assert row.average_decision_score == 0.81
    assert row.decision_score == 0.81


def test_warning_only_decision_filter_uses_warning_bucket_metrics() -> None:
    row = StrategyComparisonEngine().row_from_result(
        StrategyConfigSpec("spec", "recent_50", "fixed_1_5r", 1.5, decision_filter_mode="warning_only"),
        _result_with_decision_filter_buckets(),
    )

    assert row.decision_filter_bucket == "warning_only"
    assert row.total_trades == 1
    assert row.wins == 0
    assert row.losses == 1
    assert row.net_pnl_after_costs == -22


def test_approve_or_warning_decision_filter_uses_combined_bucket_metrics() -> None:
    row = StrategyComparisonEngine().row_from_result(
        StrategyConfigSpec("spec", "recent_50", "fixed_1_5r", 1.5, decision_filter_mode="approve_or_warning"),
        _result_with_decision_filter_buckets(),
    )

    assert row.decision_filter_bucket == "approve_or_warning"
    assert row.total_trades == 2
    assert row.wins == 1
    assert row.losses == 1
    assert row.net_pnl_after_costs == 63


def test_missing_decision_filter_simulation_falls_back_to_unfiltered_metrics() -> None:
    result = _result_with_trades()

    row = StrategyComparisonEngine().row_from_result(
        StrategyConfigSpec("spec", "recent_50", "fixed_1_5r", 1.5, decision_filter_mode="approve_only"),
        result,
    )

    assert row.decision_filter_mode == "approve_only"
    assert row.decision_filtered is False
    assert row.decision_filter_bucket is None
    assert row.total_trades == result.total_paper_trades
    assert row.net_pnl == result.net_pnl


def test_profit_factor_is_none_without_losses() -> None:
    result = _result_with_trades()
    result.trade_outcome_diagnostics.trades = [
        TradeOutcomeRecord(1, "LONG", "PAPER_CLOSED_TP", pnl=100, result="WIN")
    ]

    row = StrategyComparisonEngine().row_from_result(
        StrategyConfigSpec("spec", "recent_50", "fixed_1r", 1.0),
        result,
    )

    assert row.profit_factor is None


def test_profit_factor_is_none_without_trades() -> None:
    result = _result_with_trades()
    result.trade_outcome_diagnostics.trades = []

    row = StrategyComparisonEngine().row_from_result(
        StrategyConfigSpec("spec", "recent_50", "fixed_1r", 1.0),
        result,
    )

    assert row.profit_factor is None


def test_direction_pnl_extraction_from_records() -> None:
    row = StrategyComparisonEngine().row_from_result(
        StrategyConfigSpec("spec", "recent_50", "fixed_1_5r", 1.5),
        _result_with_trades(),
    )

    assert row.long_count == 1
    assert row.long_pnl == 100
    assert row.short_count == 2
    assert row.short_pnl == 50


def test_row_from_result_preserves_auto_trend_fallback() -> None:
    row = StrategyComparisonEngine().row_from_result(
        StrategyConfigSpec(
            "recent_50|fixed_1_5r|min_rr=1.5|dir=auto_trend|trend_fallback=block",
            "recent_50",
            "fixed_1_5r",
            1.5,
            "auto_trend",
            "block",
        ),
        _result_with_trades(),
    )

    assert row.direction_mode == "auto_trend"
    assert row.auto_trend_fallback == "block"


def test_row_from_result_preserves_regime_fields() -> None:
    row = StrategyComparisonEngine().row_from_result(
        StrategyConfigSpec(
            "recent_50|fixed_1_5r|min_rr=1.5|dir=regime_trend|regime=rolling_return|lookback=50|thr=0.01|regime_fb=block",
            "recent_50",
            "fixed_1_5r",
            1.5,
            "regime_trend",
            "all",
            "rolling_return",
            50,
            0.01,
            "block",
        ),
        _result_with_trades(),
    )

    assert row.direction_mode == "regime_trend"
    assert row.regime_lookback == 50
    assert row.regime_threshold_pct == 0.01
    assert row.regime_fallback == "block"


def test_row_from_result_preserves_direction_quality_fields() -> None:
    row = StrategyComparisonEngine().row_from_result(
        StrategyConfigSpec(
            "recent_50|fixed_1_5r|min_rr=1.5|dir=all|dq=long_strict|long_preset=displacement",
            "recent_50",
            "fixed_1_5r",
            1.5,
            direction_quality_mode="long_strict",
            strict_long_preset="displacement",
            strict_long_require_displacement=True,
        ),
        _result_with_trades(),
    )

    assert row.direction_quality_mode == "long_strict"
    assert row.strict_long_preset == "displacement"


def test_row_from_result_preserves_strategy_profile() -> None:
    row = StrategyComparisonEngine().row_from_result(
        StrategyConfigSpec(
            "profile=balanced_smc",
            "recent_50",
            "fixed_1_5r",
            1.5,
            strategy_profile="balanced_smc",
        ),
        _result_with_trades(),
    )

    assert row.strategy_profile == "balanced_smc"


def test_row_from_result_includes_regime_diagnostic_summary_fields() -> None:
    row = StrategyComparisonEngine().row_from_result(
        StrategyConfigSpec("spec", "recent_50", "fixed_1_5r", 1.5),
        _result_with_trades(),
    )

    assert row.long_in_bearish_count == 1
    assert row.long_in_bearish_pnl == -25
    assert row.short_in_bullish_count == 2
    assert row.short_in_bullish_pnl == -50


def test_run_single_strategy_returns_expected_fixture_fields() -> None:
    row = StrategyComparisonEngine().run_single_strategy(
        FIXTURE_PATH,
        StrategyConfigSpec("recent_50|fixed_1_5r|min_rr=1.5|dir=all", "recent_50", "fixed_1_5r", 1.5),
        min_candles=50,
    )

    assert row.strategy_name == "recent_50|fixed_1_5r|min_rr=1.5|dir=all"
    assert row.direction_mode == "all"
    assert row.total_windows == 100
    assert row.processed_windows == 51
    assert row.elapsed_seconds is not None


def test_run_comparison_returns_same_number_of_rows_as_specs() -> None:
    specs = [
        StrategyConfigSpec("one", "current_external", "original", 2.0),
        StrategyConfigSpec("two", "recent_50", "fixed_1r", 1.0),
    ]

    report = StrategyComparisonEngine().run_comparison(FIXTURE_PATH, specs, min_candles=50)

    assert len(report.strategies) == 2


def test_default_strategy_specs_include_recent_50_fixed_1_5r() -> None:
    names = [spec.name for spec in build_default_strategy_specs()]

    assert "recent_50|fixed_1_5r|min_rr=1.5|dir=all" in names


def test_exit_modes_recent_50_specs_include_fixed_modes() -> None:
    exit_modes = {spec.exit_mode for spec in build_exit_modes_recent_50_specs()}
    direction_modes = {spec.direction_mode for spec in build_exit_modes_recent_50_specs()}

    assert {"fixed_1r", "fixed_1_5r", "fixed_2r", "fixed_3r"}.issubset(exit_modes)
    assert direction_modes == {"all"}


def test_direction_modes_recent_50_fixed_1_5r_specs_include_all_modes() -> None:
    specs = build_direction_modes_recent_50_fixed_1_5r_specs()

    assert [spec.direction_mode for spec in specs] == ["all", "long_only", "short_only"]
    assert all(spec.dealing_range_mode == "recent_50" for spec in specs)
    assert all(spec.exit_mode == "fixed_1_5r" for spec in specs)
    assert all(spec.min_risk_reward == 1.5 for spec in specs)


def test_trend_direction_recent_50_fixed_1_5r_specs_include_auto_trend_fallbacks() -> None:
    specs = build_trend_direction_recent_50_fixed_1_5r_specs()

    assert len(specs) == 5
    assert [spec.direction_mode for spec in specs] == ["all", "short_only", "long_only", "auto_trend", "auto_trend"]
    assert [spec.auto_trend_fallback for spec in specs[-2:]] == ["all", "block"]
    assert "dir=auto_trend|trend_fallback=all" in specs[-2].name
    assert "dir=auto_trend|trend_fallback=block" in specs[-1].name


def test_regime_direction_recent_50_fixed_1_5r_specs_include_regime_variants() -> None:
    specs = build_regime_direction_recent_50_fixed_1_5r_specs()

    assert len(specs) == 9
    assert [spec.direction_mode for spec in specs[:4]] == ["all", "short_only", "long_only", "auto_trend"]
    assert all(spec.direction_mode == "regime_trend" for spec in specs[4:])
    assert [spec.regime_lookback for spec in specs[4:7]] == [100, 200, 300]
    assert specs[-1].regime_fallback == "block"


def test_long_strict_recent_50_fixed_1_5r_specs_include_required_variants() -> None:
    specs = build_long_strict_recent_50_fixed_1_5r_specs()

    assert len(specs) == 10
    assert specs[0].direction_mode == "all"
    assert specs[0].direction_quality_mode == "off"
    assert specs[1].direction_mode == "short_only"
    assert specs[1].direction_quality_mode == "off"
    assert all(spec.direction_quality_mode == "long_strict" for spec in specs[2:])
    assert "dq=long_strict|long_preset=regime_known" in specs[2].name
    assert "dq=long_strict|long_preset=regime_bullish_displacement_score100" in specs[-1].name
    assert specs[-1].strict_long_require_regime_bullish is True
    assert specs[-1].strict_long_require_displacement is True
    assert specs[-1].strict_long_min_setup_score == 100


def test_recommended_profile_specs_include_expected_profiles() -> None:
    specs = build_recommended_profile_specs()

    assert len(specs) == 4
    assert [spec.strategy_profile for spec in specs] == [
        "balanced_smc",
        "bearish_smc",
        "research_baseline",
        "default",
    ]
    assert [spec.name for spec in specs] == [
        "profile=balanced_smc",
        "profile=bearish_smc",
        "profile=research_baseline",
        "profile=default",
    ]
    assert specs[0].dealing_range_mode == "recent_50"
    assert specs[0].direction_quality_mode == "long_strict"
    assert specs[0].strict_long_require_regime_known is True
    assert specs[0].strict_long_require_displacement is True
    assert specs[1].direction_mode == "short_only"
    assert specs[2].direction_mode == "all"
    assert specs[2].direction_quality_mode == "off"
    assert specs[3].dealing_range_mode == "current_external"
    assert specs[3].exit_mode == "original"


def test_recommended_profile_with_cost_specs_exist() -> None:
    specs = build_recommended_profile_with_cost_specs()

    assert [spec.name for spec in specs] == [
        "profile=balanced_smc",
        "profile=balanced_smc|cost=percent",
        "profile=bearish_smc",
        "profile=bearish_smc|cost=percent",
        "profile=research_baseline|cost=percent",
    ]
    assert specs[1].cost_model == "percent"
    assert specs[1].commission_pct == 0.0004
    assert specs[1].slippage_pct == 0.0002
    assert specs[1].spread_pct == 0.0001


def test_decision_gate_profile_with_cost_specs_exist() -> None:
    specs = build_decision_gate_profile_with_cost_specs()

    assert len(specs) == 10
    assert [spec.decision_filter_mode for spec in specs] == [
        "off",
        "approve_only",
        "approve_or_warning",
        "warning_only",
        "off",
        "approve_only",
        "approve_or_warning",
        "warning_only",
        "off",
        "approve_only",
    ]
    assert specs[1].name == "profile=balanced_smc|cost=percent|decision=approve_only"
    assert specs[7].strategy_profile == "bearish_smc"
    assert all(spec.cost_model == "percent" for spec in specs)
    assert all(spec.commission_pct == 0.0004 for spec in specs)


def test_direction_quality_preset_config_expands_long_strict_rules() -> None:
    config = direction_quality_preset_config("regime_known_displacement_score100")

    assert config["strict_long_require_regime_known"] is True
    assert config["strict_long_require_regime_bullish"] is False
    assert config["strict_long_require_displacement"] is True
    assert config["strict_long_min_setup_score"] == 100


def test_invalid_direction_quality_preset_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported strict long preset"):
        direction_quality_preset_config("moonshot")


def test_no_trades_strategy_row_does_not_crash() -> None:
    result = RollingBacktestResult(
        total_windows=1,
        processed_windows=1,
        skipped_windows=0,
        failed_windows=0,
        min_candles=1,
        total_paper_trades=0,
        closed_trades=0,
        open_trades=0,
        wins=0,
        losses=0,
        win_rate=0,
        net_pnl=0,
        average_pnl=0,
        max_drawdown=0,
        ignored_contexts=1,
    )

    row = StrategyComparisonEngine().row_from_result(StrategyConfigSpec("none", "current_external", "original", 2), result)

    assert row.total_trades == 0
    assert row.profit_factor is None


def test_fast_mode_still_returns_comparison_rows() -> None:
    spec = StrategyConfigSpec("recent_50|fixed_1r|min_rr=1.0", "recent_50", "fixed_1r", 1.0)

    report = StrategyComparisonEngine().run_comparison(
        FIXTURE_PATH,
        [spec],
        min_candles=50,
        enable_diagnostics=False,
    )

    assert len(report.strategies) == 1
    assert report.strategies[0].strategy_name == spec.name


def test_fast_mode_key_metrics_match_normal_fixture() -> None:
    spec = StrategyConfigSpec("recent_50|fixed_1_5r|min_rr=1.5|dir=all", "recent_50", "fixed_1_5r", 1.5)
    engine = StrategyComparisonEngine()

    normal = engine.run_single_strategy(FIXTURE_PATH, spec, min_candles=50)
    fast = engine.run_single_strategy(FIXTURE_PATH, spec, min_candles=50, enable_diagnostics=False)

    assert fast.total_trades == normal.total_trades
    assert fast.wins == normal.wins
    assert fast.losses == normal.losses
    assert fast.net_pnl == normal.net_pnl
    assert fast.max_drawdown == normal.max_drawdown
    assert fast.long_pnl == normal.long_pnl
    assert fast.short_pnl == normal.short_pnl


def test_progress_callback_receives_start_finish_and_rolling_events() -> None:
    events: list[str] = []
    spec = StrategyConfigSpec("recent_50|fixed_1r|min_rr=1.0", "recent_50", "fixed_1r", 1.0)

    StrategyComparisonEngine().run_comparison(
        FIXTURE_PATH,
        [spec],
        min_candles=50,
        progress_every=25,
        enable_diagnostics=False,
        progress_callback=lambda payload: events.append(payload["event"]),
    )

    assert "comparison_start" in events
    assert "strategy_start" in events
    assert "rolling_progress" in events
    assert "strategy_finish" in events


def test_run_comparison_passes_direction_quality_config_to_engine(monkeypatch) -> None:
    captured_configs = []

    class FakeRollingBacktestEngine:
        def __init__(self, *args, config, **kwargs):
            captured_configs.append(config)

        def run(self, candles):
            return RollingBacktestResult(
                total_windows=1,
                processed_windows=1,
                skipped_windows=0,
                failed_windows=0,
                min_candles=1,
                total_paper_trades=0,
                closed_trades=0,
                open_trades=0,
                wins=0,
                losses=0,
                win_rate=0,
                net_pnl=0,
                average_pnl=0,
                max_drawdown=0,
                ignored_contexts=1,
            )

    monkeypatch.setattr(strategy_module, "RollingBacktestEngine", FakeRollingBacktestEngine)
    spec = StrategyConfigSpec(
        "recent_50|fixed_1_5r|min_rr=1.5|dir=all|dq=long_strict|long_preset=regime_bullish_displacement_score100",
        "recent_50",
        "fixed_1_5r",
        1.5,
        direction_quality_mode="long_strict",
        strict_long_preset="regime_bullish_displacement_score100",
        strict_long_require_regime_bullish=True,
        strict_long_require_displacement=True,
        strict_long_min_setup_score=100,
    )

    StrategyComparisonEngine().run_comparison(FIXTURE_PATH, [spec], min_candles=50)

    assert captured_configs[0].direction_quality_mode == "long_strict"
    assert captured_configs[0].strict_long_require_regime_bullish is True
    assert captured_configs[0].strict_long_require_displacement is True
    assert captured_configs[0].strict_long_min_setup_score == 100


def test_run_comparison_passes_strategy_profile_config_to_engine(monkeypatch) -> None:
    captured_configs = []

    class FakeRollingBacktestEngine:
        def __init__(self, *args, config, **kwargs):
            captured_configs.append(config)

        def run(self, candles):
            return RollingBacktestResult(
                total_windows=1,
                processed_windows=1,
                skipped_windows=0,
                failed_windows=0,
                min_candles=1,
                total_paper_trades=0,
                closed_trades=0,
                open_trades=0,
                wins=0,
                losses=0,
                win_rate=0,
                net_pnl=0,
                average_pnl=0,
                max_drawdown=0,
                ignored_contexts=1,
            )

    monkeypatch.setattr(strategy_module, "RollingBacktestEngine", FakeRollingBacktestEngine)

    StrategyComparisonEngine().run_comparison(FIXTURE_PATH, [build_recommended_profile_specs()[0]], min_candles=50)

    assert captured_configs[0].strategy_profile == "balanced_smc"
    assert captured_configs[0].dealing_range_mode == "recent_50"
    assert captured_configs[0].direction_quality_mode == "long_strict"


def test_run_comparison_passes_decision_filter_mode_to_engine(monkeypatch) -> None:
    captured_configs = []

    class FakeRollingBacktestEngine:
        def __init__(self, *args, config, **kwargs):
            captured_configs.append(config)

        def run(self, candles):
            return RollingBacktestResult(
                total_windows=1,
                processed_windows=1,
                skipped_windows=0,
                failed_windows=0,
                min_candles=1,
                total_paper_trades=0,
                closed_trades=0,
                open_trades=0,
                wins=0,
                losses=0,
                win_rate=0,
                net_pnl=0,
                average_pnl=0,
                max_drawdown=0,
                ignored_contexts=1,
            )

    monkeypatch.setattr(strategy_module, "RollingBacktestEngine", FakeRollingBacktestEngine)
    spec = StrategyConfigSpec(
        "profile=balanced_smc|cost=percent|decision=approve_only",
        "recent_50",
        "fixed_1_5r",
        1.5,
        strategy_profile="balanced_smc",
        cost_model="percent",
        decision_filter_mode="approve_only",
    )

    StrategyComparisonEngine().run_comparison(FIXTURE_PATH, [spec], min_candles=50)

    assert captured_configs[0].decision_filter_mode == "approve_only"
