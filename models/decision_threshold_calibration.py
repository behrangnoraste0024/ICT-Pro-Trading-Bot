from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DecisionThresholdBucket:
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
    event_type: str = "DECISION_THRESHOLD_BUCKET"


@dataclass
class DecisionThresholdCalibrationResult:
    thresholds: list[DecisionThresholdBucket] = field(default_factory=list)
    best_by_net_after_costs: Optional[str] = None
    best_by_drawdown: Optional[str] = None
    best_by_profit_factor: Optional[str] = None
    diagnostics: dict = field(default_factory=dict)
    event_type: str = "DECISION_THRESHOLD_CALIBRATION_RESULT"
