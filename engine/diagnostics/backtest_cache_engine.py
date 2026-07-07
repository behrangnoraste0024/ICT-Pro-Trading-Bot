from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.backtest_cache import BacktestCacheKey, BacktestCacheMetadata, BacktestCacheResult


class BacktestCacheEngine:
    SCHEMA_VERSION = "2.48.0"

    def build_key(
        self,
        fixture_path: str,
        strategy_set: str,
        sort_by: str,
        min_candles: int,
        max_windows: int | None,
        fast: bool,
        cost_model: str | None = None,
        commission_pct: float | None = None,
        slippage_pct: float | None = None,
        spread_pct: float | None = None,
        profile_version: str = SCHEMA_VERSION,
        code_version: str | None = None,
    ) -> BacktestCacheKey:
        metadata = self._fixture_metadata(fixture_path)
        return BacktestCacheKey(
            fixture_path=str(Path(fixture_path)),
            fixture_mtime_ns=metadata["mtime_ns"],
            fixture_size_bytes=metadata["size_bytes"],
            strategy_set=strategy_set,
            sort_by=sort_by,
            min_candles=min_candles,
            max_windows=max_windows,
            fast=fast,
            cost_model=cost_model,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
            spread_pct=spread_pct,
            profile_version=profile_version,
            code_version=code_version,
        )

    def cache_key_hash(self, key: BacktestCacheKey) -> str:
        encoded = json.dumps(key.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def cache_path(self, cache_dir: str, key: BacktestCacheKey) -> str:
        return str(Path(cache_dir) / f"{self.cache_key_hash(key)}.json")

    def read(self, cache_dir: str, key: BacktestCacheKey) -> BacktestCacheResult:
        path = self.cache_path(cache_dir, key)
        if not Path(path).exists():
            return BacktestCacheResult(hit=False, cache_path=path, error_message="CACHE_MISSING")
        try:
            with Path(path).open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if raw.get("schema_version") != self.SCHEMA_VERSION:
                return BacktestCacheResult(hit=False, cache_path=path, error_message="SCHEMA_MISMATCH")
            metadata_raw = raw.get("metadata") or {}
            expected_hash = self.cache_key_hash(key)
            if metadata_raw.get("cache_key_hash") != expected_hash:
                return BacktestCacheResult(hit=False, cache_path=path, error_message="CACHE_KEY_MISMATCH")
            metadata = BacktestCacheMetadata(**metadata_raw)
            return BacktestCacheResult(hit=True, cache_path=path, metadata=metadata, payload=raw.get("payload"))
        except Exception as exc:
            return BacktestCacheResult(hit=False, cache_path=path, error_message=str(exc))

    def write(self, cache_dir: str, key: BacktestCacheKey, payload: dict[str, Any]) -> BacktestCacheResult:
        key_hash = self.cache_key_hash(key)
        path = Path(self.cache_path(cache_dir, key))
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata = BacktestCacheMetadata(
            cache_key_hash=key_hash,
            created_at=datetime.now(timezone.utc).isoformat(),
            fixture_path=key.fixture_path,
            fixture_mtime_ns=key.fixture_mtime_ns,
            fixture_size_bytes=key.fixture_size_bytes,
            strategy_set=key.strategy_set,
            sort_by=key.sort_by,
            max_windows=key.max_windows,
            fast=key.fast,
            code_version=key.code_version,
        )
        cache_payload = {
            "schema_version": self.SCHEMA_VERSION,
            "metadata": metadata.to_dict(),
            "payload": payload,
        }
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as handle:
                json.dump(cache_payload, handle, indent=2, sort_keys=True)
            os.replace(tmp_path, path)
            return BacktestCacheResult(hit=True, cache_path=str(path), metadata=metadata, payload=payload)
        except Exception as exc:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            return BacktestCacheResult(hit=False, cache_path=str(path), error_message=str(exc))

    def _fixture_metadata(self, fixture_path: str) -> dict[str, int | None]:
        path = Path(fixture_path)
        if not path.exists():
            return {"mtime_ns": None, "size_bytes": None}
        stat = path.stat()
        return {"mtime_ns": stat.st_mtime_ns, "size_bytes": stat.st_size}
