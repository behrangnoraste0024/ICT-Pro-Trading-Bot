from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class BinanceFuturesTestnetOrderTestStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class BinanceFuturesTestnetOrderTestAction(StrEnum):
    VALIDATE = "VALIDATE"
    CHECK_CREDENTIALS = "CHECK_CREDENTIALS"
    BUILD_PREVIEW = "BUILD_PREVIEW"
    SUBMIT_TEST_ORDER = "SUBMIT_TEST_ORDER"
    RUNNER_VALIDATE = "RUNNER_VALIDATE"
    HARD_BLOCK = "HARD_BLOCK"


class BinanceFuturesTestnetOrderTestDecision(StrEnum):
    CONFIG_VALID = "CONFIG_VALID"
    CREDENTIALS_NOT_CONFIGURED = "CREDENTIALS_NOT_CONFIGURED"
    CREDENTIALS_INCOMPLETE = "CREDENTIALS_INCOMPLETE"
    CREDENTIALS_PRESENT = "CREDENTIALS_PRESENT"
    NETWORK_CONFIRMATION_REQUIRED = "NETWORK_CONFIRMATION_REQUIRED"
    ORDER_TEST_PREVIEW_VALID = "ORDER_TEST_PREVIEW_VALID"
    ORDER_TEST_PREVIEW_REJECTED = "ORDER_TEST_PREVIEW_REJECTED"
    ORDER_TEST_ACCEPTED = "ORDER_TEST_ACCEPTED"
    ORDER_TEST_REJECTED = "ORDER_TEST_REJECTED"
    ORDER_TEST_PUBLIC_VALIDATION_PASSED = "ORDER_TEST_PUBLIC_VALIDATION_PASSED"
    MARKET_REFERENCE_PRICE_REQUIRED = "MARKET_REFERENCE_PRICE_REQUIRED"
    MARKET_REFERENCE_PRICE_UNAVAILABLE = "MARKET_REFERENCE_PRICE_UNAVAILABLE"
    MARKET_REFERENCE_PRICE_INVALID = "MARKET_REFERENCE_PRICE_INVALID"
    MARKET_NOTIONAL_NOT_EVALUATED = "MARKET_NOTIONAL_NOT_EVALUATED"
    MARKET_NOTIONAL_EXCEEDED = "MARKET_NOTIONAL_EXCEEDED"
    EXCHANGE_MIN_NOTIONAL_FAILED = "EXCHANGE_MIN_NOTIONAL_FAILED"
    EXCHANGE_FILTERS_NOT_EVALUATED = "EXCHANGE_FILTERS_NOT_EVALUATED"
    EXCHANGE_FILTER_VALIDATION_FAILED = "EXCHANGE_FILTER_VALIDATION_FAILED"
    CLOCK_SKEW_EXCEEDED = "CLOCK_SKEW_EXCEEDED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    NETWORK_FAILED = "NETWORK_FAILED"
    ACTUAL_ORDER_OPERATION_BLOCKED = "ACTUAL_ORDER_OPERATION_BLOCKED"


class OrderTestNotionalValidationStatus(StrEnum):
    NOT_EVALUATED = "NOT_EVALUATED"
    PASS = "PASS"
    FAIL = "FAIL"


class OrderTestExchangeFilterValidationStatus(StrEnum):
    NOT_EVALUATED = "NOT_EVALUATED"
    PASS = "PASS"
    FAIL = "FAIL"


class OrderTestReferencePriceSource(StrEnum):
    MARK_PRICE = "MARK_PRICE"


