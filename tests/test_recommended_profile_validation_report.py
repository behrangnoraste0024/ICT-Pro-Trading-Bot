from __future__ import annotations

from models.recommended_profile_validation import (
    RecommendedProfileValidation,
    RecommendedProfileValidationResult,
)
from reporting.recommended_profile_validation_report import format_recommended_profile_validation_report


def test_report_displays_recommended_profile_validation_section() -> None:
    candidate = RecommendedProfileValidation(
        recommended_strategy_name="profile=balanced_smc_decision_065|cost=percent",
        recommended_profile="balanced_smc_decision_065",
        recommendation_reason="selected from decision-065 research profiles",
        score_threshold=0.65,
        total_trades=5,
        wins=5,
        losses=0,
        win_rate=100.0,
        gross_net_pnl=1828.77,
        total_cost=424.53,
        net_pnl_after_costs=1404.24,
        max_drawdown=0.0,
        profit_factor=None,
        average_decision_score=0.77,
        average_execution_quality=0.79,
        baseline_strategy_name="profile=balanced_smc|cost=percent",
        baseline_net_pnl_after_costs=1000.0,
        baseline_max_drawdown=10.0,
        improvement_vs_baseline=404.24,
    )
    result = RecommendedProfileValidationResult(
        selected=candidate,
        candidates_evaluated=1,
        ranking=[candidate],
    )

    output = format_recommended_profile_validation_report(result)

    assert "===== RECOMMENDED PROFILE VALIDATION =====" in output
    assert "Recommended Strategy : profile=balanced_smc_decision_065|cost=percent" in output
    assert "Score Threshold      : 0.65" in output
    assert "Net After Costs      : 1404.24" in output
    assert "Baseline Strategy    : profile=balanced_smc|cost=percent" in output
    assert "Improvement vs Base  : 404.24" in output
    assert "Rank | Strategy | Profile | ScoreThreshold" in output


def test_report_handles_empty_validation_result() -> None:
    output = format_recommended_profile_validation_report(RecommendedProfileValidationResult())

    assert "Recommended Strategy : None" in output
    assert "Trades               : 0" in output
    assert "Candidate Ranking:" in output
