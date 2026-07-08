from __future__ import annotations

from models.historical_sample_preparation import HistoricalSamplePreparationAction, HistoricalSamplePreparationPlan
from reporting.historical_sample_preparation_report import format_historical_sample_preparation_report


def test_report_contains_historical_sample_preparation_plan() -> None:
    plan = HistoricalSamplePreparationPlan(
        registry_path="configs/historical_sample_registry.json",
        total_samples=1,
        ready_samples=0,
        action_required_samples=1,
        required_full_ready=False,
        required_ci_ready=False,
        actions=[
            HistoricalSamplePreparationAction(
                sample_name="sample",
                symbol="BTC/USDT",
                timeframe="15m",
                fixture_path="data/historical/sample.json",
                current_status="MISSING",
                required_for_full_gate=True,
                required_for_ci_gate=True,
                expected_min_candles=1000,
                action_type="IMPORT_REQUIRED",
                reason="sample file is missing",
                suggested_download_command="download suggestion",
                suggested_import_command="import suggestion",
            )
        ],
    )

    text = format_historical_sample_preparation_report(plan)

    assert "===== HISTORICAL SAMPLE PREPARATION PLAN =====" in text
    assert "Need Action   : 1" in text
    assert "sample | BTC/USDT | 15m | MISSING | IMPORT_REQUIRED" in text
    assert "Suggested Commands:" in text
    assert "import suggestion" in text
