from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DecisionThresholdSegmentBucket:
    segment_index: int
    segment_name: str
    threshold: float
    name: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    gross_net_pnl: float
    total_cost: float
    net_pnl_after_costs: float
    average_pnl: float
    average_net_pnl_after_costs: float
    max_drawdown: float
    profit_factor: Optional[float]
    average_execution_quality: Optional[float]
    average_decision_score: Optional[float]
    event_type: str = "DECISION_THRESHOLD_SEGMENT_BUCKET"


@dataclass
class DecisionThresholdSegmentSummary:
    segment_index: int
    segment_name: str
    start_trade_index: int
    end_trade_index: int
    total_source_trades: int
    best_by_net_after_costs: Optional[str]
    best_by_drawdown: Optional[str]
    buckets: list[DecisionThresholdSegmentBucket] = field(default_factory=list)
    event_type: str = "DECISION_THRESHOLD_SEGMENT_SUMMARY"


@dataclass
class DecisionThresholdRobustnessResult:
    segment_count: int
    thresholds: list[float] = field(default_factory=list)
    segment_summaries: list[DecisionThresholdSegmentSummary] = field(default_factory=list)
    threshold_stability: dict = field(default_factory=dict)
    best_overall_threshold: Optional[float] = None
    robust_threshold: Optional[float] = None
    diagnostics: dict = field(default_factory=dict)
    event_type: str = "DECISION_THRESHOLD_ROBUSTNESS_RESULT"
