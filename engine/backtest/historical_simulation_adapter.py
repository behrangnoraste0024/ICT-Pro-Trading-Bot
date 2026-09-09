from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping, Sequence

from models.historical_simulation import (
    HistoricalSimulationConstraintCandidateReportRow,
    HistoricalSimulationConstraintCandidateReportSummary,
    HistoricalSimulationConstraintDiagnostic,
    HistoricalSimulationConstraintEligibilitySummary,
    HistoricalSimulationConstraintFailureDetail,
    HistoricalSimulationConstraintFailureDistribution,
    HistoricalSimulationConstraintFailureSummary,
    HistoricalSimulationDiagnostics,
    HistoricalSimulationOutcomeAnalyticsSummary,
    HistoricalSimulationParameterSweepCandidate,
    HistoricalSimulationParameterSweepSummary,
    HistoricalSimulationReportRow,
    HistoricalSimulationReportSummary,
    HistoricalSimulationReplayStep,
    HistoricalSimulationReplaySummary,
    HistoricalSimulationRecord,
    HistoricalSimulationResult,
)
from models.strategy_signal import StrategySignalResult


class HistoricalSimulationAdapter:
    """Deterministic advisory-signal simulation adapter."""

    _SNAPSHOT_FIELDS = ("timestamp", "open", "high", "low", "close", "volume")

    def simulate(
        self,
        historical_data: Sequence[Mapping[str, Any] | object],
        signals: Sequence[StrategySignalResult],
    ) -> HistoricalSimulationResult:
        if len(historical_data) != len(signals):
            raise ValueError("historical_data and signals must have identical lengths")

        records = [
            self._record(index, market_row, _next_close(historical_data, index), signal)
            for index, (market_row, signal) in enumerate(zip(historical_data, signals, strict=True))
        ]

        return HistoricalSimulationResult(
            records=records,
            diagnostics=self._diagnostics(records),
        )

    def diagnose_records(
        self,
        historical_data: Sequence[Mapping[str, Any] | object],
        records: Sequence[HistoricalSimulationRecord],
    ) -> HistoricalSimulationResult:
        if len(historical_data) != len(records):
            raise ValueError("historical_data and records must have identical lengths")

        diagnosed_records = [
            self._diagnosed_record(record, market_row, _next_close(historical_data, index))
            for index, (market_row, record) in enumerate(zip(historical_data, records, strict=True))
        ]

        return HistoricalSimulationResult(
            records=diagnosed_records,
            diagnostics=self._diagnostics(diagnosed_records),
        )

    def build_report(self, result: HistoricalSimulationResult) -> HistoricalSimulationReportSummary:
        rows = [
            self._report_row(record)
            for record in sorted(result.records, key=lambda record: record.index)
        ]
        diagnostics = result.diagnostics

        return HistoricalSimulationReportSummary(
            rows=rows,
            total_rows=len(rows),
            simulated_rows=diagnostics.simulated_signal_records,
            no_decision_rows=diagnostics.no_decision_records,
            total_unitless_return=diagnostics.total_unitless_return,
            win_rate=diagnostics.win_rate,
            loss_rate=diagnostics.loss_rate,
            flat_rate=diagnostics.flat_rate,
            profit_factor=diagnostics.profit_factor,
            expectancy=diagnostics.expectancy,
            max_drawdown=diagnostics.max_drawdown,
            risk_adjusted_diagnostic_ratio=diagnostics.risk_adjusted_diagnostic_ratio,
        )

    def build_replay(self, result: HistoricalSimulationResult) -> HistoricalSimulationReplaySummary:
        report = self.build_report(result)
        steps: list[HistoricalSimulationReplayStep] = []
        cumulative_diagnostic_value = 0.0

        for step_index, row in enumerate(report.rows):
            if row.decision_status == "SIMULATED_SIGNAL":
                cumulative_diagnostic_value = round(cumulative_diagnostic_value + row.raw_point_movement, 4)

            steps.append(
                HistoricalSimulationReplayStep(
                    step_index=step_index,
                    record_index=row.index,
                    direction=row.direction,
                    decision_status=row.decision_status,
                    directional_outcome=row.directional_outcome,
                    raw_point_movement=row.raw_point_movement,
                    percentage_movement=row.percentage_movement,
                    confidence_score=row.confidence_score,
                    blockers_count=row.blockers_count,
                    reasons_count=row.reasons_count,
                    cumulative_diagnostic_value=cumulative_diagnostic_value,
                    cumulative_equity_value=_equity_at(result.diagnostics.equity_curve, row.index, cumulative_diagnostic_value),
                )
            )

        ending_diagnostic_value = steps[-1].cumulative_diagnostic_value if steps else 0.0
        ending_equity_value = steps[-1].cumulative_equity_value if steps else 0.0

        return HistoricalSimulationReplaySummary(
            steps=steps,
            total_steps=len(steps),
            simulated_steps=report.simulated_rows,
            no_decision_steps=report.no_decision_rows,
            ending_diagnostic_value=ending_diagnostic_value,
            ending_equity_value=ending_equity_value,
        )

    def build_outcome_analytics(self, result: HistoricalSimulationResult) -> HistoricalSimulationOutcomeAnalyticsSummary:
        report = self.build_report(result)
        replay = self.build_replay(result)
        simulated_rows = [row for row in report.rows if row.decision_status == "SIMULATED_SIGNAL"]
        confidence_values = [row.confidence_score for row in simulated_rows]
        movement_values = [row.raw_point_movement for row in simulated_rows]
        blocker_counts = [row.blockers_count for row in report.rows]
        reason_counts = [row.reasons_count for row in report.rows]

        return HistoricalSimulationOutcomeAnalyticsSummary(
            decision_status_counts=_counts(row.decision_status for row in report.rows),
            direction_counts=_counts(row.direction for row in report.rows),
            outcome_counts=_counts(row.directional_outcome for row in report.rows),
            simulated_ratio=_rate(report.simulated_rows, report.total_rows),
            no_decision_ratio=_rate(report.no_decision_rows, report.total_rows),
            confidence_minimum=_minimum(confidence_values),
            confidence_maximum=_maximum(confidence_values),
            confidence_average=_average(confidence_values),
            movement_minimum=_minimum(movement_values),
            movement_maximum=_maximum(movement_values),
            movement_average=_average(movement_values),
            movement_total=round(sum(movement_values), 4),
            blockers_total=sum(blocker_counts),
            blockers_maximum=max(blocker_counts, default=0),
            blockers_average=_average(blocker_counts),
            reasons_total=sum(reason_counts),
            reasons_maximum=max(reason_counts, default=0),
            reasons_average=_average(reason_counts),
            replay_ending_diagnostic_value=replay.ending_diagnostic_value,
            replay_ending_equity_value=replay.ending_equity_value,
        )

    def build_parameter_sweep(
        self,
        candidates: Mapping[str, HistoricalSimulationResult] | Sequence[tuple[str, HistoricalSimulationResult]],
    ) -> HistoricalSimulationParameterSweepSummary:
        candidate_items = _candidate_items(candidates)
        ranked_items = sorted(
            candidate_items,
            key=lambda item: _sweep_rank_key(item[0], item[1]),
        )

        ranked_candidates = [
            self._parameter_sweep_candidate(candidate_id, result, rank)
            for rank, (candidate_id, result) in enumerate(ranked_items, start=1)
        ]
        worst_candidate = min(ranked_items, key=lambda item: _sweep_worst_key(item[0], item[1])) if ranked_items else None

        return HistoricalSimulationParameterSweepSummary(
            candidates=ranked_candidates,
            candidate_count=len(ranked_candidates),
            best_candidate_id=ranked_candidates[0].candidate_id if ranked_candidates else "",
            worst_candidate_id=worst_candidate[0] if worst_candidate else "",
            ranking_metric="total_return_desc_drawdown_asc_profit_factor_desc_win_rate_desc_expectancy_desc_candidate_id_asc",
        )

    def build_constraint_eligibility(
        self,
        sweep: HistoricalSimulationParameterSweepSummary,
        constraints: Mapping[str, float | int],
    ) -> HistoricalSimulationConstraintEligibilitySummary:
        constraint_values = _constraint_values(constraints)
        diagnostics = [
            self._constraint_diagnostic(candidate, constraint_values)
            for candidate in sorted(sweep.candidates, key=lambda candidate: candidate.candidate_id)
        ]

        return HistoricalSimulationConstraintEligibilitySummary(
            diagnostics=diagnostics,
            candidate_count=len(diagnostics),
            eligible_count=sum(diagnostic.is_eligible for diagnostic in diagnostics),
            ineligible_count=sum(not diagnostic.is_eligible for diagnostic in diagnostics),
            constraint_names=list(constraint_values),
        )

    def build_constraint_failure_distribution(
        self,
        eligibility: HistoricalSimulationConstraintEligibilitySummary,
    ) -> HistoricalSimulationConstraintFailureSummary:
        diagnostics = sorted(eligibility.diagnostics, key=lambda diagnostic: diagnostic.candidate_id)
        constraint_names = _constraint_distribution_names(eligibility)
        failure_details = [
            HistoricalSimulationConstraintFailureDetail(
                candidate_id=diagnostic.candidate_id,
                failed_constraints=sorted(diagnostic.failed_constraints),
                reasons=sorted(diagnostic.reasons),
            )
            for diagnostic in diagnostics
            if diagnostic.failed_constraints
        ]
        distributions = [
            HistoricalSimulationConstraintFailureDistribution(
                constraint_name=constraint_name,
                pass_count=sum(constraint_name in diagnostic.passed_constraints for diagnostic in diagnostics),
                failure_count=sum(constraint_name in diagnostic.failed_constraints for diagnostic in diagnostics),
            )
            for constraint_name in constraint_names
        ]

        return HistoricalSimulationConstraintFailureSummary(
            distributions=distributions,
            failure_details=failure_details,
            total_candidate_count=eligibility.candidate_count,
            eligible_candidate_count=eligibility.eligible_count,
            ineligible_candidate_count=eligibility.ineligible_count,
            most_common_failed_constraints=[
                distribution.constraint_name
                for distribution in sorted(
                    distributions,
                    key=lambda distribution: (-distribution.failure_count, distribution.constraint_name),
                )
                if distribution.failure_count > 0
            ],
            stable_reason_order=sorted({reason for diagnostic in diagnostics for reason in diagnostic.reasons}),
        )

    def build_constraint_candidate_report(
        self,
        sweep: HistoricalSimulationParameterSweepSummary,
        eligibility: HistoricalSimulationConstraintEligibilitySummary,
    ) -> HistoricalSimulationConstraintCandidateReportSummary:
        diagnostics_by_candidate_id = _diagnostics_by_candidate_id(eligibility.diagnostics)
        rows = [
            self._constraint_candidate_report_row(candidate, diagnostics_by_candidate_id[candidate.candidate_id])
            for candidate in sorted(sweep.candidates, key=lambda candidate: (candidate.rank, candidate.candidate_id))
        ]

        return HistoricalSimulationConstraintCandidateReportSummary(
            rows=rows,
            total_candidate_count=len(rows),
            eligible_candidate_count=sum(row.is_eligible for row in rows),
            ineligible_candidate_count=sum(not row.is_eligible for row in rows),
        )

    def _record(
        self,
        index: int,
        market_row: Mapping[str, Any] | object,
        next_close: float | None,
        signal: StrategySignalResult,
    ) -> HistoricalSimulationRecord:
        signal_status = _normalized(signal.signal_status)
        direction = _normalized(signal.direction)
        has_advisory_signal = signal_status == "SIGNAL" and direction in {"LONG", "SHORT"} and not signal.blockers
        current_close = _to_float(_read_field(market_row, "close"))
        raw_movement = _raw_movement(direction, current_close, next_close) if has_advisory_signal else 0.0
        percentage_movement = _percentage_movement(raw_movement, current_close) if has_advisory_signal else 0.0

        return HistoricalSimulationRecord(
            index=index,
            decision_status="SIMULATED_SIGNAL" if has_advisory_signal else "NO_DECISION",
            signal_status=signal_status,
            direction=direction if has_advisory_signal else "NONE",
            confidence_score=round(float(signal.confidence_score), 4),
            directional_outcome=_directional_outcome(raw_movement) if has_advisory_signal else "NOT_EVALUATED",
            raw_point_movement=raw_movement,
            percentage_movement=percentage_movement,
            reasons=list(signal.reasons),
            blockers=list(signal.blockers),
            source_evidence=deepcopy(signal.source_evidence),
            market_snapshot=self._market_snapshot(market_row),
        )

    def _diagnosed_record(
        self,
        record: HistoricalSimulationRecord,
        market_row: Mapping[str, Any] | object,
        next_close: float | None,
    ) -> HistoricalSimulationRecord:
        current_close = _to_float(_read_field(market_row, "close"))
        raw_movement = (
            _raw_movement(record.direction, current_close, next_close)
            if record.decision_status == "SIMULATED_SIGNAL"
            else 0.0
        )
        percentage_movement = (
            _percentage_movement(raw_movement, current_close)
            if record.decision_status == "SIMULATED_SIGNAL"
            else 0.0
        )

        return HistoricalSimulationRecord(
            index=record.index,
            decision_status=record.decision_status,
            signal_status=record.signal_status,
            direction=record.direction,
            confidence_score=record.confidence_score,
            directional_outcome=_directional_outcome(raw_movement)
            if record.decision_status == "SIMULATED_SIGNAL"
            else "NOT_EVALUATED",
            raw_point_movement=raw_movement,
            percentage_movement=percentage_movement,
            reasons=list(record.reasons),
            blockers=list(record.blockers),
            source_evidence=deepcopy(record.source_evidence),
            market_snapshot=self._market_snapshot(market_row),
            event_type=record.event_type,
        )

    def _market_snapshot(self, market_row: Mapping[str, Any] | object) -> dict[str, Any]:
        return {
            field: _read_field(market_row, field)
            for field in self._SNAPSHOT_FIELDS
            if _read_field(market_row, field) is not None
        }

    def _report_row(self, record: HistoricalSimulationRecord) -> HistoricalSimulationReportRow:
        return HistoricalSimulationReportRow(
            index=record.index,
            direction=record.direction,
            decision_status=record.decision_status,
            directional_outcome=record.directional_outcome,
            raw_point_movement=record.raw_point_movement,
            percentage_movement=record.percentage_movement,
            confidence_score=record.confidence_score,
            blockers_count=len(record.blockers),
            reasons_count=len(record.reasons),
        )

    def _parameter_sweep_candidate(
        self,
        candidate_id: str,
        result: HistoricalSimulationResult,
        rank: int,
    ) -> HistoricalSimulationParameterSweepCandidate:
        analytics = self.build_outcome_analytics(result)
        diagnostics = result.diagnostics

        return HistoricalSimulationParameterSweepCandidate(
            candidate_id=candidate_id,
            rank=rank,
            total_unitless_return=diagnostics.total_unitless_return,
            max_drawdown=diagnostics.max_drawdown,
            profit_factor=diagnostics.profit_factor,
            win_rate=diagnostics.win_rate,
            expectancy=diagnostics.expectancy,
            confidence_average=analytics.confidence_average,
            movement_average=analytics.movement_average,
            movement_total=analytics.movement_total,
            replay_ending_diagnostic_value=analytics.replay_ending_diagnostic_value,
            replay_ending_equity_value=analytics.replay_ending_equity_value,
        )

    def _constraint_diagnostic(
        self,
        candidate: HistoricalSimulationParameterSweepCandidate,
        constraints: Mapping[str, float],
    ) -> HistoricalSimulationConstraintDiagnostic:
        passed_constraints: list[str] = []
        failed_constraints: list[str] = []
        reasons: list[str] = []

        for name, threshold in constraints.items():
            actual = _constraint_metric(candidate, name)
            passed = _constraint_passes(name, actual, threshold)
            target = "at most" if name.startswith("max_") else "at least"
            reason_status = "passed" if passed else "failed"
            reasons.append(f"{name} {reason_status}: {actual} must be {target} {threshold}")
            if passed:
                passed_constraints.append(name)
            else:
                failed_constraints.append(name)

        return HistoricalSimulationConstraintDiagnostic(
            candidate_id=candidate.candidate_id,
            is_eligible=not failed_constraints,
            passed_constraints=passed_constraints,
            failed_constraints=failed_constraints,
            reasons=reasons,
        )

    def _constraint_candidate_report_row(
        self,
        candidate: HistoricalSimulationParameterSweepCandidate,
        diagnostic: HistoricalSimulationConstraintDiagnostic,
    ) -> HistoricalSimulationConstraintCandidateReportRow:
        return HistoricalSimulationConstraintCandidateReportRow(
            candidate_id=candidate.candidate_id,
            rank=candidate.rank,
            is_eligible=diagnostic.is_eligible,
            pass_count=len(diagnostic.passed_constraints),
            failure_count=len(diagnostic.failed_constraints),
            failed_constraints=sorted(diagnostic.failed_constraints),
            reasons=sorted(diagnostic.reasons),
            total_unitless_return=candidate.total_unitless_return,
            max_drawdown=candidate.max_drawdown,
            profit_factor=candidate.profit_factor,
            win_rate=candidate.win_rate,
            expectancy=candidate.expectancy,
        )

    def _diagnostics(self, records: Iterable[HistoricalSimulationRecord]) -> HistoricalSimulationDiagnostics:
        record_list = list(records)
        simulated_records = [record for record in record_list if record.decision_status == "SIMULATED_SIGNAL"]
        confidence_values = [record.confidence_score for record in simulated_records]
        movement_values = [record.raw_point_movement for record in simulated_records]
        equity_curve = _equity_curve(record_list)
        win_movements = [movement for movement in movement_values if movement > 0]
        loss_movements = [movement for movement in movement_values if movement < 0]
        win_count = sum(record.directional_outcome == "WIN" for record in simulated_records)
        loss_count = sum(record.directional_outcome == "LOSS" for record in simulated_records)
        flat_count = sum(record.directional_outcome == "FLAT" for record in simulated_records)
        total_return = round(sum(movement_values), 4)
        max_drawdown = _max_drawdown(equity_curve)

        return HistoricalSimulationDiagnostics(
            total_records=len(record_list),
            simulated_signal_records=len(simulated_records),
            no_decision_records=sum(record.decision_status == "NO_DECISION" for record in record_list),
            long_records=sum(record.direction == "LONG" for record in simulated_records),
            short_records=sum(record.direction == "SHORT" for record in simulated_records),
            blocked_records=sum(bool(record.blockers) for record in record_list),
            average_confidence_score=round(sum(confidence_values) / len(confidence_values), 4)
            if confidence_values
            else 0.0,
            win_count=win_count,
            loss_count=loss_count,
            flat_count=flat_count,
            expectancy=round(sum(movement_values) / len(movement_values), 4) if movement_values else 0.0,
            equity_curve=equity_curve,
            max_drawdown=max_drawdown,
            total_unitless_return=total_return,
            win_rate=_rate(win_count, len(simulated_records)),
            loss_rate=_rate(loss_count, len(simulated_records)),
            flat_rate=_rate(flat_count, len(simulated_records)),
            profit_factor=_profit_factor(win_movements, loss_movements),
            average_win=_average(win_movements),
            average_loss=_average(loss_movements),
            risk_adjusted_diagnostic_ratio=_risk_adjusted_diagnostic_ratio(total_return, max_drawdown),
        )


