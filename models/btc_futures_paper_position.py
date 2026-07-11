from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
from enum import StrEnum
from typing import Any


class BTCFuturesPaperStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class BTCFuturesPaperAccountStatus(StrEnum):
    UNINITIALIZED = "UNINITIALIZED"
    READY = "READY"
    BLOCKED = "BLOCKED"


class BTCFuturesPaperPositionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    STOPPED_OUT = "STOPPED_OUT"
    TAKE_PROFIT = "TAKE_PROFIT"
    LIQUIDATED_SIMULATED = "LIQUIDATED_SIMULATED"


class BTCFuturesPaperSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class BTCFuturesPaperAction(StrEnum):
    VALIDATE = "VALIDATE"
    INITIALIZE = "INITIALIZE"
    STATUS = "STATUS"
    OPEN_POSITION = "OPEN_POSITION"
    MARK_TO_MARKET = "MARK_TO_MARKET"
    MARK_TO_MARKET_LIVE = "MARK_TO_MARKET_LIVE"
    APPLY_FUNDING = "APPLY_FUNDING"
    CLOSE_POSITION = "CLOSE_POSITION"
    LEDGER_SUMMARY = "LEDGER_SUMMARY"
    RESET = "RESET"
    SIMULATE_LIFECYCLE = "SIMULATE_LIFECYCLE"


class BTCFuturesPaperDecision(StrEnum):
    CONFIG_VALID = "CONFIG_VALID"
    STATE_INITIALIZED = "STATE_INITIALIZED"
    STATE_ALREADY_INITIALIZED = "STATE_ALREADY_INITIALIZED"
    STATE_MISSING = "STATE_MISSING"
    STATE_CORRUPT = "STATE_CORRUPT"
    ACCOUNT_READY = "ACCOUNT_READY"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_OPEN_REJECTED = "POSITION_OPEN_REJECTED"
    POSITION_ALREADY_OPEN = "POSITION_ALREADY_OPEN"
    NO_OPEN_POSITION = "NO_OPEN_POSITION"
    MARK_UPDATED = "MARK_UPDATED"
    POSITION_CLOSED_STOP_LOSS = "POSITION_CLOSED_STOP_LOSS"
    POSITION_CLOSED_TAKE_PROFIT = "POSITION_CLOSED_TAKE_PROFIT"
    POSITION_LIQUIDATED_SIMULATED = "POSITION_LIQUIDATED_SIMULATED"
    POSITION_CLOSED_MANUAL = "POSITION_CLOSED_MANUAL"
    FUNDING_APPLIED = "FUNDING_APPLIED"
    LIVE_MARK_FETCH_FAILED = "LIVE_MARK_FETCH_FAILED"
    DAILY_LOSS_LIMIT_REACHED = "DAILY_LOSS_LIMIT_REACHED"
    DRAWDOWN_LIMIT_REACHED = "DRAWDOWN_LIMIT_REACHED"
    MAX_TRADES_REACHED = "MAX_TRADES_REACHED"
    INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN"
    RISK_MODEL_REJECTED = "RISK_MODEL_REJECTED"
    LEVERAGE_NOT_ALLOWED = "LEVERAGE_NOT_ALLOWED"
    DUPLICATE_ACTION = "DUPLICATE_ACTION"
    RESET_COMPLETED = "RESET_COMPLETED"
    OPERATION_FAILED = "OPERATION_FAILED"


