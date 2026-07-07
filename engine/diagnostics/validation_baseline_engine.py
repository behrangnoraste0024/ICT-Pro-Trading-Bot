from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.validation_baseline import ValidationBaselineConfig


class ValidationBaselineEngine:
    def __init__(self, repo_root: str | Path | None = None) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)

    def default_config(self) -> ValidationBaselineConfig:
        return ValidationBaselineConfig()

    def load(self, config_path: str) -> ValidationBaselineConfig:
        path = Path(config_path)
        if not path.exists():
            return self.default_config()
        data = json.loads(path.read_text(encoding="utf-8"))
        return ValidationBaselineConfig(**{**self.default_config().to_dict(), **data})

    def save(self, config: ValidationBaselineConfig, config_path: str) -> str:
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
        return str(path)

    def resolve_baseline_path(self, config: ValidationBaselineConfig) -> str | None:
        if not config.baseline_snapshot_path:
            return None
        path = Path(config.baseline_snapshot_path)
        if not path.is_absolute():
            path = self.repo_root / path
        return str(path.resolve())

    def validate_baseline_path(self, config: ValidationBaselineConfig) -> str:
        resolved = self.resolve_baseline_path(config)
        if resolved is None:
            raise FileNotFoundError("baseline_snapshot_path is not set")
        path = Path(resolved)
        if not path.exists():
            raise FileNotFoundError(f"baseline snapshot not found: {resolved}")
        if not path.is_file():
            raise FileNotFoundError(f"baseline snapshot is not a file: {resolved}")
        return str(path)

    def pin_snapshot(self, snapshot_path: str, config_path: str, dry_run: bool = False) -> ValidationBaselineConfig:
        snapshot = Path(snapshot_path)
        if not snapshot.exists():
            raise FileNotFoundError(f"snapshot not found: {snapshot_path}")
        data = json.loads(snapshot.read_text(encoding="utf-8"))
        metadata: dict[str, Any] = data.get("metadata") or {}
        config = self.load(config_path)
        config.baseline_snapshot_path = self._stored_path(snapshot)
        config.baseline_git_commit = metadata.get("git_commit")
        config.baseline_created_at = metadata.get("created_at")
        config.recommended_profile = metadata.get("recommended_profile") or config.recommended_profile
        if not dry_run:
            self.save(config, config_path)
        return config

    def clear(self, config_path: str, dry_run: bool = False) -> ValidationBaselineConfig:
        config = self.load(config_path)
        config.baseline_snapshot_path = None
        config.baseline_git_commit = None
        config.baseline_created_at = None
        if not dry_run:
            self.save(config, config_path)
        return config

    def _stored_path(self, snapshot_path: Path) -> str:
        resolved = snapshot_path.resolve()
        try:
            return str(resolved.relative_to(self.repo_root.resolve()))
        except ValueError:
            return str(resolved)
