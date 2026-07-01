from dataclasses import dataclass, field
from typing import Any

from models.backtest_diagnostics import BacktestDiagnostics
from models.entry_followthrough_diagnostics import EntryFollowthroughDiagnostics
from models.sl_tp_outcome_diagnostics import SLTPOutcomeDiagnostics
from models.trade_outcome_diagnostics import TradeOutcomeDiagnostics
from models.virtual_exit_diagnostics import VirtualExitDiagnostics


@dataclass
class RollingBacktestResult:

    total_windows: int
    processed_windows: int
    skipped_windows: int
    failed_windows: int
    min_candles: int
    total_paper_trades: int
    closed_trades: int
    open_trades: int
    wins: int
    losses: int
    win_rate: float
    net_pnl: float
    average_pnl: float
    max_drawdown: float
    ignored_contexts: int
    stateful_mode: bool = True
    opened_trades: int = 0
    closed_by_state: int = 0
    duplicate_signals_skipped: int = 0
    diagnostics: BacktestDiagnostics | None = None
    diagnostics_windows_analyzed: int = 0
    dealing_range_mode: str = "current_external"
    range_mode_fallback_count: int = 0
    exit_mode: str = "original"
    exit_mode_fallback_counts: dict[str, int] = field(default_factory=dict)
    min_risk_reward: float = 2.0
    direction_mode: str = "all"
    direction_mode_fallback_counts: dict[str, int] = field(default_factory=dict)
    trade_outcome_diagnostics: TradeOutcomeDiagnostics | None = None
    sl_tp_outcome_diagnostics: SLTPOutcomeDiagnostics | None = None
    entry_followthrough_diagnostics: EntryFollowthroughDiagnostics | None = None
    virtual_exit_diagnostics: VirtualExitDiagnostics | None = None
    trade_outcome_contexts: list[Any] = field(default_factory=list)
    event_type: str = "ROLLING_BACKTEST_RESULT"

    def __str__(self) -> str:
        return (
            f"{self.event_type} | WINDOWS={self.total_windows} | "
            f"PROCESSED={self.processed_windows} | TRADES={self.total_paper_trades} | "
            f"WINS={self.wins} | LOSSES={self.losses} | "
            f"WIN_RATE={self.win_rate}% | NET_PNL={self.net_pnl} | "
            f"FAILED={self.failed_windows} | OPENED={self.opened_trades} | "
            f"CLOSED_BY_STATE={self.closed_by_state} | "
            f"DUPLICATES_SKIPPED={self.duplicate_signals_skipped}"
        )
