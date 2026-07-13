from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class BinanceFuturesTestnetProtectiveOrdersConfig:
    schema_version: str = "1.0"
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    exchange_symbol: str = "BTCUSDT"
    exchange: str = "binance"
    market_type: str = "futures"
    futures_contract_type: str = "USDT_PERPETUAL"
    strategy_profile: str = "balanced_smc_decision_065"
    rest_base_url: str = "https://demo-fapi.binance.com"
    allowed_hosts: list[str] = field(default_factory=lambda: ["demo-fapi.binance.com"])
    api_key_env_var: str = "BINANCE_FUTURES_TESTNET_API_KEY"
    api_secret_env_var: str = "BINANCE_FUTURES_TESTNET_API_SECRET"
    server_time_path: str = "/fapi/v1/time"
    exchange_info_path: str = "/fapi/v1/exchangeInfo"
    position_mode_path: str = "/fapi/v1/positionSide/dual"
    position_risk_path: str = "/fapi/v3/positionRisk"
    algo_order_path: str = "/fapi/v1/algoOrder"
    request_timeout_seconds: int = 30
    recv_window_ms: int = 10000
    maximum_recv_window_ms: int = 10000
    maximum_clock_skew_ms: int = 5000
    feature_enabled: bool = False
    automatic_execution_enabled: bool = False
    explicit_cli_only: bool = True
    manual_only: bool = True
    testnet_only: bool = True
    allowed_algo_type: str = "CONDITIONAL"
    allowed_order_types: list[str] = field(default_factory=lambda: ["STOP_MARKET", "TAKE_PROFIT_MARKET"])
    allowed_methods: list[str] = field(default_factory=lambda: ["POST", "GET", "DELETE"])
    required_position_mode: str = "ONE_WAY"
    required_position_side: str = "BOTH"
    working_type: str = "MARK_PRICE"
    close_position: bool = True
    price_protect: bool = True
    new_order_response_type: str = "ACK"
    maximum_position_abs_quantity: float = 0.002
    maximum_position_notional_usdt: float = 150.0
    minimum_stop_offset_bps: int = 500
    maximum_stop_offset_bps: int = 3000
    default_stop_offset_bps: int = 1000
    minimum_take_profit_offset_bps: int = 500
    maximum_take_profit_offset_bps: int = 3000
    default_take_profit_offset_bps: int = 1000
    max_create_retries: int = 0
    max_cancel_retries: int = 0
    max_query_retries: int = 1
    client_algo_id_prefix: str = "smcbot-protect-"
    maximum_client_algo_id_length: int = 36
    pair_confirmation_phrase: str = "CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE"
    recovery_confirmation_phrase: str = "CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY"
    journal_path: str = "data/runtime/binance_futures_testnet_protective_orders/protective.json"
    lock_path: str = "data/runtime/binance_futures_testnet_protective_orders/protective.lock"
    report_export_dir: str = "reports/binance_futures_testnet_protective_orders"
    allow_position_entry: bool = False
    allow_position_close: bool = False
    allow_market_order: bool = False
    allow_regular_limit_order: bool = False
    allow_cancel_all: bool = False
    allow_open_algo_order_list: bool = False
    allow_order_history: bool = False
    allow_trade_history: bool = False
    allow_leverage_change: bool = False
    allow_margin_mode_change: bool = False
    allow_position_mode_change: bool = False
    allow_production_endpoint: bool = False
    allow_real_funds: bool = False
    allow_raw_request_persistence: bool = False
    allow_raw_response_persistence: bool = False
    allow_authenticated_header_logging: bool = False
    allow_signature_logging: bool = False
    allow_signed_url_logging: bool = False
    allow_sanitized_local_journal: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetProtectiveIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetProtectiveCredentialMetadata:
    api_key_present: bool = False
    api_secret_present: bool = False
    api_key_length: int = 0
    api_secret_length: int = 0
    credentials_complete: bool = False
    values_redacted: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetProtectiveExchangeFilters:
    symbol: str = "BTCUSDT"
    price_tick_size: Decimal | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetProtectivePosition:
    symbol: str = "BTCUSDT"
    position_side: str = "BOTH"
    position_amt: Decimal = Decimal("0")
    entry_price: Decimal = Decimal("0")
    mark_price: Decimal = Decimal("0")
    notional: Decimal = Decimal("0")
    direction: str = "NONE"

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetProtectivePreview:
    pair_id: str = ""
    symbol: str = "BTCUSDT"
    position_direction: str = ""
    position_amount: Decimal = Decimal("0")
    entry_price: Decimal = Decimal("0")
    mark_price: Decimal = Decimal("0")
    protective_side: str = ""
    stop_client_algo_id: str = ""
    take_profit_client_algo_id: str = ""
    stop_offset_bps: int = 1000
    take_profit_offset_bps: int = 1000
    stop_trigger: Decimal | None = None
    take_profit_trigger: Decimal | None = None
    transmission_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetProtectiveAlgoSummary:
    symbol: str | None = None
    client_algo_id: str | None = None
    algo_id: str | None = None
    algo_type: str | None = None
    side: str | None = None
    position_side: str | None = None
    order_type: str | None = None
    trigger_price: Decimal | None = None
    algo_status: str | None = None
    actual_order_id: str | None = None
    executed_quantity: Decimal = Decimal("0")
    actual_price: Decimal | None = None
    close_position: bool | None = None
    working_type: str | None = None
    price_protect: bool | None = None
    response_code: int | None = None
    response_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetProtectiveRequestMetadata:
    method: str = ""
    host: str = "demo-fapi.binance.com"
    path: str = "/fapi/v1/algoOrder"
    parameter_names: list[str] = field(default_factory=list)
    timestamp: int = 0
    recv_window_ms: int = 10000
    signature_generated: bool = False
    signature_redacted: bool = True
    api_key_header_used: bool = False
    request_transmitted: bool = False
    response_received: bool = False
    response_status_code: int | None = None
    final_host_validated: bool = False
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetProtectiveJournal:
    pair_id: str = ""
    stop_client_algo_id: str = ""
    take_profit_client_algo_id: str = ""
    phase: str = "CREATED_LOCALLY"
    recovery_required: bool = False
    baseline_available: bool = False
    baseline_position_amount: Decimal | None = None
    baseline_position_direction: str | None = None
    stop_trigger: Decimal | None = None
    take_profit_trigger: Decimal | None = None
    entries: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))


