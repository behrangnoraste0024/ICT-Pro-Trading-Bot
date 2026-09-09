from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StrategySignalResult:
    signal_status: str
    direction: str
    confidence_score: float
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    source_evidence: dict[str, Any] = field(default_factory=dict)
    event_type: str = "STRATEGY_SIGNAL"
