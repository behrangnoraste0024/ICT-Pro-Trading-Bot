from __future__ import annotations

from models.decision import DecisionResult
from models.execution_quality import ExecutionQualityResult
from models.market_context import MarketContext


class DecisionFusionEngine:
    def evaluate(
        self,
        context: MarketContext,
        execution_quality: ExecutionQualityResult,
        net_pnl_after_costs: float | None = None,
    ) -> DecisionResult:
        performance_score = self._performance_score(context, net_pnl_after_costs)
        execution_score = execution_quality.score
        regime_alignment_score = self._regime_alignment_score(context)
        setup_quality_score = self._setup_quality_score(context)
        stability_score = self._stability_score(context)
        final_score = self._clamp(
            performance_score * 0.40
            + execution_score * 0.25
            + regime_alignment_score * 0.15
            + setup_quality_score * 0.10
            + stability_score * 0.10
        )
        return DecisionResult(
            final_score=final_score,
            decision=self._decision(final_score),
            breakdown={
                "performance_score": performance_score,
                "execution_quality_score": execution_score,
                "regime_alignment_score": regime_alignment_score,
                "setup_quality_score": setup_quality_score,
                "stability_score": stability_score,
                "weights": {
                    "performance": 0.40,
                    "execution_quality": 0.25,
                    "regime_alignment": 0.15,
                    "setup_quality": 0.10,
                    "stability": 0.10,
                },
            },
        )

    def attach(
        self,
        context: MarketContext,
        execution_quality: ExecutionQualityResult,
        net_pnl_after_costs: float | None = None,
    ) -> MarketContext:
        result = self.evaluate(context, execution_quality, net_pnl_after_costs)
        context.decision_result = result
        context.decision_score = result.final_score
        context.decision_status = result.decision
        return context

    def _performance_score(self, context: MarketContext, net_pnl_after_costs: float | None) -> float:
        pnl = net_pnl_after_costs
        if pnl is None:
            pnl = getattr(context, "paper_pnl", None)
        if pnl is None:
            return 0.5
        return self._clamp((float(pnl) + 500.0) / 1000.0)

    def _regime_alignment_score(self, context: MarketContext) -> float:
        regime = getattr(context, "market_regime", None)
        direction = getattr(context, "paper_trade_direction", "NONE")
        if regime in (None, "UNKNOWN", "RANGE"):
            return 0.6
        if direction in ("BULLISH", "LONG") and regime == "BULLISH":
            return 1.0
        if direction in ("BEARISH", "SHORT") and regime == "BEARISH":
            return 1.0
        return 0.25

    def _setup_quality_score(self, context: MarketContext) -> float:
        return self._clamp(float(getattr(context, "setup_score", 0) or 0) / 100.0)

    def _stability_score(self, context: MarketContext) -> float:
        blockers = len(getattr(context, "setup_blockers", []) or []) + len(getattr(context, "trade_quality_blockers", []) or [])
        if blockers == 0:
            return 1.0
        if blockers <= 2:
            return 0.6
        return 0.25

    def _decision(self, score: float) -> str:
        if score >= 0.7:
            return "APPROVE"
        if score >= 0.45:
            return "WARNING"
        return "REJECT"

    def _clamp(self, value: float) -> float:
        return max(0.0, min(float(value), 1.0))
