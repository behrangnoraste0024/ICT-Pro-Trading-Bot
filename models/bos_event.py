from dataclasses import dataclass


@dataclass
class BOSEvent:

    candle_index: int

    level: float

    direction: str      # Bullish / Bearish

    event_type: str     # BOS / CHOCH

    def __str__(self):

        return (
            f"{self.event_type} | "
            f"{self.direction} | "
            f"{self.level}"
        )