@dataclass
class BinanceFuturesTestnetOrderTestConfig:
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
    futures_feed_config_path: str = "configs/btc_futures_read_only_feed.json"
    futures_risk_model_config_path: str = "configs/btc_futures_risk_model.json"
    futures_paper_position_config_path: str = "configs/btc_futures_paper_position.json"
    feature_enabled: bool = False
    automatic_execution_enabled: bool = False
    explicit_cli_only: bool = True
    testnet_only: bool = True
    test_order_only: bool = True
    rest_base_url: str = "https://demo-fapi.binance.com"
    allowed_hosts: list[str] = field(default_factory=lambda: ["demo-fapi.binance.com"])
    api_key_env_var: str = "BINANCE_FUTURES_TESTNET_API_KEY"
    api_secret_env_var: str = "BINANCE_FUTURES_TESTNET_API_SECRET"
    allowed_http_methods: list[str] = field(default_factory=lambda: ["POST"])
    test_order_path: str = "/fapi/v1/order/test"
    mark_price_path: str = "/fapi/v1/premiumIndex"
    market_reference_price_source: str = OrderTestReferencePriceSource.MARK_PRICE.value
    allowed_authenticated_paths: list[str] = field(default_factory=lambda: ["/fapi/v1/order/test"])
    require_explicit_network_confirmation: bool = True
    network_confirmation_phrase: str = "CONFIRM_TESTNET_ORDER_TEST"
    request_timeout_seconds: int = 10
    max_authenticated_retries: int = 0
    recv_window_ms: int = 5000
    maximum_recv_window_ms: int = 10000
    maximum_clock_skew_ms: int = 5000
    allow_public_server_time_fetch: bool = True
    allow_public_exchange_info_fetch: bool = True
    allow_local_order_test_preview: bool = True
    allow_explicit_test_order_request: bool = True
    require_market_reference_price: bool = True
    allow_zero_market_reference_price: bool = False
    allow_unknown_market_notional: bool = False
    allow_unvalidated_exchange_filters_for_transmission: bool = False
    require_exchange_filters_before_transmission: bool = True
    allowed_order_types: list[str] = field(default_factory=lambda: ["MARKET", "LIMIT"])
    allowed_sides: list[str] = field(default_factory=lambda: ["BUY", "SELL"])
    default_time_in_force: str = "GTC"
    allowed_time_in_force: list[str] = field(default_factory=lambda: ["GTC", "IOC", "FOK"])
    maximum_quantity: float = 0.01
    maximum_test_notional_usdt: float = 100.0
    require_exchange_filter_validation: bool = True
    require_unique_client_order_id: bool = True
    client_order_id_prefix: str = "smcbot-test-"
    maximum_client_order_id_length: int = 36
    allow_reduce_only: bool = True
    allow_close_position: bool = False
    allow_position_side: bool = False
    allow_actual_order_submission: bool = False
    allow_order_cancellation: bool = False
    allow_order_modification: bool = False
    allow_order_query: bool = False
    allow_open_order_query: bool = False
    allow_trade_query: bool = False
    allow_income_query: bool = False
    allow_conditional_order: bool = False
    allow_algo_order: bool = False
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
    allow_raw_request_print: bool = False
    allow_raw_response_print: bool = False
    allow_raw_request_persistence: bool = False
    allow_raw_response_persistence: bool = False
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
    require_testnet_read_only_config_pass: bool = True
    require_futures_feed_config_pass: bool = True
    require_futures_risk_model_config_pass: bool = True
    require_futures_paper_position_config_pass: bool = True
    require_kill_switch_enabled: bool = True
    report_export_dir: str = "reports/binance_futures_testnet_order_test"
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetOrderTestIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetOrderTestCredentialMetadata:
    api_key_present: bool = False
    api_secret_present: bool = False
    api_key_length: int = 0
    api_secret_length: int = 0
    credentials_complete: bool = False
    values_redacted: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetExchangeFilterSummary:
    symbol: str = "BTCUSDT"
    price_tick_size: Decimal | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    lot_step_size: Decimal | None = None
    min_qty: Decimal | None = None
    max_qty: Decimal | None = None
    market_lot_step_size: Decimal | None = None
    market_min_qty: Decimal | None = None
    market_max_qty: Decimal | None = None
    min_notional: Decimal | None = None
    source: str = "PUBLIC_EXCHANGE_INFO"
    raw_response_included: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetOrderTestPreview:
    client_order_id: str = ""
    symbol: str = "BTCUSDT"
    side: str = "BUY"
    order_type: str = "MARKET"
    quantity: Decimal = Decimal("0")
    price: Decimal | None = None
    time_in_force: str | None = None
    reduce_only: bool = False
    reference_price: Decimal | None = None
    reference_price_source: str | None = None
    estimated_notional: Decimal | None = None
    configured_max_notional_valid: bool | None = None
    exchange_min_notional_valid: bool | None = None
    notional_validation_status: str = OrderTestNotionalValidationStatus.NOT_EVALUATED.value
    exchange_filter_validation_status: str = OrderTestExchangeFilterValidationStatus.NOT_EVALUATED.value
    exchange_filters_valid: bool | None = None
    local_rules_valid: bool = True
    transmission_ready: bool = False
    executable: bool = False
    actual_order_endpoint_used: bool = False
    matching_engine_submission: bool = False
    exchange_order_created: bool = False
    exchange_order_id: str | None = None
    position_created: bool = False
    parameter_names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetOrderTestRequestMetadata:
    method: str = "POST"
    host: str = "demo-fapi.binance.com"
    path: str = "/fapi/v1/order/test"
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
    response_empty_object: bool = False
    response_body_type: str = "unknown"
    response_byte_count_category: str = "unknown"
    response_content_type_category: str = "unknown"
    binance_error_code: str | None = None
    binance_error_message: str | None = None
    retry_count: int = 0
    raw_url_exposed: bool = False
    raw_headers_exposed: bool = False
    raw_request_included: bool = False
    raw_response_included: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetOrderTestValidationReport:
    schema_version: str = "1.0"
    config_path: str = ""
    created_at: str | None = None
    status: str = BinanceFuturesTestnetOrderTestStatus.FAIL.value
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BinanceFuturesTestnetOrderTestConfig | None = None
    issues: list[BinanceFuturesTestnetOrderTestIssue] = field(default_factory=list)
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
class BinanceFuturesTestnetOrderTestResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    action: str = BinanceFuturesTestnetOrderTestAction.VALIDATE.value
    status: str = BinanceFuturesTestnetOrderTestStatus.FAIL.value
    decision: str = BinanceFuturesTestnetOrderTestDecision.ACTUAL_ORDER_OPERATION_BLOCKED.value
    reason: str = ""
    credential_metadata: BinanceFuturesTestnetOrderTestCredentialMetadata | None = None
    exchange_filter_summary: BinanceFuturesTestnetExchangeFilterSummary | None = None
    preview: BinanceFuturesTestnetOrderTestPreview | None = None
    request_metadata: BinanceFuturesTestnetOrderTestRequestMetadata | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    issues: list[BinanceFuturesTestnetOrderTestIssue] = field(default_factory=list)
    safety_summary: dict[str, Any] = field(default_factory=dict)
    credentials_inspected: bool = False
    public_server_time_request_used: bool = False
    public_exchange_info_request_used: bool = False
    signature_generated: bool = False
    authenticated_transport_invoked: bool = False
    test_order_request_transmitted: bool = False
    authenticated_test_request_used: bool = False
    actual_order_submitted: bool = False
    actual_order_endpoint_used: bool = False
    matching_engine_submission: bool = False
    exchange_order_created: bool = False
    exchange_order_id: str | None = None
    order_cancelled: bool = False
    order_modified: bool = False
    position_created: bool = False
    position_closed: bool = False
    leverage_changed: bool = False
    margin_mode_changed: bool = False
    conditional_order_created: bool = False
    algo_order_created: bool = False
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
    raw_request_printed: bool = False
    raw_response_printed: bool = False
    raw_request_persisted: bool = False
    raw_response_persisted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            **_serialize(asdict(self)),
            "credential_metadata": None if self.credential_metadata is None else self.credential_metadata.to_dict(),
            "exchange_filter_summary": None if self.exchange_filter_summary is None else self.exchange_filter_summary.to_dict(),
            "preview": None if self.preview is None else self.preview.to_dict(),
            "request_metadata": None if self.request_metadata is None else self.request_metadata.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }


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
