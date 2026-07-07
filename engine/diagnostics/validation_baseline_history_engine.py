from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.validation_baseline_history import ValidationBaselineHistory, ValidationBaselineHistoryEntry


class ValidationBaselineHistoryEngine:
    def load(self, history_path: str) -> ValidationBaselineHistory:
        path = Path(history_path)
        if not path.exists():
            return ValidationBaselineHistory()
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed baseline history file: {history_path}") from exc
        if not isinstance(loaded, dict):
            raise ValueError(f"baseline history must be a JSON object: {history_path}")
        entries = loaded.get("entries", [])
        if not isinstance(entries, list):
            raise ValueError(f"baseline history entries must be a list: {history_path}")
        return ValidationBaselineHistory(
            schema_version=str(loaded.get("schema_version") or "1.0"),
            entries=[self._entry(entry, history_path) for entry in entries],
        )

    def save(self, history: ValidationBaselineHistory, history_path: str) -> str:
        path = Path(history_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(history.to_dict(), indent=2), encoding="utf-8")
        return str(path)

    def append_entry(self, history_path: str, entry: ValidationBaselineHistoryEntry) -> ValidationBaselineHistory:
        history = self.load(history_path)
        history.entries.append(entry)
        self.save(history, history_path)
        return history

    def _entry(self, data: Any, history_path: str) -> ValidationBaselineHistoryEntry:
        if not isinstance(data, dict):
            raise ValueError(f"baseline history entry must be an object: {history_path}")
        default = ValidationBaselineHistoryEntry(promoted_at="", action="")
        merged = {**default.to_dict(), **data}
        flags = merged.get("comparison_regression_flags") or []
        if not isinstance(flags, list):
            raise ValueError(f"baseline history comparison_regression_flags must be a list: {history_path}")
        merged["comparison_regression_flags"] = [str(flag) for flag in flags]
        return ValidationBaselineHistoryEntry(**merged)
