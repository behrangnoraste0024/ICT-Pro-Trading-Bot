from __future__ import annotations

import inspect
from dataclasses import asdict

import engine.backtest.historical_simulation_adapter as adapter_module
import models.historical_simulation as simulation_models
from engine.backtest.historical_simulation_adapter import (
    HistoricalSimulationAdapter,
    simulate_historical_signals,
)
from models.strategy_signal import StrategySignalResult


def _signal(
    *,
    status: str = "SIGNAL",
    direction: str = "LONG",
    confidence: float = 0.9,
    blockers: list[str] | None = None,
) -> StrategySignalResult:
    return StrategySignalResult(
        signal_status=status,
        direction=direction,
        confidence_score=confidence,
        reasons=["advisory evidence aligned"],
        blockers=[] if blockers is None else blockers,
        source_evidence={"trend": direction, "source": {"nested": True}},
    )


def test_historical_simulation_output_is_deterministic() -> None:
    historical_data = [
        {"timestamp": "2026-01-01T00:00:00Z", "open": 100, "high": 105, "low": 99, "close": 104},
        {"timestamp": "2026-01-01T00:01:00Z", "open": 104, "high": 106, "low": 103, "close": 105},
    ]
    signals = [_signal(direction="LONG"), _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0)]

    first = simulate_historical_signals(historical_data, signals)
    second = simulate_historical_signals(historical_data, signals)

    assert first == second
    assert asdict(first) == asdict(second)


def test_historical_simulation_records_advisory_decisions_only() -> None:
    result = HistoricalSimulationAdapter().simulate(
        [{"close": 101}, {"close": 99}, {"close": 100}],
        [
            _signal(direction="LONG", confidence=0.8),
            _signal(direction="SHORT", confidence=0.6),
            _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0, blockers=["directional context is not aligned"]),
        ],
    )

    assert [record.decision_status for record in result.records] == [
        "SIMULATED_SIGNAL",
        "SIMULATED_SIGNAL",
        "NO_DECISION",
    ]
    assert [record.direction for record in result.records] == ["LONG", "SHORT", "NONE"]
    assert result.diagnostics.total_records == 3
    assert result.diagnostics.simulated_signal_records == 2
    assert result.diagnostics.no_decision_records == 1
    assert result.diagnostics.long_records == 1
    assert result.diagnostics.short_records == 1
    assert result.diagnostics.blocked_records == 1
    assert result.diagnostics.average_confidence_score == 0.7


def test_mark_to_market_outcomes_are_directional_and_stable() -> None:
    result = HistoricalSimulationAdapter().simulate(
        [{"close": 100}, {"close": 105}, {"close": 103}, {"close": 103}],
        [
            _signal(direction="LONG"),
            _signal(direction="SHORT"),
            _signal(direction="LONG"),
            _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0),
        ],
    )

    assert [record.directional_outcome for record in result.records] == [
        "WIN",
        "WIN",
        "FLAT",
        "NOT_EVALUATED",
    ]
    assert [record.raw_point_movement for record in result.records] == [5.0, 2.0, 0.0, 0.0]
    assert [record.percentage_movement for record in result.records] == [5.0, 1.9048, 0.0, 0.0]
    assert result.diagnostics.win_count == 2
    assert result.diagnostics.loss_count == 0
    assert result.diagnostics.flat_count == 1
    assert result.diagnostics.expectancy == 2.3333
    assert result.diagnostics.equity_curve == [5.0, 7.0, 7.0, 7.0]
    assert result.diagnostics.max_drawdown == 0.0
    assert result.diagnostics.total_unitless_return == 7.0
    assert result.diagnostics.win_rate == 66.6667
    assert result.diagnostics.loss_rate == 0.0
    assert result.diagnostics.flat_rate == 33.3333
    assert result.diagnostics.profit_factor == 7.0
    assert result.diagnostics.average_win == 3.5
    assert result.diagnostics.average_loss == 0.0
    assert result.diagnostics.risk_adjusted_diagnostic_ratio == 7.0


def test_mark_to_market_drawdown_is_deterministic() -> None:
    result = HistoricalSimulationAdapter().simulate(
        [{"close": 100}, {"close": 105}, {"close": 103}, {"close": 106}],
        [
            _signal(direction="LONG"),
            _signal(direction="LONG"),
            _signal(direction="SHORT"),
            _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0),
        ],
    )

    assert [record.raw_point_movement for record in result.records] == [5.0, -2.0, -3.0, 0.0]
    assert [record.directional_outcome for record in result.records] == [
        "WIN",
        "LOSS",
        "LOSS",
        "NOT_EVALUATED",
    ]
    assert result.diagnostics.win_count == 1
    assert result.diagnostics.loss_count == 2
    assert result.diagnostics.flat_count == 0
    assert result.diagnostics.expectancy == 0.0
    assert result.diagnostics.equity_curve == [5.0, 3.0, 0.0, 0.0]
    assert result.diagnostics.max_drawdown == 5.0
    assert result.diagnostics.total_unitless_return == 0.0
    assert result.diagnostics.win_rate == 33.3333
    assert result.diagnostics.loss_rate == 66.6667
    assert result.diagnostics.flat_rate == 0.0
    assert result.diagnostics.profit_factor == 1.0
    assert result.diagnostics.average_win == 5.0
    assert result.diagnostics.average_loss == -2.5
    assert result.diagnostics.risk_adjusted_diagnostic_ratio == 0.0


