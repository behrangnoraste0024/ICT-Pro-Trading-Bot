from __future__ import annotations

import json

import pytest

from engine.diagnostics.historical_sample_preparation_engine import HistoricalSamplePreparationEngine


def _registry(path, samples) -> None:
    path.write_text(json.dumps({"schema_version": "1.0", "samples": samples}), encoding="utf-8")


def _sample(name: str, fixture_path: str, *, minimum: int = 2, full: bool = False, ci: bool = False) -> dict:
    return {
        "sample_name": name,
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "fixture_path": fixture_path,
        "expected_min_candles": minimum,
        "required_for_full_gate": full,
        "required_for_ci_gate": ci,
    }


def test_plan_marks_available_sample_as_none(tmp_path) -> None:
    fixture = tmp_path / "available.json"
    fixture.write_text(json.dumps([{}, {}]), encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("available", str(fixture))])

    plan = HistoricalSamplePreparationEngine(repo_root=tmp_path).build_plan(str(registry))

    assert plan.ready_samples == 1
    assert plan.action_required_samples == 0
    assert plan.actions[0].action_type == "NONE"


def test_plan_marks_missing_sample_as_import_required(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("missing", str(tmp_path / "missing.json"))])

    plan = HistoricalSamplePreparationEngine(repo_root=tmp_path).build_plan(str(registry))

    assert plan.actions[0].action_type == "IMPORT_REQUIRED"
    assert plan.actions[0].current_status == "MISSING"


def test_plan_marks_invalid_sample_as_replace_recommended(tmp_path) -> None:
    fixture = tmp_path / "invalid.json"
    fixture.write_text("{", encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("invalid", str(fixture))])

    plan = HistoricalSamplePreparationEngine(repo_root=tmp_path).build_plan(str(registry))

    assert plan.actions[0].action_type == "REPLACE_RECOMMENDED"
    assert plan.actions[0].current_status == "INVALID_JSON"


def test_plan_counts_ready_and_action_required_samples(tmp_path) -> None:
    ready = tmp_path / "ready.json"
    ready.write_text(json.dumps([{}, {}]), encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(
        registry,
        [
            _sample("ready", str(ready), full=True, ci=True),
            _sample("missing", str(tmp_path / "missing.json")),
        ],
    )

    plan = HistoricalSamplePreparationEngine(repo_root=tmp_path).build_plan(str(registry))

    assert plan.ready_samples == 1
    assert plan.action_required_samples == 1
    assert plan.required_full_ready is True
    assert plan.required_ci_ready is True


def test_build_plan_filters_by_sample(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    _registry(
        registry,
        [
            _sample("one", str(tmp_path / "one.json")),
            _sample("two", str(tmp_path / "two.json")),
        ],
    )

    plan = HistoricalSamplePreparationEngine(repo_root=tmp_path).build_plan(str(registry), "two")

    assert plan.total_samples == 1
    assert plan.actions[0].sample_name == "two"


def test_unknown_sample_raises(tmp_path) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("known", str(tmp_path / "known.json"))])

    with pytest.raises(ValueError, match="historical sample not found"):
        HistoricalSamplePreparationEngine(repo_root=tmp_path).build_plan(str(registry), "missing")


def test_import_source_dry_run_validates_but_does_not_write_destination(tmp_path) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "dest.json"
    source.write_text(json.dumps([{}, {}]), encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(destination))])

    result = HistoricalSamplePreparationEngine(repo_root=tmp_path).import_source(
        str(registry),
        "sample",
        str(source),
        dry_run=True,
    )

    assert result["candle_count"] == 2
    assert not destination.exists()


def test_import_source_writes_destination_when_valid(tmp_path) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "dest.json"
    source.write_text(json.dumps([{}, {}]), encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(destination))])

    HistoricalSamplePreparationEngine(repo_root=tmp_path).import_source(str(registry), "sample", str(source))

    assert destination.exists()
    assert json.loads(destination.read_text(encoding="utf-8")) == [{}, {}]


def test_import_source_refuses_overwrite_unless_overwrite(tmp_path) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "dest.json"
    source.write_text(json.dumps([{}, {}]), encoding="utf-8")
    destination.write_text(json.dumps([{"old": True}]), encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(destination))])

    with pytest.raises(FileExistsError, match="destination already exists"):
        HistoricalSamplePreparationEngine(repo_root=tmp_path).import_source(str(registry), "sample", str(source))

    HistoricalSamplePreparationEngine(repo_root=tmp_path).import_source(
        str(registry),
        "sample",
        str(source),
        overwrite=True,
    )
    assert json.loads(destination.read_text(encoding="utf-8")) == [{}, {}]


def test_import_source_refuses_too_few_candles_unless_allowed(tmp_path) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "dest.json"
    source.write_text(json.dumps([{}]), encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(destination), minimum=2)])

    with pytest.raises(ValueError, match="too few candles"):
        HistoricalSamplePreparationEngine(repo_root=tmp_path).import_source(str(registry), "sample", str(source))

    result = HistoricalSamplePreparationEngine(repo_root=tmp_path).import_source(
        str(registry),
        "sample",
        str(source),
        allow_too_few=True,
        dry_run=True,
    )
    assert result["candle_count"] == 1


def test_import_source_supports_dict_with_candles_key(tmp_path) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "dest.json"
    source.write_text(json.dumps({"candles": [{}, {}]}), encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(destination))])

    result = HistoricalSamplePreparationEngine(repo_root=tmp_path).import_source(
        str(registry),
        "sample",
        str(source),
        dry_run=True,
    )

    assert result["candle_count"] == 2


def test_import_source_invalid_json_raises(tmp_path) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "dest.json"
    source.write_text("{", encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(destination))])

    with pytest.raises(ValueError, match="source file invalid JSON"):
        HistoricalSamplePreparationEngine(repo_root=tmp_path).import_source(str(registry), "sample", str(source))
