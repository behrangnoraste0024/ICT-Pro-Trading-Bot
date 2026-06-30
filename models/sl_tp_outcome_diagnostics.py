from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SLTPOutcomeRecord:
    trade_number: int
    direction: str
    result: str
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    exit_price: float | None = None
    entry_index: int | None = None
    exit_index: int | None = None
    bars_held: int | None = None
    risk: float | None = None
    reward: float | None = None
    risk_reward: float | None = None
    mae: float | None = None
    mfe: float | None = None
    mae_r: float | None = None
    mfe_r: float | None = None
    tp_progress: float | None = None
    sl_progress: float | None = None
    reached_25_pct_tp: bool | None = None
    reached_50_pct_tp: bool | None = None
    reached_75_pct_tp: bool | None = None
    reached_25_pct_sl: bool | None = None
    reached_50_pct_sl: bool | None = None
    reached_75_pct_sl: bool | None = None
    fast_loss: bool = False
    almost_tp_then_loss: bool = False
    no_follow_through_loss: bool = False
    high_rr_loss: bool = False
    setup_score: float | int | None = None
    entry_trigger_type: str | None = None
    current_price_zone: str | None = None
    in_ote_zone: bool | None = None
    matched_poi_count: int = 0
    matched_poi_types: list[str] = field(default_factory=list)
    event_type: str = "SL_TP_OUTCOME_RECORD"

    def __str__(self) -> str:
        return (
            f"SLTP #{self.trade_number} | {self.direction} | {self.result} | "
            f"BARS={self.bars_held} | MAE_R={self.mae_r} | "
            f"MFE_R={self.mfe_r} | TP_PROGRESS={self.tp_progress}"
        )


@dataclass
class SLTPOutcomeDiagnostics:
    records: list[SLTPOutcomeRecord] = field(default_factory=list)
    total_trades: int = 0
    closed_trades: int = 0
    open_trades: int = 0
    wins: int = 0
    losses: int = 0
    average_bars_held: float | None = None
    average_mae_r: float | None = None
    average_mfe_r: float | None = None
    average_tp_progress: float | None = None
    average_sl_progress: float | None = None
    fast_loss_count: int = 0
    almost_tp_then_loss_count: int = 0
    no_follow_through_loss_count: int = 0
    high_rr_loss_count: int = 0
    reached_25_pct_tp_count: int = 0
    reached_50_pct_tp_count: int = 0
    reached_75_pct_tp_count: int = 0
    reached_25_pct_sl_count: int = 0
    reached_50_pct_sl_count: int = 0
    reached_75_pct_sl_count: int = 0
    average_mfe_r_winners: float | None = None
    average_mae_r_winners: float | None = None
    average_mfe_r_losers: float | None = None
    average_mae_r_losers: float | None = None
    long_loss_count: int = 0
    short_loss_count: int = 0
    long_win_count: int = 0
    short_win_count: int = 0
    event_type: str = "SL_TP_OUTCOME_DIAGNOSTICS"

    def losing_records(self) -> list[SLTPOutcomeRecord]:
        return [record for record in self.records if record.result == "LOSS"]

    def winning_records(self) -> list[SLTPOutcomeRecord]:
        return [record for record in self.records if record.result == "WIN"]

    def high_rr_loss_records(self) -> list[SLTPOutcomeRecord]:
        return [record for record in self.records if record.high_rr_loss]

    def almost_tp_then_loss_records(self) -> list[SLTPOutcomeRecord]:
        return [record for record in self.records if record.almost_tp_then_loss]

    def __str__(self) -> str:
        return (
            f"{self.event_type} | TRADES={self.total_trades} | "
            f"FAST_LOSSES={self.fast_loss_count} | HIGH_RR_LOSSES={self.high_rr_loss_count}"
        )
