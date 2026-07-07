from __future__ import annotations

import pytest

from engine.diagnostics.walk_forward_validation_engine import WalkForwardValidationEngine
from models.cost_diagnostics import CostDiagnostics, TradeCostBreakdown
from models.market_context import MarketContext


def _trade(score: float | None, status: str, pnl: float, execution_quality: float | None = 0.8) -> MarketContext:
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


def test_splits_trades_chronologically_into_four_segments() -> None:
    result = WalkForwardValidationEngine().validate_contexts(
        [
            _trade(0.9, "PAPER_CLOSED_TP", 1),
            _trade(0.9, "PAPER_CLOSED_TP", 2),
            _trade(0.9, "PAPER_CLOSED_TP", 3),
            _trade(0.9, "PAPER_CLOSED_TP", 4),
            _trade(0.9, "PAPER_CLOSED_TP", 5),
        ],
        segment_count=4,
    )

    assert [(s.start_trade_index, s.end_trade_index, s.total_trades) for s in result.segments] == [
        (1, 2, 2),
        (3, 3, 1),
        (4, 4, 1),
        (5, 5, 1),
    ]


def test_filters_trades_using_decision_score_threshold() -> None:
    result = WalkForwardValidationEngine().validate_contexts(
        [
            _trade(0.70, "PAPER_CLOSED_TP", 100),
            _trade(0.64, "PAPER_CLOSED_SL", -40),
            _trade(0.85, "PAPER_CLOSED_TP", 20),
        ],
        segment_count=1,
        score_threshold=0.65,
    )

    segment = result.segments[0]
    assert segment.total_trades == 2
    assert segment.wins == 2
    assert segment.gross_net_pnl == 120
    assert segment.average_decision_score == pytest.approx((0.70 + 0.85) / 2)


def test_excludes_missing_decision_score_and_records_diagnostics() -> None:
    result = WalkForwardValidationEngine().validate_contexts(
        [_trade(None, "PAPER_CLOSED_TP", 100), _trade(0.9, "PAPER_CLOSED_SL", -25)],
        segment_count=1,
    )

    assert result.segments[0].total_trades == 1
    assert result.segments[0].losses == 1
    assert result.diagnostics["excluded_missing_decision_score"] == 1


def test_uses_net_after_cost_when_available() -> None:
    result = WalkForwardValidationEngine().validate_contexts(
        [
            _trade(0.70, "PAPER_CLOSED_TP", 100),
            _trade(0.80, "PAPER_CLOSED_SL", -40),
            _trade(0.90, "PAPER_CLOSED_TP", 20),
        ],
        cost_diagnostics=_costs(),
        segment_count=1,
    )

    segment = result.segments[0]
    assert segment.gross_net_pnl == 80
    assert segment.total_cost == 6
    assert segment.net_pnl_after_costs == 74
    assert result.net_pnl_after_costs == 74


def test_falls_back_to_gross_pnl_when_cost_data_missing() -> None:
    result = WalkForwardValidationEngine().validate_contexts(
        [_trade(0.70, "PAPER_CLOSED_TP", 100), _trade(0.80, "PAPER_CLOSED_SL", -40)],
        segment_count=1,
    )

    assert result.segments[0].total_cost == 0
    assert result.segments[0].net_pnl_after_costs == 60


def test_segment_pass_fail_logic_works() -> None:
    result = WalkForwardValidationEngine().validate_contexts(
        [_trade(0.70, "PAPER_CLOSED_SL", -10)],
        segment_count=1,
    )

    assert result.segments[0].passed is False
    assert "NON_POSITIVE_NET_AFTER_COSTS" in result.segments[0].failure_reasons


def test_overall_pass_when_all_non_empty_segments_pass() -> None:
    result = WalkForwardValidationEngine().validate_contexts(
        [_trade(0.70, "PAPER_CLOSED_TP", 10), _trade(0.80, "PAPER_CLOSED_TP", 20)],
        segment_count=2,
    )

    assert result.validation_status == "PASS"
    assert result.passed_segments == 2
    assert result.empty_segments == 0


def test_overall_warning_when_empty_or_losing_segment_exists_but_aggregate_positive() -> None:
    result = WalkForwardValidationEngine().validate_contexts(
        [_trade(0.70, "PAPER_CLOSED_TP", 100), _trade(0.80, "PAPER_CLOSED_SL", -10)],
        segment_count=4,
    )

    assert result.validation_status == "WARNING"
    assert result.empty_segments == 2
    assert result.losing_segments == 1
    assert result.net_pnl_after_costs == 90


def test_overall_fail_when_aggregate_net_after_costs_non_positive() -> None:
    result = WalkForwardValidationEngine().validate_contexts(
        [_trade(0.70, "PAPER_CLOSED_TP", 10), _trade(0.80, "PAPER_CLOSED_SL", -20)],
        segment_count=2,
    )

    assert result.validation_status == "FAIL"
    assert result.net_pnl_after_costs == -10


def test_engine_does_not_mutate_trades() -> None:
    context = _trade(0.70, "PAPER_CLOSED_TP", 100)
    original = context.__dict__.copy()

    WalkForwardValidationEngine().validate_contexts([context], segment_count=1)

    assert context.__dict__ == original
