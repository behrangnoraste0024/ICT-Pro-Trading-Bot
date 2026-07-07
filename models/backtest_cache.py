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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BacktestCacheResult:
    hit: bool
    cache_path: str | None = None
    metadata: BacktestCacheMetadata | None = None
    error_message: str | None = None
    payload: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "hit": self.hit,
            "cache_path": self.cache_path,
            "metadata": None if self.metadata is None else self.metadata.to_dict(),
            "error_message": self.error_message,
            "payload": self.payload,
        }
