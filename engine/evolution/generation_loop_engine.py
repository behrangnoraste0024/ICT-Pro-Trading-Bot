from __future__ import annotations

from engine.evolution.strategy_evolution_core import StrategyEvolutionCore
from models.evolution import GenerationResult
from models.strategy_comparison import StrategyComparisonReport


class GenerationLoopEngine:
    def __init__(self, core: StrategyEvolutionCore | None = None):
        self.core = core if core is not None else StrategyEvolutionCore()

    def run_generation(
        self,
        comparison_report: StrategyComparisonReport,
        generation: int = 0,
        top_k: int = 3,
    ) -> GenerationResult:
        evaluations = self.core.rank(comparison_report.strategies, generation=generation)
        selected = self.core.select_top_k(evaluations, top_k=top_k)
        next_generation = self.core.generate_next(selected, generation=generation + 1)
        return GenerationResult(
            generation=generation,
            evaluated=evaluations,
            selected=selected,
            next_generation=next_generation,
            top_k=top_k,
        )
