from __future__ import annotations

import json

import pytest

from engine.diagnostics.validation_baseline_history_engine import ValidationBaselineHistoryEngine
from models.validation_baseline_history import ValidationBaselineHistory, ValidationBaselineHistoryEntry


def _entry(action: str = "PIN", commit: str = "abc123") -> ValidationBaselineHistoryEntry:
    return ValidationBaselineHistoryEntry(
        promoted_at="2026-07-07T12:00:00+00:00",
        action=action,
        baseline_snapshot_path="reports/snapshot.json",
        baseline_git_commit=commit,
        baseline_created_at="2026-07-07T11:00:00+00:00",
        recommended_profile="balanced_smc_decision_065",
    )


def test_loads_empty_history_when_file_missing(tmp_path) -> None:
    history = ValidationBaselineHistoryEngine().load(str(tmp_path / "missing.json"))

    assert history.schema_version == "1.0"
    assert history.entries == []


def test_saves_and_reloads_history(tmp_path) -> None:
    path = tmp_path / "history.json"
    engine = ValidationBaselineHistoryEngine()
    engine.save(ValidationBaselineHistory(entries=[_entry()]), str(path))

    loaded = engine.load(str(path))

    assert len(loaded.entries) == 1
    assert loaded.entries[0].baseline_git_commit == "abc123"


def test_appends_history_entry(tmp_path) -> None:
    path = tmp_path / "history.json"
    engine = ValidationBaselineHistoryEngine()

    history = engine.append_entry(str(path), _entry(action="PROMOTE"))

    assert len(history.entries) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["entries"][0]["action"] == "PROMOTE"


def test_preserves_entry_order(tmp_path) -> None:
    path = tmp_path / "history.json"
    engine = ValidationBaselineHistoryEngine()
    engine.append_entry(str(path), _entry(action="PIN", commit="first"))
    engine.append_entry(str(path), _entry(action="PROMOTE", commit="second"))

    loaded = engine.load(str(path))

    assert [entry.baseline_git_commit for entry in loaded.entries] == ["first", "second"]


def test_malformed_history_file_gives_clear_error(tmp_path) -> None:
    path = tmp_path / "history.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="malformed baseline history file"):
        ValidationBaselineHistoryEngine().load(str(path))


def test_history_entries_must_be_list(tmp_path) -> None:
    path = tmp_path / "history.json"
    path.write_text(json.dumps({"schema_version": "1.0", "entries": {}}), encoding="utf-8")

    with pytest.raises(ValueError, match="entries must be a list"):
        ValidationBaselineHistoryEngine().load(str(path))
