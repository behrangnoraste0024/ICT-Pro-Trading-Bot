from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EntryFollowthroughHorizon:
    horizon: int
    available: bool = False
    candles_used: int = 0
    favorable_move: float | None = None
    adverse_move: float | None = None
    favorable_r: float | None = None
    adverse_r: float | None = None
    tp_progress: float | None = None
    sl_pressure: float | None = None


@dataclass
class EntryFollowthroughRecord:
    trade_number: int
    direction: str
    result: str
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    risk: float | None = None
    reward: float | None = None
    risk_reward: float | None = None
    bars_held: int | None = None
    entry_trigger_type: str | None = None
    setup_score: float | int | None = None
    current_price_zone: str | None = None
    in_ote_zone: bool | None = None
    matched_poi_count: int = 0
    matched_poi_types: list[str] = field(default_factory=list)
    next_candle_available: bool = False
    next_candle_continuation: bool | None = None
    next_candle_rejection: bool | None = None
    next_candle_close: float | None = None
    horizons: dict[int, EntryFollowthroughHorizon] = field(default_factory=dict)
    immediate_favorable: bool = False
    immediate_adverse: bool = False
    no_followthrough_3: bool = False
    strong_followthrough_3: bool = False
    early_reversal_3: bool = False
    event_type: str = "ENTRY_FOLLOWTHROUGH_RECORD"

    def __str__(self) -> str:
        h3 = self.horizons.get(3, EntryFollowthroughHorizon(horizon=3))
        return (
            f"{self.event_type} #{self.trade_number} | {self.direction} | {self.result} | "
            f"H3_FAV_R={h3.favorable_r} | H3_ADV_R={h3.adverse_r} | NO_FT={self.no_followthrough_3}"
        )


@dataclass
class EntryFollowthroughDiagnostics:
    records: list[EntryFollowthroughRecord] = field(default_factory=list)
    total_trades: int = 0
    closed_trades: int = 0
    open_trades: int = 0
    wins: int = 0
    losses: int = 0
    next_candle_available_count: int = 0
    next_candle_continuation_count: int = 0
    next_candle_rejection_count: int = 0
    immediate_favorable_count: int = 0
    immediate_adverse_count: int = 0
    no_followthrough_3_count: int = 0
    strong_followthrough_3_count: int = 0
    early_reversal_3_count: int = 0
    average_h1_favorable_r: float | None = None
    average_h1_adverse_r: float | None = None
    average_h3_favorable_r: float | None = None
    average_h3_adverse_r: float | None = None
    average_h5_favorable_r: float | None = None
    average_h5_adverse_r: float | None = None
    winners_average_h3_favorable_r: float | None = None
    losers_average_h3_favorable_r: float | None = None
    winners_next_candle_continuation_count: int = 0
    losers_next_candle_continuation_count: int = 0
    trigger_counts: dict[str, int] = field(default_factory=dict)
    trigger_win_counts: dict[str, int] = field(default_factory=dict)
    trigger_loss_counts: dict[str, int] = field(default_factory=dict)
    trigger_average_h3_favorable_r: dict[str, float] = field(default_factory=dict)
    trigger_average_h3_adverse_r: dict[str, float] = field(default_factory=dict)
    long_no_followthrough_3_count: int = 0
    short_no_followthrough_3_count: int = 0
    long_early_reversal_3_count: int = 0
    short_early_reversal_3_count: int = 0
    event_type: str = "ENTRY_FOLLOWTHROUGH_DIAGNOSTICS"

    def no_followthrough_records(self) -> list[EntryFollowthroughRecord]:
        return [record for record in self.records if record.no_followthrough_3]

    def early_reversal_records(self) -> list[EntryFollowthroughRecord]:
        return [record for record in self.records if record.early_reversal_3]

    def strong_followthrough_records(self) -> list[EntryFollowthroughRecord]:
        return [record for record in self.records if record.strong_followthrough_3]

    def __str__(self) -> str:
        return (
            f"{self.event_type} | TRADES={self.total_trades} | "
            f"NO_FT3={self.no_followthrough_3_count} | EARLY_REV3={self.early_reversal_3_count}"
        )
