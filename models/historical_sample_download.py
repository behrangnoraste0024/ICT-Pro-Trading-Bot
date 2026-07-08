from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class HistoricalSampleDownloadRequest:
    sample_name: str
    symbol: str
    timeframe: str
    fixture_path: str
    expected_min_candles: int
    exchange: str
    limit: int
    current_status: str
    should_download: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HistoricalSampleDownloadResult:
    sample_name: str
    symbol: str
    timeframe: str
    fixture_path: str
    exchange: str
    status: str
    candle_count: int = 0
    expected_min_candles: int = 0
    file_size_bytes: int | None = None
    downloaded_at: str | None = None
    error_message: str | None = None
    metadata_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HistoricalSampleDownloadPlan:
    registry_path: str
    exchange: str
    total_samples: int = 0
    planned_downloads: int = 0
    skipped_samples: int = 0
    results: list[HistoricalSampleDownloadResult] = field(default_factory=list)
    requests: list[HistoricalSampleDownloadRequest] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_path": self.registry_path,
            "exchange": self.exchange,
            "total_samples": self.total_samples,
            "planned_downloads": self.planned_downloads,
            "skipped_samples": self.skipped_samples,
            "results": [result.to_dict() for result in self.results],
            "requests": [request.to_dict() for request in self.requests],
        }
