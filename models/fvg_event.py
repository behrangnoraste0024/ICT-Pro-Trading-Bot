from dataclasses import dataclass
from typing import Optional


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
    mitigation_type: str = "NONE"
    mitigation_index: Optional[int] = None
    active: bool = True
    event_type: str = "FVG"

    def __str__(self) -> str:
        status = "ACTIVE" if self.active else "INACTIVE"
        return (
            f"{self.event_type} | {self.direction} | "
            f"{self.lower_bound} - {self.upper_bound} | {status} | {self.mitigation_type}"
        )
