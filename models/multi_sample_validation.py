from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MultiSampleDefinition:
    name: str
    fixture_path: str
    symbol: str
    timeframe: str
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MultiSampleValidationRow:
    sample_name: str
    fixture_path: str
    symbol: str
    timeframe: str
    status: str
    recommended_profile: str | None = None
    recommended_strategy: str | None = None
    score_threshold: float | None = None
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    gross_net_pnl: float = 0.0
    total_cost: float = 0.0
    net_pnl_after_costs: float = 0.0
    max_drawdown: float = 0.0
    profitable_segments: int | None = None
    losing_segments: int | None = None
    empty_segments: int | None = None
    worst_segment_net_pnl_after_costs: float | None = None
    validation_status: str | None = None
    improvement_vs_baseline: float | None = None
    elapsed_seconds: float = 0.0
    error_message: str | None = None
    cache_status: str | None = None
    cache_key_hash: str | None = None
    cache_read_elapsed_seconds: float | None = None
    original_elapsed_seconds: float | None = None
    estimated_saved_seconds: float | None = None
    cache_age_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MultiSampleValidationResult:
    rows: list[MultiSampleValidationRow] = field(default_factory=list)
    total_samples: int = 0
    completed_samples: int = 0
    passed_samples: int = 0
    warning_samples: int = 0
    failed_samples: int = 0
    skipped_samples: int = 0
    error_samples: int = 0
    recommended_profile: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    event_type: str = "MULTI_SAMPLE_VALIDATION_RESULT"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": [row.to_dict() for row in self.rows],
            "total_samples": self.total_samples,
            "completed_samples": self.completed_samples,
            "passed_samples": self.passed_samples,
            "warning_samples": self.warning_samples,
            "failed_samples": self.failed_samples,
            "skipped_samples": self.skipped_samples,
            "error_samples": self.error_samples,
            "recommended_profile": self.recommended_profile,
            "diagnostics": self.diagnostics,
            "event_type": self.event_type,
        }
