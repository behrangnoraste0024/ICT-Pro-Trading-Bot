from dataclasses import dataclass


@dataclass
class OrderBlockEvent:

    index: int
    trigger_index: int
    direction: str
    lower_bound: float
    upper_bound: float
    open: float
    high: float
    low: float
    close: float
    source_event_type: str
    event_type: str = "ORDER_BLOCK"
    mitigated: bool = False
    active: bool = True

    def __str__(self):

        state = "ACTIVE" if self.active else "INACTIVE"

        return (
            f"{self.event_type} | "
            f"{self.direction} | "
            f"{self.lower_bound} - {self.upper_bound} | "
            f"{state} | "
            f"{self.source_event_type}"
        )
