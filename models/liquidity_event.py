from dataclasses import dataclass


@dataclass
class LiquidityEvent:
    candle_index: int
    level_index: int
    level: float
    direction: str
    event_type: str = "LIQUIDITY_SWEEP"
    swept: bool = True

    def __str__(self) -> str:
        return f"{self.event_type} | {self.direction} | {self.level}"
