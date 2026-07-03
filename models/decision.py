from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DecisionResult:
    final_score: float
    decision: str
    breakdown: dict[str, Any] = field(default_factory=dict)
    event_type: str = "DECISION_RESULT"
