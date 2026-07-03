from __future__ import annotations

from engine.evolution.generation_loop_engine import GenerationLoopEngine
from models.strategy_comparison import StrategyComparisonReport
from models.strategy_comparison import StrategyComparisonRow
from reporting.generation_loop_report import format_generation_result


def test_generation_loop_report_contains_selected_and_generated_candidates() -> None:
    result = GenerationLoopEngine().run_generation(
        StrategyComparisonReport(
            fixture="fixture.json",
            min_candles=50,
            strategies=[
                StrategyComparisonRow("winner", net_pnl_after_costs=100, win_rate=60, total_trades=5),
                StrategyComparisonRow("loser", net_pnl_after_costs=-10, win_rate=20, total_trades=5),
            ],
        ),
        generation=0,
        top_k=1,
    )

    output = format_generation_result(result)

    assert "===== GENERATION LOOP REPORT =====" in output
    assert "Selected Candidates:" in output
    assert "Next Generation Candidates:" in output
    assert "winner" in output
