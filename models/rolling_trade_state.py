from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RollingTradeState:

    is_open: bool = False
    direction: str = "NONE"
    status: str = "EMPTY"
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    entry_index: Optional[int] = None
    exit_price: Optional[float] = None
    exit_index: Optional[int] = None
    pnl: Optional[float] = None
    reasons: list[str] = field(default_factory=list)
    event_type: str = "ROLLING_TRADE_STATE"

    def __str__(self) -> str:
        if self.status == "OPEN":
            return (
                f"{self.event_type} | {self.status} | {self.direction} | "
                f"ENTRY={self.entry_price} | SL={self.stop_loss} | TP={self.take_profit}"
            )

        return (
            f"{self.event_type} | {self.status} | {self.direction} | "
            f"ENTRY={self.entry_price} | EXIT={self.exit_price} | PNL={self.pnl}"
        )