def test_aggregate_performance_metrics_are_deterministic() -> None:
    historical_data = [{"close": 100}, {"close": 104}, {"close": 101}, {"close": 101}]
    signals = [
        _signal(direction="LONG"),
        _signal(direction="LONG"),
        _signal(direction="SHORT"),
        _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0),
    ]

    first = HistoricalSimulationAdapter().simulate(historical_data, signals)
    second = HistoricalSimulationAdapter().simulate(historical_data, signals)

    assert first.diagnostics == second.diagnostics
    assert asdict(first.diagnostics) == asdict(second.diagnostics)
    assert first.diagnostics.total_unitless_return == 1.0
    assert first.diagnostics.win_rate == 33.3333
    assert first.diagnostics.loss_rate == 33.3333
    assert first.diagnostics.flat_rate == 33.3333
    assert first.diagnostics.profit_factor == 1.3333
    assert first.diagnostics.average_win == 4.0
    assert first.diagnostics.average_loss == -3.0
    assert first.diagnostics.risk_adjusted_diagnostic_ratio == 0.3333


def test_existing_simulation_records_can_be_diagnosed_without_mutation() -> None:
    adapter = HistoricalSimulationAdapter()
    baseline = adapter.simulate(
        [{"close": 100}, {"close": 100}],
        [_signal(direction="LONG"), _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0)],
    )
    original_records = asdict(baseline)
    original_diagnostics = asdict(baseline.diagnostics)
    historical_rows = [{"close": 100}, {"close": 110}]
    original_rows = [dict(row) for row in historical_rows]

    diagnosed = adapter.diagnose_records(historical_rows, baseline.records)
    repeated = adapter.diagnose_records(historical_rows, baseline.records)

    assert diagnosed == repeated
    assert diagnosed.records[0].raw_point_movement == 10.0
    assert diagnosed.records[0].percentage_movement == 10.0
    assert diagnosed.diagnostics.equity_curve == [10.0, 10.0]
    assert diagnosed.diagnostics.total_unitless_return == 10.0
    assert diagnosed.diagnostics.win_rate == 100.0
    assert diagnosed.diagnostics.risk_adjusted_diagnostic_ratio == 10.0
    assert asdict(baseline) == original_records
    assert asdict(baseline.diagnostics) == original_diagnostics
    assert historical_rows == original_rows


def test_report_rows_are_deterministic_and_index_stable() -> None:
    result = HistoricalSimulationAdapter().simulate(
        [{"close": 100}, {"close": 105}, {"close": 103}, {"close": 103}],
        [
            _signal(direction="LONG"),
            _signal(direction="SHORT"),
            _signal(direction="LONG"),
            _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0),
        ],
    )

    first = HistoricalSimulationAdapter().build_report(result)
    second = HistoricalSimulationAdapter().build_report(result)

    assert first == second
    assert asdict(first) == asdict(second)
    assert [row.index for row in first.rows] == [0, 1, 2, 3]
    assert [row.direction for row in first.rows] == ["LONG", "SHORT", "LONG", "NONE"]
    assert [row.decision_status for row in first.rows] == [
        "SIMULATED_SIGNAL",
        "SIMULATED_SIGNAL",
        "SIMULATED_SIGNAL",
        "NO_DECISION",
    ]
    assert [row.directional_outcome for row in first.rows] == [
        "WIN",
        "WIN",
        "FLAT",
        "NOT_EVALUATED",
    ]
    assert [row.raw_point_movement for row in first.rows] == [5.0, 2.0, 0.0, 0.0]
    assert [row.percentage_movement for row in first.rows] == [5.0, 1.9048, 0.0, 0.0]
    assert [row.confidence_score for row in first.rows] == [0.9, 0.9, 0.9, 0.0]
    assert [row.blockers_count for row in first.rows] == [0, 0, 0, 0]
    assert [row.reasons_count for row in first.rows] == [1, 1, 1, 1]


def test_report_summary_metadata_comes_from_existing_diagnostics() -> None:
    result = HistoricalSimulationAdapter().simulate(
        [{"close": 100}, {"close": 105}, {"close": 103}, {"close": 106}],
        [
            _signal(direction="LONG"),
            _signal(direction="LONG"),
            _signal(direction="SHORT"),
            _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0),
        ],
    )

    summary = HistoricalSimulationAdapter().build_report(result)

    assert summary.total_rows == 4
    assert summary.simulated_rows == result.diagnostics.simulated_signal_records
    assert summary.no_decision_rows == result.diagnostics.no_decision_records
    assert summary.total_unitless_return == result.diagnostics.total_unitless_return
    assert summary.win_rate == result.diagnostics.win_rate
    assert summary.loss_rate == result.diagnostics.loss_rate
    assert summary.flat_rate == result.diagnostics.flat_rate
    assert summary.profit_factor == result.diagnostics.profit_factor
    assert summary.expectancy == result.diagnostics.expectancy
    assert summary.max_drawdown == result.diagnostics.max_drawdown
    assert summary.risk_adjusted_diagnostic_ratio == result.diagnostics.risk_adjusted_diagnostic_ratio


def test_report_preserves_mixed_record_sequence_by_index_without_mutation() -> None:
    adapter = HistoricalSimulationAdapter()
    result = adapter.simulate(
        [{"close": 100}, {"close": 100}, {"close": 98}],
        [
            _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0, blockers=["blocked"]),
            _signal(direction="SHORT"),
            _signal(direction="LONG"),
        ],
    )
    reordered_result = type(result)(
        records=[result.records[2], result.records[0], result.records[1]],
        diagnostics=result.diagnostics,
    )
    original_result = asdict(reordered_result)
    original_records = [asdict(record) for record in reordered_result.records]
    original_diagnostics = asdict(reordered_result.diagnostics)

    summary = adapter.build_report(reordered_result)
    repeated = adapter.build_report(reordered_result)

    assert summary == repeated
    assert [row.index for row in summary.rows] == [0, 1, 2]
    assert [row.decision_status for row in summary.rows] == [
        "NO_DECISION",
        "SIMULATED_SIGNAL",
        "SIMULATED_SIGNAL",
    ]
    assert summary.rows[0].blockers_count == 1
    assert summary.rows[0].directional_outcome == "NOT_EVALUATED"
    assert asdict(reordered_result) == original_result
    assert [asdict(record) for record in reordered_result.records] == original_records
    assert asdict(reordered_result.diagnostics) == original_diagnostics


