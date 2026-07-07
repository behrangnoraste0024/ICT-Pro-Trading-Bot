from __future__ import annotations

import json
from pathlib import Path

from engine.diagnostics.backtest_cache_engine import BacktestCacheEngine


def _fixture(tmp_path, name: str = "fixture.json", content: str = "[]"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def _key(engine: BacktestCacheEngine, fixture_path, **overrides):
    values = {
        "fixture_path": str(fixture_path),
        "strategy_set": "recommended_decision_profiles_with_costs",
        "sort_by": "net_pnl_after_costs",
        "min_candles": 50,
        "max_windows": None,
        "fast": False,
        "profile_version": BacktestCacheEngine.SCHEMA_VERSION,
    }
    values.update(overrides)
    return engine.build_key(**values)


def test_cache_key_changes_when_fixture_path_changes(tmp_path) -> None:
    engine = BacktestCacheEngine()
    first = _key(engine, _fixture(tmp_path, "a.json"))
    second = _key(engine, _fixture(tmp_path, "b.json"))

    assert engine.cache_key_hash(first) != engine.cache_key_hash(second)


def test_cache_key_changes_when_fixture_metadata_changes(tmp_path) -> None:
    engine = BacktestCacheEngine()
    fixture = _fixture(tmp_path, content="[]")
    first = _key(engine, fixture)
    fixture.write_text("[1, 2, 3]", encoding="utf-8")
    second = _key(engine, fixture)

    assert engine.cache_key_hash(first) != engine.cache_key_hash(second)


def test_cache_key_changes_when_strategy_set_changes(tmp_path) -> None:
    engine = BacktestCacheEngine()
    fixture = _fixture(tmp_path)

    assert engine.cache_key_hash(_key(engine, fixture)) != engine.cache_key_hash(_key(engine, fixture, strategy_set="other"))


def test_cache_key_changes_when_max_windows_changes(tmp_path) -> None:
    engine = BacktestCacheEngine()
    fixture = _fixture(tmp_path)

    assert engine.cache_key_hash(_key(engine, fixture)) != engine.cache_key_hash(_key(engine, fixture, max_windows=100))


def test_cache_miss_when_file_missing(tmp_path) -> None:
    engine = BacktestCacheEngine()
    result = engine.read(str(tmp_path / "cache"), _key(engine, _fixture(tmp_path)))

    assert result.hit is False
    assert result.error_message == "CACHE_MISSING"
    assert result.diagnostics is not None
    assert result.diagnostics.cache_status == "MISS"
    assert result.diagnostics.cache_key_hash is not None


def test_cache_write_creates_file_and_read_hit_returns_payload(tmp_path) -> None:
    engine = BacktestCacheEngine()
    key = _key(engine, _fixture(tmp_path))
    write_result = engine.write(str(tmp_path / "cache"), key, {"value": 123}, compute_elapsed_seconds=3.5)
    read_result = engine.read(str(tmp_path / "cache"), key)

    assert write_result.cache_path is not None
    assert (tmp_path / "cache").exists()
    assert read_result.hit is True
    assert read_result.payload == {"value": 123}
    assert read_result.diagnostics is not None
    assert read_result.diagnostics.cache_status == "HIT"
    assert read_result.diagnostics.cache_read_elapsed_seconds is not None
    assert read_result.diagnostics.original_compute_elapsed_seconds == 3.5
    assert read_result.diagnostics.estimated_saved_seconds is not None
    assert read_result.diagnostics.estimated_saved_seconds <= 3.5
    assert read_result.diagnostics.cache_age_seconds is not None


def test_cache_write_records_compute_elapsed(tmp_path) -> None:
    engine = BacktestCacheEngine()
    key = _key(engine, _fixture(tmp_path))

    result = engine.write(str(tmp_path / "cache"), key, {"value": 123}, compute_elapsed_seconds=7.25)

    assert result.diagnostics is not None
    assert result.diagnostics.cache_status == "WRITE"
    assert result.diagnostics.current_compute_elapsed_seconds == 7.25
    assert result.metadata is not None
    assert result.metadata.original_compute_elapsed_seconds == 7.25


def test_corrupt_cache_file_is_ignored_safely(tmp_path) -> None:
    engine = BacktestCacheEngine()
    key = _key(engine, _fixture(tmp_path))
    path = engine.cache_path(str(tmp_path / "cache"), key)
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / Path(path).name).write_text("{not-json", encoding="utf-8")

    result = engine.read(str(tmp_path / "cache"), key)

    assert result.hit is False
    assert result.error_message is not None
    assert result.diagnostics is not None
    assert result.diagnostics.cache_status == "ERROR"


def test_schema_mismatch_is_ignored_safely(tmp_path) -> None:
    engine = BacktestCacheEngine()
    key = _key(engine, _fixture(tmp_path))
    written = engine.write(str(tmp_path / "cache"), key, {"value": 123})
    path = written.cache_path
    assert path is not None
    data = json.loads((tmp_path / "cache" / Path(path).name).read_text(encoding="utf-8"))
    data["schema_version"] = "old"
    (tmp_path / "cache" / Path(path).name).write_text(json.dumps(data), encoding="utf-8")

    result = engine.read(str(tmp_path / "cache"), key)

    assert result.hit is False
    assert result.error_message == "SCHEMA_MISMATCH"


def test_refresh_cache_bypasses_existing_cache_by_caller_convention(tmp_path) -> None:
    engine = BacktestCacheEngine()
    key = _key(engine, _fixture(tmp_path))
    engine.write(str(tmp_path / "cache"), key, {"value": "old"})
    write_result = engine.write(
        str(tmp_path / "cache"),
        key,
        {"value": "new"},
        compute_elapsed_seconds=1.25,
        cache_status="REFRESH",
    )

    result = engine.read(str(tmp_path / "cache"), key)

    assert result.payload == {"value": "new"}
    assert write_result.diagnostics is not None
    assert write_result.diagnostics.cache_status == "REFRESH"


def test_cache_directory_is_gitignored() -> None:
    assert ".cache/" in Path(".gitignore").read_text(encoding="utf-8")
