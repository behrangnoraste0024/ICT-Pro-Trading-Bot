from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RecommendedProfileValidation:
    recommended_strategy_name: str | None
    recommended_profile: str | None
    recommendation_reason: str
    score_threshold: float | None
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    gross_net_pnl: float
    total_cost: float
    net_pnl_after_costs: float
    max_drawdown: float
    profit_factor: float | None
    average_decision_score: float | None
    average_execution_quality: float | None
    baseline_strategy_name: str | None = None
    baseline_net_pnl_after_costs: float | None = None
    baseline_max_drawdown: float | None = None
    improvement_vs_baseline: float | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecommendedProfileValidationResult:
    selected: RecommendedProfileValidation | None = None
    candidates_evaluated: int = 0
    ranking: list[RecommendedProfileValidation] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    event_type: str = "RECOMMENDED_PROFILE_VALIDATION_RESULT"

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected": None if self.selected is None else self.selected.to_dict(),
            "candidates_evaluated": self.candidates_evaluated,
            "ranking": [candidate.to_dict() for candidate in self.ranking],
            "diagnostics": self.diagnostics,
            "event_type": self.event_type,
        }
