from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.multi_sample_validation import MultiSampleDefinition


@dataclass
class ValidationSampleScopeResult:
    sample_scope: str
    selected_samples: list[MultiSampleDefinition] = field(default_factory=list)
    excluded_samples: list[MultiSampleDefinition] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_scope": self.sample_scope,
            "selected_samples": [sample.to_dict() for sample in self.selected_samples],
            "excluded_samples": [sample.to_dict() for sample in self.excluded_samples],
            "diagnostics": self.diagnostics,
        }
