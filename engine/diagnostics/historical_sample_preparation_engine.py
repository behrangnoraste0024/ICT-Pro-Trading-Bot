from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from engine.diagnostics.historical_sample_registry_engine import HistoricalSampleRegistryEngine
from models.historical_sample_preparation import (
    HistoricalSamplePreparationAction,
    HistoricalSamplePreparationPlan,
)


class HistoricalSamplePreparationEngine:
    def __init__(self, repo_root: str | Path | None = None, registry_engine: HistoricalSampleRegistryEngine | None = None) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.registry_engine = registry_engine or HistoricalSampleRegistryEngine(repo_root=self.repo_root)

    def build_plan(
        self,
        registry_path: str = "configs/historical_sample_registry.json",
        sample_name: str | None = None,
    ) -> HistoricalSamplePreparationPlan:
        report = self.registry_engine.check(registry_path)
        samples = report.samples
        if sample_name is not None:
            samples = [sample for sample in samples if sample.sample_name == sample_name]
            if not samples:
                raise ValueError(f"historical sample not found in registry: {sample_name}")
        actions = [self._action(sample) for sample in samples]
        return HistoricalSamplePreparationPlan(
            registry_path=registry_path,
            total_samples=len(actions),
            ready_samples=sum(1 for action in actions if action.action_type == "NONE"),
            action_required_samples=sum(1 for action in actions if action.action_type != "NONE"),
            required_full_ready=all(
                action.action_type == "NONE" for action in actions if action.required_for_full_gate
            ),
            required_ci_ready=all(
                action.action_type == "NONE" for action in actions if action.required_for_ci_gate
            ),
            actions=actions,
        )

    def import_source(
        self,
        registry_path: str,
        sample_name: str,
        source_path: str,
        *,
        dry_run: bool = False,
        overwrite: bool = False,
        allow_too_few: bool = False,
    ) -> dict[str, Any]:
        plan = self.build_plan(registry_path, sample_name)
        action = plan.actions[0]
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"source file not found: {source_path}")
        count = self._source_candle_count(source)
        if count < action.expected_min_candles and not allow_too_few:
            raise ValueError(
                f"source has too few candles: {count} < {action.expected_min_candles}"
            )
        destination = self._destination(action.fixture_path)
        if destination.exists() and not overwrite:
            raise FileExistsError(f"destination already exists: {destination}")
        result = {
            "sample_name": sample_name,
            "source_path": str(source),
            "destination_path": str(destination),
            "candle_count": count,
            "expected_min_candles": action.expected_min_candles,
            "allow_too_few": allow_too_few,
            "dry_run": dry_run,
        }
        if dry_run:
            return result
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return result

    def _action(self, sample) -> HistoricalSamplePreparationAction:
        if sample.status == "AVAILABLE":
            action_type = "NONE"
            reason = "sample is available and meets minimum candle count"
        elif sample.status == "MISSING":
            action_type = "IMPORT_REQUIRED"
            reason = "sample file is missing"
        else:
            action_type = "REPLACE_RECOMMENDED"
            reason = sample.error_message or f"sample status is {sample.status}"
        return HistoricalSamplePreparationAction(
            sample_name=sample.sample_name,
            symbol=sample.symbol,
            timeframe=sample.timeframe,
            fixture_path=sample.fixture_path,
            current_status=sample.status,
            required_for_full_gate=sample.required_for_full_gate,
            required_for_ci_gate=sample.required_for_ci_gate,
            expected_min_candles=sample.expected_min_candles,
            action_type=action_type,
            reason=reason,
            suggested_download_command=(
                f"Use your preferred downloader/exporter to create {sample.fixture_path} "
                f"with at least {sample.expected_min_candles} candles for {sample.symbol} {sample.timeframe}."
            ),
            suggested_import_command=(
                f"py scripts/prepare_historical_samples.py --sample {sample.sample_name} "
                "--source <path-to-downloaded-json> --import-source"
            ),
        )

    def _destination(self, fixture_path: str) -> Path:
        path = Path(fixture_path)
        if not path.is_absolute():
            path = self.repo_root / path
        return path

    def _source_candle_count(self, source: Path) -> int:
        try:
            loaded = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"source file invalid JSON: {source}") from exc
        count = self._candle_count(loaded)
        if count is None:
            raise ValueError(f"source file unsupported candle JSON shape: {source}")
        return count

    def _candle_count(self, loaded: Any) -> int | None:
        if isinstance(loaded, list):
            return len(loaded)
        if isinstance(loaded, dict):
            for key in ("candles", "data", "rows"):
                value = loaded.get(key)
                if isinstance(value, list):
                    return len(value)
        return None
