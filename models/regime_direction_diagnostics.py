from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RegimeDirectionBucket:
    key: str
    count: int = 0
    wins: int = 0
    losses: int = 0
    open_trades: int = 0
    pnl: float = 0.0
    average_pnl: float = 0.0

    def add_trade(self, result: str, pnl: float | None) -> None:
        self.count += 1
        if result == "WIN":
            self.wins += 1
        elif result == "LOSS":
            self.losses += 1
        elif result == "OPEN":
            self.open_trades += 1

        self.pnl += float(pnl or 0)
        self.average_pnl = self.pnl / self.count if self.count else 0.0


@dataclass
class RegimeDirectionDiagnostics:
    total_trades: int = 0
    trades_with_regime: int = 0
    trades_missing_regime: int = 0
    by_direction_regime: dict[str, RegimeDirectionBucket] = field(default_factory=dict)
    by_regime_reason: dict[str, RegimeDirectionBucket] = field(default_factory=dict)
    by_direction_mode_reason: dict[str, RegimeDirectionBucket] = field(default_factory=dict)
    by_resolved_direction: dict[str, RegimeDirectionBucket] = field(default_factory=dict)
    long_in_bearish_count: int = 0
    long_in_bearish_pnl: float = 0.0
    short_in_bullish_count: int = 0
    short_in_bullish_pnl: float = 0.0
    missing_metadata_count: int = 0
    event_type: str = "REGIME_DIRECTION_DIAGNOSTICS"

    def __str__(self) -> str:
        return (
            f"{self.event_type} | TRADES={self.total_trades} | "
            f"WITH_REGIME={self.trades_with_regime} | MISSING={self.trades_missing_regime}"
        )
