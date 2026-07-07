from __future__ import annotations

import json

import pytest

from engine.diagnostics.historical_sample_registry_engine import HistoricalSampleRegistryEngine


def _registry(path, samples) -> None:
    path.write_text(json.dumps({"schema_version": "1.0", "samples": samples}), encoding="utf-8")


def _sample(fixture_path: str, *, minimum: int = 2, full: bool = False, ci: bool = False) -> dict:
    return {
        "sample_name": "sample",
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "fixture_path": fixture_path,
        "expected_min_candles": minimum,
        "required_for_full_gate": full,
        "required_for_ci_gate": ci,
    }


def test_loads_registry_config(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("candles.json")])

    schema, samples = HistoricalSampleRegistryEngine(repo_root=tmp_path).load_registry(str(registry))

    assert schema == "1.0"
    assert samples[0].sample_name == "sample"
    assert samples[0].expected_min_candles == 2


def test_reports_missing_sample(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("missing.json")])

    report = HistoricalSampleRegistryEngine(repo_root=tmp_path).check(str(registry))

    assert report.missing_samples == 1
    assert report.samples[0].status == "MISSING"


def test_reports_available_sample_with_list_json(tmp_path) -> None:
    fixture = tmp_path / "candles.json"
    fixture.write_text(json.dumps([{"close": 1}, {"close": 2}]), encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("candles.json")])

    report = HistoricalSampleRegistryEngine(repo_root=tmp_path).check(str(registry))

    assert report.available_samples == 1
    assert report.samples[0].candle_count == 2
    assert report.samples[0].status == "AVAILABLE"


def test_reports_available_sample_with_candles_key_json(tmp_path) -> None:
    fixture = tmp_path / "candles.json"
    fixture.write_text(json.dumps({"candles": [{"close": 1}, {"close": 2}]}), encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("candles.json")])

    report = HistoricalSampleRegistryEngine(repo_root=tmp_path).check(str(registry))

    assert report.samples[0].candle_count == 2
    assert report.samples[0].status == "AVAILABLE"


def test_reports_invalid_json(tmp_path) -> None:
    fixture = tmp_path / "candles.json"
    fixture.write_text("{", encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("candles.json")])

    report = HistoricalSampleRegistryEngine(repo_root=tmp_path).check(str(registry))

    assert report.invalid_samples == 1
    assert report.samples[0].status == "INVALID_JSON"


def test_reports_too_few_candles(tmp_path) -> None:
    fixture = tmp_path / "candles.json"
    fixture.write_text(json.dumps([{"close": 1}]), encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("candles.json", minimum=2)])

    report = HistoricalSampleRegistryEngine(repo_root=tmp_path).check(str(registry))

    assert report.invalid_samples == 1
    assert report.samples[0].status == "TOO_FEW_CANDLES"
    assert report.samples[0].meets_min_candles is False


def test_required_full_available_true_when_required_sample_available(tmp_path) -> None:
    fixture = tmp_path / "candles.json"
    fixture.write_text(json.dumps([{}, {}]), encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("candles.json", full=True)])

    report = HistoricalSampleRegistryEngine(repo_root=tmp_path).check(str(registry))

    assert report.required_full_available is True


def test_required_full_available_false_when_required_sample_missing(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("missing.json", full=True)])

    report = HistoricalSampleRegistryEngine(repo_root=tmp_path).check(str(registry))

    assert report.required_full_available is False


def test_required_ci_available_tracks_ci_required_samples(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("missing.json", ci=True)])

    report = HistoricalSampleRegistryEngine(repo_root=tmp_path).check(str(registry))

    assert report.required_ci_available is False


def test_missing_registry_file_raises_clear_error(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="historical sample registry not found"):
        HistoricalSampleRegistryEngine(repo_root=tmp_path).check(str(tmp_path / "missing.json"))
