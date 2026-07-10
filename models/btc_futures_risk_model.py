from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class BTCFuturesRiskStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class BTCFuturesRiskAction(StrEnum):
    VALIDATE = "VALIDATE"
    ANALYZE_SCENARIO = "ANALYZE_SCENARIO"
    ANALYZE_LIVE = "ANALYZE_LIVE"
    COMPARE_LEVERAGE = "COMPARE_LEVERAGE"


class BTCFuturesRiskDecision(StrEnum):
    SAFE_SIMULATION = "SAFE_SIMULATION"
    WARNING_LIQUIDATION_DISTANCE = "WARNING_LIQUIDATION_DISTANCE"
    WARNING_FUNDING_COST = "WARNING_FUNDING_COST"
    REJECT_LEVERAGE_NOT_ALLOWED = "REJECT_LEVERAGE_NOT_ALLOWED"
    REJECT_LIQUIDATION_TOO_CLOSE = "REJECT_LIQUIDATION_TOO_CLOSE"
    REJECT_STOP_BEYOND_LIQUIDATION = "REJECT_STOP_BEYOND_LIQUIDATION"
    REJECT_INVALID_RISK_REWARD = "REJECT_INVALID_RISK_REWARD"
    REJECT_MARGIN_LIMIT = "REJECT_MARGIN_LIMIT"
    REJECT_NOTIONAL_LIMIT = "REJECT_NOTIONAL_LIMIT"
    INVALID_SCENARIO = "INVALID_SCENARIO"
    DATA_FETCH_FAILED = "DATA_FETCH_FAILED"
    MODEL_FAILED = "MODEL_FAILED"


class BTCFuturesPositionSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class BTCFuturesRiskConfig:
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
    paper_account_config_path: str = "configs/btc_paper_account.json"
    risk_model_enabled: bool = False
    simulation_only: bool = True
    dry_run_only: bool = True
    model_name: str = "simplified_isolated_linear_v1"
    model_accuracy: str = "APPROXIMATE_CONSERVATIVE"
    exchange_exact_liquidation: bool = False
    margin_mode: str = "isolated"
    position_mode: str = "one_way"
    allowed_leverage: list[int] = field(default_factory=lambda: [1, 2, 3, 5])
    default_leverage: int = 2
    max_leverage: int = 5
    default_scenario_side: str = "LONG"
    default_notional: float = 1000.0
    default_stop_loss_distance_pct: float = 2.0
    default_take_profit_distance_pct: float = 3.0
    maintenance_margin_rate: float = 0.004
    liquidation_fee_reserve_rate: float = 0.002
    additional_safety_buffer_rate: float = 0.005
    min_liquidation_distance_pct: float = 5.0
    warning_liquidation_distance_pct: float = 10.0
    max_initial_margin_pct_of_account_equity: float = 20.0
    max_notional_pct_of_account_equity: float = 100.0
    allow_public_futures_market_data_fetch: bool = True
    allow_public_mark_price_fetch: bool = True
    allow_public_funding_fetch: bool = True
    allow_leverage_simulation: bool = True
    allow_liquidation_modeling: bool = True
    allow_margin_calculation: bool = True
    allow_funding_estimation: bool = True
    allow_scenario_comparison: bool = True
    allow_real_leverage_change: bool = False
    allow_exchange_margin_mode_change: bool = False
    allow_private_api: bool = False
    allow_api_key_usage: bool = False
    allow_trading_api: bool = False
    allow_account_data: bool = False
    allow_balance_fetch: bool = False
    allow_position_fetch: bool = False
    allow_order_submission: bool = False
    allow_order_cancellation: bool = False
    allow_real_position_creation: bool = False
    allow_paper_futures_position_creation: bool = False
    allow_paper_trade_persistence: bool = False
    allow_executable_trade_creation: bool = False
    allow_paper_account_state_mutation: bool = False
    allow_runner_state_mutation: bool = False
    allow_execution_state_mutation: bool = False
    require_runtime_config_pass: bool = True
    require_monitoring_config_pass: bool = True
    require_runner_config_pass: bool = True
    require_futures_feed_config_pass: bool = True
    require_paper_account_config_pass: bool = True
    require_kill_switch_enabled: bool = True
    funding_periods_to_estimate: int = 3
    report_export_dir: str = "reports/futures_risk_model"
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCFuturesRiskIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCFuturesRiskScenarioInput:
    side: str
    entry_price: float
    mark_price: float
    stop_loss: float
    take_profit: float
    notional_value: float
    leverage: int
    account_equity: float
    funding_rate: float | None = None
    funding_periods: int = 3
    source: str = "manual"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCFuturesRiskCalculation:
    quantity: float
    notional_value: float
    leverage: int
    initial_margin: float
    initial_margin_pct_of_equity: float
    maintenance_margin_at_mark: float
    liquidation_fee_reserve_at_mark: float
    effective_maintenance_rate: float
    estimated_liquidation_price: float
    bankruptcy_price_estimate: float | None
    liquidation_distance_value: float
    liquidation_distance_pct: float
    stop_distance_value: float
    stop_distance_pct: float
    take_profit_distance_value: float
    take_profit_distance_pct: float
    risk_amount_to_stop: float
    reward_amount_to_take_profit: float
    risk_reward_ratio: float
    unrealized_pnl_at_mark: float
    equity_at_mark: float
    margin_ratio: float | None
    funding_payment_per_period: float | None
    total_funding_estimate: float | None
    stop_before_liquidation: bool
    liquidation_buffer_after_stop_pct: float | None
    model_accuracy: str
    assumptions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCFuturesRiskResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    exchange_symbol: str = "BTCUSDT"
    market_type: str = "futures"
    futures_contract_type: str = "USDT_PERPETUAL"
    strategy_profile: str = "balanced_smc_decision_065"
    status: str = BTCFuturesRiskStatus.FAIL.value
    decision: str = BTCFuturesRiskDecision.MODEL_FAILED.value
    reason: str = ""
    scenario: BTCFuturesRiskScenarioInput | None = None
    calculation: BTCFuturesRiskCalculation | None = None
    dry_run_only: bool = True
    simulation_only: bool = True
    model_name: str = "simplified_isolated_linear_v1"
    model_accuracy: str = "APPROXIMATE_CONSERVATIVE"
    exchange_exact_liquidation: bool = False
    public_market_data_used: bool = False
    private_api_used: bool = False
    api_key_used: bool = False
    trading_api_used: bool = False
    account_data_used: bool = False
    balance_fetch_used: bool = False
    position_fetch_used: bool = False
    exchange_leverage_changed: bool = False
    exchange_margin_mode_changed: bool = False
    order_submitted: bool = False
    order_cancelled: bool = False
    real_position_created: bool = False
    paper_futures_position_created: bool = False
    paper_trade_persisted: bool = False
    executable_trade_created: bool = False
    paper_account_state_mutated: bool = False
    runner_state_mutated: bool = False
    execution_state_mutated: bool = False
    issues: list[BTCFuturesRiskIssue] = field(default_factory=list)
    safety_summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "scenario": None if self.scenario is None else self.scenario.to_dict(),
            "calculation": None if self.calculation is None else self.calculation.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class BTCFuturesLeverageComparisonRow:
    leverage: int
    status: str
    decision: str
    initial_margin: float | None
    estimated_liquidation_price: float | None
    liquidation_distance_pct: float | None
    margin_ratio: float | None
    stop_before_liquidation: bool | None
    total_funding_estimate: float | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCFuturesLeverageComparisonResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    symbol: str = "BTC/USDT"
    side: str = "LONG"
    entry_price: float = 0.0
    mark_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    notional_value: float = 0.0
    account_equity: float = 0.0
    status: str = BTCFuturesRiskStatus.FAIL.value
    safest_leverage: int | None = None
    highest_accepted_leverage: int | None = None
    rows: list[BTCFuturesLeverageComparisonRow] = field(default_factory=list)
    issues: list[BTCFuturesRiskIssue] = field(default_factory=list)
    safety_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "rows": [row.to_dict() for row in self.rows], "issues": [issue.to_dict() for issue in self.issues]}


@dataclass
class BTCFuturesRiskValidationReport:
    schema_version: str = "1.0"
    config_path: str | None = None
    created_at: str | None = None
    status: str = BTCFuturesRiskStatus.FAIL.value
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BTCFuturesRiskConfig | None = None
    issues: list[BTCFuturesRiskIssue] = field(default_factory=list)
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
