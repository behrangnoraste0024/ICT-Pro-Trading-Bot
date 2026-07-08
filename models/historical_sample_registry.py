from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class HistoricalSampleDefinition:
    sample_name: str
    symbol: str
    timeframe: str
    fixture_path: str
    expected_min_candles: int
    required_for_full_gate: bool = False
    required_for_ci_gate: bool = False
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HistoricalSampleAvailability:
    sample_name: str
    symbol: str
    timeframe: str
    fixture_path: str
    exists: bool
    readable: bool
    file_size_bytes: int | None
    modified_at: str | None
    candle_count: int | None
    expected_min_candles: int
    meets_min_candles: bool
    status: str
    required_for_full_gate: bool
    required_for_ci_gate: bool
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HistoricalSampleRegistryReport:
    schema_version: str = "1.0"
    registry_path: str | None = None
    total_samples: int = 0
    available_samples: int = 0
    missing_samples: int = 0
    invalid_samples: int = 0
    required_full_available: bool = True
    required_ci_available: bool = True
    samples: list[HistoricalSampleAvailability] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "registry_path": self.registry_path,
            "total_samples": self.total_samples,
            "available_samples": self.available_samples,
            "missing_samples": self.missing_samples,
            "invalid_samples": self.invalid_samples,
            "required_full_available": self.required_full_available,
            "required_ci_available": self.required_ci_available,
            "samples": [sample.to_dict() for sample in self.samples],
        }
