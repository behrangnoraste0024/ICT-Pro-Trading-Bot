from __future__ import annotations

from types import SimpleNamespace

from models.decision_filter_simulation import DecisionFilterBucket
from models.decision_filter_simulation import DecisionFilterSimulationResult
from models.decision_threshold_calibration import DecisionThresholdBucket
from models.decision_threshold_calibration import DecisionThresholdCalibrationResult
from models.decision_threshold_robustness import DecisionThresholdRobustnessResult
from models.decision_threshold_robustness import DecisionThresholdSegmentBucket
from models.decision_threshold_robustness import DecisionThresholdSegmentSummary
from models.rolling_backtest_result import RollingBacktestResult
from reporting.rolling_backtest_report import format_rolling_backtest_report


def _result() -> RollingBacktestResult:
    result = RollingBacktestResult(
        total_windows=1,
        processed_windows=1,
        skipped_windows=0,
        failed_windows=0,
        min_candles=1,
        total_paper_trades=1,
        closed_trades=1,
        open_trades=0,
        wins=1,
        losses=0,
        win_rate=100.0,
        net_pnl=10.0,
        average_pnl=10.0,
        max_drawdown=0.0,
        ignored_contexts=0,
    )
    context = SimpleNamespace(
        paper_trade_status="PAPER_CLOSED_TP",
        paper_trade_direction="BULLISH",
        execution_quality_score=0.83,
        decision_score=0.74,
        decision_status="APPROVE",
        execution_quality_result=SimpleNamespace(reasoning={"timing": "good"}),
        decision_result=SimpleNamespace(breakdown={"score": 0.74}),
        adaptive_signal=SimpleNamespace(reason="NO_ADJUSTMENT"),
    )
    result.trade_outcome_contexts = [context]
    result.decision_filter_simulation = DecisionFilterSimulationResult(
        buckets=[
            DecisionFilterBucket(
                name="all_trades",
                decision_values=[],
                total_trades=1,
                wins=1,
                losses=0,
                win_rate=100,
                gross_net_pnl=10,
                total_cost=1,
                net_pnl_after_costs=9,
                average_pnl=10,
                average_net_pnl_after_costs=9,
                max_drawdown=0,
                profit_factor=None,
                average_execution_quality=0.83,
                average_decision_score=0.74,
            )
        ],
        best_by_net_after_costs="all_trades",
        best_by_drawdown="all_trades",
    )
    result.decision_threshold_calibration = DecisionThresholdCalibrationResult(
        thresholds=[
            DecisionThresholdBucket(
                threshold=0.7,
                name="score_gte_0.70",
                total_trades=1,
                wins=1,
                losses=0,
                win_rate=100,
                gross_net_pnl=10,
                total_cost=1,
                net_pnl_after_costs=9,
                average_pnl=10,
                average_net_pnl_after_costs=9,
                max_drawdown=0,
                profit_factor=None,
                average_execution_quality=0.83,
                average_decision_score=0.74,
            )
        ],
        best_by_net_after_costs="score_gte_0.70",
        best_by_drawdown="score_gte_0.70",
        best_by_profit_factor=None,
    )
    segment_bucket = DecisionThresholdSegmentBucket(
        segment_index=1,
        segment_name="segment_1",
        threshold=0.7,
        name="score_gte_0.70",
        total_trades=1,
        wins=1,
        losses=0,
        win_rate=100,
        gross_net_pnl=10,
        total_cost=1,
        net_pnl_after_costs=9,
        average_pnl=10,
        average_net_pnl_after_costs=9,
        max_drawdown=0,
        profit_factor=None,
        average_execution_quality=0.83,
        average_decision_score=0.74,
    )
    result.decision_threshold_robustness = DecisionThresholdRobustnessResult(
        segment_count=1,
        thresholds=[0.7],
        segment_summaries=[
            DecisionThresholdSegmentSummary(
                segment_index=1,
                segment_name="segment_1",
                start_trade_index=1,
                end_trade_index=1,
                total_source_trades=1,
                best_by_net_after_costs="score_gte_0.70",
                best_by_drawdown="score_gte_0.70",
                buckets=[segment_bucket],
            )
        ],
        threshold_stability={
            0.7: {
                "segments_with_trades": 1,
                "profitable_segments": 1,
                "losing_segments": 0,
                "total_net_pnl_after_costs": 9,
                "average_net_pnl_after_costs": 9,
                "worst_segment_net_pnl_after_costs": 9,
                "average_drawdown": 0,
                "max_drawdown": 0,
                "total_trades": 1,
                "total_wins": 1,
                "total_losses": 0,
                "aggregate_win_rate": 100,
            }
        },
        best_overall_threshold=0.7,
        robust_threshold=0.7,
    )
    return result


def test_report_includes_execution_quality_section() -> None:
    output = format_rolling_backtest_report(_result(), "fixture.json", 1, show_trades=True)

    assert "===== EXECUTION QUALITY / DECISION =====" in output
    assert "Average Execution Quality" in output
    assert "Average Decision Score" in output
    assert "APPROVE" in output
    assert "exec_q=0.83" in output


def test_report_includes_decision_filter_simulation_section() -> None:
    output = format_rolling_backtest_report(_result(), "fixture.json", 1)

    assert "===== DECISION FILTER SIMULATION =====" in output
    assert "Bucket | Trades | W/L | Win% | GrossPnL | Cost | NetAfterCost | AvgDecision | AvgExecQ | MaxDD | PF" in output
    assert "all_trades | 1 | 1/0 | 100" in output


def test_report_includes_decision_threshold_calibration_section() -> None:
    output = format_rolling_backtest_report(_result(), "fixture.json", 1)

    assert "===== DECISION THRESHOLD CALIBRATION =====" in output
    assert "Best By Net After Costs : score_gte_0.70" in output
    assert "Best By Profit Factor   : None" in output
    assert "Threshold | Trades | W/L | Win% | GrossPnL | Cost | NetAfterCost | AvgDecision | AvgExecQ | MaxDD | PF" in output
    assert "0.7 | 1 | 1/0 | 100" in output


def test_report_includes_decision_threshold_robustness_section() -> None:
    output = format_rolling_backtest_report(_result(), "fixture.json", 1)

    assert "===== DECISION THRESHOLD ROBUSTNESS =====" in output
    assert "Segments              : 1" in output
    assert "Best Overall Threshold: 0.7" in output
    assert "Robust Threshold      : 0.7" in output
    assert "Threshold Stability:" in output
    assert "Segment Details:" in output
    assert "segment_1 | 0.7 | 1 | 1/0 | 100" in output
