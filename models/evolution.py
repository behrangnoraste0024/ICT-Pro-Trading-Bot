from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from models.strategy_comparison import StrategyConfigSpec


@dataclass
class EvolutionCandidate:
    candidate_id: str
    strategy_spec: StrategyConfigSpec
    generation: int = 0
    parent_id: str | None = None
    mutation_reason: str = "SEED"
    event_type: str = "EVOLUTION_CANDIDATE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvolutionEvaluation:
    candidate: EvolutionCandidate
    fitness: float
    net_pnl_after_costs: float
    gross_net_pnl: float
    win_rate: float
    profit_factor: float | None
    max_drawdown: float
    total_trades: int
    execution_quality_score: float | None = None
    event_type: str = "EVOLUTION_EVALUATION"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GenerationResult:
    generation: int
    evaluated: list[EvolutionEvaluation] = field(default_factory=list)
    selected: list[EvolutionEvaluation] = field(default_factory=list)
    next_generation: list[EvolutionCandidate] = field(default_factory=list)
    top_k: int = 0
    event_type: str = "GENERATION_RESULT"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
