from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EntryTriggerEvent:

    direction: str
    status: str
    trigger_type: str
    confirmed: bool
    candle_index: Optional[int]
    current_price: Optional[float]
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    event_type: str = "ENTRY_TRIGGER"

    def __str__(self) -> str:
        if self.confirmed:
            return (
                f"{self.event_type} | {self.direction} | {self.status} | "
                f"{self.trigger_type} | PRICE={self.current_price}"
            )

        return (
            f"{self.event_type} | {self.direction} | {self.status} | "
            f"{self.trigger_type} | BLOCKERS={','.join(self.blockers)}"
        )
