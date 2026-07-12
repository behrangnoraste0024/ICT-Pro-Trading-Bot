from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class LifecycleStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    CRITICAL = "CRITICAL"


class LifecycleAction(StrEnum):
    VALIDATE = "VALIDATE"
    CHECK_CREDENTIALS = "CHECK_CREDENTIALS"
    BUILD_PREVIEW = "BUILD_PREVIEW"
    RUN_LIFECYCLE = "RUN_LIFECYCLE"
    QUERY_ORDER = "QUERY_ORDER"
    RECOVERY_CANCEL = "RECOVERY_CANCEL"
    RUNNER_VALIDATE = "RUNNER_VALIDATE"
    HARD_BLOCK = "HARD_BLOCK"


class LifecycleDecision(StrEnum):
    CONFIG_VALID = "CONFIG_VALID"
    CREDENTIALS_NOT_CONFIGURED = "CREDENTIALS_NOT_CONFIGURED"
    CREDENTIALS_INCOMPLETE = "CREDENTIALS_INCOMPLETE"
    CREDENTIALS_PRESENT = "CREDENTIALS_PRESENT"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    POSITION_MODE_UNSUPPORTED = "POSITION_MODE_UNSUPPORTED"
    OPEN_POSITION_DETECTED = "OPEN_POSITION_DETECTED"
    BOOK_TICKER_UNAVAILABLE = "BOOK_TICKER_UNAVAILABLE"
    EXCHANGE_FILTER_VALIDATION_FAILED = "EXCHANGE_FILTER_VALIDATION_FAILED"
    POST_ONLY_PRICE_UNSAFE = "POST_ONLY_PRICE_UNSAFE"
    LIFECYCLE_PREVIEW_VALID = "LIFECYCLE_PREVIEW_VALID"
    ORDER_CREATE_ACCEPTED = "ORDER_CREATE_ACCEPTED"
    ORDER_CREATE_REJECTED = "ORDER_CREATE_REJECTED"
    ORDER_QUERY_SUCCESS = "ORDER_QUERY_SUCCESS"
    ORDER_CANCEL_SUCCESS = "ORDER_CANCEL_SUCCESS"
    ORDER_CANCEL_FAILED = "ORDER_CANCEL_FAILED"
    ORDER_FINAL_STATUS_VERIFIED = "ORDER_FINAL_STATUS_VERIFIED"
    ORDER_STATE_UNKNOWN = "ORDER_STATE_UNKNOWN"
    UNEXPECTED_FILL_DETECTED = "UNEXPECTED_FILL_DETECTED"
    UNEXPECTED_POSITION_DETECTED = "UNEXPECTED_POSITION_DETECTED"
    LIFECYCLE_COMPLETE = "LIFECYCLE_COMPLETE"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    OPERATION_BLOCKED = "OPERATION_BLOCKED"


class LifecyclePhase(StrEnum):
    CREATED_LOCALLY = "CREATED_LOCALLY"
    PRECHECKED = "PRECHECKED"
    CREATE_REQUEST_STARTED = "CREATE_REQUEST_STARTED"
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_QUERIED = "ORDER_QUERIED"
    CANCEL_REQUEST_STARTED = "CANCEL_REQUEST_STARTED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    FINAL_QUERY_COMPLETE = "FINAL_QUERY_COMPLETE"
    POSITION_VERIFIED = "POSITION_VERIFIED"
    COMPLETE = "COMPLETE"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    FAILED = "FAILED"


