from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


KILL_SWITCH_STATES = {"ENGAGED", "RELEASED"}
KILL_SWITCH_SCOPE = "BINANCE_FUTURES_TESTNET:BTCUSDT"


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


@dataclass(frozen=True)
class KillSwitchState:
    scope: str
    environment: str
    symbol: str
    state: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1

    def __post_init__(self) -> None:
        if self.scope != KILL_SWITCH_SCOPE:
            raise ValueError("unsupported kill switch scope")
        if self.environment != "BINANCE_FUTURES_TESTNET" or self.symbol != "BTCUSDT":
            raise ValueError("unsupported kill switch environment or symbol")
        if self.state not in KILL_SWITCH_STATES:
            raise ValueError("unsupported kill switch state")
