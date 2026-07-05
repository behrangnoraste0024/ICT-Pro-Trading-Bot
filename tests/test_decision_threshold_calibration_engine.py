from __future__ import annotations

import pytest

from engine.diagnostics.decision_threshold_calibration_engine import DecisionThresholdCalibrationEngine
from models.cost_diagnostics import CostDiagnostics, TradeCostBreakdown
from models.market_context import MarketContext


def _trade(
    score: float | None,
    status: str,
    pnl: float,
    execution_quality: float | None = None,
) -> MarketContext:
    context = MarketContext()
    context.paper_trade_status = status
    context.paper_pnl = pnl
    context.decision_score = score
    context.execution_quality_score = execution_quality
    return context


def _costs() -> CostDiagnostics:
    return CostDiagnostics(
        cost_model="percent",
        commission_pct=0.0004,
        slippage_pct=0.0002,
        spread_pct=0.0001,
        total_trades=3,
        closed_trades=3,
        gross_net_pnl=60,
        total_commission_cost=3,
        total_slippage_cost=2,
        total_spread_cost=1,
        total_cost=6,
        net_pnl_after_costs=54,
        average_cost_per_trade=2,
        average_net_pnl_after_costs=18,
        cost_to_gross_profit_ratio=0.05,
        trades=[
            TradeCostBreakdown(1, "LONG", 100, 1, 1, 1, 3, 97, 100, 110, True),
            TradeCostBreakdown(2, "SHORT", -40, 1, 1, 1, 3, -43, 100, 104, True),
            TradeCostBreakdown(3, "LONG", 20, 0, 0, 0, 0, 20, 100, 102, True),
        ],
    )


def test_threshold_bucket_includes_only_scores_at_or_above_threshold() -> None:
    result = DecisionThresholdCalibrationEngine().summarize_contexts(
        [
            _trade(0.70, "PAPER_CLOSED_TP", 100, 0.8),
            _trade(0.64, "PAPER_CLOSED_SL", -40, 0.6),
            _trade(0.85, "PAPER_CLOSED_TP", 20, 0.9),
        ],
        thresholds=[0.65],
    )

    bucket = result.thresholds[0]
    assert bucket.name == "score_gte_0.65"
    assert bucket.total_trades == 2
    assert bucket.wins == 2
    assert bucket.losses == 0
    assert bucket.gross_net_pnl == 120
    assert bucket.average_decision_score == pytest.approx((0.70 + 0.85) / 2)


def test_missing_decision_score_trades_are_excluded_safely() -> None:
    result = DecisionThresholdCalibrationEngine().summarize_contexts(
        [_trade(None, "PAPER_CLOSED_TP", 100), _trade(0.9, "PAPER_CLOSED_SL", -25)],
        thresholds=[0.60],
    )

    bucket = result.thresholds[0]
    assert bucket.total_trades == 1
    assert bucket.losses == 1
    assert result.diagnostics["trades_missing_decision_score"] == 1
    assert result.diagnostics["trades_with_decision_score"] == 1


def test_net_pnl_after_costs_is_used_when_cost_data_exists() -> None:
    result = DecisionThresholdCalibrationEngine().summarize_contexts(
        [
            _trade(0.70, "PAPER_CLOSED_TP", 100),
            _trade(0.80, "PAPER_CLOSED_SL", -40),
            _trade(0.50, "PAPER_CLOSED_TP", 20),
        ],
        cost_diagnostics=_costs(),
        thresholds=[0.60],
    )

    bucket = result.thresholds[0]
    assert bucket.gross_net_pnl == 60
    assert bucket.total_cost == 6
    assert bucket.net_pnl_after_costs == 54


def test_gross_pnl_fallback_works_when_cost_data_is_missing() -> None:
    result = DecisionThresholdCalibrationEngine().summarize_contexts(
        [_trade(0.70, "PAPER_CLOSED_TP", 100), _trade(0.80, "PAPER_CLOSED_SL", -40)],
        thresholds=[0.60],
    )

    bucket = result.thresholds[0]
    assert bucket.total_cost == 0
    assert bucket.net_pnl_after_costs == 60


def test_engine_does_not_mutate_trades() -> None:
    context = _trade(0.70, "PAPER_CLOSED_TP", 100)
    before = dict(context.__dict__)

    DecisionThresholdCalibrationEngine().summarize_contexts([context], thresholds=[0.60])

    assert context.__dict__ == before


def test_empty_threshold_bucket_is_safe() -> None:
    result = DecisionThresholdCalibrationEngine().summarize_contexts(
        [_trade(0.50, "PAPER_CLOSED_TP", 100)],
        thresholds=[0.85],
    )

    bucket = result.thresholds[0]
    assert bucket.total_trades == 0
    assert bucket.win_rate == 0
    assert bucket.average_decision_score is None
    assert result.best_by_net_after_costs is None


def test_non_trade_contexts_are_ignored() -> None:
    context = MarketContext()
    context.paper_trade_status = "NO_PAPER_TRADE"
    context.decision_score = 0.99

    result = DecisionThresholdCalibrationEngine().summarize_contexts([context], thresholds=[0.60])

    assert result.thresholds[0].total_trades == 0
    assert result.diagnostics["source_trades"] == 0
