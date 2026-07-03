from __future__ import annotations

from engine.evolution.generation_loop_engine import GenerationLoopEngine
from models.strategy_comparison import StrategyComparisonReport
from models.strategy_comparison import StrategyComparisonRow


def _report() -> StrategyComparisonReport:
    return StrategyComparisonReport(
        fixture="fixture.json",
        min_candles=50,
        strategies=[
            StrategyComparisonRow("weak", net_pnl_after_costs=10, win_rate=30, max_drawdown=5, total_trades=5),
            StrategyComparisonRow("strong", net_pnl_after_costs=100, win_rate=70, max_drawdown=5, total_trades=5),
            StrategyComparisonRow("flat", net_pnl_after_costs=0, win_rate=50, max_drawdown=0, total_trades=0),
        ],
    )


def test_generation_loop_selects_top_k() -> None:
    result = GenerationLoopEngine().run_generation(_report(), generation=0, top_k=2)

    assert result.top_k == 2
    assert len(result.evaluated) == 3
    assert len(result.selected) == 2
    assert result.selected[0].candidate.strategy_spec.name == "strong"


def test_generation_loop_generates_next_candidates() -> None:
    result = GenerationLoopEngine().run_generation(_report(), generation=0, top_k=2)

    assert len(result.next_generation) == 2
    assert all(candidate.generation == 1 for candidate in result.next_generation)
    assert all(candidate.parent_id is not None for candidate in result.next_generation)
