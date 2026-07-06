from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from models.recommended_profile_validation import (
    RecommendedProfileValidation,
    RecommendedProfileValidationResult,
)
from models.strategy_comparison import StrategyComparisonReport, StrategyComparisonRow


class RecommendedProfileValidationEngine:
    def validate(
        self,
        comparison: StrategyComparisonReport | Iterable[StrategyComparisonRow],
    ) -> RecommendedProfileValidationResult:
        rows = self._rows(comparison)
        baseline = self._baseline(rows)
        candidates = [row for row in rows if self._is_recommended_candidate(row)]
        ranking = [self._to_validation(row, baseline) for row in sorted(candidates, key=self._rank_key)]
        selected = ranking[0] if ranking else None
        return RecommendedProfileValidationResult(
            selected=selected,
            candidates_evaluated=len(candidates),
            ranking=ranking,
            diagnostics={
                "source_rows": len(rows),
                "baseline_found": baseline is not None,
                "candidate_rule": "profile contains _decision_065 or decision_score_threshold == 0.65",
            },
        )

    def _rows(self, comparison: StrategyComparisonReport | Iterable[StrategyComparisonRow]) -> list[StrategyComparisonRow]:
        if isinstance(comparison, StrategyComparisonReport):
            return list(comparison.strategies)
        return list(comparison)

    def _is_recommended_candidate(self, row: StrategyComparisonRow) -> bool:
        profile = getattr(row, "strategy_profile", "") or ""
        threshold = getattr(row, "decision_score_threshold", None)
        return "_decision_065" in profile or threshold == 0.65

    def _baseline(self, rows: list[StrategyComparisonRow]) -> StrategyComparisonRow | None:
        for row in rows:
            if row.strategy_name == "profile=balanced_smc|cost=percent":
                return row
        for row in rows:
            if row.strategy_profile == "balanced_smc" and row.cost_model == "percent":
                return row
        return None

    def _rank_key(self, row: StrategyComparisonRow) -> tuple[float, float, float, int, int]:
        return (
            -float(getattr(row, "net_pnl_after_costs", 0.0) or 0.0),
            float(getattr(row, "max_drawdown", 0.0) or 0.0),
            -float(getattr(row, "win_rate", 0.0) or 0.0),
            -int(getattr(row, "total_trades", 0) or 0),
            self._profile_preference(row),
        )

    def _profile_preference(self, row: StrategyComparisonRow) -> int:
        return 0 if row.strategy_profile == "balanced_smc_decision_065" else 1

    def _to_validation(
        self,
        row: StrategyComparisonRow,
        baseline: StrategyComparisonRow | None,
    ) -> RecommendedProfileValidation:
        baseline_net = None if baseline is None else float(baseline.net_pnl_after_costs)
        baseline_dd = None if baseline is None else float(baseline.max_drawdown)
        improvement = None if baseline_net is None else float(row.net_pnl_after_costs) - baseline_net
        return RecommendedProfileValidation(
            recommended_strategy_name=row.strategy_name,
            recommended_profile=row.strategy_profile,
            recommendation_reason=self._reason(row, baseline, improvement),
            score_threshold=row.decision_score_threshold,
            total_trades=row.total_trades,
            wins=row.wins,
            losses=row.losses,
            win_rate=float(row.win_rate or 0.0),
            gross_net_pnl=float(row.gross_net_pnl),
            total_cost=float(row.total_cost),
            net_pnl_after_costs=float(row.net_pnl_after_costs),
            max_drawdown=float(row.max_drawdown),
            profit_factor=row.profit_factor,
            average_decision_score=row.average_decision_score,
            average_execution_quality=row.average_execution_quality,
            baseline_strategy_name=None if baseline is None else baseline.strategy_name,
            baseline_net_pnl_after_costs=baseline_net,
            baseline_max_drawdown=baseline_dd,
            improvement_vs_baseline=improvement,
            diagnostics={
                "decision_threshold_filtered": row.decision_threshold_filtered,
                "decision_threshold_bucket": row.decision_threshold_bucket,
                "cost_model": row.cost_model,
            },
        )

    def _reason(
        self,
        row: StrategyComparisonRow,
        baseline: StrategyComparisonRow | None,
        improvement: float | None,
    ) -> str:
        parts = [
            "selected from decision-065 research profiles",
            "ranked by net after costs, drawdown, win rate, and trade count",
        ]
        if row.strategy_profile == "balanced_smc_decision_065":
            parts.append("balanced profile preferred on ties")
        if improvement is not None:
            parts.append(f"improvement vs baseline: {improvement:.2f}")
        elif baseline is None:
            parts.append("baseline not found")
        return "; ".join(parts)
