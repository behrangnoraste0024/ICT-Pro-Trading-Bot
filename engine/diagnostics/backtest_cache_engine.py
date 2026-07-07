from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.backtest_cache import (
    BacktestCacheKey,
    BacktestCacheMetadata,
    BacktestCacheResult,
    BacktestCacheRuntimeDiagnostics,
)


class BacktestCacheEngine:
    SCHEMA_VERSION = "2.49.0"

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
        started_at = time.perf_counter()
        path = self.cache_path(cache_dir, key)
        key_hash = self.cache_key_hash(key)
        if not Path(path).exists():
            return self._result(
                hit=False,
                key=key,
                cache_path=path,
                cache_key_hash=key_hash,
                status="MISS",
                error_message="CACHE_MISSING",
                read_started_at=started_at,
            )
        try:
            with Path(path).open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if raw.get("schema_version") != self.SCHEMA_VERSION:
                return self._result(
                    hit=False,
                    key=key,
                    cache_path=path,
                    cache_key_hash=key_hash,
                    status="ERROR",
                    error_message="SCHEMA_MISMATCH",
                    read_started_at=started_at,
                    schema_version=raw.get("schema_version"),
                )
            metadata_raw = raw.get("metadata") or {}
            expected_hash = key_hash
            if metadata_raw.get("cache_key_hash") != expected_hash:
                return self._result(
                    hit=False,
                    key=key,
                    cache_path=path,
                    cache_key_hash=key_hash,
                    status="ERROR",
                    error_message="CACHE_KEY_MISMATCH",
                    read_started_at=started_at,
                )
            metadata = BacktestCacheMetadata(**metadata_raw)
            return self._result(
                hit=True,
                key=key,
                cache_path=path,
                cache_key_hash=key_hash,
                status="HIT",
                metadata=metadata,
                payload=raw.get("payload"),
                read_started_at=started_at,
            )
        except Exception as exc:
            return self._result(
                hit=False,
                key=key,
                cache_path=path,
                cache_key_hash=key_hash,
                status="ERROR",
                error_message=str(exc),
                read_started_at=started_at,
            )

    def write(
        self,
        cache_dir: str,
        key: BacktestCacheKey,
        payload: dict[str, Any],
        compute_elapsed_seconds: float | None = None,
        cache_status: str = "WRITE",
    ) -> BacktestCacheResult:
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
            original_compute_elapsed_seconds=compute_elapsed_seconds,
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
            diagnostics = self._diagnostics(
                status=cache_status,
                key=key,
                cache_path=str(path),
                cache_key_hash=key_hash,
                metadata=metadata,
                current_compute_elapsed_seconds=compute_elapsed_seconds,
            )
            return BacktestCacheResult(
                hit=True,
                cache_path=str(path),
                metadata=metadata,
                payload=payload,
                diagnostics=diagnostics,
            )
        except Exception as exc:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            diagnostics = self._diagnostics(
                status="ERROR",
                key=key,
                cache_path=str(path),
                cache_key_hash=key_hash,
                error_message=str(exc),
                current_compute_elapsed_seconds=compute_elapsed_seconds,
            )
            return BacktestCacheResult(hit=False, cache_path=str(path), error_message=str(exc), diagnostics=diagnostics)

    def _fixture_metadata(self, fixture_path: str) -> dict[str, int | None]:
        path = Path(fixture_path)
        if not path.exists():
            return {"mtime_ns": None, "size_bytes": None}
        stat = path.stat()
        return {"mtime_ns": stat.st_mtime_ns, "size_bytes": stat.st_size}

    def _result(
        self,
        hit: bool,
        key: BacktestCacheKey,
        cache_path: str,
        cache_key_hash: str,
        status: str,
        metadata: BacktestCacheMetadata | None = None,
        payload: dict[str, Any] | None = None,
        error_message: str | None = None,
        read_started_at: float | None = None,
        schema_version: str | None = None,
    ) -> BacktestCacheResult:
        read_elapsed = None if read_started_at is None else time.perf_counter() - read_started_at
        diagnostics = self._diagnostics(
            status=status,
            key=key,
            cache_path=cache_path,
            cache_key_hash=cache_key_hash,
            metadata=metadata,
            cache_read_elapsed_seconds=read_elapsed,
            error_message=error_message,
            schema_version=schema_version,
        )
        return BacktestCacheResult(
            hit=hit,
            cache_path=cache_path,
            metadata=metadata,
            error_message=error_message,
            payload=payload,
            diagnostics=diagnostics,
        )

    def _diagnostics(
        self,
        status: str,
        key: BacktestCacheKey,
        cache_path: str | None,
        cache_key_hash: str | None,
        metadata: BacktestCacheMetadata | None = None,
        cache_read_elapsed_seconds: float | None = None,
        current_compute_elapsed_seconds: float | None = None,
        error_message: str | None = None,
        schema_version: str | None = None,
    ) -> BacktestCacheRuntimeDiagnostics:
        original_elapsed = None if metadata is None else metadata.original_compute_elapsed_seconds
        saved = None
        if original_elapsed is not None and cache_read_elapsed_seconds is not None:
            saved = max(original_elapsed - cache_read_elapsed_seconds, 0.0)
        return BacktestCacheRuntimeDiagnostics(
            cache_status=status,
            cache_key_hash=cache_key_hash,
            cache_path=cache_path,
            cache_schema_version=schema_version or self.SCHEMA_VERSION,
            cache_created_at=None if metadata is None else metadata.created_at,
            cache_age_seconds=self._cache_age_seconds(metadata),
            cache_read_elapsed_seconds=cache_read_elapsed_seconds,
            original_compute_elapsed_seconds=original_elapsed,
            current_compute_elapsed_seconds=current_compute_elapsed_seconds,
            estimated_saved_seconds=saved,
            fixture_path=key.fixture_path,
            fixture_mtime_ns=key.fixture_mtime_ns,
            fixture_size_bytes=key.fixture_size_bytes,
            error_message=error_message,
        )

    def _cache_age_seconds(self, metadata: BacktestCacheMetadata | None) -> float | None:
        if metadata is None:
            return None
        try:
            created_at = datetime.fromisoformat(metadata.created_at)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            return max((datetime.now(timezone.utc) - created_at).total_seconds(), 0.0)
        except ValueError:
            return None
