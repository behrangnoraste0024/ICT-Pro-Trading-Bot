from dataclasses import dataclass


@dataclass
class BreakerBlockEvent:

    index: int
    source_order_block_index: int
    source_trigger_index: int
    invalidation_index: int
    direction: str
    original_order_block_direction: str
    lower_bound: float
    upper_bound: float
    source_event_type: str
    event_type: str = "BREAKER_BLOCK"
    active: bool = True
    mitigated: bool = False

    def __str__(self):

        state = "ACTIVE" if self.active else "INACTIVE"

        return (
            f"{self.event_type} | "
            f"{self.direction} | "
            f"{self.lower_bound} - {self.upper_bound} | "
            f"{state} | "
            f"FROM_{self.original_order_block_direction}_OB"
        )
