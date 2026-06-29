from dataclasses import dataclass


@dataclass
class FVGEvent:
    index: int
    start_index: int
    middle_index: int
    end_index: int
    direction: str
    lower_bound: float
    upper_bound: float
    mitigated: bool = False
    event_type: str = "FVG"

    def __str__(self) -> str:
        return f"{self.event_type} | {self.direction} | {self.lower_bound} - {self.upper_bound}"
