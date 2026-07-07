from __future__ import annotations

from models.historical_sample_registry import HistoricalSampleRegistryReport


def format_historical_sample_registry_report(report: HistoricalSampleRegistryReport, quiet: bool = False) -> str:
    lines = [
        "===== HISTORICAL SAMPLE REGISTRY =====",
        f"Registry : {report.registry_path}",
        f"Total    : {report.total_samples}",
        f"Available: {report.available_samples}",
        f"Missing  : {report.missing_samples}",
        f"Invalid  : {report.invalid_samples}",
        f"Full Required Available: {_yes_no(report.required_full_available)}",
        f"CI Required Available  : {_yes_no(report.required_ci_available)}",
    ]
    if quiet:
        return "\n".join(lines)
    lines.extend(
        [
            "",
            "Samples:",
            "Sample | Symbol | TF | Status | Candles | Min | RequiredFull | RequiredCI | SizeBytes | ModifiedAt | Path | Error",
        ]
    )
    for sample in report.samples:
        lines.append(
            f"{sample.sample_name} | {sample.symbol} | {sample.timeframe} | {sample.status} | "
            f"{_fmt(sample.candle_count)} | {sample.expected_min_candles} | "
            f"{_yes_no(sample.required_for_full_gate)} | {_yes_no(sample.required_for_ci_gate)} | "
            f"{_fmt(sample.file_size_bytes)} | {_fmt(sample.modified_at)} | "
            f"{sample.fixture_path} | {_fmt(sample.error_message)}"
        )
    return "\n".join(lines)


def _yes_no(value: bool) -> str:
    return "YES" if value else "NO"


def _fmt(value) -> str:
    return "None" if value is None else str(value)
