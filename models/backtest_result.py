from dataclasses import dataclass


@dataclass
class BacktestResult:

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
    event_type: str = "BACKTEST_RESULT"

    def __str__(self) -> str:
        return (
            f"{self.event_type} | TRADES={self.total_paper_trades} | "
            f"CLOSED={self.closed_trades} | WINS={self.wins} | "
            f"LOSSES={self.losses} | WIN_RATE={self.win_rate}% | "
            f"NET_PNL={self.net_pnl}"
        )
