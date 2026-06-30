from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OTEDiagnostics:
    windows_analyzed: int = 0
    ote_available_count: int = 0
    ote_missing_count: int = 0
    in_ote_count: int = 0
    not_in_ote_count: int = 0
    near_ote_0_1_pct_count: int = 0
    near_ote_0_25_pct_count: int = 0
    near_ote_0_5_pct_count: int = 0
    near_ote_1_0_pct_count: int = 0
    average_distance_to_ote: float | None = None
    median_distance_to_ote: float | None = None
    max_distance_to_ote: float | None = None
    premium_count: int = 0
    discount_count: int = 0
    equilibrium_count: int = 0
    unknown_zone_count: int = 0
    bullish_ote_count: int = 0
    bearish_ote_count: int = 0
    none_ote_count: int = 0
    average_distance_to_equilibrium: float | None = None
    median_distance_to_equilibrium: float | None = None
    max_distance_to_equilibrium: float | None = None
    near_equilibrium_0_1_pct_count: int = 0
    near_equilibrium_0_25_pct_count: int = 0
    near_equilibrium_0_5_pct_count: int = 0
    event_type: str = "OTE_DIAGNOSTICS"

    def __str__(self) -> str:
        return (
            f"{self.event_type} | WINDOWS={self.windows_analyzed} | "
            f"IN_OTE={self.in_ote_count} | NOT_IN_OTE={self.not_in_ote_count} | "
            f"NEAR_0.5%={self.near_ote_0_5_pct_count}"
        )
