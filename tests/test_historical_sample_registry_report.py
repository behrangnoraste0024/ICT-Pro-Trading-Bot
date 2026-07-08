from __future__ import annotations

from models.historical_sample_registry import HistoricalSampleAvailability, HistoricalSampleRegistryReport
from reporting.historical_sample_registry_report import format_historical_sample_registry_report


def test_text_report_contains_historical_sample_registry() -> None:
    report = HistoricalSampleRegistryReport(
        registry_path="configs/historical_sample_registry.json",
        total_samples=1,
        available_samples=1,
        required_full_available=True,
        required_ci_available=True,
        samples=[
            HistoricalSampleAvailability(
                sample_name="sample",
                symbol="BTC/USDT",
                timeframe="15m",
                fixture_path="data/historical/sample.json",
                exists=True,
                readable=True,
                file_size_bytes=100,
                modified_at="2026-07-08T00:00:00+00:00",
                candle_count=1000,
                expected_min_candles=1000,
                meets_min_candles=True,
                status="AVAILABLE",
                required_for_full_gate=True,
                required_for_ci_gate=True,
            )
        ],
    )

    text = format_historical_sample_registry_report(report)

    assert "===== HISTORICAL SAMPLE REGISTRY =====" in text
    assert "Full Required Available: YES" in text
    assert "sample | BTC/USDT | 15m | AVAILABLE" in text


def test_quiet_report_omits_sample_table() -> None:
    report = HistoricalSampleRegistryReport(total_samples=0)

    text = format_historical_sample_registry_report(report, quiet=True)

    assert "Samples:" not in text