def test_replay_timeline_is_deterministic_and_index_stable() -> None:
    result = HistoricalSimulationAdapter().simulate(
        [{"close": 100}, {"close": 105}, {"close": 103}, {"close": 103}],
        [
            _signal(direction="LONG"),
            _signal(direction="SHORT"),
            _signal(direction="LONG"),
            _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0),
        ],
    )

    first = HistoricalSimulationAdapter().build_replay(result)
    second = HistoricalSimulationAdapter().build_replay(result)

    assert first == second
    assert asdict(first) == asdict(second)
    assert [step.step_index for step in first.steps] == [0, 1, 2, 3]
    assert [step.record_index for step in first.steps] == [0, 1, 2, 3]
    assert [step.direction for step in first.steps] == ["LONG", "SHORT", "LONG", "NONE"]
    assert [step.decision_status for step in first.steps] == [
        "SIMULATED_SIGNAL",
        "SIMULATED_SIGNAL",
        "SIMULATED_SIGNAL",
        "NO_DECISION",
    ]
    assert [step.directional_outcome for step in first.steps] == [
        "WIN",
        "WIN",
        "FLAT",
        "NOT_EVALUATED",
    ]
    assert [step.raw_point_movement for step in first.steps] == [5.0, 2.0, 0.0, 0.0]
    assert [step.percentage_movement for step in first.steps] == [5.0, 1.9048, 0.0, 0.0]
    assert [step.confidence_score for step in first.steps] == [0.9, 0.9, 0.9, 0.0]
    assert [step.blockers_count for step in first.steps] == [0, 0, 0, 0]
    assert [step.reasons_count for step in first.steps] == [1, 1, 1, 1]
    assert [step.cumulative_diagnostic_value for step in first.steps] == [5.0, 7.0, 7.0, 7.0]
    assert [step.cumulative_equity_value for step in first.steps] == result.diagnostics.equity_curve
    assert first.total_steps == 4
    assert first.simulated_steps == 3
    assert first.no_decision_steps == 1
    assert first.ending_diagnostic_value == 7.0
    assert first.ending_equity_value == 7.0


def test_replay_preserves_reordered_records_by_original_index_without_mutation() -> None:
    adapter = HistoricalSimulationAdapter()
    result = adapter.simulate(
        [{"close": 100}, {"close": 100}, {"close": 98}],
        [
            _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0, blockers=["blocked"]),
            _signal(direction="SHORT"),
            _signal(direction="LONG"),
        ],
    )
    reordered_result = type(result)(
        records=[result.records[2], result.records[0], result.records[1]],
        diagnostics=result.diagnostics,
    )
    report = adapter.build_report(reordered_result)
    original_result = asdict(reordered_result)
    original_report = asdict(report)

    replay = adapter.build_replay(reordered_result)
    repeated = adapter.build_replay(reordered_result)

    assert replay == repeated
    assert [step.step_index for step in replay.steps] == [0, 1, 2]
    assert [step.record_index for step in replay.steps] == [0, 1, 2]
    assert [step.decision_status for step in replay.steps] == [
        "NO_DECISION",
        "SIMULATED_SIGNAL",
        "SIMULATED_SIGNAL",
    ]
    assert [step.directional_outcome for step in replay.steps] == [
        "NOT_EVALUATED",
        "WIN",
        "FLAT",
    ]
    assert [step.cumulative_diagnostic_value for step in replay.steps] == [0.0, 2.0, 2.0]
    assert [step.cumulative_equity_value for step in replay.steps] == result.diagnostics.equity_curve
    assert replay.steps[0].blockers_count == 1
    assert replay.steps[0].reasons_count == 1
    assert asdict(reordered_result) == original_result
    assert asdict(report) == original_report


def test_replay_empty_result_is_deterministic_diagnostic_summary() -> None:
    adapter = HistoricalSimulationAdapter()
    result = adapter.simulate([], [])

    replay = adapter.build_replay(result)
    repeated = adapter.build_replay(result)

    assert replay == repeated
    assert replay.steps == []
    assert replay.total_steps == 0
    assert replay.simulated_steps == 0
    assert replay.no_decision_steps == 0
    assert replay.ending_diagnostic_value == 0.0
    assert replay.ending_equity_value == 0.0


def test_outcome_analytics_summary_is_deterministic_and_uses_existing_outputs() -> None:
    result = HistoricalSimulationAdapter().simulate(
        [{"close": 100}, {"close": 105}, {"close": 103}, {"close": 103}],
        [
            _signal(direction="LONG"),
            _signal(direction="SHORT"),
            _signal(direction="LONG"),
            _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0),
        ],
    )

    first = HistoricalSimulationAdapter().build_outcome_analytics(result)
    second = HistoricalSimulationAdapter().build_outcome_analytics(result)

    assert first == second
    assert asdict(first) == asdict(second)
    assert first.decision_status_counts == {"NO_DECISION": 1, "SIMULATED_SIGNAL": 3}
    assert first.direction_counts == {"LONG": 2, "NONE": 1, "SHORT": 1}
    assert first.outcome_counts == {"FLAT": 1, "NOT_EVALUATED": 1, "WIN": 2}
    assert first.simulated_ratio == 75.0
    assert first.no_decision_ratio == 25.0
    assert first.confidence_minimum == 0.9
    assert first.confidence_maximum == 0.9
    assert first.confidence_average == 0.9
    assert first.movement_minimum == 0.0
    assert first.movement_maximum == 5.0
    assert first.movement_average == 2.3333
    assert first.movement_total == 7.0
    assert first.blockers_total == 0
    assert first.blockers_maximum == 0
    assert first.blockers_average == 0.0
    assert first.reasons_total == 4
    assert first.reasons_maximum == 1
    assert first.reasons_average == 1.0
    assert first.replay_ending_diagnostic_value == 7.0
    assert first.replay_ending_equity_value == 7.0


def test_outcome_analytics_preserves_mixed_decision_inputs_without_mutation() -> None:
    adapter = HistoricalSimulationAdapter()
    result = adapter.simulate(
        [{"close": 100}, {"close": 100}, {"close": 98}],
        [
            _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0, blockers=["blocked"]),
            _signal(direction="SHORT", confidence=0.7),
            _signal(direction="LONG", confidence=0.5),
        ],
    )
    report = adapter.build_report(result)
    replay = adapter.build_replay(result)
    original_result = asdict(result)
    original_report = asdict(report)
    original_replay = asdict(replay)

    analytics = adapter.build_outcome_analytics(result)
    repeated = adapter.build_outcome_analytics(result)

    assert analytics == repeated
    assert analytics.decision_status_counts == {"NO_DECISION": 1, "SIMULATED_SIGNAL": 2}
    assert analytics.direction_counts == {"LONG": 1, "NONE": 1, "SHORT": 1}
    assert analytics.outcome_counts == {"FLAT": 1, "NOT_EVALUATED": 1, "WIN": 1}
    assert analytics.simulated_ratio == 66.6667
    assert analytics.no_decision_ratio == 33.3333
    assert analytics.confidence_minimum == 0.5
    assert analytics.confidence_maximum == 0.7
    assert analytics.confidence_average == 0.6
    assert analytics.movement_minimum == 0.0
    assert analytics.movement_maximum == 2.0
    assert analytics.movement_average == 1.0
    assert analytics.movement_total == 2.0
    assert analytics.blockers_total == 1
    assert analytics.blockers_maximum == 1
    assert analytics.blockers_average == 0.3333
    assert analytics.reasons_total == 3
    assert analytics.reasons_maximum == 1
    assert analytics.reasons_average == 1.0
    assert analytics.replay_ending_diagnostic_value == replay.ending_diagnostic_value
    assert analytics.replay_ending_equity_value == replay.ending_equity_value
    assert asdict(result) == original_result
    assert asdict(report) == original_report
    assert asdict(replay) == original_replay


def test_outcome_analytics_empty_result_is_deterministic_zero_summary() -> None:
    adapter = HistoricalSimulationAdapter()
    result = adapter.simulate([], [])

    analytics = adapter.build_outcome_analytics(result)
    repeated = adapter.build_outcome_analytics(result)

    assert analytics == repeated
    assert analytics.decision_status_counts == {}
    assert analytics.direction_counts == {}
    assert analytics.outcome_counts == {}
    assert analytics.simulated_ratio == 0.0
    assert analytics.no_decision_ratio == 0.0
    assert analytics.confidence_minimum == 0.0
    assert analytics.confidence_maximum == 0.0
    assert analytics.confidence_average == 0.0
    assert analytics.movement_minimum == 0.0
    assert analytics.movement_maximum == 0.0
    assert analytics.movement_average == 0.0
    assert analytics.movement_total == 0
    assert analytics.blockers_total == 0
    assert analytics.blockers_maximum == 0
    assert analytics.blockers_average == 0.0
    assert analytics.reasons_total == 0
    assert analytics.reasons_maximum == 0
    assert analytics.reasons_average == 0.0
    assert analytics.replay_ending_diagnostic_value == 0.0
    assert analytics.replay_ending_equity_value == 0.0


def test_parameter_sweep_summary_is_deterministic_and_ranked_by_existing_metrics() -> None:
    adapter = HistoricalSimulationAdapter()
    tied_a = adapter.simulate(
        [{"close": 100}, {"close": 105}, {"close": 103}, {"close": 103}],
        [
            _signal(direction="LONG"),
            _signal(direction="SHORT"),
            _signal(direction="LONG"),
            _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0),
        ],
    )
    tied_b = adapter.simulate(
        [{"close": 100}, {"close": 105}, {"close": 103}, {"close": 103}],
        [
            _signal(direction="LONG"),
            _signal(direction="SHORT"),
            _signal(direction="LONG"),
            _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0),
        ],
    )
    lower_ranked = adapter.simulate(
        [{"close": 100}, {"close": 105}, {"close": 103}, {"close": 106}],
        [
            _signal(direction="LONG"),
            _signal(direction="LONG"),
            _signal(direction="SHORT"),
            _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0),
        ],
    )

    first = adapter.build_parameter_sweep(
        {
            "candidate_b": tied_b,
            "drawdown_case": lower_ranked,
            "candidate_a": tied_a,
        }
    )
    second = adapter.build_parameter_sweep(
        {
            "drawdown_case": lower_ranked,
            "candidate_b": tied_b,
            "candidate_a": tied_a,
        }
    )

    assert first == second
    assert asdict(first) == asdict(second)
    assert first.candidate_count == 3
    assert [candidate.candidate_id for candidate in first.candidates] == [
        "candidate_a",
        "candidate_b",
        "drawdown_case",
    ]
    assert [candidate.rank for candidate in first.candidates] == [1, 2, 3]
    assert first.best_candidate_id == "candidate_a"
    assert first.worst_candidate_id == "drawdown_case"
    assert first.ranking_metric == (
        "total_return_desc_drawdown_asc_profit_factor_desc_win_rate_desc_expectancy_desc_candidate_id_asc"
    )
    assert first.candidates[0].total_unitless_return == tied_a.diagnostics.total_unitless_return
    assert first.candidates[0].max_drawdown == tied_a.diagnostics.max_drawdown
    assert first.candidates[0].profit_factor == tied_a.diagnostics.profit_factor
    assert first.candidates[0].win_rate == tied_a.diagnostics.win_rate
    assert first.candidates[0].expectancy == tied_a.diagnostics.expectancy
    assert first.candidates[0].confidence_average == adapter.build_outcome_analytics(tied_a).confidence_average
    assert first.candidates[0].movement_average == adapter.build_outcome_analytics(tied_a).movement_average
    assert first.candidates[0].movement_total == adapter.build_outcome_analytics(tied_a).movement_total
    assert first.candidates[0].replay_ending_diagnostic_value == adapter.build_replay(tied_a).ending_diagnostic_value
    assert first.candidates[0].replay_ending_equity_value == adapter.build_replay(tied_a).ending_equity_value


