from __future__ import annotations

from models.snapshot_comparison import SnapshotComparisonResult


def format_snapshot_comparison_report(result: SnapshotComparisonResult) -> str:
    lines = [
        "===== SNAPSHOT COMPARISON / REGRESSION GUARD =====",
        f"Baseline Snapshot : {result.baseline_path}",
        f"Candidate Snapshot: {result.candidate_path}",
        f"Baseline Commit   : {result.baseline_git_commit}",
        f"Candidate Commit  : {result.candidate_git_commit}",
        f"Baseline Created  : {result.baseline_created_at}",
        f"Candidate Created : {result.candidate_created_at}",
        f"Baseline Profile  : {result.baseline_recommended_profile}",
        f"Candidate Profile : {result.candidate_recommended_profile}",
        f"Regression Status : {result.regression_status}",
        "",
        "Summary:",
        f"Samples Compared  : {result.total_samples_compared}",
        f"Passed Samples    : {result.passed_samples}",
        f"Warning Samples   : {result.warning_samples}",
        f"Failed Samples    : {result.failed_samples}",
        f"NetAfterCost Delta: {_fmt(result.aggregate_net_after_costs_delta)}",
        f"MaxDD Delta       : {_fmt(result.aggregate_max_drawdown_delta)}",
        "",
        "Regression Flags:",
    ]
    lines.extend(_flag_lines(result.regression_flags))
    lines.extend(["", "Improvement Flags:"])
    lines.extend(_flag_lines(result.improvement_flags))
    lines.extend(
        [
            "",
            "Sample Comparison:",
            "Sample | Symbol | TF | Severity | Status Base->Cand | WF Base->Cand | Profile Base->Cand | Trades Delta | Win% Delta | NetAfterCost Base | NetAfterCost Cand | Net Delta | MaxDD Base | MaxDD Cand | MaxDD Delta | Flags",
        ]
    )
    for row in result.sample_comparisons:
        lines.append(
            f"{row.sample_name} | {row.symbol} | {row.timeframe} | {row.severity} | "
            f"{row.baseline_status}->{row.candidate_status} | "
            f"{row.baseline_wf_status}->{row.candidate_wf_status} | "
            f"{row.baseline_profile}->{row.candidate_profile} | "
            f"{row.trades_delta} | {_fmt(row.win_rate_delta)} | "
            f"{_fmt(row.baseline_net_after_costs)} | {_fmt(row.candidate_net_after_costs)} | "
            f"{_fmt(row.net_after_costs_delta)} | {_fmt(row.baseline_max_drawdown)} | "
            f"{_fmt(row.candidate_max_drawdown)} | {_fmt(row.max_drawdown_delta)} | "
            f"{','.join(row.regression_flags)}"
        )
    return "\n".join(lines)


def _flag_lines(flags: list[str]) -> list[str]:
    if not flags:
        return ["- None"]
    return [f"- {flag}" for flag in flags]


def _fmt(value) -> str:
    if value is None:
        return "None"
    if isinstance(value, (float, int)):
        return f"{value:.2f}"
    return str(value)