@dataclass
class BinanceFuturesTestnetProtectiveValidationReport:
    schema_version: str = "1.0"
    config_path: str = ""
    created_at: str | None = None
    status: str = "FAIL"
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BinanceFuturesTestnetProtectiveOrdersConfig | None = None
    issues: list[BinanceFuturesTestnetProtectiveIssue] = field(default_factory=list)
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
class BinanceFuturesTestnetProtectiveResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    action: str = "VALIDATE"
    status: str = "FAIL"
    decision: str = "OPERATION_BLOCKED"
    reason: str = ""
    pair_id: str = ""
    phase: str = "FAILED"
    stop_client_algo_id: str = ""
    take_profit_client_algo_id: str = ""
    credential_metadata: BinanceFuturesTestnetProtectiveCredentialMetadata | None = None
    exchange_filters: BinanceFuturesTestnetProtectiveExchangeFilters | None = None
    position: BinanceFuturesTestnetProtectivePosition | None = None
    final_position: BinanceFuturesTestnetProtectivePosition | None = None
    preview: BinanceFuturesTestnetProtectivePreview | None = None
    stop_order: BinanceFuturesTestnetProtectiveAlgoSummary | None = None
    take_profit_order: BinanceFuturesTestnetProtectiveAlgoSummary | None = None
    final_stop_order: BinanceFuturesTestnetProtectiveAlgoSummary | None = None
    final_take_profit_order: BinanceFuturesTestnetProtectiveAlgoSummary | None = None
    create_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata] = field(default_factory=list)
    query_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata] = field(default_factory=list)
    cancel_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata] = field(default_factory=list)
    journal: BinanceFuturesTestnetProtectiveJournal | None = None
    issues: list[BinanceFuturesTestnetProtectiveIssue] = field(default_factory=list)
    lifecycle_complete: bool = False
    recovery_required: bool = False
    unexpected_trigger: bool = False
    unexpected_position_change: bool = False
    create_request_transmitted: bool = False
    query_request_transmitted: bool = False
    cancel_request_transmitted: bool = False
    production_endpoint_used: bool = False
    real_funds_used: bool = False
    secrets_exposed: bool = False
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **_serialize(asdict(self)),
            "credential_metadata": None if self.credential_metadata is None else self.credential_metadata.to_dict(),
            "exchange_filters": None if self.exchange_filters is None else self.exchange_filters.to_dict(),
            "position": None if self.position is None else self.position.to_dict(),
            "final_position": None if self.final_position is None else self.final_position.to_dict(),
            "preview": None if self.preview is None else self.preview.to_dict(),
            "stop_order": None if self.stop_order is None else self.stop_order.to_dict(),
            "take_profit_order": None if self.take_profit_order is None else self.take_profit_order.to_dict(),
            "final_stop_order": None if self.final_stop_order is None else self.final_stop_order.to_dict(),
            "final_take_profit_order": None if self.final_take_profit_order is None else self.final_take_profit_order.to_dict(),
            "create_requests": [item.to_dict() for item in self.create_requests],
            "query_requests": [item.to_dict() for item in self.query_requests],
            "cancel_requests": [item.to_dict() for item in self.cancel_requests],
            "journal": None if self.journal is None else self.journal.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def serialize_protective(value: Any) -> Any:
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