@dataclass
class BinanceFuturesTestnetOrderLifecycleConfig:
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
    testnet_read_only_config_path: str = "configs/binance_futures_testnet_read_only.json"
    testnet_order_test_config_path: str = "configs/binance_futures_testnet_order_test.json"
    futures_feed_config_path: str = "configs/btc_futures_read_only_feed.json"
    futures_risk_model_config_path: str = "configs/btc_futures_risk_model.json"
    futures_paper_position_config_path: str = "configs/btc_futures_paper_position.json"
    feature_enabled: bool = False
    automatic_execution_enabled: bool = False
    explicit_cli_only: bool = True
    manual_lifecycle_only: bool = True
    testnet_only: bool = True
    single_order_only: bool = True
    rest_base_url: str = "https://demo-fapi.binance.com"
    allowed_hosts: list[str] = field(default_factory=lambda: ["demo-fapi.binance.com"])
    api_key_env_var: str = "BINANCE_FUTURES_TESTNET_API_KEY"
    api_secret_env_var: str = "BINANCE_FUTURES_TESTNET_API_SECRET"
    server_time_path: str = "/fapi/v1/time"
    exchange_info_path: str = "/fapi/v1/exchangeInfo"
    book_ticker_path: str = "/fapi/v1/ticker/bookTicker"
    position_mode_path: str = "/fapi/v1/positionSide/dual"
    position_risk_path: str = "/fapi/v3/positionRisk"
    order_path: str = "/fapi/v1/order"
    allowed_order_methods: list[str] = field(default_factory=lambda: ["POST", "GET", "DELETE"])
    allowed_order_types: list[str] = field(default_factory=lambda: ["LIMIT"])
    allowed_time_in_force: list[str] = field(default_factory=lambda: ["GTX"])
    allowed_sides: list[str] = field(default_factory=lambda: ["BUY", "SELL"])
    required_position_mode: str = "ONE_WAY"
    required_position_side: str = "BOTH"
    require_zero_position_before_create: bool = True
    require_zero_position_after_cancel: bool = True
    require_explicit_lifecycle_confirmation: bool = True
    lifecycle_confirmation_phrase: str = "CONFIRM_TESTNET_POST_ONLY_LIFECYCLE"
    require_explicit_cancel_confirmation: bool = True
    cancel_confirmation_phrase: str = "CONFIRM_TESTNET_CANCEL_ORDER"
    require_explicit_query_confirmation: bool = True
    query_confirmation_phrase: str = "CONFIRM_TESTNET_READ_ONLY"
    request_timeout_seconds: int = 10
    max_create_retries: int = 0
    max_cancel_retries: int = 0
    max_query_retries: int = 1
    recv_window_ms: int = 5000
    maximum_recv_window_ms: int = 10000
    maximum_clock_skew_ms: int = 5000
    minimum_price_offset_bps: int = 50
    default_price_offset_bps: int = 100
    maximum_price_offset_bps: int = 5000
    maximum_quantity: float = 0.01
    maximum_lifecycle_notional_usdt: float = 100.0
    new_order_response_type: str = "ACK"
    client_order_id_prefix: str = "smcbot-lifecycle-"
    maximum_client_order_id_length: int = 36
    require_exchange_filter_validation: bool = True
    require_book_ticker_validation: bool = True
    require_non_marketable_price: bool = True
    require_gtx_post_only: bool = True
    allow_standalone_create: bool = False
    allow_lifecycle_create_query_cancel: bool = True
    allow_exact_order_query: bool = True
    allow_exact_order_recovery_cancel: bool = True
    allow_market_order: bool = False
    allow_conditional_order: bool = False
    allow_algo_order: bool = False
    allow_batch_order: bool = False
    allow_order_modification: bool = False
    allow_cancel_all: bool = False
    allow_open_order_list_query: bool = False
    allow_all_order_history_query: bool = False
    allow_trade_history_query: bool = False
    allow_position_creation: bool = False
    allow_position_close: bool = False
    allow_leverage_change: bool = False
    allow_margin_mode_change: bool = False
    allow_position_mode_change: bool = False
    allow_multi_assets_mode_change: bool = False
    allow_position_margin_change: bool = False
    allow_user_data_stream: bool = False
    allow_listen_key: bool = False
    allow_websocket_connection: bool = False
    allow_production_endpoint: bool = False
    allow_production_credentials: bool = False
    allow_real_funds: bool = False
    allow_runner_order_creation: bool = False
    allow_monitoring_order_creation: bool = False
    allow_strategy_order_creation: bool = False
    allow_background_order_creation: bool = False
    allow_futures_paper_state_mutation: bool = False
    allow_spot_paper_account_state_mutation: bool = False
    allow_runner_state_mutation: bool = False
    allow_execution_state_mutation: bool = False
    allow_raw_request_print: bool = False
    allow_raw_response_print: bool = False
    allow_raw_request_persistence: bool = False
    allow_raw_response_persistence: bool = False
    allow_authenticated_header_logging: bool = False
    allow_signature_logging: bool = False
    allow_signed_url_logging: bool = False
    allow_sanitized_local_lifecycle_journal: bool = True
    lifecycle_journal_path: str = "data/runtime/binance_futures_testnet_order_lifecycle/lifecycle.json"
    lifecycle_lock_path: str = "data/runtime/binance_futures_testnet_order_lifecycle/lifecycle.lock"
    require_runtime_config_pass: bool = True
    require_monitoring_config_pass: bool = True
    require_runner_config_pass: bool = True
    require_testnet_adapter_config_pass: bool = True
    require_testnet_read_only_config_pass: bool = True
    require_testnet_order_test_config_pass: bool = True
    require_futures_feed_config_pass: bool = True
    require_futures_risk_model_config_pass: bool = True
    require_futures_paper_position_config_pass: bool = True
    require_kill_switch_enabled: bool = True
    report_export_dir: str = "reports/binance_futures_testnet_order_lifecycle"
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetLifecycleIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetLifecycleCredentialMetadata:
    api_key_present: bool = False
    api_secret_present: bool = False
    api_key_length: int = 0
    api_secret_length: int = 0
    credentials_complete: bool = False
    values_redacted: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetBookTicker:
    symbol: str = "BTCUSDT"
    bid_price: Decimal = Decimal("0")
    ask_price: Decimal = Decimal("0")
    bid_qty: Decimal | None = None
    ask_qty: Decimal | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetLifecycleExchangeFilters:
    symbol: str = "BTCUSDT"
    price_tick_size: Decimal | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    lot_step_size: Decimal | None = None
    min_qty: Decimal | None = None
    max_qty: Decimal | None = None
    min_notional: Decimal | None = None
    raw_response_included: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetLifecyclePreview:
    lifecycle_id: str = ""
    client_order_id: str = ""
    symbol: str = "BTCUSDT"
    side: str = "BUY"
    order_type: str = "LIMIT"
    time_in_force: str = "GTX"
    quantity: Decimal = Decimal("0")
    price_offset_bps: int = 100
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    derived_price: Decimal | None = None
    estimated_notional: Decimal | None = None
    exchange_filters_valid: bool | None = None
    non_marketable_price_valid: bool | None = None
    position_mode_valid: bool | None = None
    zero_position_precheck_valid: bool | None = None
    post_only_valid: bool = True
    local_rules_valid: bool = True
    transmission_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetOrderSummary:
    symbol: str = "BTCUSDT"
    client_order_id: str = ""
    order_id: str | None = None
    side: str | None = None
    order_type: str | None = None
    time_in_force: str | None = None
    price: Decimal | None = None
    original_quantity: Decimal | None = None
    executed_quantity: Decimal | None = None
    status: str | None = None
    raw_response_included: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetLifecycleRequestMetadata:
    method: str = ""
    host: str = "demo-fapi.binance.com"
    path: str = "/fapi/v1/order"
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
    retry_count: int = 0
    raw_url_exposed: bool = False
    raw_headers_exposed: bool = False
    raw_request_included: bool = False
    raw_response_included: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetLifecycleJournal:
    lifecycle_id: str = ""
    client_order_id: str = ""
    phase: str = LifecyclePhase.CREATED_LOCALLY.value
    recovery_required: bool = False
    entries: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetLifecycleValidationReport:
    schema_version: str = "1.0"
    config_path: str = ""
    created_at: str | None = None
    status: str = LifecycleStatus.FAIL.value
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BinanceFuturesTestnetOrderLifecycleConfig | None = None
    issues: list[BinanceFuturesTestnetLifecycleIssue] = field(default_factory=list)
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
            "diagnostics": _serialize(dict(self.diagnostics)),
        }


