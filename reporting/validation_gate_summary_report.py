from __future__ import annotations

from models.validation_gate_summary import ValidationGateSummary


def format_validation_gate_summary(summary: ValidationGateSummary) -> str:
    return "\n".join(
        [
            "===== VALIDATION GATE SUMMARY =====",
            f"Gate Status       : {summary.gate_status}",
            f"Regression Status : {summary.regression_status}",
            f"Profile           : {summary.recommended_profile}",
            f"Baseline Commit   : {summary.baseline_commit}",
            f"Candidate Commit  : {summary.candidate_commit}",
            f"Baseline Snapshot : {_fmt_path(summary.baseline_snapshot_path)}",
            f"Candidate Snapshot: {_fmt_path(summary.candidate_snapshot_path)}",
            f"Comparison        : {_fmt_comparisons(summary.comparison_paths)}",
            (
                "Samples           : "
                f"total={summary.total_samples} completed={summary.completed_samples} "
                f"passed={summary.passed_samples} failed={summary.failed_samples} "
                f"skipped={summary.skipped_samples}"
            ),
            f"NetAfterCost Delta: {_fmt(summary.net_after_costs_delta)}",
            f"MaxDD Delta       : {_fmt(summary.max_drawdown_delta)}",
            f"Regression Flags  : {summary.regression_flag_count}",
            f"Warning Samples   : {summary.warning_sample_count}",
            f"Failed Samples    : {summary.failed_sample_count}",
            f"Cache             : {_fmt_cache(summary)}",
            f"Fail On Regression: {str(summary.fail_on_regression).lower()}",
            "===============================",
        ]
    )


def _fmt(value) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, (float, int)):
        return f"{value:.2f}"
    return str(value)


def _fmt_path(value: str | None) -> str:
    return value or "N/A"


def _fmt_comparisons(paths: list[str]) -> str:
    if not paths:
        return "N/A"
    return ", ".join(paths)


def _fmt_cache(summary: ValidationGateSummary) -> str:
    if summary.primary_cache_status is None:
        return "N/A"
    return (
        f"{summary.primary_cache_status} original={_fmt(summary.primary_original_elapsed)}s "
        f"read={_fmt(summary.primary_cache_read_elapsed)}s "
        f"saved={_fmt(summary.primary_saved_estimate)}s"
    )
