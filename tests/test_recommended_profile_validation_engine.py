from __future__ import annotations

from engine.diagnostics.recommended_profile_validation_engine import RecommendedProfileValidationEngine
from models.strategy_comparison import StrategyComparisonReport, StrategyComparisonRow


def _row(
    strategy_name: str,
    profile: str,
    net_after: float,
    max_drawdown: float = 0.0,
    win_rate: float = 100.0,
    trades: int = 5,
    threshold: float | None = None,
) -> StrategyComparisonRow:
    return StrategyComparisonRow(
        strategy_name=strategy_name,
        strategy_profile=profile,
        decision_score_threshold=threshold,
        total_trades=trades,
        wins=trades,
        losses=0,
        win_rate=win_rate,
        gross_net_pnl=net_after + 10,
        total_cost=10,
        net_pnl_after_costs=net_after,
        max_drawdown=max_drawdown,
        profit_factor=None,
        average_decision_score=0.77,
        average_execution_quality=0.79,
        cost_model="percent",
    )


def test_selects_balanced_decision_065_when_tied_with_bearish() -> None:
    report = StrategyComparisonReport(
        fixture="fixture.json",
        min_candles=50,
        strategies=[
            _row("profile=balanced_smc|cost=percent", "balanced_smc", 100),
            _row("profile=bearish_smc_decision_065|cost=percent", "bearish_smc_decision_065", 200, threshold=0.65),
            _row("profile=balanced_smc_decision_065|cost=percent", "balanced_smc_decision_065", 200, threshold=0.65),
        ],
    )

    result = RecommendedProfileValidationEngine().validate(report)

    assert result.selected is not None
    assert result.selected.recommended_profile == "balanced_smc_decision_065"
    assert result.selected.recommended_strategy_name == "profile=balanced_smc_decision_065|cost=percent"


def test_ranks_by_net_pnl_after_costs_first() -> None:
    result = RecommendedProfileValidationEngine().validate(
        [
            _row("balanced", "balanced_smc_decision_065", 100, threshold=0.65),
            _row("bearish", "bearish_smc_decision_065", 150, threshold=0.65),
        ]
    )

    assert result.ranking[0].recommended_strategy_name == "bearish"


def test_uses_drawdown_as_tie_break() -> None:
    result = RecommendedProfileValidationEngine().validate(
        [
            _row("higher_dd", "balanced_smc_decision_065", 100, max_drawdown=25, threshold=0.65),
            _row("lower_dd", "bearish_smc_decision_065", 100, max_drawdown=5, threshold=0.65),
        ]
    )

    assert result.ranking[0].recommended_strategy_name == "lower_dd"


def test_computes_improvement_vs_baseline() -> None:
    result = RecommendedProfileValidationEngine().validate(
        [
            _row("profile=balanced_smc|cost=percent", "balanced_smc", 100),
            _row("profile=balanced_smc_decision_065|cost=percent", "balanced_smc_decision_065", 175, threshold=0.65),
        ]
    )

    assert result.selected is not None
    assert result.selected.baseline_strategy_name == "profile=balanced_smc|cost=percent"
    assert result.selected.baseline_net_pnl_after_costs == 100
    assert result.selected.improvement_vs_baseline == 75


def test_handles_missing_baseline_safely() -> None:
    result = RecommendedProfileValidationEngine().validate(
        [_row("profile=balanced_smc_decision_065|cost=percent", "balanced_smc_decision_065", 175, threshold=0.65)]
    )

    assert result.selected is not None
    assert result.selected.baseline_strategy_name is None
    assert result.selected.improvement_vs_baseline is None
    assert result.diagnostics["baseline_found"] is False


def test_handles_empty_comparison_result_safely() -> None:
    result = RecommendedProfileValidationEngine().validate(
        StrategyComparisonReport(fixture="fixture.json", min_candles=50, strategies=[])
    )

    assert result.selected is None
    assert result.candidates_evaluated == 0
    assert result.ranking == []


def test_profile_name_or_threshold_can_make_candidate() -> None:
    result = RecommendedProfileValidationEngine().validate(
        [
            _row("threshold_only", "balanced_smc", 120, threshold=0.65),
            _row("ignored", "balanced_smc", 200, threshold=None),
        ]
    )

    assert result.candidates_evaluated == 1
    assert result.selected is not None
    assert result.selected.recommended_strategy_name == "threshold_only"
