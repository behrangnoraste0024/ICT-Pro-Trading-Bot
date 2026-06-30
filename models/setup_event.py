from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SetupEvent:

    direction: str
    status: str
    score: int
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    current_price: Optional[float] = None
    price_zone: str = "UNKNOWN"
    trend: str = "UNKNOWN"
    ote_direction: str = "NONE"
    in_ote_zone: bool = False
    matched_pois: list[str] = field(default_factory=list)
    event_type: str = "SETUP"

    def __str__(self) -> str:
        if self.status == "VALID":
            return (
                f"{self.event_type} | {self.direction} | {self.status} | "
                f"SCORE={self.score} | POIS={len(self.matched_pois)}"
            )

        return (
            f"{self.event_type} | {self.direction} | {self.status} | "
            f"SCORE={self.score} | BLOCKERS={','.join(self.blockers)}"
        )
