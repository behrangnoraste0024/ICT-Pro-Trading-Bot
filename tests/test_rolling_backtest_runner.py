from __future__ import annotations

import importlib
from pathlib import Path

from models.backtest_diagnostics import BacktestDiagnostics
from models.dealing_range_diagnostics import DealingRangeDiagnostics
from models.entry_followthrough_diagnostics import (
    EntryFollowthroughDiagnostics,
    EntryFollowthroughHorizon,
    EntryFollowthroughRecord,
)
from models.ote_diagnostics import OTEDiagnostics
from models.range_candidate_diagnostics import RangeCandidateDiagnostics, RangeCandidateStats
from models.rolling_backtest_result import RollingBacktestResult
from models.sl_tp_outcome_diagnostics import SLTPOutcomeDiagnostics, SLTPOutcomeRecord
from models.trade_outcome_diagnostics import TradeOutcomeDiagnostics, TradeOutcomeRecord
from models.virtual_exit_diagnostics import (
    VirtualExitDiagnostics,
    VirtualExitPolicyResult,
    VirtualExitPolicySummary,
    VirtualExitRecord,
)
from reporting.rolling_backtest_report import format_rolling_backtest_report
from scripts.run_rolling_backtest import main


FIXTURE_PATH = "tests/fixtures/btcusdt_100_candles.json"


def _result() -> RollingBacktestResult:
    return RollingBacktestResult(
        total_windows=100,
        processed_windows=51,
        skipped_windows=49,
        failed_windows=0,
        min_candles=50,
        total_paper_trades=5,
        closed_trades=4,
        open_trades=1,
        wins=3,
        losses=1,
        win_rate=75.0,
        net_pnl=25.0,
        average_pnl=6.25,
        max_drawdown=5.0,
        ignored_contexts=46,
    )


def _result_with_diagnostics() -> RollingBacktestResult:
    candidate_stats = {
        name: RangeCandidateStats(candidate_name=name)
        for name in [
            "CURRENT_EXTERNAL_RANGE",
            "RECENT_50_CANDLE_RANGE",
            "RECENT_100_CANDLE_RANGE",
            "RECENT_200_CANDLE_RANGE",
            "RECENT_SWING_RANGE",
        ]
    }
    candidate_stats["RECENT_50_CANDLE_RANGE"].candidate_aligned_zone_count = 2
    candidate_stats["RECENT_50_CANDLE_RANGE"].in_ote_count = 1
    candidate_stats["RECENT_50_CANDLE_RANGE"].candidate_fix_wrong_zone_count = 3
    result = _result()
    result.diagnostics = BacktestDiagnostics(
        setup_blockers={"A": 1, "B": 3},
        entry_blockers={},
        trade_plan_blockers={},
        trade_quality_blockers={},
        paper_trade_blockers={},
        setup_status_counts={"INVALID": 2},
        entry_status_counts={"NOT_CONFIRMED": 2},
        trade_plan_status_counts={"NO_TRADE": 2},
        trade_quality_status_counts={"REJECTED": 2},
        paper_trade_status_counts={"NO_PAPER_TRADE": 2},
        ote_diagnostics=OTEDiagnostics(
            windows_analyzed=2,
            ote_available_count=2,
            in_ote_count=1,
            not_in_ote_count=1,
            near_ote_0_5_pct_count=1,
            average_distance_to_ote=2.5,
            median_distance_to_ote=2.5,
            max_distance_to_ote=5,
            premium_count=1,
            discount_count=1,
            bullish_ote_count=1,
            bearish_ote_count=1,
            average_distance_to_equilibrium=1.5,
            median_distance_to_equilibrium=1.5,
            max_distance_to_equilibrium=3,
            near_equilibrium_0_5_pct_count=1,
        ),
        dealing_range_diagnostics=DealingRangeDiagnostics(
            windows_analyzed=2,
            range_available_count=2,
            average_range_size=20,
            median_range_size=20,
            min_range_size=10,
            max_range_size=30,
            average_range_size_percent=0.2,
            median_range_size_percent=0.2,
            min_range_size_percent=0.1,
            max_range_size_percent=0.3,
            premium_count=1,
            discount_count=1,
            uptrend_count=1,
            downtrend_count=1,
            trend_zone_counts={"DOWNTREND|DISCOUNT": 3, "UPTREND|PREMIUM": 1},
            ote_direction_zone_counts={"BEARISH|DISCOUNT": 3, "BULLISH|PREMIUM": 1},
            bearish_ote_discount_count=3,
            bullish_ote_premium_count=1,
            downtrend_discount_count=3,
            uptrend_premium_count=1,
            average_distance_to_equilibrium=5,
            median_distance_to_equilibrium=5,
            max_distance_to_equilibrium=8,
            average_distance_to_equilibrium_percent=0.05,
            median_distance_to_equilibrium_percent=0.05,
            max_distance_to_equilibrium_percent=0.08,
            average_external_high_age=12,
            average_external_low_age=10,
            max_external_high_age=20,
            max_external_low_age=15,
        ),
        range_candidate_diagnostics=RangeCandidateDiagnostics(windows_analyzed=2, candidates=candidate_stats),
        windows_analyzed=2,
    )
    return result


