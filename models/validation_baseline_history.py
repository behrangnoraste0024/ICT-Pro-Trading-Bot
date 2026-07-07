from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ValidationBaselineHistoryEntry:
    promoted_at: str
    action: str
    baseline_snapshot_path: str | None = None
    baseline_git_commit: str | None = None
    baseline_created_at: str | None = None
    recommended_profile: str | None = None
    previous_baseline_snapshot_path: str | None = None
    previous_baseline_git_commit: str | None = None
    comparison_status: str | None = None
    comparison_net_after_costs_delta: float | None = None
    comparison_max_drawdown_delta: float | None = None
    comparison_regression_flags: list[str] = field(default_factory=list)
    promoted_by_command: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationBaselineHistory:
    schema_version: str = "1.0"
    entries: list[ValidationBaselineHistoryEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "entries": [entry.to_dict() for entry in self.entries],
        }
