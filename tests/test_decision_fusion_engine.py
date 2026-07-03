from __future__ import annotations

import pytest

from engine.decision.decision_fusion_engine import DecisionFusionEngine
from models.execution_quality import ExecutionQualityResult
from models.market_context import MarketContext


def _context() -> MarketContext:
    context = MarketContext()
    context.paper_trade_status = "PAPER_CLOSED_TP"
    context.paper_trade_direction = "BULLISH"
    context.paper_pnl = 100.0
    context.setup_score = 80
    context.market_regime = "BULLISH"
    context.setup_blockers = []
    context.trade_quality_blockers = []
    return context


def test_decision_fusion_evaluate_uses_expected_weights() -> None:
    context = _context()
    execution_quality = ExecutionQualityResult(
        score=0.8,
        volatility_component=0.8,
        spread_component=0.8,
        structure_component=0.8,
        liquidity_component=0.8,
        timing_component=0.8,
        reasoning={},
    )

    result = DecisionFusionEngine().evaluate(context, execution_quality, net_pnl_after_costs=100.0)

    assert result.final_score == pytest.approx(0.77)
    assert result.decision == "APPROVE"
    assert result.breakdown["performance_score"] == 0.6
    assert result.breakdown["execution_quality_score"] == 0.8
    assert result.breakdown["regime_alignment_score"] == 1.0


def test_decision_fusion_attach_populates_context() -> None:
    context = _context()
    execution_quality = ExecutionQualityResult(
        score=0.5,
        volatility_component=0.5,
        spread_component=0.5,
        structure_component=0.5,
        liquidity_component=0.5,
        timing_component=0.5,
        reasoning={},
    )

    result = DecisionFusionEngine().attach(context, execution_quality, net_pnl_after_costs=-200.0)

    assert context.decision_result is not None
    assert context.decision_score == context.decision_result.final_score
    assert context.decision_status == context.decision_result.decision
