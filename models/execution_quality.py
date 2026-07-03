from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionQualityResult:
    score: float
    volatility_component: float
    spread_component: float
    structure_component: float
    liquidity_component: float
    timing_component: float
    reasoning: dict[str, Any] = field(default_factory=dict)
    event_type: str = "EXECUTION_QUALITY_RESULT"
