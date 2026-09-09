from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class BinanceFuturesTestnetForwardTestStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class BinanceFuturesTestnetForwardTestExecutionMode(StrEnum):
    DISABLED = "DISABLED"
    LOCAL = "LOCAL_TEST_SIMULATED_TRANSPORT"
    SUPERVISED = "SUPERVISED_TESTNET_ORDER_TEST"


class BinanceFuturesTestnetForwardTestDecision(StrEnum):
    VALIDATION_PASS = "VALIDATION_PASS"
    DISABLED_BY_DEFAULT = "DISABLED_BY_DEFAULT"
    EXECUTION_NOT_AUTHORIZED = "EXECUTION_NOT_AUTHORIZED"
    CONFIG_INVALID = "CONFIG_INVALID"
    LOCAL_SIMULATION_EVIDENCE = "LOCAL_SIMULATION_EVIDENCE"


@dataclass
class BinanceFuturesTestnetForwardTestConfig:
    schema_version: str = "1.0"
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    exchange_symbol: str = "BTCUSDT"
    environment: str = "BINANCE_FUTURES_TESTNET"
    exchange: str = "binance"
    market_type: str = "futures"
    futures_contract_type: str = "USDT_PERPETUAL"
    strategy_profile: str = "balanced_smc_decision_065"
    forward_loop_config_path: str = "configs/btc_forward_test_loop.json"
    runtime_config_path: str = "configs/btc_paper_runtime.json"
    monitoring_config_path: str = "configs/btc_paper_monitoring.json"
    runner_config_path: str = "configs/btc_paper_runner.json"
    testnet_order_test_config_path: str = "configs/binance_futures_testnet_order_test.json"
    testnet_order_lifecycle_config_path: str = "configs/binance_futures_testnet_order_lifecycle.json"
    testnet_protective_orders_config_path: str = "configs/binance_futures_testnet_protective_orders.json"
    feature_enabled: bool = False
    execution_enabled: bool = False
    execution_mode: str = "DISABLED"
    explicit_execution_authorization_required: bool = True
    local_evidence_only: bool = True
    testnet_only: bool = True
    btc_usdt_only: bool = True
    rest_base_url: str = "https://demo-fapi.binance.com"
    allowed_hosts: list[str] = field(default_factory=lambda: ["demo-fapi.binance.com"])
    allow_unknown_environment: bool = False
    allow_production_endpoint: bool = False
    allow_production_credentials: bool = False
    allow_real_funds: bool = False
    allow_network_in_automated_tests: bool = False
    allow_auto_permit_issue: bool = False
    allow_permit_reuse: bool = False
    allow_permit_refund: bool = False
    require_supplied_permit_reference: bool = True
    require_real_permit_gate: bool = True
    require_existing_mutation_boundary: bool = True
    require_existing_risk_authority: bool = True
    require_existing_kill_switch_authority: bool = True
    require_request_immutability: bool = True
    require_reconciliation_on_uncertain: bool = True
    require_restart_duplicate_protection: bool = True
    post_retry_count: int = 0
    delete_retry_count: int = 0
    report_export_dir: str = "reports/binance_futures_testnet_forward_test"
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetForwardTestIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetForwardTestEvidence:
    schema_version: str = "1.0"
    run_id: str = ""
    start_timestamp: str = ""
    end_timestamp: str = ""
    environment: str = "BINANCE_FUTURES_TESTNET"
    symbol: str = "BTCUSDT"
    production_disabled: bool = True
    execution_enabled: bool = False
    execution_mode: str = "DISABLED"
    execution_authorized: bool = False
    order_test_requested_count: int = 0
    actual_binance_demo_execution: bool = False
    transport_mode: str = "LOCAL_TEST_SIMULATED_TRANSPORT"
    strategy_decision_count: int = 0
    permit_reference_count: int = 0
    permit_consumed_count: int | None = 0
    signing_count: int | None = 0
    post_count: int | None = 0
    delete_count: int = 0
    post_retry_count: int = 0
    delete_retry_count: int = 0
    accepted_mutation_count: int = 0
    rejected_mutation_count: int = 0
    canceled_mutation_count: int = 0
    uncertain_mutation_count: int = 0
    reconciliation_count: int = 0
    duplicate_mutation_count: int = 0
    risk_denial_count: int = 0
    kill_switch_denial_count: int = 0
    restart_count: int = 0
    sanitized_error_count: int = 0
    final_position_state: str = "NOT_INSPECTED"
    final_persisted_state: str = "NOT_MUTATED"
    evidence_complete: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BinanceFuturesTestnetForwardTestValidationReport:
    schema_version: str = "1.0"
    config_path: str | None = None
    created_at: str | None = None
    status: str = BinanceFuturesTestnetForwardTestStatus.FAIL.value
    decision: str = BinanceFuturesTestnetForwardTestDecision.CONFIG_INVALID.value
    reason: str = ""
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BinanceFuturesTestnetForwardTestConfig | None = None
    issues: list[BinanceFuturesTestnetForwardTestIssue] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "config": None if self.config is None else {
                key: value for key, value in self.config.to_dict().items()
                if not key.endswith("_path") and key not in {"notes", "report_export_dir"}
            },
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class BinanceFuturesTestnetForwardTestResult:
    schema_version: str = "1.0"
    action: str = "RUN"
    status: str = BinanceFuturesTestnetForwardTestStatus.FAIL.value
    decision: str = BinanceFuturesTestnetForwardTestDecision.EXECUTION_NOT_AUTHORIZED.value
    reason: str = ""
    config_path: str | None = None
    evidence: BinanceFuturesTestnetForwardTestEvidence | None = None
    issues: list[BinanceFuturesTestnetForwardTestIssue] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "evidence": None if self.evidence is None else self.evidence.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }
