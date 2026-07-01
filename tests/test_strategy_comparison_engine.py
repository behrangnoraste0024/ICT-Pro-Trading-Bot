from __future__ import annotations

from models.entry_followthrough_diagnostics import EntryFollowthroughDiagnostics
from models.rolling_backtest_result import RollingBacktestResult
from models.sl_tp_outcome_diagnostics import SLTPOutcomeDiagnostics
from models.strategy_comparison import StrategyComparisonReport, StrategyComparisonRow, StrategyConfigSpec
from models.trade_outcome_diagnostics import TradeOutcomeDiagnostics, TradeOutcomeRecord
from engine.backtest.strategy_comparison_engine import (
    StrategyComparisonEngine,
    build_default_strategy_specs,
    build_exit_modes_recent_50_specs,
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
    return result


def test_strategy_config_spec_string_contains_modes() -> None:
    spec = StrategyConfigSpec("recent", "recent_50", "fixed_1_5r", 1.5)

    assert str(spec) == "recent_50|fixed_1_5r|min_rr=1.5"


def test_strategy_comparison_row_string_contains_name_and_pnl() -> None:
    row = StrategyComparisonRow("recent_50|fixed_1_5r|min_rr=1.5", rank=1, total_trades=10, net_pnl=500.98)

    assert "#1 recent_50|fixed_1_5r|min_rr=1.5" in str(row)
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


def test_run_single_strategy_returns_expected_fixture_fields() -> None:
    row = StrategyComparisonEngine().run_single_strategy(
        FIXTURE_PATH,
        StrategyConfigSpec("recent_50|fixed_1_5r|min_rr=1.5", "recent_50", "fixed_1_5r", 1.5),
        min_candles=50,
    )

    assert row.strategy_name == "recent_50|fixed_1_5r|min_rr=1.5"
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

    assert "recent_50|fixed_1_5r|min_rr=1.5" in names


def test_exit_modes_recent_50_specs_include_fixed_modes() -> None:
    exit_modes = {spec.exit_mode for spec in build_exit_modes_recent_50_specs()}

    assert {"fixed_1r", "fixed_1_5r", "fixed_2r", "fixed_3r"}.issubset(exit_modes)


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
    spec = StrategyConfigSpec("recent_50|fixed_1_5r|min_rr=1.5", "recent_50", "fixed_1_5r", 1.5)
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
