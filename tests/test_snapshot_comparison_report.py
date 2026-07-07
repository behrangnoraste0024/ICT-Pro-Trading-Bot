from __future__ import annotations

from models.snapshot_comparison import SnapshotComparisonResult, SnapshotSampleComparison
from reporting.snapshot_comparison_report import format_snapshot_comparison_report


def test_report_displays_comparison_section() -> None:
    result = SnapshotComparisonResult(
        baseline_path="baseline.json",
        candidate_path="candidate.json",
        baseline_git_commit="abc123",
        candidate_git_commit="def456",
        baseline_created_at="2026-07-07T12:00:00+00:00",
        candidate_created_at="2026-07-07T13:00:00+00:00",
        baseline_recommended_profile="balanced_smc_decision_065",
        candidate_recommended_profile="balanced_smc_decision_065",
        total_samples_compared=1,
        passed_samples=1,
        aggregate_net_after_costs_delta=100.0,
        regression_status="PASS",
        improvement_flags=["btcusdt_15m_1000:NET_AFTER_COSTS_INCREASED"],
        sample_comparisons=[
            SnapshotSampleComparison(
                sample_name="btcusdt_15m_1000",
                symbol="BTC/USDT",
                timeframe="15m",
                severity="PASS",
                baseline_status="PASSED",
                candidate_status="PASSED",
                baseline_wf_status="PASS",
                candidate_wf_status="PASS",
                baseline_profile="balanced_smc_decision_065",
                candidate_profile="balanced_smc_decision_065",
                baseline_net_after_costs=1404.24,
                candidate_net_after_costs=1504.24,
                net_after_costs_delta=100.0,
            )
        ],
    )

    output = format_snapshot_comparison_report(result)

    assert "===== SNAPSHOT COMPARISON / REGRESSION GUARD =====" in output
    assert "Regression Status : PASS" in output
    assert "Sample | Symbol | TF | Severity" in output
    assert "btcusdt_15m_1000 | BTC/USDT | 15m | PASS" in output
