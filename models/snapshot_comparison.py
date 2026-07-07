from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SnapshotSampleComparison:
    sample_name: str
    symbol: str | None = None
    timeframe: str | None = None
    baseline_status: str | None = None
    candidate_status: str | None = None
    status_changed: bool = False
    baseline_profile: str | None = None
    candidate_profile: str | None = None
    profile_changed: bool = False
    baseline_trades: int = 0
    candidate_trades: int = 0
    trades_delta: int = 0
    baseline_win_rate: float = 0.0
    candidate_win_rate: float = 0.0
    win_rate_delta: float = 0.0
    baseline_net_after_costs: float = 0.0
    candidate_net_after_costs: float = 0.0
    net_after_costs_delta: float = 0.0
    baseline_max_drawdown: float = 0.0
    candidate_max_drawdown: float = 0.0
    max_drawdown_delta: float = 0.0
    baseline_wf_status: str | None = None
    candidate_wf_status: str | None = None
    wf_status_changed: bool = False
    baseline_profitable_segments: int | None = None
    candidate_profitable_segments: int | None = None
    profitable_segments_delta: int | None = None
    baseline_losing_segments: int | None = None
    candidate_losing_segments: int | None = None
    losing_segments_delta: int | None = None
    baseline_empty_segments: int | None = None
    candidate_empty_segments: int | None = None
    empty_segments_delta: int | None = None
    baseline_worst_segment_net: float | None = None
    candidate_worst_segment_net: float | None = None
    worst_segment_net_delta: float | None = None
    regression_flags: list[str] = field(default_factory=list)
    improvement_flags: list[str] = field(default_factory=list)
    severity: str = "PASS"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SnapshotComparisonResult:
    baseline_path: str
    candidate_path: str
    baseline_git_commit: str | None = None
    candidate_git_commit: str | None = None
    baseline_created_at: str | None = None
    candidate_created_at: str | None = None
    baseline_recommended_profile: str | None = None
    candidate_recommended_profile: str | None = None
    recommended_profile_changed: bool = False
    total_samples_compared: int = 0
    passed_samples: int = 0
    warning_samples: int = 0
    failed_samples: int = 0
    aggregate_net_after_costs_delta: float = 0.0
    aggregate_max_drawdown_delta: float = 0.0
    regression_status: str = "PASS"
    regression_flags: list[str] = field(default_factory=list)
    improvement_flags: list[str] = field(default_factory=list)
    sample_comparisons: list[SnapshotSampleComparison] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "sample_comparisons": [comparison.to_dict() for comparison in self.sample_comparisons],
        }
