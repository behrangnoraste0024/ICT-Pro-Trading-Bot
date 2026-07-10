from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class BTCPaperAccountStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class BTCPaperAccountAction(StrEnum):
    VALIDATE = "VALIDATE"
    STATUS = "STATUS"
    INITIALIZE = "INITIALIZE"
    RESET = "RESET"
    SIMULATE_LIVE_OBSERVATION = "SIMULATE_LIVE_OBSERVATION"
    MARK_TO_MARKET = "MARK_TO_MARKET"
    LEDGER_SUMMARY = "LEDGER_SUMMARY"


class BTCPaperAccountDecision(StrEnum):
    ACCOUNT_READY = "ACCOUNT_READY"
    ACCOUNT_INITIALIZED = "ACCOUNT_INITIALIZED"
    NO_ACTION_SIGNAL_NOT_APPROVED = "NO_ACTION_SIGNAL_NOT_APPROVED"
    NO_ACTION_NO_CANDIDATE = "NO_ACTION_NO_CANDIDATE"
    VIRTUAL_ORDER_CREATED = "VIRTUAL_ORDER_CREATED"
    VIRTUAL_POSITION_OPENED = "VIRTUAL_POSITION_OPENED"
    VIRTUAL_POSITION_UPDATED = "VIRTUAL_POSITION_UPDATED"
    VIRTUAL_TRADE_REJECTED_RISK = "VIRTUAL_TRADE_REJECTED_RISK"
    VIRTUAL_TRADE_REJECTED_LIMIT = "VIRTUAL_TRADE_REJECTED_LIMIT"
    MARK_TO_MARKET_UPDATED = "MARK_TO_MARKET_UPDATED"
    STATE_MISSING = "STATE_MISSING"
    ACTION_FAILED = "ACTION_FAILED"


@dataclass
class BTCPaperAccountConfig:
    schema_version: str = "1.0"
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    quote_currency: str = "USDT"
    strategy_profile: str = "balanced_smc_decision_065"
    runtime_config_path: str = "configs/btc_paper_runtime.json"
    monitoring_config_path: str = "configs/btc_paper_monitoring.json"
    runner_config_path: str = "configs/btc_paper_runner.json"
    signal_evaluation_config_path: str = "configs/btc_paper_signal_evaluation.json"
    trade_candidate_config_path: str = "configs/btc_paper_trade_candidate.json"
    candidate_journal_config_path: str = "configs/btc_paper_candidate_journal.json"
    forward_test_config_path: str = "configs/btc_forward_test_loop.json"
    live_market_feed_config_path: str = "configs/btc_live_market_feed.json"
    paper_account_enabled: bool = False
    simulation_only: bool = True
    dry_run_only: bool = True
    initial_balance: float = 10000.0
    risk_per_trade_pct: float = 0.5
    max_risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 2.0
    max_drawdown_pct: float = 5.0
    max_open_virtual_positions: int = 1
    max_virtual_trades_per_day: int = 3
    min_risk_reward: float = 1.5
    require_stop_loss: bool = True
    require_take_profit: bool = True
    allow_local_paper_state_write: bool = True
    allow_local_paper_ledger_write: bool = True
    allow_virtual_order_creation: bool = True
    allow_virtual_position_creation: bool = True
    allow_virtual_pnl_calculation: bool = True
    allow_public_market_data_fetch: bool = True
    allow_private_api: bool = False
    allow_api_key_usage: bool = False
    allow_trading_api: bool = False
    allow_account_data: bool = False
    allow_balance_fetch: bool = False
    allow_position_fetch: bool = False
    allow_real_order_submission: bool = False
    allow_order_cancellation: bool = False
    allow_real_position_creation: bool = False
    allow_exchange_connection_for_trading: bool = False
    allow_executable_trade_creation: bool = False
    allow_runner_state_mutation: bool = False
    allow_execution_state_mutation: bool = False
    require_runtime_config_pass: bool = True
    require_monitoring_config_pass: bool = True
    require_runner_config_pass: bool = True
    require_signal_config_pass: bool = True
    require_trade_candidate_config_pass: bool = True
    require_candidate_journal_config_pass: bool = True
    require_forward_test_config_pass: bool = True
    require_live_market_feed_config_pass: bool = True
    require_kill_switch_enabled: bool = True
    fill_model: str = "virtual_next_close"
    slippage_rate: float = 0.0002
    fee_rate: float = 0.0004
    state_path: str = "reports/paper_account/btc_paper_account_state.json"
    ledger_path: str = "reports/paper_account/btc_paper_account_ledger.jsonl"
    report_export_dir: str = "reports/paper_account"
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperAccountIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperAccountVirtualOrder:
    order_id: str
    created_at: str
    symbol: str
    side: str
    order_type: str
    status: str
    quantity: float
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    risk_amount: float
    fee_estimate: float
    slippage_estimate: float
    source: str
    candidate_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperAccountVirtualPosition:
    position_id: str
    opened_at: str
    updated_at: str
    symbol: str
    side: str
    status: str
    quantity: float
    entry_price: float
    mark_price: float
    stop_loss: float | None
    take_profit: float | None
    notional_value: float
    risk_amount: float
    unrealized_pnl: float
    realized_pnl: float
    fees_paid: float
    source_order_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperAccountLedgerEntry:
    entry_id: str
    created_at: str
    entry_type: str
    symbol: str
    decision: str
    balance_before: float
    balance_after: float
    equity_before: float
    equity_after: float
    realized_pnl_delta: float
    unrealized_pnl_delta: float
    virtual_order_id: str | None
    virtual_position_id: str | None
    reason: str
    safety_summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperAccountState:
    schema_version: str = "1.0"
    created_at: str | None = None
    updated_at: str | None = None
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    quote_currency: str = "USDT"
    strategy_profile: str = "balanced_smc_decision_065"
    initial_balance: float = 10000.0
    cash_balance: float = 10000.0
    equity: float = 10000.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_fees: float = 0.0
    total_slippage: float = 0.0
    open_positions: list[BTCPaperAccountVirtualPosition] = field(default_factory=list)
    closed_positions: list[BTCPaperAccountVirtualPosition] = field(default_factory=list)
    pending_orders: list[BTCPaperAccountVirtualOrder] = field(default_factory=list)
    filled_orders: list[BTCPaperAccountVirtualOrder] = field(default_factory=list)
    total_virtual_orders: int = 0
    total_virtual_positions_opened: int = 0
    total_no_action_events: int = 0
    total_risk_rejections: int = 0
    last_mark_price: float | None = None
    last_mark_at: str | None = None
    dry_run_only: bool = True
    private_api_used: bool = False
    api_key_used: bool = False
    trading_api_used: bool = False
    account_data_used: bool = False
    balance_fetch_used: bool = False
    position_fetch_used: bool = False
    real_order_submitted: bool = False
    order_cancelled: bool = False
    real_position_created: bool = False
    exchange_connected_for_trading: bool = False
    executable_trade_created: bool = False
    runner_state_mutated: bool = False
    execution_state_mutated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "open_positions": [position.to_dict() for position in self.open_positions],
            "closed_positions": [position.to_dict() for position in self.closed_positions],
            "pending_orders": [order.to_dict() for order in self.pending_orders],
            "filled_orders": [order.to_dict() for order in self.filled_orders],
        }


