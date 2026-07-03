from __future__ import annotations

from engine.decision.adaptive_decision_engine import AdaptiveDecisionEngine
from models.adaptive_signal import AdaptiveSignal
from models.decision import DecisionResult
from models.execution_quality import ExecutionQualityResult
from models.market_context import MarketContext


def _decision(score: float = 0.8, decision: str = "APPROVE") -> DecisionResult:
    return DecisionResult(final_score=score, decision=decision, breakdown={"base": score})


def _execution_quality(score: float) -> ExecutionQualityResult:
    return ExecutionQualityResult(
        score=score,
        volatility_component=score,
        spread_component=score,
        structure_component=score,
        liquidity_component=score,
        timing_component=score,
        reasoning={},
    )


def test_low_execution_quality_rejects_trade() -> None:
    context = MarketContext()
    context.paper_trade_direction = "BULLISH"

    result = AdaptiveDecisionEngine().apply(context, _decision(), _execution_quality(0.35))

    assert result.decision == "REJECT"
    assert context.adaptive_signal == AdaptiveSignal(
        original_decision="APPROVE",
        final_decision="REJECT",
        reason="EXECUTION_QUALITY_TOO_LOW",
        adjustments={
            "original_decision": "APPROVE",
            "final_decision": "REJECT",
            "reason": "EXECUTION_QUALITY_TOO_LOW",
        },
    )


def test_regime_mismatch_downgrades_decision() -> None:
    context = MarketContext()
    context.paper_trade_direction = "BULLISH"
    context.market_regime = "BEARISH"

    result = AdaptiveDecisionEngine().apply(context, _decision(), _execution_quality(0.8))

    assert result.decision == "WARNING"
    assert context.decision_status == "WARNING"
    assert context.adaptive_signal.reason == "REGIME_MISMATCH"


def test_setup_unstable_warns_or_rejects() -> None:
    context = MarketContext()
    context.paper_trade_direction = "BULLISH"
    context.setup_score = 40
    context.setup_blockers = ["A", "B", "C"]

    result = AdaptiveDecisionEngine().apply(context, _decision(), _execution_quality(0.8))

    assert result.decision in {"WARNING", "REJECT"}
    assert context.adaptive_signal.reason == "SETUP_UNSTABLE"