def simulate_historical_signals(
    historical_data: Sequence[Mapping[str, Any] | object],
    signals: Sequence[StrategySignalResult],
) -> HistoricalSimulationResult:
    return HistoricalSimulationAdapter().simulate(historical_data, signals)


def _read_field(value: Mapping[str, Any] | object, field: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _next_close(historical_data: Sequence[Mapping[str, Any] | object], index: int) -> float | None:
    if index + 1 >= len(historical_data):
        return None
    return _to_float(_read_field(historical_data[index + 1], "close"))


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _raw_movement(direction: str, current_close: float | None, next_close: float | None) -> float:
    if current_close is None or next_close is None:
        return 0.0
    if direction == "LONG":
        return round(next_close - current_close, 4)
    if direction == "SHORT":
        return round(current_close - next_close, 4)
    return 0.0


def _percentage_movement(raw_movement: float, current_close: float | None) -> float:
    if current_close in (None, 0):
        return 0.0
    return round(raw_movement / current_close * 100, 4)


def _directional_outcome(raw_movement: float) -> str:
    if raw_movement > 0:
        return "WIN"
    if raw_movement < 0:
        return "LOSS"
    return "FLAT"


def _equity_curve(records: Iterable[HistoricalSimulationRecord]) -> list[float]:
    equity = 0.0
    curve: list[float] = []
    for record in records:
        if record.decision_status == "SIMULATED_SIGNAL":
            equity = round(equity + record.raw_point_movement, 4)
        curve.append(equity)
    return curve


def _equity_at(equity_curve: Sequence[float], index: int, fallback: float) -> float:
    if 0 <= index < len(equity_curve):
        return equity_curve[index]
    return fallback


def _max_drawdown(equity_curve: Iterable[float]) -> float:
    peak = 0.0
    max_drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return round(max_drawdown, 4)


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(count / total * 100, 4)


def _average(values: Sequence[float | int]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _minimum(values: Sequence[float]) -> float:
    return min(values) if values else 0.0


def _maximum(values: Sequence[float]) -> float:
    return max(values) if values else 0.0


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in sorted(values):
        counts[value] = counts.get(value, 0) + 1
    return counts


def _candidate_items(
    candidates: Mapping[str, HistoricalSimulationResult] | Sequence[tuple[str, HistoricalSimulationResult]],
) -> list[tuple[str, HistoricalSimulationResult]]:
    items = candidates.items() if isinstance(candidates, Mapping) else candidates
    candidate_items = [(str(candidate_id), result) for candidate_id, result in items]
    candidate_ids = [candidate_id for candidate_id, _ in candidate_items]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("candidate identifiers must be unique")
    return sorted(candidate_items, key=lambda item: item[0])


_CONSTRAINT_METRICS = {
    "min_total_unitless_return",
    "max_drawdown",
    "min_profit_factor",
    "min_win_rate",
    "min_expectancy",
    "min_confidence_average",
    "min_movement_total",
}


def _constraint_values(constraints: Mapping[str, float | int]) -> dict[str, float]:
    unsupported = sorted(set(constraints) - _CONSTRAINT_METRICS)
    if unsupported:
        raise ValueError(f"unsupported diagnostic constraints: {', '.join(unsupported)}")
    return {name: float(constraints[name]) for name in sorted(constraints)}


def _constraint_distribution_names(eligibility: HistoricalSimulationConstraintEligibilitySummary) -> list[str]:
    names = set(eligibility.constraint_names)
    for diagnostic in eligibility.diagnostics:
        names.update(diagnostic.passed_constraints)
        names.update(diagnostic.failed_constraints)
    return sorted(names)


def _diagnostics_by_candidate_id(
    diagnostics: Sequence[HistoricalSimulationConstraintDiagnostic],
) -> dict[str, HistoricalSimulationConstraintDiagnostic]:
    diagnostic_map: dict[str, HistoricalSimulationConstraintDiagnostic] = {}
    duplicate_candidate_ids: list[str] = []
    for diagnostic in diagnostics:
        if diagnostic.candidate_id in diagnostic_map:
            duplicate_candidate_ids.append(diagnostic.candidate_id)
        diagnostic_map[diagnostic.candidate_id] = diagnostic
    if duplicate_candidate_ids:
        duplicates = ", ".join(sorted(set(duplicate_candidate_ids)))
        raise ValueError(f"constraint diagnostics must be unique by candidate_id: {duplicates}")
    return diagnostic_map


def _constraint_metric(candidate: HistoricalSimulationParameterSweepCandidate, name: str) -> float:
    if name == "max_drawdown":
        return float(candidate.max_drawdown)
    metric_name = name.removeprefix("min_").removeprefix("max_")
    return float(getattr(candidate, metric_name))


def _constraint_passes(name: str, actual: float, threshold: float) -> bool:
    if name.startswith("max_"):
        return actual <= threshold
    return actual >= threshold


def _sweep_rank_key(candidate_id: str, result: HistoricalSimulationResult) -> tuple[float, float, float, float, float, str]:
    diagnostics = result.diagnostics
    return (
        -diagnostics.total_unitless_return,
        diagnostics.max_drawdown,
        -diagnostics.profit_factor,
        -diagnostics.win_rate,
        -diagnostics.expectancy,
        candidate_id,
    )


def _sweep_worst_key(candidate_id: str, result: HistoricalSimulationResult) -> tuple[float, float, float, float, float, str]:
    diagnostics = result.diagnostics
    return (
        diagnostics.total_unitless_return,
        -diagnostics.max_drawdown,
        diagnostics.profit_factor,
        diagnostics.win_rate,
        diagnostics.expectancy,
        candidate_id,
    )


def _profit_factor(win_movements: Sequence[float], loss_movements: Sequence[float]) -> float:
    gross_win = sum(win_movements)
    gross_loss = abs(sum(loss_movements))
    if gross_loss == 0:
        return round(gross_win, 4) if gross_win > 0 else 0.0
    return round(gross_win / gross_loss, 4)


def _risk_adjusted_diagnostic_ratio(total_return: float, max_drawdown: float) -> float:
    if max_drawdown == 0:
        return total_return if total_return > 0 else 0.0
    return round(total_return / max_drawdown, 4)


def _normalized(value: Any) -> str:
    if value is None:
        return "NONE"
    return str(value).strip().upper()
