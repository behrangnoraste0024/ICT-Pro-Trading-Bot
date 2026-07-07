from __future__ import annotations

from dataclasses import dataclass

from engine.backtest.strategy_comparison_engine import build_recommended_decision_profile_with_cost_specs
from engine.diagnostics.multi_sample_validation_engine import MultiSampleValidationEngine
from models.multi_sample_validation import MultiSampleDefinition
from models.recommended_profile_validation import RecommendedProfileValidation, RecommendedProfileValidationResult
from models.walk_forward_validation import WalkForwardRecommendedProfileValidation


@dataclass
class _RollingResult:
    trade_outcome_contexts: list
    cost_diagnostics: object | None


class _ComparisonEngine:
    def __init__(self, raises: bool = False) -> None:
        self.raises = raises

    def run_comparison(self, **kwargs):
        if self.raises:
            raise RuntimeError("comparison failed")
        return object()


class _RecommendationEngine:
    def __init__(self, selected: RecommendedProfileValidation | None = None) -> None:
        self.selected = selected or RecommendedProfileValidation(
            recommended_strategy_name="profile=balanced_smc_decision_065|cost=percent",
            recommended_profile="balanced_smc_decision_065",
            recommendation_reason="test",
            score_threshold=0.65,
            total_trades=2,
            wins=2,
            losses=0,
            win_rate=100.0,
            gross_net_pnl=200,
            total_cost=20,
            net_pnl_after_costs=180,
            max_drawdown=0,
            profit_factor=None,
            average_decision_score=0.8,
            average_execution_quality=0.9,
            improvement_vs_baseline=50,
        )

    def validate(self, _comparison):
        return RecommendedProfileValidationResult(selected=self.selected, candidates_evaluated=1, ranking=[self.selected] if self.selected else [])


class _WalkForwardEngine:
    def __init__(self, status: str = "PASS") -> None:
        self.status = status

    def validate_contexts(self, *args, **kwargs):
        net = 180 if self.status != "FAIL" else -10
        return WalkForwardRecommendedProfileValidation(
            profile="balanced_smc_decision_065",
            strategy_name="profile=balanced_smc_decision_065|cost=percent",
            score_threshold=0.65,
            segment_count=4,
            total_trades=2,
            wins=2 if self.status != "FAIL" else 0,
            losses=0 if self.status != "FAIL" else 2,
            win_rate=100.0 if self.status != "FAIL" else 0.0,
            gross_net_pnl=200,
            total_cost=20,
            net_pnl_after_costs=net,
            max_drawdown=0,
            profitable_segments=4 if self.status == "PASS" else 1,
            losing_segments=0 if self.status == "PASS" else 1,
            empty_segments=0,
            passed_segments=4 if self.status == "PASS" else 1,
            failed_segments=0 if self.status == "PASS" else 3,
            worst_segment_net_pnl_after_costs=10,
            average_segment_net_pnl_after_costs=45,
            validation_status=self.status,
            validation_reason="test",
        )


class _RollingEngine:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def run(self, _candles):
        return _RollingResult([], None)


def _engine(path_exists=True, wf_status="PASS", raises=False) -> MultiSampleValidationEngine:
    return MultiSampleValidationEngine(
        comparison_engine=_ComparisonEngine(raises=raises),
        recommendation_engine=_RecommendationEngine(),
        walk_forward_engine=_WalkForwardEngine(wf_status),
        candles_loader=lambda _path: [],
        rolling_engine_factory=_RollingEngine,
        path_exists=lambda _path: path_exists,
    )


def _sample(path: str = "exists.json") -> MultiSampleDefinition:
    return MultiSampleDefinition("sample", path, "BTC/USDT", "15m")


def test_missing_optional_sample_returns_skipped_missing_file() -> None:
    result = _engine(path_exists=False).validate(samples=[_sample("missing.json")])

    assert result.rows[0].status == "SKIPPED_MISSING_FILE"
    assert result.skipped_samples == 1
    assert result.completed_samples == 0


def test_existing_sample_row_is_created_from_validation_results() -> None:
    result = _engine().validate(samples=[_sample()], strategy_specs=build_recommended_decision_profile_with_cost_specs())

    row = result.rows[0]
    assert row.status == "PASSED"
    assert row.recommended_profile == "balanced_smc_decision_065"
    assert row.score_threshold == 0.65
    assert row.net_pnl_after_costs == 180
    assert row.profitable_segments == 4
    assert row.improvement_vs_baseline == 50


def test_status_passed_when_walk_forward_pass() -> None:
    assert _engine(wf_status="PASS").validate(samples=[_sample()]).rows[0].status == "PASSED"


def test_status_warning_when_walk_forward_warning() -> None:
    assert _engine(wf_status="WARNING").validate(samples=[_sample()]).rows[0].status == "WARNING"


def test_status_failed_when_walk_forward_fail() -> None:
    assert _engine(wf_status="FAIL").validate(samples=[_sample()]).rows[0].status == "FAILED"


def test_error_row_created_when_sample_execution_raises() -> None:
    result = _engine(raises=True).validate(samples=[_sample()])

    row = result.rows[0]
    assert row.status == "ERROR"
    assert row.error_message == "comparison failed"
    assert result.error_samples == 1


def test_aggregate_counts_are_correct() -> None:
    engine = MultiSampleValidationEngine(
        comparison_engine=_ComparisonEngine(),
        recommendation_engine=_RecommendationEngine(),
        walk_forward_engine=_WalkForwardEngine("WARNING"),
        candles_loader=lambda _path: [],
        rolling_engine_factory=_RollingEngine,
        path_exists=lambda path: path == "exists.json",
    )

    result = engine.validate(samples=[_sample("exists.json"), _sample("missing.json")])

    assert result.total_samples == 2
    assert result.completed_samples == 1
    assert result.warning_samples == 1
    assert result.skipped_samples == 1
    assert result.recommended_profile == "balanced_smc_decision_065"
