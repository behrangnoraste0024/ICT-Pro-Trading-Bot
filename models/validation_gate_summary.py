from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ValidationGateSummary:
    gate_status: str
    regression_status: str
    recommended_profile: str | None = None
    baseline_commit: str | None = None
    candidate_commit: str | None = None
    baseline_snapshot_path: str | None = None
    candidate_snapshot_path: str | None = None
    comparison_paths: list[str] = field(default_factory=list)
    total_samples: int = 0
    completed_samples: int = 0
    passed_samples: int = 0
    failed_samples: int = 0
    skipped_samples: int = 0
    net_after_costs_delta: float | None = None
    max_drawdown_delta: float | None = None
    regression_flag_count: int = 0
    warning_sample_count: int = 0
    failed_sample_count: int = 0
    primary_cache_status: str | None = None
    primary_original_elapsed: float | None = None
    primary_cache_read_elapsed: float | None = None
    primary_saved_estimate: float | None = None
    fail_on_regression: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
