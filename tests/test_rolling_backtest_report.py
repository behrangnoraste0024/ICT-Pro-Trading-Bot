from __future__ import annotations

from types import SimpleNamespace

from models.decision_filter_simulation import DecisionFilterBucket
from models.decision_filter_simulation import DecisionFilterSimulationResult
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
