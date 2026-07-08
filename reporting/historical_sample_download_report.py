from __future__ import annotations

from models.historical_sample_download import HistoricalSampleDownloadPlan


def format_historical_sample_download_report(plan: HistoricalSampleDownloadPlan) -> str:
    lines = [
        "===== HISTORICAL SAMPLE DOWNLOAD PLAN =====",
        f"Registry         : {plan.registry_path}",
        f"Exchange         : {plan.exchange}",
        f"Total Samples    : {plan.total_samples}",
        f"Planned Downloads: {plan.planned_downloads}",
        f"Skipped Samples  : {plan.skipped_samples}",
        "",
        "Results:",
        "Sample | Symbol | TF | Status | Candles | Min | Destination | Metadata | Error",
    ]
    for result in plan.results:
        lines.append(
            f"{result.sample_name} | {result.symbol} | {result.timeframe} | {result.status} | "
            f"{result.candle_count} | {result.expected_min_candles} | {result.fixture_path} | "
            f"{_fmt(result.metadata_path)} | {_fmt(result.error_message)}"
        )
    return "\n".join(lines)


def _fmt(value) -> str:
    return "None" if value is None else str(value)