@dataclass
class BTCFuturesPaperConfig:
    schema_version: str = "1.0"
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    exchange_symbol: str = "BTCUSDT"
    exchange: str = "binance"
    market_type: str = "futures"
    futures_contract_type: str = "USDT_PERPETUAL"
    strategy_profile: str = "balanced_smc_decision_065"
    runtime_config_path: str = "configs/btc_paper_runtime.json"
    monitoring_config_path: str = "configs/btc_paper_monitoring.json"
    runner_config_path: str = "configs/btc_paper_runner.json"
    futures_read_only_feed_config_path: str = "configs/btc_futures_read_only_feed.json"
    futures_risk_model_config_path: str = "configs/btc_futures_risk_model.json"
    spot_paper_account_config_path: str = "configs/btc_paper_account.json"
    position_simulation_enabled: bool = False
    simulation_only: bool = True
    dry_run_only: bool = True
    margin_mode: str = "isolated"
    position_mode: str = "one_way"
    max_open_positions: int = 1
    allowed_leverage: list[int] = field(default_factory=lambda: [1, 2, 3, 5])
    default_leverage: int = 2
    max_leverage: int = 5
    initial_account_balance: float = 10000.0
    account_currency: str = "USDT"
    default_notional: float = 1000.0
    min_notional: float = 10.0
    max_notional_pct_of_equity: float = 100.0
    max_initial_margin_pct_of_equity: float = 20.0
    minimum_risk_reward: float = 1.5
    max_daily_realized_loss_pct: float = 2.0
    max_account_drawdown_pct: float = 5.0
    max_trades_per_day: int = 3
    taker_fee_rate: float = 0.0004
    liquidation_fee_rate: float = 0.002
    default_funding_periods: int = 1
    require_risk_model_pass: bool = True
    require_stop_before_liquidation: bool = True
    require_stop_loss: bool = True
    require_take_profit: bool = True
    auto_close_on_stop_loss: bool = True
    auto_close_on_take_profit: bool = True
    auto_close_on_simulated_liquidation: bool = True
    liquidation_trigger_precedence: bool = True
    closed_position_retention_in_state: int = 0
    allow_public_mark_price_fetch: bool = True
    allow_public_funding_fetch: bool = True
    allow_local_futures_state_write: bool = True
    allow_local_futures_ledger_write: bool = True
    allow_local_virtual_order_creation: bool = True
    allow_local_paper_futures_position_creation: bool = True
    allow_local_mark_to_market: bool = True
    allow_local_funding_application: bool = True
    allow_local_position_close: bool = True
    allow_local_simulated_liquidation: bool = True
    allow_local_futures_state_reset: bool = True
    allow_private_api: bool = False
    allow_api_key_usage: bool = False
    allow_trading_api: bool = False
    allow_account_data: bool = False
    allow_balance_fetch: bool = False
    allow_position_fetch: bool = False
    allow_real_order_submission: bool = False
    allow_order_cancellation: bool = False
    allow_real_position_creation: bool = False
    allow_exchange_paper_position_creation: bool = False
    allow_testnet_order_submission: bool = False
    allow_exchange_leverage_change: bool = False
    allow_exchange_margin_mode_change: bool = False
    allow_spot_paper_account_state_mutation: bool = False
    allow_runner_state_mutation: bool = False
    allow_execution_state_mutation: bool = False
    allow_exchange_state_mutation: bool = False
    require_runtime_config_pass: bool = True
    require_monitoring_config_pass: bool = True
    require_runner_config_pass: bool = True
    require_futures_feed_config_pass: bool = True
    require_futures_risk_model_config_pass: bool = True
    require_spot_paper_account_config_pass: bool = True
    require_kill_switch_enabled: bool = True
    state_path: str = "reports/futures_paper_position/btc_futures_paper_state.json"
    ledger_path: str = "reports/futures_paper_position/btc_futures_paper_ledger.jsonl"
    report_export_dir: str = "reports/futures_paper_position"
    lock_path: str = "reports/futures_paper_position/btc_futures_paper_state.lock"
    state_lock_timeout_seconds: int = 3
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCFuturesPaperIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCFuturesPaperPosition:
    position_id: str
    virtual_order_id: str
    symbol: str
    side: str
    status: str
    leverage: int
    quantity: float
    entry_price: float
    mark_price: float
    stop_loss: float
    take_profit: float
    notional_at_entry: float
    current_notional: float
    initial_margin: float
    maintenance_margin: float
    liquidation_fee_reserve: float
    estimated_liquidation_price: float
    liquidation_distance_pct: float
    unrealized_pnl: float
    realized_pnl: float
    funding_pnl: float
    entry_fee: float
    exit_fee: float
    total_fees: float
    risk_reward_ratio: float
    opened_at: str
    updated_at: str
    closed_at: str | None = None
    close_price: float | None = None
    close_reason: str | None = None
    model_accuracy: str = "APPROXIMATE_CONSERVATIVE"
    exchange_exact_liquidation: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCFuturesPaperAccountState:
    schema_version: str
    state_version: int
    account_id: str
    created_at: str
    updated_at: str
    project_scope: str
    symbol: str
    account_currency: str
    account_status: str
    starting_balance: float
    wallet_balance: float
    available_balance: float
    equity: float
    peak_equity: float
    current_drawdown_pct: float
    margin_used: float
    unrealized_pnl: float
    realized_pnl: float
    daily_realized_pnl: float
    funding_pnl: float
    total_fees_paid: float
    open_position: BTCFuturesPaperPosition | None
    opened_positions_count: int
    closed_positions_count: int
    liquidated_positions_count: int
    trades_today: int
    trading_day: str
    last_event_id: str | None
    processed_action_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["open_position"] = None if self.open_position is None else self.open_position.to_dict()
        return data


