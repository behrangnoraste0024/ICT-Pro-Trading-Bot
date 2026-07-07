from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from models.multi_sample_validation import MultiSampleValidationResult


@dataclass
class ValidationSnapshotMetadata:
    snapshot_schema_version: str
    created_at: str
    git_commit: str | None
    git_branch: str | None
    command: str | None
    strategy_set: str
    sort_by: str
    recommended_profile: str | None
    cache_enabled: bool
    cache_dir: str | None
    max_windows: int | None
    fast: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationSnapshot:
    metadata: ValidationSnapshotMetadata
    multi_sample_result: MultiSampleValidationResult
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "multi_sample_result": self.multi_sample_result.to_dict(),
            "diagnostics": self.diagnostics,
        }
