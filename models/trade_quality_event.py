from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TradeQualityEvent:

    status: str
    score: int
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    risk_percent: Optional[float] = None
    reward_percent: Optional[float] = None
    risk_reward: Optional[float] = None
    event_type: str = "TRADE_QUALITY"

    def __str__(self) -> str:
        if self.status == "APPROVED":
            return f"{self.event_type} | {self.status} | SCORE={self.score} | RR={self.risk_reward}"

        return (
            f"{self.event_type} | {self.status} | SCORE={self.score} | "
            f"BLOCKERS={','.join(self.blockers)}"
        )
