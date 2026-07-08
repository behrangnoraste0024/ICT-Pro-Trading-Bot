from __future__ import annotations

from pathlib import Path

from engine.diagnostics.historical_sample_registry_engine import HistoricalSampleRegistryEngine
from models.historical_sample_registry import HistoricalSampleAvailability, HistoricalSampleDefinition
from models.multi_sample_validation import MultiSampleDefinition
from models.validation_sample_scope import ValidationSampleScopeResult


SAMPLE_SCOPE_CHOICES = ("required_full", "required_ci", "btc_only", "all_available", "all_registry")


class ValidationSampleScopeEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        registry_engine: HistoricalSampleRegistryEngine | None = None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.registry_engine = registry_engine or HistoricalSampleRegistryEngine(repo_root=self.repo_root)

    def select(
        self,
        registry_path: str = "configs/historical_sample_registry.json",
        sample_scope: str = "all_registry",
        sample_names: list[str] | None = None,
    ) -> ValidationSampleScopeResult:
        schema_version, definitions = self.registry_engine.load_registry(registry_path)
        availability = {row.sample_name: row for row in self.registry_engine.check(registry_path).samples}
        effective_scope = "explicit" if sample_names else sample_scope
        if sample_names:
            selected_names = self._explicit_names(definitions, sample_names)
        else:
            selected_names = {
                definition.sample_name
                for definition in definitions
                if self._matches_scope(definition, availability.get(definition.sample_name), sample_scope)
            }
        selected: list[MultiSampleDefinition] = []
        excluded: list[MultiSampleDefinition] = []
        for definition in definitions:
            converted = self._convert(definition)
            if definition.sample_name in selected_names:
                selected.append(converted)
            else:
                excluded.append(converted)
        return ValidationSampleScopeResult(
            sample_scope=effective_scope,
            selected_samples=selected,
            excluded_samples=excluded,
            diagnostics={
                "registry_path": registry_path,
                "registry_schema_version": schema_version,
                "selected_sample_names": [sample.name for sample in selected],
                "excluded_sample_names": [sample.name for sample in excluded],
            },
        )

    def _explicit_names(
        self,
        definitions: list[HistoricalSampleDefinition],
        sample_names: list[str],
    ) -> set[str]:
        available = {definition.sample_name for definition in definitions}
        requested = set(sample_names)
        missing = sorted(requested - available)
        if missing:
            raise ValueError(f"historical sample not found in registry: {', '.join(missing)}")
        return requested

    def _matches_scope(
        self,
        definition: HistoricalSampleDefinition,
        availability: HistoricalSampleAvailability | None,
        sample_scope: str,
    ) -> bool:
        if sample_scope == "required_full":
            return definition.required_for_full_gate
        if sample_scope == "required_ci":
            return definition.required_for_ci_gate
        if sample_scope == "btc_only":
            return definition.symbol == "BTC/USDT"
        if sample_scope == "all_available":
            return availability is not None and availability.status == "AVAILABLE"
        if sample_scope == "all_registry":
            return True
        raise ValueError(f"unsupported sample scope: {sample_scope}")

    def _convert(self, definition: HistoricalSampleDefinition) -> MultiSampleDefinition:
        return MultiSampleDefinition(
            name=definition.sample_name,
            fixture_path=definition.fixture_path,
            symbol=definition.symbol,
            timeframe=definition.timeframe,
            required=definition.required_for_full_gate or definition.required_for_ci_gate,
            required_for_full_gate=definition.required_for_full_gate,
            required_for_ci_gate=definition.required_for_ci_gate,
        )
