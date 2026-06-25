from dataclasses import dataclass


@dataclass
class BOSEvent:

    candle_index: int

    level: float

    direction: str

    def __str__(self):

        return (
            f"{self.direction} BOS @ "
            f"{self.level}"
        )