def _result_with_trade_outcomes() -> RollingBacktestResult:
    result = _result()
    result.trade_outcome_diagnostics = TradeOutcomeDiagnostics(
        trades=[
            TradeOutcomeRecord(
                trade_number=1,
                direction="LONG",
                status="PAPER_CLOSED_TP",
                entry_price=100,
                stop_loss=90,
                take_profit=120,
                exit_price=120,
                pnl=20,
                result="WIN",
                risk_reward=2,
                setup_score=80,
                entry_trigger_type="CONFIRMATION",
                current_price_zone="DISCOUNT",
                in_ote_zone=True,
                matched_poi_count=1,
                matched_poi_types=["ORDER_BLOCK"],
            )
        ],
        total_trades=1,
        closed_trades=1,
        wins=1,
        net_pnl=20,
        average_pnl=20,
        win_rate=100,
    )
    result.sl_tp_outcome_diagnostics = SLTPOutcomeDiagnostics(
        records=[
            SLTPOutcomeRecord(
                trade_number=1,
                direction="LONG",
                result="WIN",
                bars_held=3,
                mae_r=0.2,
                mfe_r=2,
                tp_progress=1,
                sl_progress=0.2,
            )
        ],
        total_trades=1,
        closed_trades=1,
        wins=1,
        average_bars_held=3,
        average_mae_r=0.2,
        average_mfe_r=2,
        average_tp_progress=1,
        average_sl_progress=0.2,
        reached_25_pct_tp_count=1,
        reached_50_pct_tp_count=1,
        reached_75_pct_tp_count=1,
        reached_25_pct_sl_count=0,
        reached_50_pct_sl_count=0,
        reached_75_pct_sl_count=0,
        average_mfe_r_winners=2,
        average_mae_r_winners=0.2,
        long_win_count=1,
    )
    result.entry_followthrough_diagnostics = EntryFollowthroughDiagnostics(
        records=[
            EntryFollowthroughRecord(
                trade_number=1,
                direction="LONG",
                result="WIN",
                entry_trigger_type="CONFIRMATION_CANDLE",
                next_candle_available=True,
                next_candle_continuation=True,
                horizons={
                    1: EntryFollowthroughHorizon(horizon=1, available=True, favorable_r=0.5, adverse_r=0.1),
                    3: EntryFollowthroughHorizon(horizon=3, available=True, favorable_r=1.0, adverse_r=0.2),
                },
                immediate_favorable=True,
                strong_followthrough_3=True,
            )
        ],
        total_trades=1,
        closed_trades=1,
        wins=1,
        next_candle_available_count=1,
        next_candle_continuation_count=1,
        immediate_favorable_count=1,
        strong_followthrough_3_count=1,
        average_h1_favorable_r=0.5,
        average_h1_adverse_r=0.1,
        average_h3_favorable_r=1.0,
        average_h3_adverse_r=0.2,
        winners_average_h3_favorable_r=1.0,
        winners_next_candle_continuation_count=1,
        trigger_counts={"CONFIRMATION_CANDLE": 1},
        trigger_win_counts={"CONFIRMATION_CANDLE": 1},
        trigger_loss_counts={"CONFIRMATION_CANDLE": 0},
        trigger_average_h3_favorable_r={"CONFIRMATION_CANDLE": 1.0},
        trigger_average_h3_adverse_r={"CONFIRMATION_CANDLE": 0.2},
    )
    result.virtual_exit_diagnostics = VirtualExitDiagnostics(
        records=[
            VirtualExitRecord(
                trade_number=1,
                direction="LONG",
                actual_result="LOSS",
                actual_pnl_r=-1,
                best_policy_name="TP_1R",
                best_policy_pnl_r=1,
                policy_results={
                    "TP_1R": VirtualExitPolicyResult("TP_1R", result="WIN", virtual_pnl_r=1),
                    "TP_2R": VirtualExitPolicyResult("TP_2R", result="OPEN", virtual_pnl_r=0.4),
                    "BE_AFTER_0_5R": VirtualExitPolicyResult("BE_AFTER_0_5R", result="BREAKEVEN", virtual_pnl_r=0),
                },
            )
        ],
        policy_summaries={
            "TP_1R": VirtualExitPolicySummary("TP_1R", total_trades=1, wins=1, win_rate=100, total_pnl_r=1, average_pnl_r=1),
            "TP_2R": VirtualExitPolicySummary("TP_2R", total_trades=1, opens=1, win_rate=0, total_pnl_r=0.4, average_pnl_r=0.4),
            "BE_AFTER_0_5R": VirtualExitPolicySummary("BE_AFTER_0_5R", total_trades=1, breakevens=1, win_rate=0, total_pnl_r=0, average_pnl_r=0),
        },
        total_trades=1,
        actual_losses=1,
        actual_total_pnl_r=-1,
        best_policy_by_total_pnl_r="TP_1R",
        best_policy_by_win_rate="TP_1R",
        best_policy_by_average_pnl_r="TP_1R",
        tp_1r_would_have_won_count=1,
        be_0_5r_would_help_count=1,
    )
    return result


