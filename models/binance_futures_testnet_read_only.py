from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class BinanceFuturesTestnetReadOnlyStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class BinanceFuturesTestnetReadOnlyAction(StrEnum):
    VALIDATE = "VALIDATE"
    CHECK_CREDENTIALS = "CHECK_CREDENTIALS"
    FETCH_ACCOUNT = "FETCH_ACCOUNT"
    FETCH_BALANCE = "FETCH_BALANCE"
    FETCH_POSITION_RISK = "FETCH_POSITION_RISK"
    FETCH_ACCOUNT_SNAPSHOT = "FETCH_ACCOUNT_SNAPSHOT"
    RUNNER_VALIDATE = "RUNNER_VALIDATE"
    HARD_BLOCK = "HARD_BLOCK"


class BinanceFuturesTestnetReadOnlyDecision(StrEnum):
    CONFIG_VALID = "CONFIG_VALID"
    CREDENTIALS_NOT_CONFIGURED = "CREDENTIALS_NOT_CONFIGURED"
    CREDENTIALS_INCOMPLETE = "CREDENTIALS_INCOMPLETE"
    CREDENTIALS_PRESENT = "CREDENTIALS_PRESENT"
    NETWORK_CONFIRMATION_REQUIRED = "NETWORK_CONFIRMATION_REQUIRED"
    SERVER_TIME_UNAVAILABLE = "SERVER_TIME_UNAVAILABLE"
    CLOCK_SKEW_EXCEEDED = "CLOCK_SKEW_EXCEEDED"
    ACCOUNT_READ_SUCCESS = "ACCOUNT_READ_SUCCESS"
    BALANCE_READ_SUCCESS = "BALANCE_READ_SUCCESS"
    POSITION_READ_SUCCESS = "POSITION_READ_SUCCESS"
    ACCOUNT_SNAPSHOT_SUCCESS = "ACCOUNT_SNAPSHOT_SUCCESS"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZED_READ_ONLY_REQUEST_FAILED = "AUTHORIZED_READ_ONLY_REQUEST_FAILED"
    PATH_NOT_ALLOWED = "PATH_NOT_ALLOWED"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    PRODUCTION_ENDPOINT_BLOCKED = "PRODUCTION_ENDPOINT_BLOCKED"
    RESPONSE_VALIDATION_FAILED = "RESPONSE_VALIDATION_FAILED"
    OPERATION_BLOCKED = "OPERATION_BLOCKED"