def test_parameter_sweep_preserves_inputs_and_sequence_tie_ordering() -> None:
    adapter = HistoricalSimulationAdapter()
    alpha = adapter.simulate(
        [{"close": 100}, {"close": 101}],
        [_signal(direction="LONG", confidence=0.6), _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0)],
    )
    beta = adapter.simulate(
        [{"close": 100}, {"close": 101}],
        [_signal(direction="LONG", confidence=0.6), _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0)],
    )
    original_alpha = asdict(alpha)
    original_beta = asdict(beta)
    original_analytics = asdict(adapter.build_outcome_analytics(alpha))

    summary = adapter.build_parameter_sweep([("beta", beta), ("alpha", alpha)])
    repeated = adapter.build_parameter_sweep([("alpha", alpha), ("beta", beta)])

    assert summary == repeated
    assert [candidate.candidate_id for candidate in summary.candidates] == ["alpha", "beta"]
    assert [candidate.rank for candidate in summary.candidates] == [1, 2]
    assert summary.best_candidate_id == "alpha"
    assert summary.worst_candidate_id == "alpha"
    assert asdict(alpha) == original_alpha
    assert asdict(beta) == original_beta
    assert asdict(adapter.build_outcome_analytics(alpha)) == original_analytics


def test_parameter_sweep_empty_and_duplicate_candidates_are_deterministic() -> None:
    adapter = HistoricalSimulationAdapter()

    empty = adapter.build_parameter_sweep([])
    repeated_empty = adapter.build_parameter_sweep({})

    assert empty == repeated_empty
    assert empty.candidates == []
    assert empty.candidate_count == 0
    assert empty.best_candidate_id == ""
    assert empty.worst_candidate_id == ""

    result = adapter.simulate([{"close": 100}], [_signal()])

    try:
        adapter.build_parameter_sweep([("duplicate", result), ("duplicate", result)])
    except ValueError as exc:
        assert str(exc) == "candidate identifiers must be unique"
    else:
        raise AssertionError("expected ValueError for duplicate candidate identifiers")


def test_constraint_eligibility_is_deterministic_and_reports_stable_reasons() -> None:
    adapter = HistoricalSimulationAdapter()
    strong = adapter.simulate(
        [{"close": 100}, {"close": 105}, {"close": 103}, {"close": 103}],
        [
            _signal(direction="LONG"),
            _signal(direction="SHORT"),
            _signal(direction="LONG"),
            _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0),
        ],
    )
    weak = adapter.simulate(
        [{"close": 100}, {"close": 105}, {"close": 103}, {"close": 106}],
        [
            _signal(direction="LONG"),
            _signal(direction="LONG"),
            _signal(direction="SHORT"),
            _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0),
        ],
    )
    sweep = adapter.build_parameter_sweep({"weak": weak, "strong": strong})
    constraints = {
        "min_win_rate": 50.0,
        "min_total_unitless_return": 1.0,
        "min_profit_factor": 2.0,
        "min_movement_total": 1.0,
        "min_confidence_average": 0.8,
        "max_drawdown": 1.0,
    }

    first = adapter.build_constraint_eligibility(sweep, constraints)
    second = adapter.build_constraint_eligibility(sweep, dict(reversed(list(constraints.items()))))

    assert first == second
    assert asdict(first) == asdict(second)
    assert first.candidate_count == 2
    assert first.eligible_count == 1
    assert first.ineligible_count == 1
    assert first.constraint_names == [
        "max_drawdown",
        "min_confidence_average",
        "min_movement_total",
        "min_profit_factor",
        "min_total_unitless_return",
        "min_win_rate",
    ]
    assert [diagnostic.candidate_id for diagnostic in first.diagnostics] == ["strong", "weak"]
    assert first.diagnostics[0].is_eligible is True
    assert first.diagnostics[0].passed_constraints == first.constraint_names
    assert first.diagnostics[0].failed_constraints == []
    assert first.diagnostics[1].is_eligible is False
    assert first.diagnostics[1].passed_constraints == ["min_confidence_average"]
    assert first.diagnostics[1].failed_constraints == [
        "max_drawdown",
        "min_movement_total",
        "min_profit_factor",
        "min_total_unitless_return",
        "min_win_rate",
    ]
    assert first.diagnostics[1].reasons == [
        "max_drawdown failed: 5.0 must be at most 1.0",
        "min_confidence_average passed: 0.9 must be at least 0.8",
        "min_movement_total failed: 0.0 must be at least 1.0",
        "min_profit_factor failed: 1.0 must be at least 2.0",
        "min_total_unitless_return failed: 0.0 must be at least 1.0",
        "min_win_rate failed: 33.3333 must be at least 50.0",
    ]