def _result_with_empty_trade_outcomes() -> RollingBacktestResult:
    result = _result()
    result.trade_outcome_diagnostics = TradeOutcomeDiagnostics()
    result.sl_tp_outcome_diagnostics = SLTPOutcomeDiagnostics()
    result.entry_followthrough_diagnostics = EntryFollowthroughDiagnostics()
    result.virtual_exit_diagnostics = VirtualExitDiagnostics()
    return result


def _result_with_empty_ote_distances() -> RollingBacktestResult:
    result = _result()
    result.diagnostics = BacktestDiagnostics(ote_diagnostics=OTEDiagnostics(windows_analyzed=1), windows_analyzed=1)
    return result


def _result_with_empty_range_age() -> RollingBacktestResult:
    result = _result()
    result.diagnostics = BacktestDiagnostics(
        dealing_range_diagnostics=DealingRangeDiagnostics(windows_analyzed=1),
        windows_analyzed=1,
    )
    return result


def _result_with_empty_candidate_metrics() -> RollingBacktestResult:
    result = _result()
    result.diagnostics = BacktestDiagnostics(
        range_candidate_diagnostics=RangeCandidateDiagnostics(
            windows_analyzed=1,
            candidates={"CURRENT_EXTERNAL_RANGE": RangeCandidateStats(candidate_name="CURRENT_EXTERNAL_RANGE")},
        ),
        windows_analyzed=1,
    )
    return result


