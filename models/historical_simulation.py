from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HistoricalSimulationRecord:
    index: int
    decision_status: str
    signal_status: str
    direction: str
    confidence_score: float
    directional_outcome: str = "NOT_EVALUATED"
    raw_point_movement: float = 0.0
    percentage_movement: float = 0.0
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    source_evidence: dict[str, Any] = field(default_factory=dict)
    market_snapshot: dict[str, Any] = field(default_factory=dict)
    event_type: str = "HISTORICAL_SIMULATION_RECORD"


@dataclass(frozen=True)
class HistoricalSimulationDiagnostics:
    total_records: int
    simulated_signal_records: int
    no_decision_records: int
    long_records: int
    short_records: int
    blocked_records: int
    average_confidence_score: float
    win_count: int = 0
    loss_count: int = 0
    flat_count: int = 0
    expectancy: float = 0.0
    equity_curve: list[float] = field(default_factory=list)
    max_drawdown: float = 0.0
    total_unitless_return: float = 0.0
    win_rate: float = 0.0
    loss_rate: float = 0.0
    flat_rate: float = 0.0
    profit_factor: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    risk_adjusted_diagnostic_ratio: float = 0.0
    event_type: str = "HISTORICAL_SIMULATION_DIAGNOSTICS"


@dataclass(frozen=True)
class HistoricalSimulationReportRow:
    index: int
    direction: str
    decision_status: str
    directional_outcome: str
    raw_point_movement: float
    percentage_movement: float
    confidence_score: float
    blockers_count: int
    reasons_count: int
    event_type: str = "HISTORICAL_SIMULATION_REPORT_ROW"


@dataclass(frozen=True)
class HistoricalSimulationReportSummary:
    rows: list[HistoricalSimulationReportRow]
    total_rows: int
    simulated_rows: int
    no_decision_rows: int
    total_unitless_return: float
    win_rate: float
    loss_rate: float
    flat_rate: float
    profit_factor: float
    expectancy: float
    max_drawdown: float
    risk_adjusted_diagnostic_ratio: float
    event_type: str = "HISTORICAL_SIMULATION_REPORT_SUMMARY"


@dataclass(frozen=True)
class HistoricalSimulationReplayStep:
    step_index: int
    record_index: int
    direction: str
    decision_status: str
    directional_outcome: str
    raw_point_movement: float
    percentage_movement: float
    confidence_score: float
    blockers_count: int
    reasons_count: int
    cumulative_diagnostic_value: float
    cumulative_equity_value: float
    event_type: str = "HISTORICAL_SIMULATION_REPLAY_STEP"


@dataclass(frozen=True)
class HistoricalSimulationReplaySummary:
    steps: list[HistoricalSimulationReplayStep]
    total_steps: int
    simulated_steps: int
    no_decision_steps: int
    ending_diagnostic_value: float
    ending_equity_value: float
    event_type: str = "HISTORICAL_SIMULATION_REPLAY_SUMMARY"


@dataclass(frozen=True)
class HistoricalSimulationOutcomeAnalyticsSummary:
    decision_status_counts: dict[str, int]
    direction_counts: dict[str, int]
    outcome_counts: dict[str, int]
    simulated_ratio: float
    no_decision_ratio: float
    confidence_minimum: float
    confidence_maximum: float
    confidence_average: float
    movement_minimum: float
    movement_maximum: float
    movement_average: float
    movement_total: float
    blockers_total: int
    blockers_maximum: int
    blockers_average: float
    reasons_total: int
    reasons_maximum: int
    reasons_average: float
    replay_ending_diagnostic_value: float
    replay_ending_equity_value: float
    event_type: str = "HISTORICAL_SIMULATION_OUTCOME_ANALYTICS_SUMMARY"


@dataclass(frozen=True)
class HistoricalSimulationParameterSweepCandidate:
    candidate_id: str
    rank: int
    total_unitless_return: float
    max_drawdown: float
    profit_factor: float
    win_rate: float
    expectancy: float
    confidence_average: float
    movement_average: float
    movement_total: float
    replay_ending_diagnostic_value: float
    replay_ending_equity_value: float
    event_type: str = "HISTORICAL_SIMULATION_PARAMETER_SWEEP_CANDIDATE"


@dataclass(frozen=True)
class HistoricalSimulationParameterSweepSummary:
    candidates: list[HistoricalSimulationParameterSweepCandidate]
    candidate_count: int
    best_candidate_id: str
    worst_candidate_id: str
    ranking_metric: str
    event_type: str = "HISTORICAL_SIMULATION_PARAMETER_SWEEP_SUMMARY"


@dataclass(frozen=True)
class HistoricalSimulationConstraintDiagnostic:
    candidate_id: str
    is_eligible: bool
    passed_constraints: list[str]
    failed_constraints: list[str]
    reasons: list[str]
    event_type: str = "HISTORICAL_SIMULATION_CONSTRAINT_DIAGNOSTIC"


@dataclass(frozen=True)
class HistoricalSimulationConstraintEligibilitySummary:
    diagnostics: list[HistoricalSimulationConstraintDiagnostic]
    candidate_count: int
    eligible_count: int
    ineligible_count: int
    constraint_names: list[str]
    event_type: str = "HISTORICAL_SIMULATION_CONSTRAINT_ELIGIBILITY_SUMMARY"


@dataclass(frozen=True)
class HistoricalSimulationConstraintFailureDistribution:
    constraint_name: str
    pass_count: int
    failure_count: int
    event_type: str = "HISTORICAL_SIMULATION_CONSTRAINT_FAILURE_DISTRIBUTION"


@dataclass(frozen=True)
class HistoricalSimulationConstraintFailureDetail:
    candidate_id: str
    failed_constraints: list[str]
    reasons: list[str]
    event_type: str = "HISTORICAL_SIMULATION_CONSTRAINT_FAILURE_DETAIL"


@dataclass(frozen=True)
class HistoricalSimulationConstraintFailureSummary:
    distributions: list[HistoricalSimulationConstraintFailureDistribution]
    failure_details: list[HistoricalSimulationConstraintFailureDetail]
    total_candidate_count: int
    eligible_candidate_count: int
    ineligible_candidate_count: int
    most_common_failed_constraints: list[str]
    stable_reason_order: list[str]
    event_type: str = "HISTORICAL_SIMULATION_CONSTRAINT_FAILURE_SUMMARY"


@dataclass(frozen=True)
class HistoricalSimulationConstraintCandidateReportRow:
    candidate_id: str
    rank: int
    is_eligible: bool
    pass_count: int
    failure_count: int
    failed_constraints: list[str]
    reasons: list[str]
    total_unitless_return: float
    max_drawdown: float
    profit_factor: float
    win_rate: float
    expectancy: float
    event_type: str = "HISTORICAL_SIMULATION_CONSTRAINT_CANDIDATE_REPORT_ROW"


@dataclass(frozen=True)
class HistoricalSimulationConstraintCandidateReportSummary:
    rows: list[HistoricalSimulationConstraintCandidateReportRow]
    total_candidate_count: int
    eligible_candidate_count: int
    ineligible_candidate_count: int
    event_type: str = "HISTORICAL_SIMULATION_CONSTRAINT_CANDIDATE_REPORT_SUMMARY"


@dataclass(frozen=True)
class HistoricalSimulationResult:
    records: list[HistoricalSimulationRecord]
    diagnostics: HistoricalSimulationDiagnostics
    event_type: str = "HISTORICAL_SIMULATION_RESULT"
