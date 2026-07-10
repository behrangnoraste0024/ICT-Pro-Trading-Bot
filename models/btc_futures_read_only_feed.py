from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class BTCFuturesReadOnlyFeedStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class BTCFuturesReadOnlyFeedAction(StrEnum):
    VALIDATE = "VALIDATE"
    FETCH_ONCE = "FETCH_ONCE"
    OBSERVE_ONCE = "OBSERVE_ONCE"


class BTCFuturesReadOnlyObservationDecision(StrEnum):
    FUTURES_FEED_OK = "FUTURES_FEED_OK"
    FUTURES_FEED_OK_MARK_PRICE_ONLY = "FUTURES_FEED_OK_MARK_PRICE_ONLY"
    FUTURES_FEED_OK_FUNDING_AVAILABLE = "FUTURES_FEED_OK_FUNDING_AVAILABLE"
    FUTURES_FEED_WARNING = "FUTURES_FEED_WARNING"
    FUTURES_FEED_FAILED = "FUTURES_FEED_FAILED"
    OBSERVATION_FAILED = "OBSERVATION_FAILED"


@dataclass
class BTCFuturesReadOnlyFeedConfig:
    schema_version: str = "1.0"
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    exchange: str = "binance"
    market_type: str = "futures"
    futures_contract_type: str = "USDT_PERPETUAL"
    exchange_symbol: str = "BTCUSDT"
    strategy_profile: str = "balanced_smc_decision_065"
    runtime_config_path: str = "configs/btc_paper_runtime.json"
    monitoring_config_path: str = "configs/btc_paper_monitoring.json"
    runner_config_path: str = "configs/btc_paper_runner.json"
    live_market_feed_config_path: str = "configs/btc_live_market_feed.json"
    paper_account_config_path: str = "configs/btc_paper_account.json"
    primary_timeframe: str = "15m"
    confirmation_timeframe: str = "1h"
    primary_limit: int = 500
    confirmation_limit: int = 500
    closed_candles_only: bool = True
    dry_run_only: bool = True
    feed_enabled: bool = False
    allow_public_futures_market_data_fetch: bool = True
    allow_public_futures_mark_price_fetch: bool = True
    allow_public_futures_funding_fetch: bool = True
    allow_private_api: bool = False
    allow_api_key_usage: bool = False
    allow_trading_api: bool = False
    allow_account_data: bool = False
    allow_balance_fetch: bool = False
    allow_position_fetch: bool = False
    allow_order_submission: bool = False
    allow_order_cancellation: bool = False
    allow_real_position_creation: bool = False
    allow_paper_position_creation: bool = False
    allow_leverage: bool = False
    allow_leverage_simulation: bool = False
    allow_liquidation_modeling: bool = False
    allow_paper_trade_persistence: bool = False
    allow_executable_trade_creation: bool = False
    allow_runner_state_mutation: bool = False
    allow_execution_state_mutation: bool = False
    require_runtime_config_pass: bool = True
    require_monitoring_config_pass: bool = True
    require_runner_config_pass: bool = True
    require_live_market_feed_config_pass: bool = True
    require_paper_account_config_pass: bool = True
    require_kill_switch_enabled: bool = True
    request_timeout_seconds: int = 10
    max_fetch_retries: int = 1
    min_primary_candles: int = 100
    min_confirmation_candles: int = 100
    observation_mode: str = "fetch_once"
    status_export_dir: str = "reports/futures_read_only_feed"
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCFuturesReadOnlyIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCFuturesReadOnlyCandle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCFuturesMarkPrice:
    symbol: str
    mark_price: float
    index_price: float | None = None
    estimated_settle_price: float | None = None
    funding_rate: float | None = None
    next_funding_time: str | None = None
    timestamp: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCFuturesFundingInfo:
    symbol: str
    funding_rate: float | None = None
    funding_time: str | None = None
    next_funding_time: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCFuturesReadOnlyFeedResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    exchange_symbol: str = "BTCUSDT"
    exchange: str = "binance"
    market_type: str = "futures"
    futures_contract_type: str = "USDT_PERPETUAL"
    status: str = BTCFuturesReadOnlyFeedStatus.FAIL.value
    primary_timeframe: str = "15m"
    confirmation_timeframe: str = "1h"
    primary_candles: int = 0
    confirmation_candles: int = 0
    primary_latest_timestamp: str | None = None
    confirmation_latest_timestamp: str | None = None
    primary_latest_close: float | None = None
    confirmation_latest_close: float | None = None
    mark_price: BTCFuturesMarkPrice | None = None
    funding_info: BTCFuturesFundingInfo | None = None
    closed_candles_only: bool = True
    public_futures_market_data_fetch_used: bool = False
    public_futures_mark_price_fetch_used: bool = False
    public_futures_funding_fetch_used: bool = False
    private_api_used: bool = False
    api_key_used: bool = False
    trading_api_used: bool = False
    account_data_used: bool = False
    balance_fetch_used: bool = False
    position_fetch_used: bool = False
    order_submitted: bool = False
    order_cancelled: bool = False
    real_position_created: bool = False
    paper_position_created: bool = False
    leverage_used: bool = False
    leverage_simulation_used: bool = False
    liquidation_modeling_used: bool = False
    executable_trade_created: bool = False
    exchange_connected_for_trading: bool = False
    runner_state_mutated: bool = False
    execution_state_mutated: bool = False
    issues: list[BTCFuturesReadOnlyIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "mark_price": None if self.mark_price is None else self.mark_price.to_dict(),
            "funding_info": None if self.funding_info is None else self.funding_info.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class BTCFuturesReadOnlyObservationResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    exchange_symbol: str = "BTCUSDT"
    exchange: str = "binance"
    market_type: str = "futures"
    futures_contract_type: str = "USDT_PERPETUAL"
    strategy_profile: str = "balanced_smc_decision_065"
    status: str = BTCFuturesReadOnlyFeedStatus.FAIL.value
    decision: str = BTCFuturesReadOnlyObservationDecision.OBSERVATION_FAILED.value
    feed_status: str = BTCFuturesReadOnlyFeedStatus.FAIL.value
    primary_candles: int = 0
    confirmation_candles: int = 0
    primary_latest_timestamp: str | None = None
    confirmation_latest_timestamp: str | None = None
    primary_latest_close: float | None = None
    confirmation_latest_close: float | None = None
    mark_price_value: float | None = None
    funding_rate: float | None = None
    next_funding_time: str | None = None
    reason: str = ""
    dry_run_only: bool = True
    public_futures_market_data_fetch_used: bool = False
    public_futures_mark_price_fetch_used: bool = False
    public_futures_funding_fetch_used: bool = False
    private_api_used: bool = False
    api_key_used: bool = False
    trading_api_used: bool = False
    account_data_used: bool = False
    balance_fetch_used: bool = False
    position_fetch_used: bool = False
    order_submitted: bool = False
    order_cancelled: bool = False
    real_position_created: bool = False
    paper_position_created: bool = False
    leverage_used: bool = False
    leverage_simulation_used: bool = False
    liquidation_modeling_used: bool = False
    executable_trade_created: bool = False
    exchange_connected_for_trading: bool = False
    runner_state_mutated: bool = False
    execution_state_mutated: bool = False
    safety_summary: dict[str, Any] = field(default_factory=dict)
    issues: list[BTCFuturesReadOnlyIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "issues": [issue.to_dict() for issue in self.issues]}


@dataclass
class BTCFuturesReadOnlyValidationReport:
    schema_version: str = "1.0"
    config_path: str | None = None
    created_at: str | None = None
    status: str = BTCFuturesReadOnlyFeedStatus.FAIL.value
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BTCFuturesReadOnlyFeedConfig | None = None
    issues: list[BTCFuturesReadOnlyIssue] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

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
            "diagnostics": dict(self.diagnostics),
        }
