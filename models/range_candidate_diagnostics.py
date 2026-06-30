from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RangeCandidateStats:
    candidate_name: str
    available_count: int = 0
    missing_count: int = 0
    invalid_count: int = 0
    premium_count: int = 0
    discount_count: int = 0
    equilibrium_count: int = 0
    unknown_zone_count: int = 0
    in_ote_count: int = 0
    not_in_ote_count: int = 0
    ote_unavailable_count: int = 0
    near_ote_0_1_pct_count: int = 0
    near_ote_0_25_pct_count: int = 0
    near_ote_0_5_pct_count: int = 0
    near_ote_1_0_pct_count: int = 0
    average_distance_to_ote: float | None = None
    median_distance_to_ote: float | None = None
    max_distance_to_ote: float | None = None
    average_range_size: float | None = None
    median_range_size: float | None = None
    average_range_size_percent: float | None = None
    median_range_size_percent: float | None = None
    bearish_ote_premium_count: int = 0
    bearish_ote_discount_count: int = 0
    bullish_ote_discount_count: int = 0
    bullish_ote_premium_count: int = 0
    candidate_aligned_zone_count: int = 0
    candidate_wrong_zone_count: int = 0
    candidate_fix_wrong_zone_count: int = 0
    candidate_fix_not_in_ote_count: int = 0
    candidate_fix_near_ote_0_5_count: int = 0

    def __str__(self) -> str:
        return (
            f"{self.candidate_name} | AVAILABLE={self.available_count} | "
            f"ALIGNED={self.candidate_aligned_zone_count} | IN_OTE={self.in_ote_count} | "
            f"NEAR_0.5%={self.near_ote_0_5_pct_count}"
        )


@dataclass
class RangeCandidateDiagnostics:
    windows_analyzed: int = 0
    candidates: dict[str, RangeCandidateStats] = field(default_factory=dict)
    event_type: str = "RANGE_CANDIDATE_DIAGNOSTICS"

    def best_candidate_by_aligned_zone(self) -> RangeCandidateStats | None:
        return self._best(
            lambda stats: (
                stats.candidate_aligned_zone_count,
                stats.in_ote_count,
                stats.near_ote_0_5_pct_count,
            )
        )

    def best_candidate_by_in_ote(self) -> RangeCandidateStats | None:
        return self._best(lambda stats: (stats.in_ote_count, stats.near_ote_0_5_pct_count))

    def best_candidate_by_wrong_zone_fix(self) -> RangeCandidateStats | None:
        return self._best(lambda stats: (stats.candidate_fix_wrong_zone_count,))

    def _best(self, score_func) -> RangeCandidateStats | None:
        if not self.candidates:
            return None
        return sorted(self.candidates.values(), key=lambda stats: (*score_func(stats), stats.candidate_name), reverse=True)[0]

    def __str__(self) -> str:
        return f"{self.event_type} | WINDOWS={self.windows_analyzed} | CANDIDATES={len(self.candidates)}"
