from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TradeCostBreakdown:
    trade_index: int
    direction: str
    gross_pnl: float
    commission_cost: float
    slippage_cost: float
    spread_cost: float
    total_cost: float
    net_pnl_after_costs: float
    entry_price: float | None
    exit_price: float | None
    is_closed: bool
    event_type: str = "TRADE_COST_BREAKDOWN"


@dataclass
class CostDiagnostics:
    cost_model: str
    commission_pct: float
    slippage_pct: float
    spread_pct: float
    total_trades: int
    closed_trades: int
    gross_net_pnl: float
    total_commission_cost: float
    total_slippage_cost: float
    total_spread_cost: float
    total_cost: float
    net_pnl_after_costs: float
    average_cost_per_trade: float
    average_net_pnl_after_costs: float
    cost_to_gross_profit_ratio: float | None
    trades: list[TradeCostBreakdown] = field(default_factory=list)
    event_type: str = "COST_DIAGNOSTICS"
