from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DealingRangeDiagnostics:
    windows_analyzed: int = 0
    range_available_count: int = 0
    range_missing_count: int = 0
    invalid_range_count: int = 0
    average_range_size: float | None = None
    median_range_size: float | None = None
    max_range_size: float | None = None
    min_range_size: float | None = None
    average_range_size_percent: float | None = None
    median_range_size_percent: float | None = None
    max_range_size_percent: float | None = None
    min_range_size_percent: float | None = None
    average_distance_to_equilibrium: float | None = None
    median_distance_to_equilibrium: float | None = None
    max_distance_to_equilibrium: float | None = None
    average_distance_to_equilibrium_percent: float | None = None
    median_distance_to_equilibrium_percent: float | None = None
    max_distance_to_equilibrium_percent: float | None = None
    premium_count: int = 0
    discount_count: int = 0
    equilibrium_count: int = 0
    unknown_zone_count: int = 0
    uptrend_count: int = 0
    downtrend_count: int = 0
    range_trend_count: int = 0
    unknown_trend_count: int = 0
    trend_zone_counts: dict[str, int] = field(default_factory=dict)
    ote_direction_zone_counts: dict[str, int] = field(default_factory=dict)
    bearish_ote_discount_count: int = 0
    bullish_ote_premium_count: int = 0
    downtrend_discount_count: int = 0
    uptrend_premium_count: int = 0
    average_external_high_age: float | None = None
    average_external_low_age: float | None = None
    max_external_high_age: float | None = None
    max_external_low_age: float | None = None
    event_type: str = "DEALING_RANGE_DIAGNOSTICS"

    def __str__(self) -> str:
        return (
            f"{self.event_type} | WINDOWS={self.windows_analyzed} | "
            f"RANGE_AVAILABLE={self.range_available_count} | "
            f"PREMIUM={self.premium_count} | DISCOUNT={self.discount_count}"
        )