def test_constraint_eligibility_preserves_sweep_and_handles_empty_constraints() -> None:
    adapter = HistoricalSimulationAdapter()
    result = adapter.simulate(
        [{"close": 100}, {"close": 101}],
        [_signal(direction="LONG"), _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0)],
    )
    sweep = adapter.build_parameter_sweep({"candidate": result})
    original_sweep = asdict(sweep)

    summary = adapter.build_constraint_eligibility(sweep, {})
    repeated = adapter.build_constraint_eligibility(sweep, {})

    assert summary == repeated
    assert summary.candidate_count == 1
    assert summary.eligible_count == 1
    assert summary.ineligible_count == 0
    assert summary.constraint_names == []
    assert summary.diagnostics[0].candidate_id == "candidate"
    assert summary.diagnostics[0].is_eligible is True
    assert summary.diagnostics[0].passed_constraints == []
    assert summary.diagnostics[0].failed_constraints == []
    assert summary.diagnostics[0].reasons == []
    assert asdict(sweep) == original_sweep


def test_constraint_eligibility_rejects_unsupported_static_constraints() -> None:
    adapter = HistoricalSimulationAdapter()
    result = adapter.simulate([{"close": 100}], [_signal()])
    sweep = adapter.build_parameter_sweep({"candidate": result})

    try:
        adapter.build_constraint_eligibility(sweep, {"unsupported_constraint": 1.0})
    except ValueError as exc:
        assert str(exc) == "unsupported diagnostic constraints: unsupported_constraint"
    else:
        raise AssertionError("expected ValueError for unsupported diagnostic constraint")


def test_constraint_failure_distribution_summary_is_deterministic_and_stably_ordered() -> None:
    adapter = HistoricalSimulationAdapter()
    eligibility = simulation_models.HistoricalSimulationConstraintEligibilitySummary(
        diagnostics=[
            simulation_models.HistoricalSimulationConstraintDiagnostic(
                candidate_id="candidate_b",
                is_eligible=False,
                passed_constraints=["min_profit_factor"],
                failed_constraints=["min_win_rate", "max_drawdown"],
                reasons=[
                    "min_win_rate failed: 25.0 must be at least 50.0",
                    "max_drawdown failed: 2.0 must be at most 1.0",
                    "min_profit_factor passed: 2.5 must be at least 2.0",
                ],
            ),
            simulation_models.HistoricalSimulationConstraintDiagnostic(
                candidate_id="candidate_a",
                is_eligible=False,
                passed_constraints=["max_drawdown"],
                failed_constraints=["min_profit_factor", "min_win_rate"],
                reasons=[
                    "min_profit_factor failed: 1.0 must be at least 2.0",
                    "max_drawdown passed: 0.5 must be at most 1.0",
                    "min_win_rate failed: 40.0 must be at least 50.0",
                ],
            ),
            simulation_models.HistoricalSimulationConstraintDiagnostic(
                candidate_id="candidate_c",
                is_eligible=True,
                passed_constraints=["min_win_rate", "min_profit_factor", "max_drawdown"],
                failed_constraints=[],
                reasons=[
                    "min_profit_factor passed: 3.0 must be at least 2.0",
                    "min_win_rate passed: 75.0 must be at least 50.0",
                    "max_drawdown passed: 0.2 must be at most 1.0",
                ],
            ),
        ],
        candidate_count=3,
        eligible_count=1,
        ineligible_count=2,
        constraint_names=["min_win_rate", "min_profit_factor", "max_drawdown"],
    )
    repeated_eligibility = simulation_models.HistoricalSimulationConstraintEligibilitySummary(
        diagnostics=list(reversed(eligibility.diagnostics)),
        candidate_count=3,
        eligible_count=1,
        ineligible_count=2,
        constraint_names=list(reversed(eligibility.constraint_names)),
    )

    first = adapter.build_constraint_failure_distribution(eligibility)
    second = adapter.build_constraint_failure_distribution(repeated_eligibility)

    assert first == second
    assert asdict(first) == asdict(second)
    assert first.total_candidate_count == 3
    assert first.eligible_candidate_count == 1
    assert first.ineligible_candidate_count == 2
    assert [distribution.constraint_name for distribution in first.distributions] == [
        "max_drawdown",
        "min_profit_factor",
        "min_win_rate",
    ]
    assert [(distribution.pass_count, distribution.failure_count) for distribution in first.distributions] == [
        (2, 1),
        (2, 1),
        (1, 2),
    ]
    assert first.most_common_failed_constraints == [
        "min_win_rate",
        "max_drawdown",
        "min_profit_factor",
    ]
    assert [detail.candidate_id for detail in first.failure_details] == ["candidate_a", "candidate_b"]
    assert first.failure_details[0].failed_constraints == ["min_profit_factor", "min_win_rate"]
    assert first.failure_details[1].failed_constraints == ["max_drawdown", "min_win_rate"]
    assert first.failure_details[0].reasons == [
        "max_drawdown passed: 0.5 must be at most 1.0",
        "min_profit_factor failed: 1.0 must be at least 2.0",
        "min_win_rate failed: 40.0 must be at least 50.0",
    ]
    assert first.stable_reason_order == sorted(first.stable_reason_order)


def test_constraint_failure_distribution_preserves_eligibility_inputs() -> None:
    adapter = HistoricalSimulationAdapter()
    result = adapter.simulate(
        [{"close": 100}, {"close": 101}],
        [_signal(direction="LONG"), _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0)],
    )
    sweep = adapter.build_parameter_sweep({"candidate": result})
    eligibility = adapter.build_constraint_eligibility(
        sweep,
        {"min_win_rate": 100.0, "min_total_unitless_return": 2.0},
    )
    original_eligibility = asdict(eligibility)
    original_sweep = asdict(sweep)

    summary = adapter.build_constraint_failure_distribution(eligibility)
    repeated = adapter.build_constraint_failure_distribution(eligibility)

    assert summary == repeated
    assert summary.total_candidate_count == eligibility.candidate_count
    assert summary.eligible_candidate_count == eligibility.eligible_count
    assert summary.ineligible_candidate_count == eligibility.ineligible_count
    assert asdict(eligibility) == original_eligibility
    assert asdict(sweep) == original_sweep


