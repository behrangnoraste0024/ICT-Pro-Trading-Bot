from __future__ import annotations

import json
from pathlib import Path

from engine.diagnostics.validation_snapshot_engine import ValidationSnapshotEngine
from models.multi_sample_validation import MultiSampleValidationResult, MultiSampleValidationRow


def _result() -> MultiSampleValidationResult:
    return MultiSampleValidationResult(
        rows=[
            MultiSampleValidationRow(
                sample_name="btcusdt_15m_1000",
                fixture_path="data/historical/btcusdt_15m_1000.json",
                symbol="BTC/USDT",
                timeframe="15m",
                status="PASSED",
                recommended_profile="balanced_smc_decision_065",
                recommended_strategy="profile=balanced_smc_decision_065|cost=percent",
                score_threshold=0.65,
                total_trades=5,
                wins=5,
                losses=0,
                win_rate=100.0,
                net_pnl_after_costs=1404.24,
                max_drawdown=0.0,
                profitable_segments=4,
                losing_segments=0,
                empty_segments=0,
                worst_segment_net_pnl_after_costs=157.54,
                validation_status="PASS",
                improvement_vs_baseline=1215.74,
                cache_status="HIT",
                cache_read_elapsed_seconds=0.03,
                original_elapsed_seconds=2560.70,
                estimated_saved_seconds=2560.67,
                cache_age_seconds=10.0,
            )
        ],
        total_samples=1,
        completed_samples=1,
        passed_samples=1,
        recommended_profile="balanced_smc_decision_065",
    )


def _snapshot(engine: ValidationSnapshotEngine):
    return engine.build_snapshot(
        result=_result(),
        strategy_set="recommended_decision_profiles_with_costs",
        sort_by="net_pnl_after_costs",
        recommended_profile="balanced_smc_decision_065",
        cache_enabled=True,
        cache_dir=".cache/backtests",
        max_windows=100,
        fast=False,
        command="run_multi_sample_validation.py --export-snapshot",
    )


def test_builds_snapshot_metadata_with_provided_values(monkeypatch) -> None:
    engine = ValidationSnapshotEngine()
    monkeypatch.setattr(engine, "_git_value", lambda command: "abc123" if "rev-parse" in command else "v1-core")

    snapshot = _snapshot(engine)

    assert snapshot.metadata.snapshot_schema_version == "2.50.0"
    assert snapshot.metadata.git_commit == "abc123"
    assert snapshot.metadata.git_branch == "v1-core"
    assert snapshot.metadata.strategy_set == "recommended_decision_profiles_with_costs"
    assert snapshot.metadata.cache_enabled is True
    assert snapshot.metadata.max_windows == 100


def test_safely_handles_missing_git_metadata(monkeypatch) -> None:
    engine = ValidationSnapshotEngine()
    monkeypatch.setattr(engine, "_git_value", lambda _command: None)

    snapshot = _snapshot(engine)

    assert snapshot.metadata.git_commit is None
    assert snapshot.metadata.git_branch is None


def test_exports_json_file(tmp_path, monkeypatch) -> None:
    engine = ValidationSnapshotEngine()
    monkeypatch.setattr(engine, "_git_value", lambda _command: "abc123")

    path = engine.export_json(_snapshot(engine), str(tmp_path))
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    assert Path(path).exists()
    assert data["metadata"]["recommended_profile"] == "balanced_smc_decision_065"
    assert data["multi_sample_result"]["rows"][0]["sample_name"] == "btcusdt_15m_1000"


def test_exports_markdown_file(tmp_path, monkeypatch) -> None:
    engine = ValidationSnapshotEngine()
    monkeypatch.setattr(engine, "_git_value", lambda _command: "abc123")

    path = engine.export_markdown(_snapshot(engine), str(tmp_path))
    text = Path(path).read_text(encoding="utf-8")

    assert Path(path).exists()
    assert "# Validation Snapshot" in text
    assert "| Sample | Symbol | TF | Status" in text
    assert "btcusdt_15m_1000" in text


def test_filename_is_filesystem_safe_and_includes_timestamp_and_profile(monkeypatch) -> None:
    engine = ValidationSnapshotEngine()
    monkeypatch.setattr(engine, "_git_value", lambda _command: "abc123")
    snapshot = _snapshot(engine)

    filename = engine.filename(snapshot, "json")

    assert filename.startswith("validation_snapshot_")
    assert "abc123" in filename
    assert "balanced_smc_decision_065" in filename
    assert " " not in filename
    assert filename.endswith(".json")


def test_export_both_writes_json_and_markdown(tmp_path, monkeypatch) -> None:
    engine = ValidationSnapshotEngine()
    monkeypatch.setattr(engine, "_git_value", lambda _command: "abc123")

    paths = engine.export(_snapshot(engine), str(tmp_path), "both")

    assert len(paths) == 2
    assert {Path(path).suffix for path in paths} == {".json", ".md"}


def test_generated_snapshot_files_are_gitignored() -> None:
    text = Path(".gitignore").read_text(encoding="utf-8")

    assert "reports/validation_snapshots/*.json" in text
    assert "reports/validation_snapshots/*.md" in text
