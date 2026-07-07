from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class BacktestCacheKey:
    fixture_path: str
    fixture_mtime_ns: int | None
    fixture_size_bytes: int | None
    strategy_set: str
    sort_by: str
    min_candles: int
    max_windows: int | None
    fast: bool
    cost_model: str | None
    commission_pct: float | None
    slippage_pct: float | None
    spread_pct: float | None
    profile_version: str
    code_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BacktestCacheMetadata:
    cache_key_hash: str
    created_at: str
    fixture_path: str
    fixture_mtime_ns: int | None
    fixture_size_bytes: int | None
    strategy_set: str
    sort_by: str
    max_windows: int | None
    fast: bool
    code_version: str | None = None
    original_compute_elapsed_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BacktestCacheRuntimeDiagnostics:
    cache_status: str
    cache_key_hash: str | None = None
    cache_path: str | None = None
    cache_schema_version: str | None = None
    cache_created_at: str | None = None
    cache_age_seconds: float | None = None
    cache_read_elapsed_seconds: float | None = None
    original_compute_elapsed_seconds: float | None = None
    current_compute_elapsed_seconds: float | None = None
    estimated_saved_seconds: float | None = None
    fixture_path: str | None = None
    fixture_mtime_ns: int | None = None
    fixture_size_bytes: int | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BacktestCacheResult:
    hit: bool
    cache_path: str | None = None
    metadata: BacktestCacheMetadata | None = None
    error_message: str | None = None
    payload: dict[str, Any] | None = None
    diagnostics: BacktestCacheRuntimeDiagnostics | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "hit": self.hit,
            "cache_path": self.cache_path,
            "metadata": None if self.metadata is None else self.metadata.to_dict(),
            "error_message": self.error_message,
            "payload": self.payload,
            "diagnostics": None if self.diagnostics is None else self.diagnostics.to_dict(),
        }
