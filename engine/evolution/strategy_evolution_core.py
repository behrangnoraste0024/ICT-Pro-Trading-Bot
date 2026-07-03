from __future__ import annotations

from dataclasses import replace

from models.evolution import EvolutionCandidate
from models.evolution import EvolutionEvaluation
from models.strategy_comparison import StrategyComparisonRow
from models.strategy_comparison import StrategyConfigSpec


class StrategyEvolutionCore:
    def candidate_from_spec(
        self,
        spec: StrategyConfigSpec,
        generation: int = 0,
        parent_id: str | None = None,
        mutation_reason: str = "SEED",
    ) -> EvolutionCandidate:
        return EvolutionCandidate(
            candidate_id=self._candidate_id(spec, generation),
            strategy_spec=spec,
            generation=generation,
            parent_id=parent_id,
            mutation_reason=mutation_reason,
        )

    def evaluate_row(self, row: StrategyComparisonRow, generation: int = 0) -> EvolutionEvaluation:
        spec = self.spec_from_row(row)
        candidate = self.candidate_from_spec(spec, generation=generation)
        fitness = self.fitness(row)
        return EvolutionEvaluation(
            candidate=candidate,
            fitness=fitness,
            net_pnl_after_costs=self._net_after_costs(row),
            gross_net_pnl=self._gross_pnl(row),
            win_rate=float(row.win_rate or 0.0),
            profit_factor=row.profit_factor,
            max_drawdown=float(row.max_drawdown or 0.0),
            total_trades=row.total_trades,
            execution_quality_score=self._execution_quality_score(row),
        )

    def spec_from_row(self, row: StrategyComparisonRow) -> StrategyConfigSpec:
        return StrategyConfigSpec(
            name=row.strategy_name,
            dealing_range_mode=row.dealing_range_mode,
            exit_mode=row.exit_mode,
            min_risk_reward=row.min_risk_reward,
            direction_mode=row.direction_mode,
            auto_trend_fallback=row.auto_trend_fallback,
            regime_mode=row.regime_mode,
            regime_lookback=row.regime_lookback,
            regime_threshold_pct=row.regime_threshold_pct,
            regime_fallback=row.regime_fallback,
            direction_quality_mode=row.direction_quality_mode,
            strict_long_preset=row.strict_long_preset,
            strategy_profile=row.strategy_profile,
            cost_model=row.cost_model,
            commission_pct=row.commission_pct,
            slippage_pct=row.slippage_pct,
            spread_pct=row.spread_pct,
        )

    def fitness(self, row: StrategyComparisonRow) -> float:
        net_after_costs = self._net_after_costs(row)
        win_rate_score = float(row.win_rate or 0.0) * 0.10
        profit_factor_score = min(float(row.profit_factor or 0.0), 5.0) * 10.0
        drawdown_penalty = float(row.max_drawdown or 0.0) * 0.10
        quality_score = self._execution_quality_score(row) or 0.0
        trade_penalty = 25.0 if row.total_trades == 0 else 0.0
        return net_after_costs + win_rate_score + profit_factor_score + quality_score - drawdown_penalty - trade_penalty

    def rank(self, rows: list[StrategyComparisonRow], generation: int = 0) -> list[EvolutionEvaluation]:
        evaluations = [self.evaluate_row(row, generation=generation) for row in rows]
        return sorted(evaluations, key=lambda evaluation: evaluation.fitness, reverse=True)

    def select_top_k(self, evaluations: list[EvolutionEvaluation], top_k: int) -> list[EvolutionEvaluation]:
        return evaluations[: max(top_k, 0)]

    def mutate(self, evaluation: EvolutionEvaluation, generation: int) -> EvolutionCandidate:
        row_like = evaluation
        spec = evaluation.candidate.strategy_spec
        if evaluation.total_trades < 2:
            return self._mutate_low_trades(spec, row_like, generation)
        if evaluation.win_rate < 50:
            return self._mutate_low_win_rate(spec, row_like, generation)
        if evaluation.max_drawdown > max(abs(evaluation.net_pnl_after_costs), 1.0):
            return self._mutate_high_drawdown(spec, row_like, generation)
        if self._low_cost_efficiency(evaluation):
            return self._mutate_low_cost_efficiency(spec, row_like, generation)
        return self._mutated_candidate(spec, row_like, generation, spec, "NO_CHANGE")

    def generate_next(self, evaluations: list[EvolutionEvaluation], generation: int) -> list[EvolutionCandidate]:
        return [self.mutate(evaluation, generation=generation) for evaluation in evaluations]

    def _mutate_low_win_rate(
        self,
        spec: StrategyConfigSpec,
        evaluation: EvolutionEvaluation,
        generation: int,
    ) -> EvolutionCandidate:
        next_rr = self._next_risk_reward(spec.min_risk_reward)
        mutated = replace(
            spec,
            min_risk_reward=next_rr,
            exit_mode=self._exit_mode_for_rr(next_rr),
            name=f"{spec.name}|mut=raise_rr_{next_rr}",
        )
        return self._mutated_candidate(spec, evaluation, generation, mutated, "LOW_WIN_RATE_RAISE_RR")

    def _mutate_high_drawdown(
        self,
        spec: StrategyConfigSpec,
        evaluation: EvolutionEvaluation,
        generation: int,
    ) -> EvolutionCandidate:
        if spec.direction_quality_mode == "off":
            mutated = replace(
                spec,
                direction_quality_mode="long_strict",
                strict_long_preset="regime_known",
                strict_long_require_regime_known=True,
                name=f"{spec.name}|mut=tighten_dq_regime_known",
            )
        else:
            mutated = replace(
                spec,
                strict_long_preset="regime_known_displacement",
                strict_long_require_regime_known=True,
                strict_long_require_displacement=True,
                name=f"{spec.name}|mut=tighten_dq_displacement",
            )
        return self._mutated_candidate(spec, evaluation, generation, mutated, "HIGH_DRAWDOWN_TIGHTEN_FILTERS")

    def _mutate_low_cost_efficiency(
        self,
        spec: StrategyConfigSpec,
        evaluation: EvolutionEvaluation,
        generation: int,
    ) -> EvolutionCandidate:
        mutated = replace(
            spec,
            slippage_pct=max(spec.slippage_pct * 0.5, 0.0),
            name=f"{spec.name}|mut=lower_slippage",
        )
        return self._mutated_candidate(spec, evaluation, generation, mutated, "LOW_COST_EFFICIENCY_ADJUST_SLIPPAGE")

    def _mutate_low_trades(
        self,
        spec: StrategyConfigSpec,
        evaluation: EvolutionEvaluation,
        generation: int,
    ) -> EvolutionCandidate:
        if spec.direction_quality_mode != "off":
            mutated = replace(spec, direction_quality_mode="off", strict_long_preset="none", name=f"{spec.name}|mut=relax_dq")
        elif spec.direction_mode != "all":
            mutated = replace(spec, direction_mode="all", name=f"{spec.name}|mut=relax_direction")
        else:
            next_rr = self._previous_risk_reward(spec.min_risk_reward)
            mutated = replace(spec, min_risk_reward=next_rr, exit_mode=self._exit_mode_for_rr(next_rr), name=f"{spec.name}|mut=lower_rr_{next_rr}")
        return self._mutated_candidate(spec, evaluation, generation, mutated, "LOW_TRADES_RELAX_ONE_CONSTRAINT")

    def _mutated_candidate(
        self,
        original: StrategyConfigSpec,
        evaluation: EvolutionEvaluation,
        generation: int,
        mutated: StrategyConfigSpec,
        reason: str,
    ) -> EvolutionCandidate:
        return self.candidate_from_spec(
            mutated,
            generation=generation,
            parent_id=evaluation.candidate.candidate_id,
            mutation_reason=reason,
        )

    def _candidate_id(self, spec: StrategyConfigSpec, generation: int) -> str:
        return f"g{generation}:{spec.name}"

    def _net_after_costs(self, row: StrategyComparisonRow) -> float:
        if row.net_pnl_after_costs is not None:
            return float(row.net_pnl_after_costs)
        return float(row.net_pnl or 0.0)

    def _gross_pnl(self, row: StrategyComparisonRow) -> float:
        if row.gross_net_pnl is not None:
            return float(row.gross_net_pnl)
        return float(row.net_pnl or 0.0)

    def _execution_quality_score(self, row: StrategyComparisonRow) -> float | None:
        value = getattr(row, "execution_quality_score", None)
        return None if value is None else float(value)

    def _low_cost_efficiency(self, evaluation: EvolutionEvaluation) -> bool:
        gross = abs(evaluation.gross_net_pnl)
        cost = max(gross - evaluation.net_pnl_after_costs, 0.0)
        return gross > 0 and cost / gross > 0.25

    def _next_risk_reward(self, current: float) -> float:
        for value in (1.5, 2.0, 3.0):
            if current < value:
                return value
        return 3.0

    def _previous_risk_reward(self, current: float) -> float:
        for value in (2.0, 1.5, 1.0):
            if current > value:
                return value
        return 1.0

    def _exit_mode_for_rr(self, risk_reward: float) -> str:
        mapping = {1.0: "fixed_1r", 1.5: "fixed_1_5r", 2.0: "fixed_2r", 3.0: "fixed_3r"}
        return mapping.get(risk_reward, "fixed_1_5r")
