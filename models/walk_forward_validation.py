from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class WalkForwardSegmentValidation:
    segment_name: str
    segment_index: int
    start_trade_index: int
    end_trade_index: int
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    gross_net_pnl: float
    total_cost: float
    net_pnl_after_costs: float
    max_drawdown: float
    average_decision_score: float | None
    average_execution_quality: float | None
    passed: bool
    failure_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WalkForwardRecommendedProfileValidation:
    profile: str
    strategy_name: str
    score_threshold: float | None
    segment_count: int
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    gross_net_pnl: float
    total_cost: float
    net_pnl_after_costs: float
    max_drawdown: float
    profitable_segments: int
    losing_segments: int
    empty_segments: int
    passed_segments: int
    failed_segments: int
    worst_segment_net_pnl_after_costs: float
    average_segment_net_pnl_after_costs: float
    validation_status: str
    validation_reason: str
    segments: list[WalkForwardSegmentValidation] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    event_type: str = "WALK_FORWARD_RECOMMENDED_PROFILE_VALIDATION"

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "strategy_name": self.strategy_name,
            "score_threshold": self.score_threshold,
            "segment_count": self.segment_count,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": self.win_rate,
            "gross_net_pnl": self.gross_net_pnl,
            "total_cost": self.total_cost,
            "net_pnl_after_costs": self.net_pnl_after_costs,
            "max_drawdown": self.max_drawdown,
            "profitable_segments": self.profitable_segments,
            "losing_segments": self.losing_segments,
            "empty_segments": self.empty_segments,
            "passed_segments": self.passed_segments,
            "failed_segments": self.failed_segments,
            "worst_segment_net_pnl_after_costs": self.worst_segment_net_pnl_after_costs,
            "average_segment_net_pnl_after_costs": self.average_segment_net_pnl_after_costs,
            "validation_status": self.validation_status,
            "validation_reason": self.validation_reason,
            "segments": [segment.to_dict() for segment in self.segments],
            "diagnostics": self.diagnostics,
            "event_type": self.event_type,
        }
