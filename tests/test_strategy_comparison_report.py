from __future__ import annotations

from models.strategy_comparison import StrategyComparisonReport, StrategyComparisonRow
from reporting.strategy_comparison_report import format_strategy_comparison_report


def _report() -> StrategyComparisonReport:
    report = StrategyComparisonReport(
        fixture="tests/fixtures/btcusdt_100_candles.json",
        min_candles=50,
        strategies=[
            StrategyComparisonRow(
                "recent_50|fixed_1_5r|min_rr=1.5|dir=auto_trend|trend_fallback=block",
                strategy_profile="balanced_smc",
                direction_mode="auto_trend",
                auto_trend_fallback="block",
                regime_lookback=50,
                regime_threshold_pct=0.01,
                regime_fallback="all",
                total_trades=10,
                wins=5,
                losses=5,
                win_rate=50.0,
                net_pnl=500.984,
                average_pnl=50.098,
                max_drawdown=596.444,
                profit_factor=1.234,
                long_pnl=-368,
                short_pnl=868.984,
                duplicate_signals_skipped=106,
                fast_losses=1,
                no_followthrough_losses=2,
                high_rr_losses=3,
                next_candle_continuation=4,
                next_candle_rejection=5,
                elapsed_seconds=12.345,
            )
        ],
    )
    report.populate_best_fields()
    return report


def test_report_includes_header() -> None:
    output = format_strategy_comparison_report(_report())

    assert "===== STRATEGY COMPARISON REPORT =====" in output


def test_report_includes_best_section() -> None:
    output = format_strategy_comparison_report(_report())

    assert "Best:" in output
    assert "Net PnL      : recent_50|fixed_1_5r|min_rr=1.5|dir=auto_trend|trend_fallback=block" in output


def test_report_includes_comparison_table() -> None:
    output = format_strategy_comparison_report(_report())

    assert "Comparison Table:" in output
    assert "Rank | Strategy | Profile | DR Mode | Exit | MinRR | Dir | DQ | LongPreset | TrendFB" in output
    assert "balanced_smc" in output
    assert "Regime | Lookback | Thr | RegimeFB" in output
    assert "off" in output
    assert "none" in output
    assert "Elapsed" in output
    assert "auto_trend" in output
    assert "block" in output
    assert "rolling_return" in output
    assert "50" in output


def test_report_includes_diagnostics_table() -> None:
    output = format_strategy_comparison_report(_report())

    assert "Diagnostics Table:" in output
    assert "FastLoss | NoFTLoss | HighRRLoss" in output


def test_report_rounds_floats_to_two_decimals() -> None:
    output = format_strategy_comparison_report(_report())

    assert "500.98" in output
    assert "50.10" in output
    assert "596.44" in output
    assert "1.23" in output
    assert "12.35" in output


def test_report_displays_long_and_short_pnl() -> None:
    output = format_strategy_comparison_report(_report())

    assert "-368" in output
    assert "868.98" in output
