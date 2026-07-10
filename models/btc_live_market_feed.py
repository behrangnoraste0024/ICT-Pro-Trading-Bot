from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class BTCLiveMarketFeedStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class BTCLiveMarketFeedAction(StrEnum):
    VALIDATE = "VALIDATE"
    FETCH_ONCE = "FETCH_ONCE"
    OBSERVE_ONCE = "OBSERVE_ONCE"


class BTCLiveMarketObservationDecision(StrEnum):
    FEED_OK = "FEED_OK"
    FEED_OK_SIGNAL_WARNING = "FEED_OK_SIGNAL_WARNING"
    FEED_OK_SIGNAL_APPROVED = "FEED_OK_SIGNAL_APPROVED"
    FEED_OK_CANDIDATE_REJECTED = "FEED_OK_CANDIDATE_REJECTED"
    FEED_OK_CANDIDATE_CREATED_DRY_RUN = "FEED_OK_CANDIDATE_CREATED_DRY_RUN"
    FEED_FAILED = "FEED_FAILED"
    OBSERVATION_FAILED = "OBSERVATION_FAILED"


@dataclass
class BTCLiveMarketFeedConfig:
    schema_version: str = "1.0"
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    exchange: str = "binance"
    market_type: str = "spot"
    strategy_profile: str = "balanced_smc_decision_065"
    runtime_config_path: str = "configs/btc_paper_runtime.json"
    monitoring_config_path: str = "configs/btc_paper_monitoring.json"
    runner_config_path: str = "configs/btc_paper_runner.json"
    signal_evaluation_config_path: str = "configs/btc_paper_signal_evaluation.json"
    trade_candidate_config_path: str = "configs/btc_paper_trade_candidate.json"
    candidate_journal_config_path: str = "configs/btc_paper_candidate_journal.json"
    forward_test_config_path: str = "configs/btc_forward_test_loop.json"
    primary_timeframe: str = "15m"
    confirmation_timeframe: str = "1h"
    primary_limit: int = 500
    confirmation_limit: int = 500
    closed_candles_only: bool = True
    dry_run_only: bool = True
    feed_enabled: bool = False
    allow_public_market_data_fetch: bool = True
    allow_private_api: bool = False
    allow_api_key_usage: bool = False
    allow_trading_api: bool = False
    allow_account_data: bool = False
    allow_balance_fetch: bool = False
    allow_position_fetch: bool = False
    allow_order_submission: bool = False
    allow_order_cancellation: bool = False
    allow_position_creation: bool = False
    allow_paper_trade_persistence: bool = False
    allow_executable_trade_creation: bool = False
    allow_state_mutation: bool = False
    allow_journal_write: bool = True
    require_runtime_config_pass: bool = True
    require_monitoring_config_pass: bool = True
    require_runner_config_pass: bool = True
    require_signal_config_pass: bool = True
    require_trade_candidate_config_pass: bool = True
    require_candidate_journal_config_pass: bool = True
    require_kill_switch_enabled: bool = True
    request_timeout_seconds: int = 10
    max_fetch_retries: int = 1
    min_primary_candles: int = 100
    min_confirmation_candles: int = 100
    observation_mode: str = "fetch_once"
    status_export_dir: str = "reports/live_market_feed"
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCLiveMarketFeedIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCLiveMarketCandle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCLiveMarketFeedResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    exchange: str = "binance"
    market_type: str = "spot"
    status: str = BTCLiveMarketFeedStatus.FAIL.value
    primary_timeframe: str = "15m"
    confirmation_timeframe: str = "1h"
    primary_candles: int = 0
    confirmation_candles: int = 0
    primary_latest_timestamp: str | None = None
    confirmation_latest_timestamp: str | None = None
    primary_latest_close: float | None = None
    confirmation_latest_close: float | None = None
    closed_candles_only: bool = True
    public_market_data_fetch_used: bool = False
    private_api_used: bool = False
    api_key_used: bool = False
    trading_api_used: bool = False
    account_data_used: bool = False
    balance_fetch_used: bool = False
    position_fetch_used: bool = False
    order_submitted: bool = False
    order_cancelled: bool = False
    exchange_connected_for_trading: bool = False
    issues: list[BTCLiveMarketFeedIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "issues": [issue.to_dict() for issue in self.issues]}


@dataclass
class BTCLiveMarketObservationResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    exchange: str = "binance"
    market_type: str = "spot"
    strategy_profile: str = "balanced_smc_decision_065"
    status: str = BTCLiveMarketFeedStatus.FAIL.value
    decision: str = BTCLiveMarketObservationDecision.OBSERVATION_FAILED.value
    feed_status: str = BTCLiveMarketFeedStatus.FAIL.value
    signal_status: str | None = None
    signal_decision: str | None = None
    signal_score: float | None = None
    signal_threshold: float | None = None
    candidate_status: str | None = None
    candidate_decision: str | None = None
    candidate_created: bool = False
    journal_entry_written: bool = False
    journal_entry_id: str | None = None
    reason: str = ""
    primary_candles: int = 0
    confirmation_candles: int = 0
    primary_latest_timestamp: str | None = None
    confirmation_latest_timestamp: str | None = None
    dry_run_only: bool = True
    public_market_data_fetch_used: bool = False
    private_api_used: bool = False
    api_key_used: bool = False
    trading_api_used: bool = False
    account_data_used: bool = False
    balance_fetch_used: bool = False
    position_fetch_used: bool = False
    executable_trade_created: bool = False
    paper_trade_persisted: bool = False
    position_created: bool = False
    order_submitted: bool = False
    order_cancelled: bool = False
    exchange_connected_for_trading: bool = False
    state_mutated: bool = False
    safety_summary: dict[str, Any] = field(default_factory=dict)
    issues: list[BTCLiveMarketFeedIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "issues": [issue.to_dict() for issue in self.issues]}


@dataclass
class BTCLiveMarketFeedValidationReport:
    schema_version: str = "1.0"
    config_path: str | None = None
    created_at: str | None = None
    status: str = BTCLiveMarketFeedStatus.FAIL.value
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BTCLiveMarketFeedConfig | None = None
    issues: list[BTCLiveMarketFeedIssue] = field(default_factory=list)
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
