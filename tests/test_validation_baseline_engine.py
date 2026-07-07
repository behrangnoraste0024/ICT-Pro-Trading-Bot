from __future__ import annotations

import json

import pytest

from engine.diagnostics.validation_baseline_engine import ValidationBaselineEngine
from models.validation_baseline import ValidationBaselineConfig


def _snapshot(path, commit="abc123", profile="balanced_smc_decision_065") -> None:
    path.write_text(
        json.dumps(
            {
                "metadata": {
                    "git_commit": commit,
                    "created_at": "2026-07-07T12:00:00+00:00",
                    "recommended_profile": profile,
                },
                "multi_sample_result": {"rows": []},
            }
        ),
        encoding="utf-8",
    )


def test_loads_default_null_baseline_config_when_file_missing(tmp_path) -> None:
    config = ValidationBaselineEngine(repo_root=tmp_path).load(str(tmp_path / "missing.json"))

    assert config.baseline_snapshot_path is None
    assert config.recommended_profile == "balanced_smc_decision_065"


def test_loads_existing_baseline_config(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"baseline_snapshot_path": "snap.json", "baseline_git_commit": "abc"}), encoding="utf-8")

    config = ValidationBaselineEngine(repo_root=tmp_path).load(str(path))

    assert config.baseline_snapshot_path == "snap.json"
    assert config.baseline_git_commit == "abc"


def test_resolves_relative_baseline_snapshot_path(tmp_path) -> None:
    engine = ValidationBaselineEngine(repo_root=tmp_path)
    config = ValidationBaselineConfig(baseline_snapshot_path="reports/snap.json")

    resolved = engine.resolve_baseline_path(config)

    assert resolved == str((tmp_path / "reports/snap.json").resolve())


def test_validates_existing_baseline_snapshot_path(tmp_path) -> None:
    snapshot = tmp_path / "snap.json"
    _snapshot(snapshot)
    engine = ValidationBaselineEngine(repo_root=tmp_path)

    resolved = engine.validate_baseline_path(ValidationBaselineConfig(baseline_snapshot_path="snap.json"))

    assert resolved == str(snapshot.resolve())


def test_reports_missing_configured_snapshot_path(tmp_path) -> None:
    engine = ValidationBaselineEngine(repo_root=tmp_path)

    with pytest.raises(FileNotFoundError):
        engine.validate_baseline_path(ValidationBaselineConfig(baseline_snapshot_path="missing.json"))


def test_pin_snapshot_stores_relative_path_and_metadata(tmp_path) -> None:
    snapshot = tmp_path / "reports" / "snap.json"
    snapshot.parent.mkdir()
    _snapshot(snapshot, commit="def456")
    config_path = tmp_path / "configs" / "validation_baseline.json"

    config = ValidationBaselineEngine(repo_root=tmp_path).pin_snapshot(str(snapshot), str(config_path))

    assert config.baseline_snapshot_path == "reports\\snap.json" or config.baseline_snapshot_path == "reports/snap.json"
    assert config.baseline_git_commit == "def456"
    assert config.baseline_created_at == "2026-07-07T12:00:00+00:00"
    assert config_path.exists()


def test_clear_removes_baseline_fields(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    ValidationBaselineEngine(repo_root=tmp_path).save(
        ValidationBaselineConfig(baseline_snapshot_path="snap.json", baseline_git_commit="abc", baseline_created_at="date"),
        str(config_path),
    )

    config = ValidationBaselineEngine(repo_root=tmp_path).clear(str(config_path))

    assert config.baseline_snapshot_path is None
    assert config.baseline_git_commit is None
    assert config.baseline_created_at is None
