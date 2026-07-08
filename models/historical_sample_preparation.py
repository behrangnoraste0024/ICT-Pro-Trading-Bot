from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class HistoricalSamplePreparationAction:
    sample_name: str
    symbol: str
    timeframe: str
    fixture_path: str
    current_status: str
    required_for_full_gate: bool
    required_for_ci_gate: bool
    expected_min_candles: int
    action_type: str
    reason: str
    suggested_download_command: str | None = None
    suggested_import_command: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HistoricalSamplePreparationPlan:
    registry_path: str
    total_samples: int = 0
    ready_samples: int = 0
    action_required_samples: int = 0
    required_full_ready: bool = True
    required_ci_ready: bool = True
    actions: list[HistoricalSamplePreparationAction] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_path": self.registry_path,
            "total_samples": self.total_samples,
            "ready_samples": self.ready_samples,
            "action_required_samples": self.action_required_samples,
            "required_full_ready": self.required_full_ready,
            "required_ci_ready": self.required_ci_ready,
            "actions": [action.to_dict() for action in self.actions],
        }
