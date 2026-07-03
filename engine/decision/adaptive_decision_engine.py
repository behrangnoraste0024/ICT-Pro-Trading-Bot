from __future__ import annotations

from models.adaptive_signal import AdaptiveSignal
from models.decision import DecisionResult
from models.execution_quality import ExecutionQualityResult
from models.market_context import MarketContext


class AdaptiveDecisionEngine:
    def apply(
        self,
        context: MarketContext,
        decision_result: DecisionResult,
        execution_quality: ExecutionQualityResult,
    ) -> DecisionResult:
        final_decision = decision_result.decision
        reason = "NO_ADJUSTMENT"
        adjustments: dict[str, object] = {}

        if execution_quality.score < 0.4:
            final_decision = "REJECT"
            reason = "EXECUTION_QUALITY_TOO_LOW"
        elif self._regime_mismatch(context):
            final_decision = self._downgrade(final_decision)
            reason = "REGIME_MISMATCH"
        elif self._setup_unstable(context):
            final_decision = "REJECT" if decision_result.final_score < 0.55 else "WARNING"
            reason = "SETUP_UNSTABLE"

        adjustments["original_decision"] = decision_result.decision
        adjustments["final_decision"] = final_decision
        adjustments["reason"] = reason
        final_result = DecisionResult(
            final_score=decision_result.final_score,
            decision=final_decision,
            breakdown={**decision_result.breakdown, "adaptive": adjustments},
        )
        context.adaptive_signal = AdaptiveSignal(
            original_decision=decision_result.decision,
            final_decision=final_decision,
            reason=reason,
            adjustments=adjustments,
        )
        context.decision_result = final_result
        context.decision_status = final_decision
        context.decision_score = final_result.final_score
        return final_result

    def _regime_mismatch(self, context: MarketContext) -> bool:
        regime = getattr(context, "market_regime", None)
        direction = getattr(context, "paper_trade_direction", "NONE")
        return (direction in ("BULLISH", "LONG") and regime == "BEARISH") or (
            direction in ("BEARISH", "SHORT") and regime == "BULLISH"
        )

    def _setup_unstable(self, context: MarketContext) -> bool:
        setup_score = float(getattr(context, "setup_score", 0) or 0)
        blockers = getattr(context, "setup_blockers", []) or []
        return setup_score < 50 or len(blockers) >= 3

    def _downgrade(self, decision: str) -> str:
        if decision == "APPROVE":
            return "WARNING"
        return "REJECT"
