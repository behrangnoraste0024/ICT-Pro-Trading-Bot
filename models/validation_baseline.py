from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ValidationBaselineConfig:
    schema_version: str = "1.0"
    baseline_snapshot_path: str | None = None
    baseline_git_commit: str | None = None
    baseline_created_at: str | None = None
    recommended_profile: str | None = "balanced_smc_decision_065"
    notes: str | None = "Set baseline_snapshot_path to a local validation snapshot JSON file for regression gate comparisons."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