@dataclass
class BinanceFuturesTestnetLifecycleResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    action: str = LifecycleAction.VALIDATE.value
    status: str = LifecycleStatus.FAIL.value
    decision: str = LifecycleDecision.OPERATION_BLOCKED.value
    reason: str = ""
    lifecycle_id: str = ""
    client_order_id: str = ""
    phase: str = LifecyclePhase.FAILED.value
    credential_metadata: BinanceFuturesTestnetLifecycleCredentialMetadata | None = None
    book_ticker: BinanceFuturesTestnetBookTicker | None = None
    exchange_filters: BinanceFuturesTestnetLifecycleExchangeFilters | None = None
    preview: BinanceFuturesTestnetLifecyclePreview | None = None
    create_request: BinanceFuturesTestnetLifecycleRequestMetadata | None = None
    query_request: BinanceFuturesTestnetLifecycleRequestMetadata | None = None
    cancel_request: BinanceFuturesTestnetLifecycleRequestMetadata | None = None
    created_order: BinanceFuturesTestnetOrderSummary | None = None
    queried_order: BinanceFuturesTestnetOrderSummary | None = None
    cancel_order: BinanceFuturesTestnetOrderSummary | None = None
    final_order: BinanceFuturesTestnetOrderSummary | None = None
    journal: BinanceFuturesTestnetLifecycleJournal | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    issues: list[BinanceFuturesTestnetLifecycleIssue] = field(default_factory=list)
    safety_summary: dict[str, Any] = field(default_factory=dict)
    credentials_inspected: bool = False
    public_server_time_request_used: bool = False
    public_exchange_info_request_used: bool = False
    public_book_ticker_request_used: bool = False
    position_mode_request_used: bool = False
    position_risk_request_used: bool = False
    signature_generated: bool = False
    authenticated_transport_invoked: bool = False
    create_request_transmitted: bool = False
    query_request_transmitted: bool = False
    cancel_request_transmitted: bool = False
    order_created: bool = False
    order_cancelled: bool = False
    lifecycle_complete: bool = False
    recovery_required: bool = False
    unexpected_fill_detected: bool = False
    unexpected_position_detected: bool = False
    actual_order_endpoint_used: bool = False
    market_order_used: bool = False
    conditional_order_created: bool = False
    algo_order_created: bool = False
    batch_order_created: bool = False
    order_modified: bool = False
    cancel_all_used: bool = False
    leverage_changed: bool = False
    margin_mode_changed: bool = False
    position_mode_changed: bool = False
    production_endpoint_used: bool = False
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
    raw_request_persisted: bool = False
    raw_response_persisted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            **_serialize(asdict(self)),
            "credential_metadata": None if self.credential_metadata is None else self.credential_metadata.to_dict(),
            "book_ticker": None if self.book_ticker is None else self.book_ticker.to_dict(),
            "exchange_filters": None if self.exchange_filters is None else self.exchange_filters.to_dict(),
            "preview": None if self.preview is None else self.preview.to_dict(),
            "create_request": None if self.create_request is None else self.create_request.to_dict(),
            "query_request": None if self.query_request is None else self.query_request.to_dict(),
            "cancel_request": None if self.cancel_request is None else self.cancel_request.to_dict(),
            "created_order": None if self.created_order is None else self.created_order.to_dict(),
            "queried_order": None if self.queried_order is None else self.queried_order.to_dict(),
            "cancel_order": None if self.cancel_order is None else self.cancel_order.to_dict(),
            "final_order": None if self.final_order is None else self.final_order.to_dict(),
            "journal": None if self.journal is None else self.journal.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def serialize_lifecycle(value: Any) -> Any:
    return _serialize(value)


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return format(value, "f")
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value
