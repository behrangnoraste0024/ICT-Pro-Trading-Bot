from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TradeOutcomeRecord:
    trade_number: int
    direction: str
    status: str
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    exit_price: float | None = None
    pnl: float | None = None
    result: str = "UNKNOWN"
    risk: float | None = None
    reward: float | None = None
    risk_reward: float | None = None
    entry_index: int | None = None
    exit_index: int | None = None
    entry_timestamp: str | int | None = None
    exit_timestamp: str | int | None = None
    setup_status: str | None = None
    setup_bias: str | None = None
    setup_score: float | int | None = None
    entry_status: str | None = None
    entry_trigger_type: str | None = None
    dealing_range_mode: str | None = None
    current_price_zone: str | None = None
    in_ote_zone: bool | None = None
    ote_direction: str | None = None
    dealing_range_high: float | None = None
    dealing_range_low: float | None = None
    equilibrium: float | None = None
    matched_poi_count: int = 0
    matched_poi_types: list[str] = field(default_factory=list)
    trade_quality_status: str | None = None
    trade_quality_score: float | int | None = None
    setup_blockers: list[str] = field(default_factory=list)
    entry_blockers: list[str] = field(default_factory=list)
    trade_plan_blockers: list[str] = field(default_factory=list)
    trade_quality_blockers: list[str] = field(default_factory=list)
    paper_trade_blockers: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    market_regime: str | None = None
    market_regime_mode: str | None = None
    market_regime_lookback: int | None = None
    market_regime_threshold_pct: float | None = None
    market_regime_return_pct: float | None = None
    market_regime_fallback: str | None = None
    market_regime_reason: str | None = None
    direction_mode_requested: str | None = None
    direction_mode_applied: str | None = None
    direction_mode_allowed: bool | None = None
    direction_mode_blocked_direction: str | None = None
    direction_mode_fallback_reason: str | None = None
    direction_mode_resolved_direction: str | None = None
    auto_trend_source_trend: str | None = None
    auto_trend_fallback: str | None = None
    regime_source_regime: str | None = None
    regime_fallback: str | None = None
    event_type: str = "TRADE_OUTCOME_RECORD"

    def __str__(self) -> str:
        return (
            f"TRADE #{self.trade_number} | {self.direction} | {self.result} | "
            f"ENTRY={self.entry_price} | EXIT={self.exit_price} | "
            f"PNL={self.pnl} | RR={self.risk_reward}"
        )


@dataclass
class TradeOutcomeDiagnostics:
    trades: list[TradeOutcomeRecord] = field(default_factory=list)
    total_trades: int = 0
    closed_trades: int = 0
    open_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    net_pnl: float = 0.0
    average_pnl: float = 0.0
    average_win: float | None = None
    average_loss: float | None = None
    largest_win: float | None = None
    largest_loss: float | None = None
    average_rr: float | None = None
    average_setup_score: float | None = None
    event_type: str = "TRADE_OUTCOME_DIAGNOSTICS"

    def winning_trades(self) -> list[TradeOutcomeRecord]:
        return [trade for trade in self.trades if trade.result == "WIN"]

    def losing_trades(self) -> list[TradeOutcomeRecord]:
        return [trade for trade in self.trades if trade.result == "LOSS"]

    def open_trade_records(self) -> list[TradeOutcomeRecord]:
        return [trade for trade in self.trades if trade.result == "OPEN"]

    def trades_by_direction(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for trade in self.trades:
            counts[trade.direction] = counts.get(trade.direction, 0) + 1
        return counts

    def pnl_by_direction(self) -> dict[str, float]:
        pnl: dict[str, float] = {}
        for trade in self.trades:
            pnl[trade.direction] = pnl.get(trade.direction, 0.0) + float(trade.pnl or 0)
        return pnl

    def __str__(self) -> str:
        return (
            f"{self.event_type} | TRADES={self.total_trades} | "
            f"WINS={self.wins} | LOSSES={self.losses} | NET_PNL={self.net_pnl}"
        )
