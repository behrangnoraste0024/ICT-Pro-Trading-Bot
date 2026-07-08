from __future__ import annotations

from models.multi_sample_validation import MultiSampleValidationResult


def format_multi_sample_validation_report(result: MultiSampleValidationResult, show_details: bool = False) -> str:
    lines = [
        "===== MULTI-SAMPLE VALIDATION =====",
        f"Recommended Profile : {result.recommended_profile}",
        f"Sample Scope        : {result.sample_scope}",
        f"Total Samples       : {result.total_samples}",
        f"Selected Samples    : {result.selected_samples}",
        f"Excluded Samples    : {result.excluded_samples}",
        f"Completed Samples   : {result.completed_samples}",
        f"Passed Samples      : {result.passed_samples}",
        f"Warning Samples     : {result.warning_samples}",
        f"Failed Samples      : {result.failed_samples}",
        f"Skipped Samples     : {result.skipped_samples}",
        f"Error Samples       : {result.error_samples}",
        "",
        "Samples:",
        "Sample | Symbol | TF | Status | Profile | ScoreThr | Trades | W/L | Win% | NetAfterCost | MaxDD | WFStatus | ProfSeg | LosingSeg | EmptySeg | WorstSegNet | ImproveVsBase | Cache | CacheRead | OrigElapsed | SavedEst | CacheAge | Error",
    ]
    for row in result.rows:
        lines.append(
            f"{row.sample_name} | {row.symbol} | {row.timeframe} | {row.status} | "
            f"{row.recommended_profile} | {_fmt(row.score_threshold)} | {row.total_trades} | "
            f"{row.wins}/{row.losses} | {_fmt(row.win_rate)} | {_fmt(row.net_pnl_after_costs)} | "
            f"{_fmt(row.max_drawdown)} | {row.validation_status} | {_fmt(row.profitable_segments)} | "
            f"{_fmt(row.losing_segments)} | {_fmt(row.empty_segments)} | "
            f"{_fmt(row.worst_segment_net_pnl_after_costs)} | {_fmt(row.improvement_vs_baseline)} | "
            f"{row.cache_status} | {_fmt(row.cache_read_elapsed_seconds)} | "
            f"{_fmt(row.original_elapsed_seconds)} | {_fmt(row.estimated_saved_seconds)} | "
            f"{_fmt(row.cache_age_seconds)} | "
            f"{row.error_message}"
        )
    if show_details:
        lines.extend(["", "Details:"])
        for row in result.rows:
            lines.append(
                f"{row.sample_name}: status={row.status}, fixture={row.fixture_path}, "
                f"elapsed={_fmt(row.elapsed_seconds)}s, reason={row.error_message}"
            )
    return "\n".join(lines)


def _fmt(value) -> str:
    if value is None:
        return "None"
    if isinstance(value, (float, int)):
        return f"{value:.2f}"
    return str(value)
