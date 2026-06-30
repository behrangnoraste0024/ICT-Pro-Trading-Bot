from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TradePlanEvent:

    direction: str
    status: str
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    risk: Optional[float]
    reward: Optional[float]
    risk_reward: Optional[float]
    entry_trigger_type: str
    blockers: list[str] = field(default_factory=list)
    event_type: str = "TRADE_PLAN"

    def __str__(self) -> str:
        if self.status == "NO_TRADE":
            return (
                f"{self.event_type} | {self.direction} | {self.status} | "
                f"BLOCKERS={','.join(self.blockers)}"
            )

        return (
            f"{self.event_type} | {self.direction} | {self.status} | "
            f"ENTRY={self.entry_price} | SL={self.stop_loss} | "
            f"TP={self.take_profit} | RR={self.risk_reward}"
        )
