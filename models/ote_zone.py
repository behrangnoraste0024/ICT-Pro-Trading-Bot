from dataclasses import dataclass
from typing import Optional


@dataclass
class OTEZone:

    direction: str
    dealing_range_high: float
    dealing_range_low: float
    level_62: float
    level_705: float
    level_79: float
    lower_bound: float
    upper_bound: float
    current_price: Optional[float] = None
    in_zone: bool = False
    event_type: str = "OTE"
    active: bool = True

    def __str__(self) -> str:
        return (
            f"{self.event_type} | "
            f"{self.direction} | "
            f"{self.lower_bound} - {self.upper_bound} | "
            f"IN_ZONE={self.in_zone} | "
            f"0.705={self.level_705}"
        )
