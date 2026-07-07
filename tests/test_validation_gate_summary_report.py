from __future__ import annotations

from models.validation_gate_summary import ValidationGateSummary
from reporting.validation_gate_summary_report import format_validation_gate_summary


def test_summary_report_displays_compact_health_fields() -> None:
    summary = ValidationGateSummary(
        gate_status="PASS",
        regression_status="PASS",
        recommended_profile="balanced_smc_decision_065",
        baseline_commit="base123",
        candidate_commit="cand123",
        baseline_snapshot_path="baseline.json",
        candidate_snapshot_path="candidate.json",
        comparison_paths=["comparison.json"],
        total_samples=4,
        completed_samples=1,
        passed_samples=1,
        failed_samples=0,
        skipped_samples=3,
        net_after_costs_delta=0.0,
        max_drawdown_delta=0.0,
        regression_flag_count=0,
        warning_sample_count=0,
        failed_sample_count=0,
        primary_cache_status="HIT",
        primary_original_elapsed=2999.44,
        primary_cache_read_elapsed=0.0,
        primary_saved_estimate=2999.44,
        fail_on_regression=True,
    )

    output = format_validation_gate_summary(summary)

    assert "===== VALIDATION GATE SUMMARY =====" in output
    assert "Gate Status       : PASS" in output
    assert "Regression Status : PASS" in output
    assert "Profile           : balanced_smc_decision_065" in output
    assert "Samples           : total=4 completed=1 passed=1 failed=0 skipped=3" in output
    assert "NetAfterCost Delta: 0.00" in output
    assert "Cache             : HIT original=2999.44s read=0.00s saved=2999.44s" in output
    assert "Fail On Regression: true" in output
