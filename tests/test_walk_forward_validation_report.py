from __future__ import annotations

from models.walk_forward_validation import (
    WalkForwardRecommendedProfileValidation,
    WalkForwardSegmentValidation,
)
from reporting.walk_forward_validation_report import format_walk_forward_validation_report


def test_report_displays_walk_forward_validation_section() -> None:
    result = WalkForwardRecommendedProfileValidation(
        profile="balanced_smc_decision_065",
        strategy_name="profile=balanced_smc_decision_065|cost=percent",
        score_threshold=0.65,
        segment_count=4,
        total_trades=2,
        wins=2,
        losses=0,
        win_rate=100.0,
        gross_net_pnl=200,
        total_cost=20,
        net_pnl_after_costs=180,
        max_drawdown=0,
        profitable_segments=2,
        losing_segments=0,
        empty_segments=2,
        passed_segments=2,
        failed_segments=2,
        worst_segment_net_pnl_after_costs=80,
        average_segment_net_pnl_after_costs=90,
        validation_status="WARNING",
        validation_reason="empty segments remain",
        segments=[
            WalkForwardSegmentValidation(
                segment_name="segment_1",
                segment_index=1,
                start_trade_index=1,
                end_trade_index=1,
                total_trades=1,
                wins=1,
                losses=0,
                win_rate=100.0,
                gross_net_pnl=100,
                total_cost=10,
                net_pnl_after_costs=90,
                max_drawdown=0,
                average_decision_score=0.77,
                average_execution_quality=0.79,
                passed=True,
            )
        ],
    )

    output = format_walk_forward_validation_report(result)

    assert "===== WALK-FORWARD RECOMMENDED PROFILE VALIDATION =====" in output
    assert "Profile              : balanced_smc_decision_065" in output
    assert "Score Threshold      : 0.65" in output
    assert "Validation Status    : WARNING" in output
    assert "Segment | Trades | W/L | Win%" in output
    assert "segment_1 | 1 | 1/0 | 100.00 | 90.00" in output