def test_constraint_candidate_report_is_deterministic_and_rank_ordered() -> None:
    adapter = HistoricalSimulationAdapter()
    sweep = simulation_models.HistoricalSimulationParameterSweepSummary(
        candidates=[
            simulation_models.HistoricalSimulationParameterSweepCandidate(
                candidate_id="candidate_b",
                rank=1,
                total_unitless_return=3.0,
                max_drawdown=0.5,
                profit_factor=3.0,
                win_rate=75.0,
                expectancy=1.0,
                confidence_average=0.9,
                movement_average=1.0,
                movement_total=3.0,
                replay_ending_diagnostic_value=3.0,
                replay_ending_equity_value=3.0,
            ),
            simulation_models.HistoricalSimulationParameterSweepCandidate(
                candidate_id="candidate_a",
                rank=1,
                total_unitless_return=3.0,
                max_drawdown=0.5,
                profit_factor=3.0,
                win_rate=75.0,
                expectancy=1.0,
                confidence_average=0.9,
                movement_average=1.0,
                movement_total=3.0,
                replay_ending_diagnostic_value=3.0,
                replay_ending_equity_value=3.0,
            ),
            simulation_models.HistoricalSimulationParameterSweepCandidate(
                candidate_id="candidate_c",
                rank=3,
                total_unitless_return=0.0,
                max_drawdown=4.0,
                profit_factor=1.0,
                win_rate=25.0,
                expectancy=0.0,
                confidence_average=0.8,
                movement_average=0.0,
                movement_total=0.0,
                replay_ending_diagnostic_value=0.0,
                replay_ending_equity_value=0.0,
            ),
        ],
        candidate_count=3,
        best_candidate_id="candidate_a",
        worst_candidate_id="candidate_c",
        ranking_metric="test_rank",
    )
    eligibility = simulation_models.HistoricalSimulationConstraintEligibilitySummary(
        diagnostics=[
            simulation_models.HistoricalSimulationConstraintDiagnostic(
                candidate_id="candidate_c",
                is_eligible=False,
                passed_constraints=["min_confidence_average"],
                failed_constraints=["max_drawdown", "min_win_rate"],
                reasons=[
                    "min_win_rate failed: 25.0 must be at least 50.0",
                    "max_drawdown failed: 4.0 must be at most 1.0",
                    "min_confidence_average passed: 0.8 must be at least 0.8",
                ],
            ),
            simulation_models.HistoricalSimulationConstraintDiagnostic(
                candidate_id="candidate_b",
                is_eligible=True,
                passed_constraints=["max_drawdown", "min_win_rate", "min_confidence_average"],
                failed_constraints=[],
                reasons=[
                    "min_win_rate passed: 75.0 must be at least 50.0",
                    "max_drawdown passed: 0.5 must be at most 1.0",
                    "min_confidence_average passed: 0.9 must be at least 0.8",
                ],
            ),
            simulation_models.HistoricalSimulationConstraintDiagnostic(
                candidate_id="candidate_a",
                is_eligible=True,
                passed_constraints=["min_win_rate", "min_confidence_average", "max_drawdown"],
                failed_constraints=[],
                reasons=[
                    "min_confidence_average passed: 0.9 must be at least 0.8",
                    "max_drawdown passed: 0.5 must be at most 1.0",
                    "min_win_rate passed: 75.0 must be at least 50.0",
                ],
            ),
        ],
        candidate_count=3,
        eligible_count=2,
        ineligible_count=1,
        constraint_names=["min_win_rate", "max_drawdown", "min_confidence_average"],
    )

    first = adapter.build_constraint_candidate_report(sweep, eligibility)
    second = adapter.build_constraint_candidate_report(
        type(sweep)(
            candidates=list(reversed(sweep.candidates)),
            candidate_count=sweep.candidate_count,
            best_candidate_id=sweep.best_candidate_id,
            worst_candidate_id=sweep.worst_candidate_id,
            ranking_metric=sweep.ranking_metric,
        ),
        type(eligibility)(
            diagnostics=list(reversed(eligibility.diagnostics)),
            candidate_count=eligibility.candidate_count,
            eligible_count=eligibility.eligible_count,
            ineligible_count=eligibility.ineligible_count,
            constraint_names=list(reversed(eligibility.constraint_names)),
        ),
    )

    assert first == second
    assert asdict(first) == asdict(second)
    assert first.total_candidate_count == 3
    assert first.eligible_candidate_count == 2
    assert first.ineligible_candidate_count == 1
    assert [row.candidate_id for row in first.rows] == ["candidate_a", "candidate_b", "candidate_c"]
    assert [row.rank for row in first.rows] == [1, 1, 3]
    assert [row.is_eligible for row in first.rows] == [True, True, False]
    assert [(row.pass_count, row.failure_count) for row in first.rows] == [(3, 0), (3, 0), (1, 2)]
    assert first.rows[2].failed_constraints == ["max_drawdown", "min_win_rate"]
    assert first.rows[2].reasons == [
        "max_drawdown failed: 4.0 must be at most 1.0",
        "min_confidence_average passed: 0.8 must be at least 0.8",
        "min_win_rate failed: 25.0 must be at least 50.0",
    ]
    assert first.rows[0].total_unitless_return == 3.0
    assert first.rows[0].max_drawdown == 0.5
    assert first.rows[0].profit_factor == 3.0
    assert first.rows[0].win_rate == 75.0
    assert first.rows[0].expectancy == 1.0