@dataclass
class BTCPaperAccountValidationReport:
    schema_version: str = "1.0"
    config_path: str | None = None
    created_at: str | None = None
    status: str = BTCPaperAccountStatus.FAIL.value
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BTCPaperAccountConfig | None = None
    issues: list[BTCPaperAccountIssue] = field(default_factory=list)
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
class BTCPaperAccountActionResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    action: str = BTCPaperAccountAction.STATUS.value
    status: str = BTCPaperAccountStatus.FAIL.value
    decision: str = BTCPaperAccountDecision.ACTION_FAILED.value
    config_status: str = BTCPaperAccountStatus.FAIL.value
    state_path: str = ""
    ledger_path: str = ""
    state_exists: bool = False
    account_state: BTCPaperAccountState | None = None
    ledger_entry: BTCPaperAccountLedgerEntry | None = None
    virtual_order_created: bool = False
    virtual_position_created: bool = False
    no_action_recorded: bool = False
    mark_to_market_updated: bool = False
    reason: str = ""
    safety_summary: dict[str, Any] = field(default_factory=dict)
    issues: list[BTCPaperAccountIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "account_state": None if self.account_state is None else self.account_state.to_dict(),
            "ledger_entry": None if self.ledger_entry is None else self.ledger_entry.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class BTCPaperAccountLedgerSummary:
    schema_version: str = "1.0"
    created_at: str | None = None
    ledger_path: str = ""
    status: str = BTCPaperAccountStatus.WARNING.value
    entries_read: int = 0
    account_initialized: int = 0
    no_action: int = 0
    virtual_orders: int = 0
    virtual_positions: int = 0
    mark_to_market: int = 0
    risk_rejections: int = 0
    errors: int = 0
    latest_entry_at: str | None = None
    entries: list[BTCPaperAccountLedgerEntry] = field(default_factory=list)
    issues: list[BTCPaperAccountIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "entries": [entry.to_dict() for entry in self.entries], "issues": [issue.to_dict() for issue in self.issues]}
