from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PaperTradeEvent:

    direction: str
    status: str
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    entry_index: Optional[int]
    exit_price: Optional[float]
    exit_index: Optional[int]
    pnl: Optional[float]
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    event_type: str = "PAPER_TRADE"

    def __str__(self) -> str:
        if self.status == "NO_PAPER_TRADE":
            return (
                f"{self.event_type} | {self.direction} | {self.status} | "
                f"BLOCKERS={','.join(self.blockers)}"
            )

        parts = [
            f"{self.event_type} | {self.direction} | {self.status}",
            f"ENTRY={self.entry_price}",
        ]

        if self.exit_price is not None:
            parts.append(f"EXIT={self.exit_price}")
        if self.pnl is not None:
            parts.append(f"PNL={self.pnl}")
        if self.exit_price is None and self.pnl is None:
            parts.append(f"SL={self.stop_loss}")
            parts.append(f"TP={self.take_profit}")

        return " | ".join(parts)
