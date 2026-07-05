from __future__ import annotations

import pytest

from engine.diagnostics.decision_threshold_robustness_engine import DecisionThresholdRobustnessEngine
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


def test_trades_are_split_chronologically_into_expected_segments() -> None:
    result = DecisionThresholdRobustnessEngine().summarize_contexts(
        [
            _trade(0.9, "PAPER_CLOSED_TP", 1),
            _trade(0.9, "PAPER_CLOSED_TP", 2),
            _trade(0.9, "PAPER_CLOSED_TP", 3),
            _trade(0.9, "PAPER_CLOSED_TP", 4),
            _trade(0.9, "PAPER_CLOSED_TP", 5),
        ],
        thresholds=[0.6],
        segment_count=4,
    )

    assert [(s.start_trade_index, s.end_trade_index, s.total_source_trades) for s in result.segment_summaries] == [
        (1, 2, 2),
        (3, 3, 1),
        (4, 4, 1),
        (5, 5, 1),
    ]


def test_threshold_bucket_includes_only_segment_trades_at_or_above_threshold() -> None:
    result = DecisionThresholdRobustnessEngine().summarize_contexts(
        [
            _trade(0.70, "PAPER_CLOSED_TP", 100, 0.8),
            _trade(0.64, "PAPER_CLOSED_SL", -40, 0.6),
            _trade(0.85, "PAPER_CLOSED_TP", 20, 0.9),
        ],
        thresholds=[0.65],
        segment_count=1,
    )

    bucket = result.segment_summaries[0].buckets[0]
    assert bucket.total_trades == 2
    assert bucket.wins == 2
    assert bucket.gross_net_pnl == 120
    assert bucket.average_decision_score == pytest.approx((0.70 + 0.85) / 2)


def test_missing_decision_score_trades_are_excluded_and_counted() -> None:
    result = DecisionThresholdRobustnessEngine().summarize_contexts(
        [_trade(None, "PAPER_CLOSED_TP", 100), _trade(0.9, "PAPER_CLOSED_SL", -25)],
        thresholds=[0.60],
        segment_count=1,
    )

    bucket = result.segment_summaries[0].buckets[0]
    assert bucket.total_trades == 1
    assert bucket.losses == 1
    assert result.diagnostics["trades_missing_decision_score"] == 1


def test_net_pnl_after_costs_is_used_when_cost_data_exists() -> None:
    result = DecisionThresholdRobustnessEngine().summarize_contexts(
        [
            _trade(0.70, "PAPER_CLOSED_TP", 100),
            _trade(0.80, "PAPER_CLOSED_SL", -40),
            _trade(0.50, "PAPER_CLOSED_TP", 20),
        ],
        cost_diagnostics=_costs(),
        thresholds=[0.60],
        segment_count=1,
    )

    bucket = result.segment_summaries[0].buckets[0]
    assert bucket.gross_net_pnl == 60
    assert bucket.total_cost == 6
    assert bucket.net_pnl_after_costs == 54
    assert result.threshold_stability[0.60]["total_net_pnl_after_costs"] == 54


def test_gross_pnl_fallback_works_when_cost_data_is_missing() -> None:
    result = DecisionThresholdRobustnessEngine().summarize_contexts(
        [_trade(0.70, "PAPER_CLOSED_TP", 100), _trade(0.80, "PAPER_CLOSED_SL", -40)],
        thresholds=[0.60],
        segment_count=1,
    )

    bucket = result.segment_summaries[0].buckets[0]
    assert bucket.total_cost == 0
    assert bucket.net_pnl_after_costs == 60


def test_empty_segments_are_handled_safely() -> None:
    result = DecisionThresholdRobustnessEngine().summarize_contexts(
        [_trade(0.90, "PAPER_CLOSED_TP", 100)],
        thresholds=[0.60],
        segment_count=4,
    )

    assert result.segment_count == 4
    assert [(s.start_trade_index, s.end_trade_index, s.total_source_trades) for s in result.segment_summaries] == [
        (1, 1, 1),
        (0, 0, 0),
        (0, 0, 0),
        (0, 0, 0),
    ]
    assert result.segment_summaries[1].buckets[0].total_trades == 0


def test_engine_does_not_mutate_trades() -> None:
    context = _trade(0.70, "PAPER_CLOSED_TP", 100)
    before = dict(context.__dict__)

    DecisionThresholdRobustnessEngine().summarize_contexts([context], thresholds=[0.60], segment_count=1)

    assert context.__dict__ == before


def test_best_overall_threshold_chooses_highest_total_net_after_costs() -> None:
    result = DecisionThresholdRobustnessEngine().summarize_contexts(
        [
            _trade(0.90, "PAPER_CLOSED_TP", 100),
            _trade(0.70, "PAPER_CLOSED_SL", -70),
        ],
        thresholds=[0.60, 0.80],
        segment_count=1,
    )

    assert result.best_overall_threshold == 0.80


def test_robust_threshold_uses_stability_tie_break_rules() -> None:
    result = DecisionThresholdRobustnessEngine().summarize_contexts(
        [
            _trade(0.90, "PAPER_CLOSED_TP", 100),
            _trade(0.70, "PAPER_CLOSED_SL", -10),
            _trade(0.90, "PAPER_CLOSED_SL", -30),
            _trade(0.70, "PAPER_CLOSED_TP", 50),
        ],
        thresholds=[0.60, 0.80],
        segment_count=2,
    )

    assert result.threshold_stability[0.60]["profitable_segments"] == 2
    assert result.threshold_stability[0.80]["profitable_segments"] == 1
    assert result.robust_threshold == 0.60


def test_empty_source_has_no_best_thresholds() -> None:
    result = DecisionThresholdRobustnessEngine().summarize_contexts([], thresholds=[0.60], segment_count=2)

    assert result.best_overall_threshold is None
    assert result.robust_threshold is None
    assert result.threshold_stability[0.60]["total_trades"] == 0
