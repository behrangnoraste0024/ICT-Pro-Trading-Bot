from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from data.historical_data_utils import normalize_ohlcv_rows, save_candles_json, validate_candle_records
from engine.diagnostics.historical_sample_registry_engine import HistoricalSampleRegistryEngine
from models.historical_sample_download import (
    HistoricalSampleDownloadPlan,
    HistoricalSampleDownloadRequest,
    HistoricalSampleDownloadResult,
)


class HistoricalSampleDownloadEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        registry_engine: HistoricalSampleRegistryEngine | None = None,
        exchange_factory: Callable[[str], Any] | None = None,
        ccxt_module: Any | None = None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.registry_engine = registry_engine or HistoricalSampleRegistryEngine(repo_root=self.repo_root)
        self.exchange_factory = exchange_factory
        self.ccxt_module = ccxt_module

    def build_plan(
        self,
        registry_path: str = "configs/historical_sample_registry.json",
        *,
        exchange: str = "binance",
        sample_names: list[str] | None = None,
        limit: int | None = None,
        include_existing: bool = False,
        overwrite: bool = False,
    ) -> HistoricalSampleDownloadPlan:
        report = self.registry_engine.check(registry_path)
        selected = report.samples
        if sample_names:
            known = {sample.sample_name for sample in selected}
            missing = [name for name in sample_names if name not in known]
            if missing:
                raise ValueError(f"historical sample not found in registry: {missing[0]}")
            selected = [sample for sample in selected if sample.sample_name in set(sample_names)]
        requests = [
            self._request(sample, exchange, limit or sample.expected_min_candles, include_existing, overwrite)
            for sample in selected
        ]
        results = [self._dry_result(request) for request in requests]
        return HistoricalSampleDownloadPlan(
            registry_path=registry_path,
            exchange=exchange,
            total_samples=len(requests),
            planned_downloads=sum(1 for request in requests if request.should_download),
            skipped_samples=sum(1 for request in requests if not request.should_download),
            results=results,
            requests=requests,
        )

    def download(
        self,
        registry_path: str = "configs/historical_sample_registry.json",
        *,
        exchange: str = "binance",
        sample_names: list[str] | None = None,
        limit: int | None = None,
        dry_run: bool = False,
        overwrite: bool = False,
        include_existing: bool = False,
        allow_too_few: bool = False,
        write_metadata: bool = False,
    ) -> HistoricalSampleDownloadPlan:
        plan = self.build_plan(
            registry_path,
            exchange=exchange,
            sample_names=sample_names,
            limit=limit,
            include_existing=include_existing,
            overwrite=overwrite,
        )
        if dry_run:
            return plan
        client = self._exchange_client(exchange)
        results = [
            self._download_one(client, request, overwrite=overwrite, allow_too_few=allow_too_few, write_metadata=write_metadata)
            if request.should_download
            else self._dry_result(request)
            for request in plan.requests
        ]
        plan.results = results
        return plan

    def _request(self, sample, exchange: str, limit: int, include_existing: bool, overwrite: bool) -> HistoricalSampleDownloadRequest:
        if sample.status == "AVAILABLE" and not include_existing:
            return self._request_for(sample, exchange, limit, False, "sample already available")
        if sample.status == "AVAILABLE" and include_existing and not overwrite:
            return self._request_for(sample, exchange, limit, False, "sample already available; use --overwrite to re-download")
        if sample.exists and not overwrite and sample.status != "AVAILABLE":
            return self._request_for(sample, exchange, limit, False, "destination exists; use --overwrite to replace")
        return self._request_for(sample, exchange, limit, True, f"sample status is {sample.status}")

    def _request_for(self, sample, exchange: str, limit: int, should_download: bool, reason: str) -> HistoricalSampleDownloadRequest:
        return HistoricalSampleDownloadRequest(
            sample_name=sample.sample_name,
            symbol=sample.symbol,
            timeframe=sample.timeframe,
            fixture_path=sample.fixture_path,
            expected_min_candles=sample.expected_min_candles,
            exchange=exchange,
            limit=limit,
            current_status=sample.status,
            should_download=should_download,
            reason=reason,
        )

    def _dry_result(self, request: HistoricalSampleDownloadRequest) -> HistoricalSampleDownloadResult:
        return HistoricalSampleDownloadResult(
            sample_name=request.sample_name,
            symbol=request.symbol,
            timeframe=request.timeframe,
            fixture_path=request.fixture_path,
            exchange=request.exchange,
            status="DRY_RUN" if request.should_download else "SKIPPED",
            candle_count=0,
            expected_min_candles=request.expected_min_candles,
            error_message=None if request.should_download else request.reason,
        )

    def _download_one(
        self,
        client,
        request: HistoricalSampleDownloadRequest,
        *,
        overwrite: bool,
        allow_too_few: bool,
        write_metadata: bool,
    ) -> HistoricalSampleDownloadResult:
        destination = self._destination(request.fixture_path)
        if destination.exists() and not overwrite:
            return self._failed(request, f"destination already exists: {destination}")
        try:
            rows = client.fetch_ohlcv(request.symbol, timeframe=request.timeframe, limit=request.limit)
            records = normalize_ohlcv_rows(rows)
            validate_candle_records(records)
            if len(records) < request.expected_min_candles and not allow_too_few:
                return self._failed(request, f"downloaded too few candles: {len(records)} < {request.expected_min_candles}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp_path = destination.with_name(f"{destination.name}.tmp")
            save_candles_json(records, temp_path)
            os.replace(temp_path, destination)
            metadata_path = None
            downloaded_at = datetime.now(UTC).isoformat()
            if write_metadata:
                metadata_path = str(self._write_metadata(request, destination, records, downloaded_at))
            return HistoricalSampleDownloadResult(
                sample_name=request.sample_name,
                symbol=request.symbol,
                timeframe=request.timeframe,
                fixture_path=request.fixture_path,
                exchange=request.exchange,
                status="DOWNLOADED",
                candle_count=len(records),
                expected_min_candles=request.expected_min_candles,
                file_size_bytes=destination.stat().st_size,
                downloaded_at=downloaded_at,
                metadata_path=metadata_path,
            )
        except Exception as exc:
            return self._failed(request, str(exc))

    def _failed(self, request: HistoricalSampleDownloadRequest, message: str) -> HistoricalSampleDownloadResult:
        return HistoricalSampleDownloadResult(
            sample_name=request.sample_name,
            symbol=request.symbol,
            timeframe=request.timeframe,
            fixture_path=request.fixture_path,
            exchange=request.exchange,
            status="FAILED",
            expected_min_candles=request.expected_min_candles,
            error_message=message,
        )

    def _exchange_client(self, exchange: str):
        if self.exchange_factory is not None:
            return self.exchange_factory(exchange)
        ccxt = self.ccxt_module
        if ccxt is None:
            try:
                import ccxt as imported_ccxt
            except ImportError as exc:
                raise RuntimeError("ccxt is required for historical downloads. Install project dependencies first.") from exc
            ccxt = imported_ccxt
        exchange_class = getattr(ccxt, exchange)
        return exchange_class({"enableRateLimit": True, "timeout": 30000})

    def _destination(self, fixture_path: str) -> Path:
        path = Path(fixture_path)
        if not path.is_absolute():
            path = self.repo_root / path
        return path

    def _write_metadata(self, request: HistoricalSampleDownloadRequest, destination: Path, records: list[dict], downloaded_at: str) -> Path:
        metadata_path = destination.with_suffix(f"{destination.suffix}.metadata.json")
        metadata = {
            "schema_version": "1.0",
            "sample_name": request.sample_name,
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "exchange": request.exchange,
            "downloaded_at": downloaded_at,
            "candle_count": len(records),
            "expected_min_candles": request.expected_min_candles,
            "source": "ccxt.fetch_ohlcv",
            "ccxt_version": getattr(self.ccxt_module, "__version__", None),
        }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata_path
