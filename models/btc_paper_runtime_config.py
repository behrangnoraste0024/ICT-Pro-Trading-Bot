from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BTCPaperRuntimeConfig:
    schema_version: str = "1.0"
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    exchange: str = "binance"
    strategy_profile: str = "balanced_smc_decision_065"
    sample_scope: str = "required_full"
    primary_timeframe: str = "15m"
    confirmation_timeframe: str = "1h"
    enabled: bool = False
    paper_execution_enabled: bool = False
    live_trading_enabled: bool = False
    order_submission_enabled: bool = False
    dry_run: bool = True
    kill_switch_enabled: bool = True
    account_currency: str = "USDT"
    starting_equity: float = 10000.0
    risk_per_trade_pct: float = 0.005
    max_risk_per_trade_pct: float = 0.01
    max_daily_loss_pct: float = 0.02
    max_total_drawdown_pct: float = 0.05
    max_open_positions: int = 1
    max_trades_per_day: int = 3
    min_trade_interval_minutes: int = 15
    max_position_notional_pct: float = 0.25
    min_risk_reward: float = 1.5
    require_stop_loss: bool = True
    require_take_profit: bool = True
    allow_long: bool = True
    allow_short: bool = True
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperRuntimeConfigIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperRuntimeConfigValidationReport:
    schema_version: str = "1.0"
    config_path: str | None = None
    created_at: str | None = None
    status: str = "FAIL"
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BTCPaperRuntimeConfig | None = None
    issues: list[BTCPaperRuntimeConfigIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "config_path": self.config_path,
            "created_at": self.created_at,
            "status": self.status,
            "issue_count": self.issue_count,
            "warning_count": self.warning_count,
            "fail_count": self.fail_count,
            "config": None if self.config is None else self.config.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }
