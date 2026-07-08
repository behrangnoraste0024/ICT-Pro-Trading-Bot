from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from models.historical_sample_registry import (
    HistoricalSampleAvailability,
    HistoricalSampleDefinition,
    HistoricalSampleRegistryReport,
)


class HistoricalSampleRegistryEngine:
    def __init__(self, repo_root: str | Path | None = None) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)

    def load_registry(self, registry_path: str) -> tuple[str, list[HistoricalSampleDefinition]]:
        path = Path(registry_path)
        if not path.exists():
            raise FileNotFoundError(f"historical sample registry not found: {registry_path}")
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"historical sample registry invalid JSON: {registry_path}") from exc
        if not isinstance(loaded, dict):
            raise ValueError(f"historical sample registry must be a JSON object: {registry_path}")
        samples = loaded.get("samples")
        if not isinstance(samples, list):
            raise ValueError(f"historical sample registry samples must be a list: {registry_path}")
        return str(loaded.get("schema_version") or "1.0"), [self._sample(item, registry_path) for item in samples]

    def check(self, registry_path: str = "configs/historical_sample_registry.json") -> HistoricalSampleRegistryReport:
        schema_version, definitions = self.load_registry(registry_path)
        rows = [self._availability(definition) for definition in definitions]
        invalid = [row for row in rows if row.status not in ("AVAILABLE", "MISSING")]
        return HistoricalSampleRegistryReport(
            schema_version=schema_version,
            registry_path=registry_path,
            total_samples=len(rows),
            available_samples=sum(1 for row in rows if row.status == "AVAILABLE"),
            missing_samples=sum(1 for row in rows if row.status == "MISSING"),
            invalid_samples=len(invalid),
            required_full_available=all(
                row.status == "AVAILABLE" for row in rows if row.required_for_full_gate
            ),
            required_ci_available=all(
                row.status == "AVAILABLE" for row in rows if row.required_for_ci_gate
            ),
            samples=rows,
        )

    def _sample(self, data: Any, registry_path: str) -> HistoricalSampleDefinition:
        if not isinstance(data, dict):
            raise ValueError(f"historical sample registry entry must be an object: {registry_path}")
        try:
            return HistoricalSampleDefinition(
                sample_name=str(data["sample_name"]),
                symbol=str(data["symbol"]),
                timeframe=str(data["timeframe"]),
                fixture_path=str(data["fixture_path"]),
                expected_min_candles=int(data["expected_min_candles"]),
                required_for_full_gate=bool(data.get("required_for_full_gate", False)),
                required_for_ci_gate=bool(data.get("required_for_ci_gate", False)),
                notes=None if data.get("notes") is None else str(data.get("notes")),
            )
        except KeyError as exc:
            raise ValueError(f"historical sample registry entry missing field: {exc.args[0]}") from exc

    def _availability(self, definition: HistoricalSampleDefinition) -> HistoricalSampleAvailability:
        path = Path(definition.fixture_path)
        if not path.is_absolute():
            path = self.repo_root / path
        base = {
            "sample_name": definition.sample_name,
            "symbol": definition.symbol,
            "timeframe": definition.timeframe,
            "fixture_path": definition.fixture_path,
            "expected_min_candles": definition.expected_min_candles,
            "required_for_full_gate": definition.required_for_full_gate,
            "required_for_ci_gate": definition.required_for_ci_gate,
        }
        if not path.exists():
            return HistoricalSampleAvailability(
                **base,
                exists=False,
                readable=False,
                file_size_bytes=None,
                modified_at=None,
                candle_count=None,
                meets_min_candles=False,
                status="MISSING",
                error_message="file not found",
            )
        try:
            stat = path.stat()
            file_size = stat.st_size
            modified_at = datetime.fromtimestamp(stat.st_mtime, UTC).isoformat()
        except OSError as exc:
            return HistoricalSampleAvailability(
                **base,
                exists=True,
                readable=False,
                file_size_bytes=None,
                modified_at=None,
                candle_count=None,
                meets_min_candles=False,
                status="UNREADABLE",
                error_message=str(exc),
            )
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            count = self._candle_count(loaded)
        except json.JSONDecodeError as exc:
            return HistoricalSampleAvailability(
                **base,
                exists=True,
                readable=True,
                file_size_bytes=file_size,
                modified_at=modified_at,
                candle_count=None,
                meets_min_candles=False,
                status="INVALID_JSON",
                error_message=str(exc),
            )
        except OSError as exc:
            return HistoricalSampleAvailability(
                **base,
                exists=True,
                readable=False,
                file_size_bytes=file_size,
                modified_at=modified_at,
                candle_count=None,
                meets_min_candles=False,
                status="UNREADABLE",
                error_message=str(exc),
            )
        if count is None:
            return HistoricalSampleAvailability(
                **base,
                exists=True,
                readable=True,
                file_size_bytes=file_size,
                modified_at=modified_at,
                candle_count=None,
                meets_min_candles=False,
                status="UNKNOWN",
                error_message="unsupported candle JSON shape",
            )
        meets_min = count >= definition.expected_min_candles
        return HistoricalSampleAvailability(
            **base,
            exists=True,
            readable=True,
            file_size_bytes=file_size,
            modified_at=modified_at,
            candle_count=count,
            meets_min_candles=meets_min,
            status="AVAILABLE" if meets_min else "TOO_FEW_CANDLES",
            error_message=None if meets_min else f"expected at least {definition.expected_min_candles} candles",
        )

    def _candle_count(self, loaded: Any) -> int | None:
        if isinstance(loaded, list):
            return len(loaded)
        if isinstance(loaded, dict):
            for key in ("candles", "data", "rows"):
                value = loaded.get(key)
                if isinstance(value, list):
                    return len(value)
        return None
