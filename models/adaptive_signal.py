from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AdaptiveSignal:
    original_decision: str
    final_decision: str
    reason: str
    adjustments: dict[str, Any] = field(default_factory=dict)
    event_type: str = "ADAPTIVE_SIGNAL"