def test_constraint_candidate_report_preserves_inputs() -> None:
    adapter = HistoricalSimulationAdapter()
    result = adapter.simulate(
        [{"close": 100}, {"close": 101}],
        [_signal(direction="LONG"), _signal(status="NO_SIGNAL", direction="NONE", confidence=0.0)],
    )
    sweep = adapter.build_parameter_sweep({"candidate": result})
    eligibility = adapter.build_constraint_eligibility(
        sweep,
        {"min_win_rate": 100.0, "min_total_unitless_return": 2.0},
    )
    failure_distribution = adapter.build_constraint_failure_distribution(eligibility)
    original_sweep = asdict(sweep)
    original_eligibility = asdict(eligibility)
    original_failure_distribution = asdict(failure_distribution)

    report = adapter.build_constraint_candidate_report(sweep, eligibility)
    repeated = adapter.build_constraint_candidate_report(sweep, eligibility)

    assert report == repeated
    assert report.total_candidate_count == sweep.candidate_count
    assert report.eligible_candidate_count == eligibility.eligible_count
    assert report.ineligible_candidate_count == eligibility.ineligible_count
    assert asdict(sweep) == original_sweep
    assert asdict(eligibility) == original_eligibility
    assert asdict(failure_distribution) == original_failure_distribution


def test_blocked_signal_does_not_create_simulated_decision() -> None:
    result = HistoricalSimulationAdapter().simulate(
        [{"close": 101}],
        [_signal(direction="LONG", blockers=["entry status is not confirmed"])],
    )

    record = result.records[0]

    assert record.decision_status == "NO_DECISION"
    assert record.direction == "NONE"
    assert record.blockers == ["entry status is not confirmed"]
    assert result.diagnostics.simulated_signal_records == 0
    assert result.diagnostics.blocked_records == 1


def test_historical_simulation_copies_signal_evidence_without_mutation() -> None:
    signal = _signal()
    original_signal = asdict(signal)
    result = HistoricalSimulationAdapter().simulate([{"close": 101}], [signal])

    result.records[0].source_evidence["source"]["nested"] = False
    result.records[0].reasons.append("local test mutation")

    assert signal.source_evidence == {"trend": "LONG", "source": {"nested": True}}
    assert signal.reasons == ["advisory evidence aligned"]
    assert asdict(signal) == original_signal


def test_length_mismatch_is_rejected_before_simulation() -> None:
    try:
        HistoricalSimulationAdapter().simulate([{"close": 101}], [])
    except ValueError as exc:
        assert str(exc) == "historical_data and signals must have identical lengths"
    else:
        raise AssertionError("expected ValueError for mismatched inputs")


def test_simulation_adapter_has_no_live_integration_imports_or_credentials() -> None:
    production_source = "\n".join(
        [
            inspect.getsource(adapter_module),
            inspect.getsource(simulation_models),
        ]
    ).lower()

    prohibited_terms = [
        "binance",
        "client",
        "credential",
        "api_key",
        "secret",
        "permit",
        "transport",
        "exchange",
        "optimizer",
        "parameter_generation",
        "live_configuration",
    ]

    assert all(term not in production_source for term in prohibited_terms)


def test_simulation_records_have_no_execution_authority_fields() -> None:
    result = HistoricalSimulationAdapter().simulate([{"close": 101}], [_signal()])
    payload = asdict(result.records[0])
    report_payload = asdict(HistoricalSimulationAdapter().build_report(result))
    replay_payload = asdict(HistoricalSimulationAdapter().build_replay(result))
    analytics_payload = asdict(HistoricalSimulationAdapter().build_outcome_analytics(result))
    sweep_payload = asdict(HistoricalSimulationAdapter().build_parameter_sweep({"baseline": result}))
    eligibility_payload = asdict(
        HistoricalSimulationAdapter().build_constraint_eligibility(
            HistoricalSimulationAdapter().build_parameter_sweep({"baseline": result}),
            {"min_confidence_average": 0.0},
        )
    )
    failure_distribution_payload = asdict(
        HistoricalSimulationAdapter().build_constraint_failure_distribution(
            HistoricalSimulationAdapter().build_constraint_eligibility(
                HistoricalSimulationAdapter().build_parameter_sweep({"baseline": result}),
                {"min_confidence_average": 0.0},
            )
        )
    )
    candidate_report_payload = asdict(
        HistoricalSimulationAdapter().build_constraint_candidate_report(
            HistoricalSimulationAdapter().build_parameter_sweep({"baseline": result}),
            HistoricalSimulationAdapter().build_constraint_eligibility(
                HistoricalSimulationAdapter().build_parameter_sweep({"baseline": result}),
                {"min_confidence_average": 0.0},
            ),
        )
    )

    prohibited_fields = {
        "order",
        "order_id",
        "exchange_order_id",
        "client_order_id",
        "permit",
        "permit_id",
        "execution_authorized",
        "execution_state",
        "risk_authorized",
        "authoritative_risk",
        "monetary_risk",
        "position_size",
        "position_id",
        "position_state",
        "sizing",
        "stop_loss",
        "take_profit",
        "breakeven",
        "trailing_stop",
        "take_profit_ladder",
        "transport",
        "fill",
        "fill_price",
        "fill_quantity",
        "fill_state",
        "fee",
        "slippage",
        "funding",
        "parameter_sweep",
        "optimizer",
        "automatic_candidate_selection",
    }

    assert prohibited_fields.isdisjoint(payload)
    assert prohibited_fields.isdisjoint(asdict(result.diagnostics))
    assert prohibited_fields.isdisjoint(report_payload)
    assert prohibited_fields.isdisjoint(replay_payload)
    assert prohibited_fields.isdisjoint(analytics_payload)
    assert prohibited_fields.isdisjoint(sweep_payload)
    assert prohibited_fields.isdisjoint(eligibility_payload)
    assert prohibited_fields.isdisjoint(failure_distribution_payload)
    assert prohibited_fields.isdisjoint(candidate_report_payload)