@dataclass
class BinanceFuturesTestnetReadOnlyConfig:
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
    testnet_adapter_config_path: str = "configs/binance_futures_testnet_adapter.json"
    futures_read_only_feed_config_path: str = "configs/btc_futures_read_only_feed.json"
    futures_risk_model_config_path: str = "configs/btc_futures_risk_model.json"
    futures_paper_position_config_path: str = "configs/btc_futures_paper_position.json"
    feature_enabled: bool = False
    automatic_execution_enabled: bool = False
    explicit_cli_only: bool = True
    authenticated_read_only_available: bool = True
    dry_run_trading_only: bool = True
    testnet_only: bool = True
    rest_base_url: str = "https://demo-fapi.binance.com"
    allowed_hosts: list[str] = field(default_factory=lambda: ["demo-fapi.binance.com"])
    api_key_env_var: str = "BINANCE_FUTURES_TESTNET_API_KEY"
    api_secret_env_var: str = "BINANCE_FUTURES_TESTNET_API_SECRET"
    credential_source: str = "environment"
    allowed_http_methods: list[str] = field(default_factory=lambda: ["GET"])
    allowed_authenticated_paths: list[str] = field(default_factory=lambda: ["/fapi/v3/account", "/fapi/v3/balance", "/fapi/v3/positionRisk"])
    account_path: str = "/fapi/v3/account"
    balance_path: str = "/fapi/v3/balance"
    position_risk_path: str = "/fapi/v3/positionRisk"
    server_time_path: str = "/fapi/v1/time"
    require_explicit_network_confirmation: bool = True
    network_confirmation_phrase: str = "CONFIRM_TESTNET_READ_ONLY"
    request_timeout_seconds: int = 10
    max_authenticated_fetch_retries: int = 0
    recv_window_ms: int = 5000
    maximum_recv_window_ms: int = 10000
    maximum_clock_skew_ms: int = 5000
    allow_public_server_time_fetch: bool = True
    allow_explicit_authenticated_account_read: bool = True
    allow_explicit_authenticated_balance_read: bool = True
    allow_explicit_authenticated_position_read: bool = True
    allow_explicit_combined_account_snapshot: bool = True
    allow_automatic_authenticated_requests: bool = False
    allow_background_authenticated_polling: bool = False
    allow_runner_authenticated_requests: bool = False
    allow_monitoring_authenticated_requests: bool = False
    allow_order_query: bool = False
    allow_trade_query: bool = False
    allow_income_query: bool = False
    allow_open_order_query: bool = False
    allow_testnet_order_submission: bool = False
    allow_testnet_order_test_submission: bool = False
    allow_testnet_order_cancellation: bool = False
    allow_testnet_order_modification: bool = False
    allow_testnet_position_creation: bool = False
    allow_testnet_position_close: bool = False
    allow_testnet_leverage_change: bool = False
    allow_testnet_margin_mode_change: bool = False
    allow_testnet_position_mode_change: bool = False
    allow_testnet_multi_assets_mode_change: bool = False
    allow_testnet_position_margin_change: bool = False
    allow_user_data_stream: bool = False
    allow_listen_key: bool = False
    allow_websocket_connection: bool = False
    allow_production_endpoint: bool = False
    allow_production_credentials: bool = False
    allow_real_funds: bool = False
    allow_raw_authenticated_response_print: bool = False
    allow_raw_authenticated_response_persistence: bool = False
    allow_authenticated_header_logging: bool = False
    allow_signature_logging: bool = False
    allow_signed_url_logging: bool = False
    allow_futures_paper_state_mutation: bool = False
    allow_spot_paper_account_state_mutation: bool = False
    allow_runner_state_mutation: bool = False
    allow_execution_state_mutation: bool = False
    allow_exchange_state_mutation: bool = False
    require_runtime_config_pass: bool = True
    require_monitoring_config_pass: bool = True
    require_runner_config_pass: bool = True
    require_testnet_adapter_config_pass: bool = True
    require_futures_feed_config_pass: bool = True
    require_futures_risk_model_config_pass: bool = True
    require_futures_paper_position_config_pass: bool = True
    require_kill_switch_enabled: bool = True
    balance_asset_filter: str = "USDT"
    position_symbol_filter: str = "BTCUSDT"
    include_zero_balance_asset: bool = True
    include_zero_position: bool = True
    report_export_dir: str = "reports/binance_futures_testnet_read_only"
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetReadOnlyIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetCredentialMetadata:
    api_key_present: bool = False
    api_secret_present: bool = False
    api_key_length: int = 0
    api_secret_length: int = 0
    credentials_complete: bool = False
    credential_source: str = "environment"
    values_redacted: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetAccountSummary:
    fee_tier: int | None = None
    can_trade: bool | None = None
    can_deposit: bool | None = None
    can_withdraw: bool | None = None
    update_time: int | None = None
    multi_assets_margin: bool | None = None
    total_initial_margin: float | None = None
    total_maintenance_margin: float | None = None
    total_wallet_balance: float | None = None
    total_unrealized_profit: float | None = None
    total_margin_balance: float | None = None
    total_position_initial_margin: float | None = None
    total_open_order_initial_margin: float | None = None
    total_cross_wallet_balance: float | None = None
    total_cross_unrealized_pnl: float | None = None
    available_balance: float | None = None
    max_withdraw_amount: float | None = None
    asset_count: int = 0
    position_count: int = 0
    raw_response_included: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetBalanceSummary:
    asset: str = "USDT"
    account_alias_present: bool = False
    wallet_balance: float = 0.0
    cross_wallet_balance: float = 0.0
    cross_unrealized_pnl: float = 0.0
    available_balance: float = 0.0
    max_withdraw_amount: float = 0.0
    margin_available: bool | None = None
    update_time: int | None = None
    raw_response_included: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetPositionSummary:
    symbol: str = "BTCUSDT"
    position_side: str = "BOTH"
    position_amount: float = 0.0
    has_open_position: bool = False
    entry_price: float = 0.0
    break_even_price: float = 0.0
    mark_price: float = 0.0
    unrealized_profit: float = 0.0
    liquidation_price: float = 0.0
    isolated_margin: float = 0.0
    notional: float = 0.0
    margin_asset: str | None = None
    isolated_wallet: float = 0.0
    initial_margin: float = 0.0
    maintenance_margin: float = 0.0
    position_initial_margin: float = 0.0
    open_order_initial_margin: float = 0.0
    adl: int | None = None
    update_time: int | None = None
    raw_response_included: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetAuthenticatedRequestMetadata:
    method: str = "GET"
    host: str = "demo-fapi.binance.com"
    path: str = ""
    parameter_names: list[str] = field(default_factory=list)
    timestamp: int = 0
    recv_window_ms: int = 5000
    signature_generated: bool = False
    signature_redacted: bool = True
    api_key_header_used: bool = False
    request_transmitted: bool = False
    response_received: bool = False
    response_status_code: int | None = None
    final_host_validated: bool = False
    response_bytes: int | None = None
    retry_count: int = 0
    raw_url_exposed: bool = False
    raw_headers_exposed: bool = False
    raw_response_included: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetReadOnlyValidationReport:
    schema_version: str = "1.0"
    config_path: str = ""
    created_at: str | None = None
    status: str = BinanceFuturesTestnetReadOnlyStatus.FAIL.value
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BinanceFuturesTestnetReadOnlyConfig | None = None
    issues: list[BinanceFuturesTestnetReadOnlyIssue] = field(default_factory=list)
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
class BinanceFuturesTestnetReadOnlyResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    action: str = BinanceFuturesTestnetReadOnlyAction.VALIDATE.value
    status: str = BinanceFuturesTestnetReadOnlyStatus.FAIL.value
    decision: str = BinanceFuturesTestnetReadOnlyDecision.OPERATION_BLOCKED.value
    reason: str = ""
    credential_metadata: BinanceFuturesTestnetCredentialMetadata | None = None
    request_metadata: BinanceFuturesTestnetAuthenticatedRequestMetadata | None = None
    account_summary: BinanceFuturesTestnetAccountSummary | None = None
    balance_summary: BinanceFuturesTestnetBalanceSummary | None = None
    position_summary: BinanceFuturesTestnetPositionSummary | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    issues: list[BinanceFuturesTestnetReadOnlyIssue] = field(default_factory=list)
    safety_summary: dict[str, Any] = field(default_factory=dict)
    public_server_time_request_used: bool = False
    credentials_inspected: bool = False
    signature_generated: bool = False
    authenticated_transport_invoked: bool = False
    authenticated_testnet_request_used: bool = False
    authenticated_account_read_used: bool = False
    authenticated_balance_read_used: bool = False
    authenticated_position_read_used: bool = False
    request_transmitted: bool = False
    api_key_header_used: bool = False
    api_secret_transmitted: bool = False
    order_query_used: bool = False
    trade_query_used: bool = False
    income_query_used: bool = False
    open_order_query_used: bool = False
    order_submitted: bool = False
    test_order_submitted: bool = False
    order_cancelled: bool = False
    order_modified: bool = False
    position_created: bool = False
    position_closed: bool = False
    leverage_changed: bool = False
    margin_mode_changed: bool = False
    position_mode_changed: bool = False
    multi_assets_mode_changed: bool = False
    position_margin_changed: bool = False
    user_data_stream_opened: bool = False
    listen_key_created: bool = False
    websocket_opened: bool = False
    production_endpoint_used: bool = False
    production_credentials_used: bool = False
    real_funds_used: bool = False
    futures_paper_state_mutated: bool = False
    spot_paper_account_state_mutated: bool = False
    runner_state_mutated: bool = False
    execution_state_mutated: bool = False
    exchange_state_mutated: bool = False
    api_key_exposed: bool = False
    api_secret_exposed: bool = False
    signature_exposed: bool = False
    signed_url_exposed: bool = False
    authenticated_headers_exposed: bool = False
    raw_response_printed: bool = False
    raw_response_persisted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "credential_metadata": None if self.credential_metadata is None else self.credential_metadata.to_dict(),
            "request_metadata": None if self.request_metadata is None else self.request_metadata.to_dict(),
            "account_summary": None if self.account_summary is None else self.account_summary.to_dict(),
            "balance_summary": None if self.balance_summary is None else self.balance_summary.to_dict(),
            "position_summary": None if self.position_summary is None else self.position_summary.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }
