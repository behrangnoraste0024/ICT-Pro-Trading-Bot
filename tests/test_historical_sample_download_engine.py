from __future__ import annotations

import builtins
import json
from pathlib import Path

import pytest

from engine.diagnostics.historical_sample_download_engine import HistoricalSampleDownloadEngine


def _registry(path: Path, samples: list[dict]) -> None:
    path.write_text(json.dumps({"schema_version": "1.0", "samples": samples}), encoding="utf-8")


def _sample(name: str, fixture_path: str, *, minimum: int = 2) -> dict:
    return {
        "sample_name": name,
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "fixture_path": fixture_path,
        "expected_min_candles": minimum,
        "required_for_full_gate": False,
        "required_for_ci_gate": False,
    }


def _ohlcv(count: int) -> list[list[float]]:
    return [[1000 + index, 1.0, 2.0, 0.5, 1.5, 10.0] for index in range(count)]


class _Exchange:
    def __init__(self, rows=None, error: Exception | None = None) -> None:
        self.rows = rows if rows is not None else _ohlcv(2)
        self.error = error

    def fetch_ohlcv(self, symbol, timeframe=None, limit=None):
        if self.error:
            raise self.error
        return self.rows[:limit]


def test_dry_run_builds_plan_for_missing_samples_without_requiring_ccxt(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("missing", str(tmp_path / "missing.json"))])

    plan = HistoricalSampleDownloadEngine(repo_root=tmp_path).download(str(registry), dry_run=True)

    assert plan.planned_downloads == 1
    assert plan.results[0].status == "DRY_RUN"


def test_dry_run_skips_available_sample_by_default(tmp_path) -> None:
    fixture = tmp_path / "available.json"
    fixture.write_text(json.dumps([{"timestamp": 1, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1} for _ in range(2)]), encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("available", str(fixture))])

    plan = HistoricalSampleDownloadEngine(repo_root=tmp_path).download(str(registry), dry_run=True)

    assert plan.planned_downloads == 0
    assert plan.results[0].status == "SKIPPED"


def test_include_existing_includes_available_sample_when_overwrite_enabled(tmp_path) -> None:
    fixture = tmp_path / "available.json"
    fixture.write_text(json.dumps([{"timestamp": 1, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1} for _ in range(2)]), encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("available", str(fixture))])

    plan = HistoricalSampleDownloadEngine(repo_root=tmp_path).download(
        str(registry),
        dry_run=True,
        include_existing=True,
        overwrite=True,
    )

    assert plan.planned_downloads == 1
    assert plan.results[0].status == "DRY_RUN"


def test_sample_filters_one_sample(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    _registry(
        registry,
        [
            _sample("one", str(tmp_path / "one.json")),
            _sample("two", str(tmp_path / "two.json")),
        ],
    )

    plan = HistoricalSampleDownloadEngine(repo_root=tmp_path).download(str(registry), sample_names=["two"], dry_run=True)

    assert plan.total_samples == 1
    assert plan.results[0].sample_name == "two"


def test_unknown_sample_raises(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("known", str(tmp_path / "known.json"))])

    with pytest.raises(ValueError, match="historical sample not found"):
        HistoricalSampleDownloadEngine(repo_root=tmp_path).download(str(registry), sample_names=["unknown"], dry_run=True)


def test_mocked_download_writes_destination_json(tmp_path) -> None:
    destination = tmp_path / "downloaded.json"
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(destination))])

    plan = HistoricalSampleDownloadEngine(
        repo_root=tmp_path,
        exchange_factory=lambda exchange: _Exchange(_ohlcv(2)),
    ).download(str(registry))

    assert plan.results[0].status == "DOWNLOADED"
    records = json.loads(destination.read_text(encoding="utf-8"))
    assert records[0] == {"timestamp": 1000, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0}


def test_refuses_overwrite_unless_overwrite(tmp_path) -> None:
    destination = tmp_path / "downloaded.json"
    destination.write_text(json.dumps([{"old": True}]), encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(destination))])

    plan = HistoricalSampleDownloadEngine(
        repo_root=tmp_path,
        exchange_factory=lambda exchange: _Exchange(_ohlcv(2)),
    ).download(str(registry), include_existing=True)

    assert plan.results[0].status == "SKIPPED"

    plan = HistoricalSampleDownloadEngine(
        repo_root=tmp_path,
        exchange_factory=lambda exchange: _Exchange(_ohlcv(2)),
    ).download(str(registry), include_existing=True, overwrite=True)
    assert plan.results[0].status == "DOWNLOADED"


def test_writes_metadata_sidecar(tmp_path) -> None:
    destination = tmp_path / "downloaded.json"
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(destination))])

    plan = HistoricalSampleDownloadEngine(
        repo_root=tmp_path,
        exchange_factory=lambda exchange: _Exchange(_ohlcv(2)),
    ).download(str(registry), write_metadata=True)

    metadata_path = Path(plan.results[0].metadata_path)
    assert metadata_path.exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["sample_name"] == "sample"
    assert metadata["source"] == "ccxt.fetch_ohlcv"


def test_refuses_too_few_candles_unless_allowed(tmp_path) -> None:
    destination = tmp_path / "downloaded.json"
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(destination), minimum=2)])

    plan = HistoricalSampleDownloadEngine(
        repo_root=tmp_path,
        exchange_factory=lambda exchange: _Exchange(_ohlcv(1)),
    ).download(str(registry))
    assert plan.results[0].status == "FAILED"
    assert "too few candles" in plan.results[0].error_message

    plan = HistoricalSampleDownloadEngine(
        repo_root=tmp_path,
        exchange_factory=lambda exchange: _Exchange(_ohlcv(1)),
    ).download(str(registry), allow_too_few=True)
    assert plan.results[0].status == "DOWNLOADED"


def test_exchange_error_reports_failed(tmp_path) -> None:
    destination = tmp_path / "downloaded.json"
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(destination))])

    plan = HistoricalSampleDownloadEngine(
        repo_root=tmp_path,
        exchange_factory=lambda exchange: _Exchange(error=RuntimeError("network failed")),
    ).download(str(registry))

    assert plan.results[0].status == "FAILED"
    assert "network failed" in plan.results[0].error_message


def test_missing_ccxt_for_real_download_gives_clear_error(tmp_path, monkeypatch) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(tmp_path / "sample.json"))])
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "ccxt":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="ccxt is required for historical downloads"):
        HistoricalSampleDownloadEngine(repo_root=tmp_path).download(str(registry))
