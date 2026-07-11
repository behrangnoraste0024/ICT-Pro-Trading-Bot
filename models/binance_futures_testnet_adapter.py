from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class BinanceFuturesTestnetAdapterStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class BinanceFuturesTestnetAdapterAction(StrEnum):
    VALIDATE = "VALIDATE"
    PING_TESTNET = "PING_TESTNET"
    FETCH_SERVER_TIME = "FETCH_SERVER_TIME"
    FETCH_EXCHANGE_INFO = "FETCH_EXCHANGE_INFO"
    CHECK_CREDENTIALS = "CHECK_CREDENTIALS"
    SIGNED_REQUEST_PREVIEW = "SIGNED_REQUEST_PREVIEW"
    BUILD_ORDER_INTENT = "BUILD_ORDER_INTENT"
    HARD_BLOCK = "HARD_BLOCK"


class BinanceFuturesTestnetAdapterDecision(StrEnum):
    CONFIG_VALID = "CONFIG_VALID"
    PUBLIC_TESTNET_OK = "PUBLIC_TESTNET_OK"
    PUBLIC_TESTNET_FAILED = "PUBLIC_TESTNET_FAILED"
    CREDENTIALS_NOT_CONFIGURED = "CREDENTIALS_NOT_CONFIGURED"
    CREDENTIALS_INCOMPLETE = "CREDENTIALS_INCOMPLETE"
    CREDENTIALS_PRESENT = "CREDENTIALS_PRESENT"
    SIGNING_PREVIEW_BUILT = "SIGNING_PREVIEW_BUILT"
    SIGNING_PREVIEW_REJECTED = "SIGNING_PREVIEW_REJECTED"
    ORDER_INTENT_VALID = "ORDER_INTENT_VALID"
    ORDER_INTENT_REJECTED = "ORDER_INTENT_REJECTED"
    AUTHENTICATED_TESTNET_OPERATION_DISABLED = "AUTHENTICATED_TESTNET_OPERATION_DISABLED"
    OPERATION_FAILED = "OPERATION_FAILED"


@dataclass
class BinanceFuturesTestnetAdapterConfig:
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
    futures_paper_position_config_path: str = "configs/btc_futures_paper_position.json"
    adapter_enabled: bool = False
    connection_mode: str = "disabled"
    testnet_only: bool = True
    dry_run_only: bool = True
    rest_base_url: str = "https://demo-fapi.binance.com"
    allowed_hosts: list[str] = field(default_factory=lambda: ["demo-fapi.binance.com"])
    api_key_env_var: str = "BINANCE_FUTURES_TESTNET_API_KEY"
    api_secret_env_var: str = "BINANCE_FUTURES_TESTNET_API_SECRET"
    credential_source: str = "environment"
    request_timeout_seconds: int = 10
    max_public_fetch_retries: int = 1
    recv_window_ms: int = 5000
    maximum_recv_window_ms: int = 10000
    maximum_clock_skew_ms: int = 5000
    allowed_public_paths: list[str] = field(default_factory=lambda: ["/fapi/v1/ping", "/fapi/v1/time", "/fapi/v1/exchangeInfo"])
    allowed_signed_preview_paths: list[str] = field(default_factory=lambda: ["/fapi/v2/account", "/fapi/v2/balance", "/fapi/v2/positionRisk"])
    allow_public_testnet_ping: bool = True
    allow_public_testnet_time_fetch: bool = True
    allow_public_testnet_exchange_info_fetch: bool = True
    allow_environment_credential_presence_check: bool = True
    allow_local_hmac_signing_preview: bool = True
    allow_local_signed_request_preview: bool = True
    allow_local_order_intent_build: bool = True
    allow_authenticated_testnet_request: bool = False
    allow_authenticated_account_read: bool = False
    allow_authenticated_balance_read: bool = False
    allow_authenticated_position_read: bool = False
    allow_testnet_order_submission: bool = False
    allow_testnet_order_cancellation: bool = False
    allow_testnet_leverage_change: bool = False
    allow_testnet_margin_mode_change: bool = False
    allow_testnet_position_creation: bool = False
    allow_user_data_stream: bool = False
    allow_websocket_connection: bool = False
    allow_production_endpoint: bool = False
    allow_production_credentials: bool = False
    allow_real_funds: bool = False
    allow_futures_paper_state_mutation: bool = False
    allow_spot_paper_account_state_mutation: bool = False
    allow_runner_state_mutation: bool = False
    allow_execution_state_mutation: bool = False
    allow_exchange_state_mutation: bool = False
    require_runtime_config_pass: bool = True
    require_monitoring_config_pass: bool = True
    require_runner_config_pass: bool = True
    require_futures_feed_config_pass: bool = True
    require_futures_risk_model_config_pass: bool = True
    require_futures_paper_position_config_pass: bool = True
    require_kill_switch_enabled: bool = True
    order_intent_allowed_sides: list[str] = field(default_factory=lambda: ["BUY", "SELL"])
    order_intent_allowed_types: list[str] = field(default_factory=lambda: ["MARKET", "LIMIT", "STOP_MARKET", "TAKE_PROFIT_MARKET"])
    order_intent_default_time_in_force: str = "GTC"
    order_intent_max_quantity: float = 1.0
    order_intent_require_reduce_only_for_close: bool = True
    report_export_dir: str = "reports/binance_futures_testnet_adapter"
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetAdapterValidationReport:
    schema_version: str = "1.0"
    config_path: str = ""
    created_at: str | None = None
    status: str = BinanceFuturesTestnetAdapterStatus.FAIL.value
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BinanceFuturesTestnetAdapterConfig | None = None
    issues: list[BinanceFuturesTestnetIssue] = field(default_factory=list)
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
class BinanceFuturesTestnetAdapterResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    action: str = BinanceFuturesTestnetAdapterAction.VALIDATE.value
    status: str = BinanceFuturesTestnetAdapterStatus.FAIL.value
    decision: str = BinanceFuturesTestnetAdapterDecision.OPERATION_FAILED.value
    reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    issues: list[BinanceFuturesTestnetIssue] = field(default_factory=list)
    safety_summary: dict[str, Any] = field(default_factory=dict)
    public_request_used: bool = False
    credentials_inspected: bool = False
    signature_generated: bool = False
    request_signed: bool = False
    request_transmitted: bool = False
    authenticated_transport_invoked: bool = False
    authenticated_testnet_request_used: bool = False
    authenticated_account_read_used: bool = False
    authenticated_balance_read_used: bool = False
    authenticated_position_read_used: bool = False
    testnet_order_submitted: bool = False
    testnet_order_cancelled: bool = False
    testnet_position_created: bool = False
    exchange_leverage_changed: bool = False
    exchange_margin_mode_changed: bool = False
    user_data_stream_opened: bool = False
    websocket_opened: bool = False
    production_endpoint_used: bool = False
    production_credentials_used: bool = False
    real_funds_used: bool = False
    futures_paper_state_mutated: bool = False
    spot_paper_account_state_mutated: bool = False
    runner_state_mutated: bool = False
    execution_state_mutated: bool = False
    exchange_state_mutated: bool = False
    secrets_logged: bool = False
    secrets_persisted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "issues": [issue.to_dict() for issue in self.issues]}