def test_formatter_includes_key_metrics() -> None:
    report = format_rolling_backtest_report(_result(), FIXTURE_PATH, 50)

    assert "ROLLING BACKTEST REPORT" in report
    assert "Total Windows" in report
    assert "Processed Windows" in report
    assert "Win Rate" in report
    assert "Net PnL" in report
    assert "Max Drawdown" in report
    assert "Stateful Mode" in report
    assert "Opened Trades" in report
    assert "Closed By State" in report
    assert "Duplicates Skipped" in report


def test_formatter_includes_fixture_path_and_min_candles() -> None:
    report = format_rolling_backtest_report(_result(), FIXTURE_PATH, 50)

    assert FIXTURE_PATH in report
    assert "Min Candles       : 50" in report


def test_formatter_includes_max_windows_when_provided() -> None:
    report = format_rolling_backtest_report(_result(), FIXTURE_PATH, 50, 5)

    assert "Max Windows       : 5" in report


def test_formatter_includes_dealing_range_mode() -> None:
    report = format_rolling_backtest_report(_result(), FIXTURE_PATH, 50)

    assert "Dealing Range Mode : current_external" in report


def test_report_includes_trade_outcome_diagnostics() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50)

    assert "===== TRADE OUTCOME DIAGNOSTICS =====" in report


def test_report_includes_sl_tp_outcome_diagnostics() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50)

    assert "===== SL/TP OUTCOME DIAGNOSTICS =====" in report


def test_report_includes_entry_followthrough_diagnostics() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50)

    assert "===== ENTRY FOLLOW-THROUGH DIAGNOSTICS =====" in report


def test_report_includes_virtual_exit_diagnostics() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50)

    assert "===== VIRTUAL EXIT DIAGNOSTICS =====" in report


def test_virtual_exit_summary_appears_by_default() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50)

    assert "Best Policy by Total PnL R" in report
    assert "Policy Summary:" in report


def test_virtual_exit_trade_log_is_hidden_by_default() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50)

    assert "#1 | LONG | ACTUAL=LOSS" not in report
    assert "Hidden. Use --show-trades to display virtual exit trade log rows." in report


def test_show_trades_prints_virtual_exit_trade_log() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50, show_trades=True)

    assert "Virtual Exit Trade Log:" in report
    assert "#1 | LONG | ACTUAL=LOSS" in report


def test_no_trades_prints_empty_virtual_exit_report() -> None:
    report = format_rolling_backtest_report(_result_with_empty_trade_outcomes(), FIXTURE_PATH, 50, show_trades=True)

    assert "===== VIRTUAL EXIT DIAGNOSTICS =====" in report
    assert "Virtual Exit Trade Log:\nNo trades." in report


def test_entry_followthrough_summary_appears_by_default() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50)

    assert "Immediate Favorable" in report
    assert "Avg H3 Favorable R" in report


def test_entry_followthrough_trade_log_is_hidden_by_default() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50)

    assert "#1 | LONG | WIN | trigger=CONFIRMATION_CANDLE" not in report
    assert "Hidden. Use --show-trades to display entry follow-through trade log rows." in report


def test_show_trades_prints_entry_followthrough_trade_log() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50, show_trades=True)

    assert "Entry Follow-through Trade Log:" in report
    assert "#1 | LONG | WIN | trigger=CONFIRMATION_CANDLE" in report


def test_no_trades_prints_empty_entry_followthrough_report() -> None:
    report = format_rolling_backtest_report(_result_with_empty_trade_outcomes(), FIXTURE_PATH, 50, show_trades=True)

    assert "===== ENTRY FOLLOW-THROUGH DIAGNOSTICS =====" in report
    assert "Entry Follow-through Trade Log:\nNo trades." in report


def test_sl_tp_summary_appears_by_default() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50)

    assert "Average MAE R" in report
    assert "Fast Losses" in report


def test_sl_tp_trade_log_is_hidden_by_default() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50)

    assert "#1 | LONG | WIN | bars=3" not in report
    assert "Hidden. Use --show-trades to display SL/TP trade log rows." in report


def test_show_trades_prints_sl_tp_trade_log() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50, show_trades=True)

    assert "SL/TP Trade Log:" in report
    assert "#1 | LONG | WIN | bars=3" in report


def test_no_trades_prints_empty_sl_tp_report() -> None:
    report = format_rolling_backtest_report(_result_with_empty_trade_outcomes(), FIXTURE_PATH, 50, show_trades=True)

    assert "===== SL/TP OUTCOME DIAGNOSTICS =====" in report
    assert "SL/TP Trade Log:\nNo trades." in report


def test_trade_outcome_summary_appears_by_default() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50)

    assert "Total Trades        : 1" in report


def test_detailed_trade_log_is_hidden_by_default() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50)

    assert "#1 | LONG | WIN" not in report
    assert "Hidden. Use --show-trades" in report


def test_show_trades_prints_trade_log() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50, show_trades=True)

    assert "#1 | LONG | WIN" in report


def test_no_trades_prints_no_trades() -> None:
    report = format_rolling_backtest_report(_result_with_empty_trade_outcomes(), FIXTURE_PATH, 50, show_trades=True)

    assert "No trades." in report


def test_report_includes_direction_summary() -> None:
    report = format_rolling_backtest_report(_result_with_trade_outcomes(), FIXTURE_PATH, 50)

    assert "Direction Summary:" in report
    assert "LONG" in report


def test_report_includes_backtest_diagnostics_section() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "===== BACKTEST DIAGNOSTICS =====" in report
    assert "Windows Analyzed : 2" in report


def test_report_includes_setup_blockers() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "Setup Blockers:" in report
    assert "B                             : 3" in report


def test_report_prints_none_for_empty_blocker_sections() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "Entry Blockers:\nNone" in report


def test_report_sorts_blockers_by_count_descending() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert report.index("B                             : 3") < report.index("A                             : 1")


def test_report_includes_ote_distance_diagnostics() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "===== OTE DISTANCE DIAGNOSTICS =====" in report


def test_report_includes_near_ote_half_percent() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "Near OTE <= 0.5%" in report


def test_report_includes_price_zone_counts() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "Price Zone Counts:" in report
    assert "PREMIUM" in report
    assert "DISCOUNT" in report


def test_report_includes_equilibrium_distance() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "Equilibrium Distance:" in report
    assert "Average Distance To EQ" in report


def test_none_distance_values_render_as_none() -> None:
    report = format_rolling_backtest_report(_result_with_empty_ote_distances(), FIXTURE_PATH, 50)

    assert "Average Distance To OTE    : None" in report
    assert "Median Distance To EQ      : None" in report


def test_report_includes_dealing_range_diagnostics() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "===== DEALING RANGE DIAGNOSTICS =====" in report


def test_report_includes_trend_zone_matrix() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "Trend / Zone Matrix:" in report
    assert "DOWNTREND|DISCOUNT" in report


def test_report_includes_ote_direction_zone_matrix() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "OTE Direction / Zone Matrix:" in report
    assert "BEARISH|DISCOUNT" in report


def test_report_includes_mismatch_counts() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "Mismatch Counts:" in report
    assert "BEARISH_OTE_IN_DISCOUNT" in report


def test_none_range_age_values_render_as_none() -> None:
    report = format_rolling_backtest_report(_result_with_empty_range_age(), FIXTURE_PATH, 50)

    assert "Average External High Age     : None" in report
    assert "Max External Low Age          : None" in report


def test_report_includes_range_candidate_diagnostics() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "===== RANGE CANDIDATE DIAGNOSTICS =====" in report


def test_report_includes_best_by_aligned_zone() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "Best By Aligned Zone" in report


def test_report_includes_recent_50_candle_range() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "--- RECENT_50_CANDLE_RANGE ---" in report


def test_report_includes_recent_100_candle_range() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "--- RECENT_100_CANDLE_RANGE ---" in report


def test_report_includes_recent_swing_range() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "--- RECENT_SWING_RANGE ---" in report


def test_report_includes_fix_wrong_zone_count() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "Fix Wrong Zone Count" in report


def test_none_candidate_metrics_render_as_none() -> None:
    report = format_rolling_backtest_report(_result_with_empty_candidate_metrics(), FIXTURE_PATH, 50)

    assert "Average Distance To OTE       : None" in report


def test_runner_loads_fixture_and_returns_success(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "ROLLING BACKTEST REPORT" in captured.out


def test_runner_output_includes_diagnostics_when_using_fixture(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--progress-every", "0"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "===== BACKTEST DIAGNOSTICS =====" in captured.out


def test_missing_fixture_returns_failure(capsys) -> None:
    return_code = main(["--fixture", "missing_file.json"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "fixture not found" in captured.out


def test_invalid_min_candles_returns_failure(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "0"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "--min-candles must be greater than 0" in captured.out


def test_runner_accepts_max_windows(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--max-windows", "5"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Max Windows       : 5" in captured.out


def test_runner_accepts_progress_every_zero(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--progress-every", "0"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[rolling]" not in captured.out


def test_runner_accepts_recent_50_dealing_range_mode(capsys) -> None:
    return_code = main(
        ["--fixture", FIXTURE_PATH, "--min-candles", "50", "--progress-every", "0", "--dealing-range-mode", "recent_50"]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Dealing Range Mode : recent_50" in captured.out


def test_runner_show_trades_prints_trade_log(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--progress-every",
            "0",
            "--dealing-range-mode",
            "recent_50",
            "--show-trades",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Trade Log:" in captured.out
    assert "#1 |" in captured.out


def test_runner_default_output_does_not_include_first_trade_metadata_debug(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--progress-every",
            "0",
            "--dealing-range-mode",
            "recent_50",
            "--show-trades",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "===== FIRST TRADE METADATA DEBUG =====" not in captured.out


def test_runner_debug_first_trade_metadata_prints_debug_section(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--progress-every",
            "0",
            "--dealing-range-mode",
            "recent_50",
            "--show-trades",
            "--debug-first-trade-metadata",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "===== FIRST TRADE METADATA DEBUG =====" in captured.out
    assert "Top Level Candidate Fields:" in captured.out
    assert "Nested Candidate Objects:" in captured.out
    assert "Extracted Metadata:" in captured.out


def test_runner_default_report_includes_current_external_mode(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--progress-every", "0"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Dealing Range Mode : current_external" in captured.out


def test_invalid_dealing_range_mode_choice_fails(capsys) -> None:
    try:
        main(["--fixture", FIXTURE_PATH, "--dealing-range-mode", "bad_mode"])
    except SystemExit as exc:
        assert exc.code == 2


def test_invalid_progress_every_returns_failure(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--progress-every", "-1"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "--progress-every must be greater than or equal to 0" in captured.out


def test_invalid_max_windows_returns_failure(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--max-windows", "0"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "--max-windows must be greater than 0" in captured.out


def test_stdout_contains_progress_when_progress_every_is_small(capsys) -> None:
    return_code = main(
        ["--fixture", FIXTURE_PATH, "--min-candles", "50", "--max-windows", "5", "--progress-every", "2"]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[rolling]" in captured.out


def test_stdout_does_not_contain_progress_when_progress_every_zero(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--progress-every", "0"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[rolling]" not in captured.out


def test_no_live_network_uses_fixture_only() -> None:
    assert Path(FIXTURE_PATH).exists()
    assert main(["--fixture", FIXTURE_PATH, "--min-candles", "100"]) == 0


def test_script_import_is_safe() -> None:
    module = importlib.import_module("scripts.run_rolling_backtest")

    assert hasattr(module, "main")


def test_main_success_stdout_contains_report_header(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "100"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "===== ROLLING BACKTEST REPORT =====" in captured.out
