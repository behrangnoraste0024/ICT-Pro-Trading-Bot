from __future__ import annotations

from copy import deepcopy

import pytest

from engine.diagnostics.decision_filter_simulation_engine import DecisionFilterSimulationEngine
from models.cost_diagnostics import CostDiagnostics
from models.cost_diagnostics import TradeCostBreakdown
from models.market_context import MarketContext


def _trade(
    decision: str | None,
    status: str,
    pnl: float | None,
    execution_quality: float | None = None,
    decision_score: float | None = None,
) -> MarketContext:
    context = MarketContext()
    context.paper_trade_status = status
    context.paper_trade_direction = "BULLISH"
    context.paper_pnl = pnl
    context.decision_status = decision
    context.execution_quality_score = execution_quality
    context.decision_score = decision_score
    return context


def _cost_diagnostics() -> CostDiagnostics:
    return CostDiagnostics(
        cost_model="percent",
        commission_pct=0.0,
        slippage_pct=0.0,
        spread_pct=0.0,
        total_trades=3,
        closed_trades=3,
        gross_net_pnl=70,
        total_commission_cost=0,
        total_slippage_cost=0,
        total_spread_cost=0,
        total_cost=17,
        net_pnl_after_costs=53,
        average_cost_per_trade=17 / 3,
        average_net_pnl_after_costs=53 / 3,
        cost_to_gross_profit_ratio=None,
        trades=[
            TradeCostBreakdown(1, "BULLISH", 100, 0, 0, 0, 10, 90, 100, 190, True),
            TradeCostBreakdown(2, "BULLISH", -50, 0, 0, 0, 5, -55, 100, 45, True),
            TradeCostBreakdown(3, "BULLISH", 20, 0, 0, 0, 2, 18, 100, 118, True),
        ],
    )


def _bucket(result, name: str):
    return next(bucket for bucket in result.buckets if bucket.name == name)


def test_all_trades_bucket_includes_every_trade() -> None:
    result = DecisionFilterSimulationEngine().summarize_contexts(
        [
            _trade("APPROVE", "PAPER_CLOSED_TP", 100),
            _trade("WARNING", "PAPER_CLOSED_SL", -50),
            _trade("REJECT", "PAPER_CLOSED_TP", 20),
        ],
        _cost_diagnostics(),
    )

    bucket = _bucket(result, "all_trades")

    assert bucket.total_trades == 3
    assert bucket.wins == 2
    assert bucket.losses == 1
    assert bucket.win_rate == pytest.approx(66.6666666667)


def test_decision_buckets_filter_expected_decisions() -> None:
    result = DecisionFilterSimulationEngine().summarize_contexts(
        [
            _trade("APPROVE", "PAPER_CLOSED_TP", 100),
            _trade("WARNING", "PAPER_CLOSED_SL", -50),
            _trade("REJECT", "PAPER_CLOSED_TP", 20),
        ],
        _cost_diagnostics(),
    )

    assert _bucket(result, "approve_only").total_trades == 1
    assert _bucket(result, "warning_only").total_trades == 1
    assert _bucket(result, "reject_only").total_trades == 1
    assert _bucket(result, "approve_or_warning").total_trades == 2


def test_net_pnl_after_costs_is_used_when_available() -> None:
    result = DecisionFilterSimulationEngine().summarize_contexts(
        [
            _trade("APPROVE", "PAPER_CLOSED_TP", 100, 0.8, 0.9),
            _trade("WARNING", "PAPER_CLOSED_SL", -50, 0.6, 0.5),
            _trade("REJECT", "PAPER_CLOSED_TP", 20, 0.3, 0.2),
        ],
        _cost_diagnostics(),
    )

    bucket = _bucket(result, "all_trades")

    assert bucket.gross_net_pnl == 70
    assert bucket.total_cost == 17
    assert bucket.net_pnl_after_costs == 53
    assert bucket.average_net_pnl_after_costs == pytest.approx(53 / 3)
    assert bucket.max_drawdown == 55
    assert bucket.profit_factor == pytest.approx(108 / 55)
    assert bucket.average_execution_quality == pytest.approx((0.8 + 0.6 + 0.3) / 3)
    assert bucket.average_decision_score == pytest.approx((0.9 + 0.5 + 0.2) / 3)


def test_gross_pnl_fallback_works_without_cost_diagnostics() -> None:
    result = DecisionFilterSimulationEngine().summarize_contexts(
        [
            _trade("APPROVE", "PAPER_CLOSED_TP", 100),
            _trade("WARNING", "PAPER_CLOSED_SL", -50),
        ]
    )

    bucket = _bucket(result, "all_trades")

    assert bucket.gross_net_pnl == 50
    assert bucket.total_cost == 0
    assert bucket.net_pnl_after_costs == 50


def test_missing_decision_metadata_only_populates_all_trades() -> None:
    result = DecisionFilterSimulationEngine().summarize_contexts([_trade(None, "PAPER_CLOSED_TP", 10)])

    assert _bucket(result, "all_trades").total_trades == 1
    assert _bucket(result, "approve_only").total_trades == 0
    assert _bucket(result, "warning_only").total_trades == 0
    assert _bucket(result, "reject_only").total_trades == 0
    assert _bucket(result, "approve_or_warning").total_trades == 0


def test_empty_buckets_are_safe() -> None:
    result = DecisionFilterSimulationEngine().summarize_contexts([])
    bucket = _bucket(result, "approve_only")

    assert bucket.total_trades == 0
    assert bucket.win_rate == 0
    assert bucket.average_execution_quality is None
    assert result.best_by_net_after_costs is None


def test_simulation_does_not_mutate_trades() -> None:
    context = _trade("APPROVE", "PAPER_CLOSED_TP", 100, 0.8, 0.9)
    before = deepcopy(context.__dict__)

    DecisionFilterSimulationEngine().summarize_contexts([context])

    assert context.__dict__ == before
