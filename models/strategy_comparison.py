from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class StrategyConfigSpec:
    name: str
    dealing_range_mode: str
    exit_mode: str
    min_risk_reward: float
    direction_mode: str = "all"
    auto_trend_fallback: str = "all"
    regime_mode: str = "rolling_return"
    regime_lookback: int = 200
    regime_threshold_pct: float = 0.0
    regime_fallback: str = "all"
    direction_quality_mode: str = "off"
    strict_long_preset: str = "none"
    strict_long_require_regime_known: bool = False
    strict_long_block_unknown_regime: bool = False
    strict_long_require_regime_bullish: bool = False
    strict_long_require_displacement: bool = False
    strict_long_min_setup_score: int | None = None
    strict_short_require_regime_known: bool = False
    strict_short_block_unknown_regime: bool = False
    strict_short_require_regime_bearish: bool = False
    strict_short_require_displacement: bool = False
    strict_short_min_setup_score: int | None = None
    strategy_profile: str = "default"
    cost_model: str = "off"
    commission_pct: float = 0.0
    slippage_pct: float = 0.0
    spread_pct: float = 0.0
    event_type: str = "STRATEGY_CONFIG_SPEC"

    def __str__(self) -> str:
        value = f"{self.dealing_range_mode}|{self.exit_mode}|min_rr={self.min_risk_reward}|dir={self.direction_mode}"
        if self.direction_mode == "auto_trend":
            value = f"{value}|trend_fallback={self.auto_trend_fallback}"
        if self.direction_mode == "regime_trend":
            value = (
                f"{value}|regime={self.regime_mode}|lookback={self.regime_lookback}|"
                f"thr={self.regime_threshold_pct}|regime_fb={self.regime_fallback}"
            )
        if self.direction_quality_mode != "off":
            value = f"{value}|dq={self.direction_quality_mode}|long_preset={self.strict_long_preset}"
        return value


@dataclass
class StrategyComparisonRow:
    strategy_name: str
    rank: int | None = None
    dealing_range_mode: str = "current_external"
    exit_mode: str = "original"
    min_risk_reward: float = 2.0
    direction_mode: str = "all"
    auto_trend_fallback: str = "all"
    regime_mode: str = "rolling_return"
    regime_lookback: int = 200
    regime_threshold_pct: float = 0.0
    regime_fallback: str = "all"
    strategy_profile: str = "default"
    cost_model: str = "off"
    commission_pct: float = 0.0
    slippage_pct: float = 0.0
    spread_pct: float = 0.0
    direction_quality_mode: str = "off"
    strict_long_preset: str = "none"
    total_windows: int = 0
    processed_windows: int = 0
    failed_windows: int = 0
    opened_trades: int = 0
    duplicate_signals_skipped: int = 0
    total_trades: int = 0
    closed_trades: int = 0
    open_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float | None = None
    net_pnl: float = 0.0
    gross_net_pnl: float = 0.0
    total_cost: float = 0.0
    net_pnl_after_costs: float = 0.0
    average_pnl: float | None = None
    max_drawdown: float = 0.0
    average_rr: float | None = None
    average_setup_score: float | None = None
    long_count: int = 0
    long_pnl: float = 0.0
    short_count: int = 0
    short_pnl: float = 0.0
    profit_factor: float | None = None
    average_win: float | None = None
    average_loss: float | None = None
    largest_win: float | None = None
    largest_loss: float | None = None
    fast_losses: int = 0
    no_followthrough_losses: int = 0
    high_rr_losses: int = 0
    next_candle_continuation: int = 0
    next_candle_rejection: int = 0
    long_in_bearish_count: int = 0
    long_in_bearish_pnl: float = 0.0
    short_in_bullish_count: int = 0
    short_in_bullish_pnl: float = 0.0
    elapsed_seconds: float | None = None
    event_type: str = "STRATEGY_COMPARISON_ROW"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:
        rank = f"#{self.rank}" if self.rank is not None else "#?"
        return f"{rank} {self.strategy_name} | trades={self.total_trades} | pnl={self.net_pnl}"


@dataclass
class StrategyComparisonReport:
    fixture: str
    min_candles: int
    strategies: list[StrategyComparisonRow] = field(default_factory=list)
    best_by_net_pnl: str | None = None
    best_by_average_pnl: str | None = None
    best_by_win_rate: str | None = None
    best_by_profit_factor: str | None = None
    best_by_drawdown: str | None = None
    best_by_net_pnl_after_costs: str | None = None
    event_type: str = "STRATEGY_COMPARISON_REPORT"

    def sorted_by(self, metric: str, descending: bool = True) -> list[StrategyComparisonRow]:
        return sorted(
            self.strategies,
            key=lambda row: self._sort_value(row, metric, descending),
            reverse=descending,
        )

    def best_row(self, metric: str, prefer_lower: bool = False) -> StrategyComparisonRow | None:
        rows = [row for row in self.strategies if getattr(row, metric, None) is not None]
        if not rows:
            return None
        return min(rows, key=lambda row: getattr(row, metric)) if prefer_lower else max(rows, key=lambda row: getattr(row, metric))

    def populate_best_fields(self) -> None:
        self.best_by_net_pnl = self._best_name("net_pnl")
        self.best_by_average_pnl = self._best_name("average_pnl")
        self.best_by_win_rate = self._best_name("win_rate")
        self.best_by_profit_factor = self._best_name("profit_factor")
        self.best_by_drawdown = self._best_name("max_drawdown", prefer_lower=True)
        self.best_by_net_pnl_after_costs = self._best_name("net_pnl_after_costs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture": self.fixture,
            "min_candles": self.min_candles,
            "strategies": [row.to_dict() for row in self.strategies],
            "best_by_net_pnl": self.best_by_net_pnl,
            "best_by_average_pnl": self.best_by_average_pnl,
            "best_by_win_rate": self.best_by_win_rate,
            "best_by_profit_factor": self.best_by_profit_factor,
            "best_by_drawdown": self.best_by_drawdown,
            "best_by_net_pnl_after_costs": self.best_by_net_pnl_after_costs,
            "event_type": self.event_type,
        }

    def _best_name(self, metric: str, prefer_lower: bool = False) -> str | None:
        row = self.best_row(metric, prefer_lower=prefer_lower)
        return None if row is None else row.strategy_name

    def _sort_value(self, row: StrategyComparisonRow, metric: str, descending: bool) -> float:
        value = getattr(row, metric)
        if value is None:
            return float("-inf") if descending else float("inf")
        return float(value)
