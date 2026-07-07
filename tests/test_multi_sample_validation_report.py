from __future__ import annotations

from models.multi_sample_validation import MultiSampleValidationResult, MultiSampleValidationRow
from reporting.multi_sample_validation_report import format_multi_sample_validation_report


def test_report_displays_multi_sample_validation_section() -> None:
    result = MultiSampleValidationResult(
        rows=[
            MultiSampleValidationRow(
                sample_name="btcusdt_15m_1000",
                fixture_path="data/historical/btcusdt_15m_1000.json",
                symbol="BTC/USDT",
                timeframe="15m",
                status="PASSED",
                recommended_profile="balanced_smc_decision_065",
                recommended_strategy="profile=balanced_smc_decision_065|cost=percent",
                score_threshold=0.65,
                total_trades=5,
                wins=5,
                losses=0,
                win_rate=100.0,
                net_pnl_after_costs=1404.24,
                max_drawdown=0,
                profitable_segments=4,
                losing_segments=0,
                empty_segments=0,
                worst_segment_net_pnl_after_costs=10,
                validation_status="PASS",
                improvement_vs_baseline=1215.74,
                cache_status="HIT",
                cache_read_elapsed_seconds=0.03,
                original_elapsed_seconds=2560.70,
                estimated_saved_seconds=2560.67,
                cache_age_seconds=5.0,
            )
        ],
        total_samples=1,
        completed_samples=1,
        passed_samples=1,
        recommended_profile="balanced_smc_decision_065",
    )

    output = format_multi_sample_validation_report(result)

    assert "===== MULTI-SAMPLE VALIDATION =====" in output
    assert "Recommended Profile : balanced_smc_decision_065" in output
    assert "Sample | Symbol | TF | Status" in output
    assert "Cache | CacheRead | OrigElapsed | SavedEst | CacheAge" in output
    assert "btcusdt_15m_1000 | BTC/USDT | 15m | PASSED" in output
    assert "HIT | 0.03 | 2560.70 | 2560.67 | 5.00" in output


def test_report_displays_skipped_missing_files_clearly() -> None:
    result = MultiSampleValidationResult(
        rows=[
            MultiSampleValidationRow(
                sample_name="ethusdt_1h_1000",
                fixture_path="data/historical/ethusdt_1h_1000.json",
                symbol="ETH/USDT",
                timeframe="1h",
                status="SKIPPED_MISSING_FILE",
            )
        ],
        total_samples=1,
        skipped_samples=1,
        recommended_profile="balanced_smc_decision_065",
    )

    output = format_multi_sample_validation_report(result, show_details=True)

    assert "SKIPPED_MISSING_FILE" in output
    assert "Details:" in output
    assert "data/historical/ethusdt_1h_1000.json" in output
