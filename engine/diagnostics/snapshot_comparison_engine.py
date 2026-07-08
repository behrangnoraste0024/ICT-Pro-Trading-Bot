from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.snapshot_comparison import SnapshotComparisonResult, SnapshotSampleComparison


class SnapshotComparisonEngine:
    def compare_files(self, baseline_path: str, candidate_path: str) -> SnapshotComparisonResult:
        baseline = self._load_snapshot(baseline_path)
        candidate = self._load_snapshot(candidate_path)
        return self.compare_snapshots(baseline, candidate, baseline_path, candidate_path)

    def compare_snapshots(
        self,
        baseline: dict[str, Any],
        candidate: dict[str, Any],
        baseline_path: str = "<baseline>",
        candidate_path: str = "<candidate>",
    ) -> SnapshotComparisonResult:
        baseline_metadata = baseline.get("metadata") or {}
        candidate_metadata = candidate.get("metadata") or {}
        baseline_rows = self._rows_by_sample(baseline)
        candidate_rows = self._rows_by_sample(candidate)
        sample_names = sorted(set(baseline_rows) | set(candidate_rows))
        sample_comparisons = [
            self._compare_sample(name, baseline_rows.get(name), candidate_rows.get(name))
            for name in sample_names
        ]
        regression_flags = [
            f"{comparison.sample_name}:{flag}"
            for comparison in sample_comparisons
            for flag in comparison.regression_flags
        ]
        improvement_flags = [
            f"{comparison.sample_name}:{flag}"
            for comparison in sample_comparisons
            for flag in comparison.improvement_flags
        ]
        recommended_profile_changed = baseline_metadata.get("recommended_profile") != candidate_metadata.get("recommended_profile")
        if recommended_profile_changed:
            regression_flags.append("RECOMMENDED_PROFILE_CHANGED")
        result = SnapshotComparisonResult(
            baseline_path=baseline_path,
            candidate_path=candidate_path,
            baseline_git_commit=baseline_metadata.get("git_commit"),
            candidate_git_commit=candidate_metadata.get("git_commit"),
            baseline_created_at=baseline_metadata.get("created_at"),
            candidate_created_at=candidate_metadata.get("created_at"),
            baseline_recommended_profile=baseline_metadata.get("recommended_profile"),
            candidate_recommended_profile=candidate_metadata.get("recommended_profile"),
            recommended_profile_changed=recommended_profile_changed,
            total_samples_compared=len(sample_comparisons),
            passed_samples=sum(1 for comparison in sample_comparisons if comparison.severity == "PASS"),
            warning_samples=sum(1 for comparison in sample_comparisons if comparison.severity == "WARNING"),
            failed_samples=sum(1 for comparison in sample_comparisons if comparison.severity == "FAIL"),
            aggregate_net_after_costs_delta=sum(comparison.net_after_costs_delta for comparison in sample_comparisons),
            aggregate_max_drawdown_delta=sum(comparison.max_drawdown_delta for comparison in sample_comparisons),
            regression_flags=regression_flags,
            improvement_flags=improvement_flags,
            sample_comparisons=sample_comparisons,
            diagnostics={
                "baseline_schema_version": baseline_metadata.get("snapshot_schema_version"),
                "candidate_schema_version": candidate_metadata.get("snapshot_schema_version"),
            },
        )
        result.regression_status = self._overall_status(result)
        return result

    def _load_snapshot(self, path: str) -> dict[str, Any]:
        snapshot_path = Path(path)
        if not snapshot_path.exists():
            raise FileNotFoundError(f"snapshot not found: {path}")
        with snapshot_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise ValueError(f"snapshot must be a JSON object: {path}")
        if "multi_sample_result" not in loaded:
            raise ValueError(f"snapshot missing multi_sample_result: {path}")
        return loaded

    def _rows_by_sample(self, snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
        result = snapshot.get("multi_sample_result") or {}
        rows = result.get("rows") or []
        return {
            str(row.get("sample_name")): row
            for row in rows
            if isinstance(row, dict) and row.get("sample_name") is not None
        }

    def _compare_sample(
        self,
        sample_name: str,
        baseline: dict[str, Any] | None,
        candidate: dict[str, Any] | None,
    ) -> SnapshotSampleComparison:
        regression_flags: list[str] = []
        improvement_flags: list[str] = []
        if baseline is None:
            if self._text(candidate, "status") != "PASSED":
                regression_flags.append("CANDIDATE_ONLY_NON_PASSED")
            else:
                improvement_flags.append("NEW_PASSED_SAMPLE")
        if candidate is None:
            regression_flags.append("SAMPLE_MISSING_FROM_CANDIDATE")

        baseline = baseline or {}
        candidate = candidate or {}
        if self._text(candidate, "status") == "SKIPPED_OUT_OF_SCOPE":
            return SnapshotSampleComparison(
                sample_name=sample_name,
                symbol=self._text(candidate, "symbol") or self._text(baseline, "symbol"),
                timeframe=self._text(candidate, "timeframe") or self._text(baseline, "timeframe"),
                baseline_status=self._text(baseline, "status"),
                candidate_status=self._text(candidate, "status"),
                baseline_profile=self._text(baseline, "recommended_profile"),
                candidate_profile=self._text(candidate, "recommended_profile"),
                baseline_trades=self._int(baseline, "total_trades"),
                candidate_trades=self._int(candidate, "total_trades"),
                baseline_win_rate=self._float(baseline, "win_rate"),
                candidate_win_rate=self._float(candidate, "win_rate"),
                baseline_net_after_costs=self._float(baseline, "net_pnl_after_costs"),
                candidate_net_after_costs=self._float(candidate, "net_pnl_after_costs"),
                baseline_max_drawdown=self._float(baseline, "max_drawdown"),
                candidate_max_drawdown=self._float(candidate, "max_drawdown"),
                baseline_wf_status=self._text(baseline, "validation_status"),
                candidate_wf_status=self._text(candidate, "validation_status"),
                baseline_profitable_segments=self._optional_int(baseline, "profitable_segments"),
                candidate_profitable_segments=self._optional_int(candidate, "profitable_segments"),
                baseline_losing_segments=self._optional_int(baseline, "losing_segments"),
                candidate_losing_segments=self._optional_int(candidate, "losing_segments"),
                baseline_empty_segments=self._optional_int(baseline, "empty_segments"),
                candidate_empty_segments=self._optional_int(candidate, "empty_segments"),
                baseline_worst_segment_net=self._optional_float(baseline, "worst_segment_net_pnl_after_costs"),
                candidate_worst_segment_net=self._optional_float(candidate, "worst_segment_net_pnl_after_costs"),
                severity="PASS",
                regression_flags=[],
                improvement_flags=["SKIPPED_OUT_OF_SCOPE"],
            )
        comparison = SnapshotSampleComparison(
            sample_name=sample_name,
            symbol=self._text(candidate, "symbol") or self._text(baseline, "symbol"),
            timeframe=self._text(candidate, "timeframe") or self._text(baseline, "timeframe"),
            baseline_status=self._text(baseline, "status"),
            candidate_status=self._text(candidate, "status"),
            baseline_profile=self._text(baseline, "recommended_profile"),
            candidate_profile=self._text(candidate, "recommended_profile"),
            baseline_trades=self._int(baseline, "total_trades"),
            candidate_trades=self._int(candidate, "total_trades"),
            baseline_win_rate=self._float(baseline, "win_rate"),
            candidate_win_rate=self._float(candidate, "win_rate"),
            baseline_net_after_costs=self._float(baseline, "net_pnl_after_costs"),
            candidate_net_after_costs=self._float(candidate, "net_pnl_after_costs"),
            baseline_max_drawdown=self._float(baseline, "max_drawdown"),
            candidate_max_drawdown=self._float(candidate, "max_drawdown"),
            baseline_wf_status=self._text(baseline, "validation_status"),
            candidate_wf_status=self._text(candidate, "validation_status"),
            baseline_profitable_segments=self._optional_int(baseline, "profitable_segments"),
            candidate_profitable_segments=self._optional_int(candidate, "profitable_segments"),
            baseline_losing_segments=self._optional_int(baseline, "losing_segments"),
            candidate_losing_segments=self._optional_int(candidate, "losing_segments"),
            baseline_empty_segments=self._optional_int(baseline, "empty_segments"),
            candidate_empty_segments=self._optional_int(candidate, "empty_segments"),
            baseline_worst_segment_net=self._optional_float(baseline, "worst_segment_net_pnl_after_costs"),
            candidate_worst_segment_net=self._optional_float(candidate, "worst_segment_net_pnl_after_costs"),
            regression_flags=regression_flags,
            improvement_flags=improvement_flags,
        )
        self._compute_deltas(comparison)
        self._classify_changes(comparison)
        comparison.severity = self._sample_severity(comparison.regression_flags)
        return comparison

    def _compute_deltas(self, comparison: SnapshotSampleComparison) -> None:
        comparison.status_changed = comparison.baseline_status != comparison.candidate_status
        comparison.profile_changed = comparison.baseline_profile != comparison.candidate_profile
        comparison.trades_delta = comparison.candidate_trades - comparison.baseline_trades
        comparison.win_rate_delta = comparison.candidate_win_rate - comparison.baseline_win_rate
        comparison.net_after_costs_delta = comparison.candidate_net_after_costs - comparison.baseline_net_after_costs
        comparison.max_drawdown_delta = comparison.candidate_max_drawdown - comparison.baseline_max_drawdown
        comparison.wf_status_changed = comparison.baseline_wf_status != comparison.candidate_wf_status
        comparison.profitable_segments_delta = self._optional_delta(
            comparison.baseline_profitable_segments,
            comparison.candidate_profitable_segments,
        )
        comparison.losing_segments_delta = self._optional_delta(
            comparison.baseline_losing_segments,
            comparison.candidate_losing_segments,
        )
        comparison.empty_segments_delta = self._optional_delta(
            comparison.baseline_empty_segments,
            comparison.candidate_empty_segments,
        )
        comparison.worst_segment_net_delta = self._optional_float_delta(
            comparison.baseline_worst_segment_net,
            comparison.candidate_worst_segment_net,
        )

    def _classify_changes(self, comparison: SnapshotSampleComparison) -> None:
        flags = comparison.regression_flags
        improvements = comparison.improvement_flags
        if "SAMPLE_MISSING_FROM_CANDIDATE" in flags or "CANDIDATE_ONLY_NON_PASSED" in flags:
            return
        if "NEW_PASSED_SAMPLE" in improvements:
            return
        if comparison.baseline_status == "PASSED" and comparison.candidate_status in ("FAILED", "ERROR"):
            flags.append("STATUS_PASSED_TO_FAILED")
        elif comparison.baseline_status == "PASSED" and comparison.candidate_status == "WARNING":
            flags.append("STATUS_PASSED_TO_WARNING")
        elif comparison.baseline_status in ("FAILED", "WARNING") and comparison.candidate_status == "PASSED":
            improvements.append("STATUS_IMPROVED_TO_PASSED")

        if comparison.baseline_wf_status == "PASS" and comparison.candidate_wf_status == "FAIL":
            flags.append("WF_PASS_TO_FAIL")
        if comparison.net_after_costs_delta < 0:
            if self._large_net_drop(comparison.baseline_net_after_costs, comparison.net_after_costs_delta):
                flags.append("NET_AFTER_COSTS_DROP_FAIL")
            else:
                flags.append("NET_AFTER_COSTS_DECREASED")
        elif comparison.net_after_costs_delta > 0:
            improvements.append("NET_AFTER_COSTS_INCREASED")

        if comparison.max_drawdown_delta > 0:
            if self._large_drawdown_increase(comparison.baseline_max_drawdown, comparison.max_drawdown_delta):
                flags.append("MAX_DRAWDOWN_INCREASE_FAIL")
        elif comparison.max_drawdown_delta < 0:
            improvements.append("MAX_DRAWDOWN_DECREASED")

        if comparison.win_rate_delta < 0:
            flags.append("WIN_RATE_DECREASED")
        elif comparison.win_rate_delta > 0:
            improvements.append("WIN_RATE_INCREASED")

        if comparison.profitable_segments_delta is not None:
            if comparison.profitable_segments_delta < 0:
                flags.append("PROFITABLE_SEGMENTS_DECREASED")
            elif comparison.profitable_segments_delta > 0:
                improvements.append("PROFITABLE_SEGMENTS_INCREASED")
        if comparison.losing_segments_delta is not None:
            if comparison.losing_segments_delta > 0:
                flags.append("LOSING_SEGMENTS_INCREASED")
            elif comparison.losing_segments_delta < 0:
                improvements.append("LOSING_SEGMENTS_DECREASED")
        if comparison.baseline_trades > 0 and comparison.candidate_trades < comparison.baseline_trades * 0.5:
            flags.append("TRADES_DECREASED_MORE_THAN_50_PERCENT")

    def _sample_severity(self, flags: list[str]) -> str:
        if any(flag.endswith("_FAIL") or flag in ("STATUS_PASSED_TO_FAILED", "WF_PASS_TO_FAIL") for flag in flags):
            return "FAIL"
        if flags:
            return "WARNING"
        return "PASS"

    def _overall_status(self, result: SnapshotComparisonResult) -> str:
        if result.recommended_profile_changed:
            return "FAIL"
        if result.failed_samples:
            return "FAIL"
        if result.warning_samples:
            return "WARNING"
        return "PASS"

    def _large_net_drop(self, baseline: float, delta: float) -> bool:
        drop = abs(delta)
        threshold = abs(baseline) * 0.10
        return drop > 100 and drop > threshold

    def _large_drawdown_increase(self, baseline: float, delta: float) -> bool:
        threshold = abs(baseline) * 0.25
        return delta > 100 and delta > threshold

    def _optional_delta(self, baseline: int | None, candidate: int | None) -> int | None:
        if baseline is None or candidate is None:
            return None
        return candidate - baseline

    def _optional_float_delta(self, baseline: float | None, candidate: float | None) -> float | None:
        if baseline is None or candidate is None:
            return None
        return candidate - baseline

    def _text(self, row: dict[str, Any] | None, key: str) -> str | None:
        if not row:
            return None
        value = row.get(key)
        return None if value is None else str(value)

    def _int(self, row: dict[str, Any] | None, key: str) -> int:
        if not row:
            return 0
        try:
            return int(row.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    def _optional_int(self, row: dict[str, Any] | None, key: str) -> int | None:
        if not row or row.get(key) is None:
            return None
        try:
            return int(row.get(key))
        except (TypeError, ValueError):
            return None

    def _float(self, row: dict[str, Any] | None, key: str) -> float:
        if not row:
            return 0.0
        try:
            return float(row.get(key) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _optional_float(self, row: dict[str, Any] | None, key: str) -> float | None:
        if not row or row.get(key) is None:
            return None
        try:
            return float(row.get(key))
        except (TypeError, ValueError):
            return None