@dataclass
class BTCFuturesPaperLedgerEntry:
    schema_version: str
    event_id: str
    action_id: str | None
    created_at: str
    event_type: str
    account_id: str
    position_id: str | None
    virtual_order_id: str | None
    side: str | None
    price: float | None
    quantity: float | None
    notional: float | None
    leverage: int | None
    wallet_balance_before: float
    wallet_balance_after: float
    equity_before: float
    equity_after: float
    realized_pnl_delta: float
    unrealized_pnl_after: float
    funding_pnl_delta: float
    fee_delta: float
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCFuturesPaperActionResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    action: str = BTCFuturesPaperAction.STATUS.value
    status: str = BTCFuturesPaperStatus.FAIL.value
    decision: str = BTCFuturesPaperDecision.OPERATION_FAILED.value
    reason: str = ""
    state_path: str = ""
    ledger_path: str = ""
    account_state: BTCFuturesPaperAccountState | None = None
    position: BTCFuturesPaperPosition | None = None
    ledger_entry: BTCFuturesPaperLedgerEntry | None = None
    state_written: bool = False
    ledger_written: bool = False
    local_virtual_order_created: bool = False
    local_paper_futures_position_created: bool = False
    local_position_closed: bool = False
    local_simulated_liquidation_applied: bool = False
    local_funding_applied: bool = False
    public_mark_price_used: bool = False
    public_funding_used: bool = False
    private_api_used: bool = False
    api_key_used: bool = False
    trading_api_used: bool = False
    account_data_used: bool = False
    balance_fetch_used: bool = False
    position_fetch_used: bool = False
    real_order_submitted: bool = False
    order_cancelled: bool = False
    real_position_created: bool = False
    exchange_paper_position_created: bool = False
    testnet_order_submitted: bool = False
    exchange_leverage_changed: bool = False
    exchange_margin_mode_changed: bool = False
    spot_paper_account_state_mutated: bool = False
    runner_state_mutated: bool = False
    execution_state_mutated: bool = False
    exchange_state_mutated: bool = False
    issues: list[BTCFuturesPaperIssue] = field(default_factory=list)
    safety_summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "account_state": None if self.account_state is None else self.account_state.to_dict(),
            "position": None if self.position is None else self.position.to_dict(),
            "ledger_entry": None if self.ledger_entry is None else self.ledger_entry.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class BTCFuturesPaperValidationReport:
    schema_version: str = "1.0"
    config_path: str = ""
    created_at: str | None = None
    status: str = BTCFuturesPaperStatus.FAIL.value
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BTCFuturesPaperConfig | None = None
    issues: list[BTCFuturesPaperIssue] = field(default_factory=list)
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


@dataclass
class BTCFuturesPaperLedgerSummary:
    total_entries: int = 0
    initialized_events: int = 0
    position_opened_events: int = 0
    mark_events: int = 0
    funding_events: int = 0
    manual_close_events: int = 0
    stop_loss_events: int = 0
    take_profit_events: int = 0
    liquidation_events: int = 0
    rejected_events: int = 0
    realized_pnl_total: float = 0.0
    funding_pnl_total: float = 0.0
    fee_total: float = 0.0
    latest_event_at: str | None = None
    latest_event_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def dataclass_from_dict(cls, data: dict[str, Any]):
    if cls is BTCFuturesPaperAccountState:
        payload = dict(data)
        if isinstance(payload.get("open_position"), dict):
            payload["open_position"] = dataclass_from_dict(BTCFuturesPaperPosition, payload["open_position"])
        return cls(**{field.name: payload.get(field.name) for field in fields(cls)})
    if is_dataclass(cls):
        return cls(**{field.name: data.get(field.name) for field in fields(cls)})
    raise TypeError(f"{cls} is not a dataclass")
