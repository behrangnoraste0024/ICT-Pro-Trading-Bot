from __future__ import annotations

from models.historical_sample_download import HistoricalSampleDownloadPlan, HistoricalSampleDownloadResult
from reporting.historical_sample_download_report import format_historical_sample_download_report


def test_download_report_contains_expected_header_and_rows() -> None:
    plan = HistoricalSampleDownloadPlan(
        registry_path="configs/historical_sample_registry.json",
        exchange="binance",
        total_samples=1,
        planned_downloads=1,
        skipped_samples=0,
        results=[
            HistoricalSampleDownloadResult(
                sample_name="sample",
                symbol="BTC/USDT",
                timeframe="15m",
                fixture_path="data/historical/sample.json",
                exchange="binance",
                status="DRY_RUN",
                candle_count=0,
                expected_min_candles=1000,
            )
        ],
    )

    text = format_historical_sample_download_report(plan)

    assert "===== HISTORICAL SAMPLE DOWNLOAD PLAN =====" in text
    assert "Planned Downloads: 1" in text
    assert "sample | BTC/USDT | 15m | DRY_RUN" in text
