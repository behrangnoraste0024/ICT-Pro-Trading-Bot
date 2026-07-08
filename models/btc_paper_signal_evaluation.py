from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class BTCPaperSignalEvaluationStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class BTCPaperSignalEvaluationDecision(StrEnum):
    NONE = "NONE"
    SETUP_DETECTED = "SETUP_DETECTED"
    ENTRY_CANDIDATE = "ENTRY_CANDIDATE"
    APPROVED_DRY_RUN = "APPROVED_DRY_RUN"
    WARNING_DRY_RUN = "WARNING_DRY_RUN"
    REJECTED_DRY_RUN = "REJECTED_DRY_RUN"
    ERROR = "ERROR"


@dataclass
class BTCPaperSignalEvaluationConfig:
    schema_version: str = "1.0"
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    strategy_profile: str = "balanced_smc_decision_065"
    runtime_config_path: str = "configs/btc_paper_runtime.json"
    monitoring_config_path: str = "configs/btc_paper_monitoring.json"
    runner_config_path: str = "configs/btc_paper_runner.json"
    sample_name: str = "btcusdt_15m_1000"
    fixture_path: str = "data/historical/btcusdt_15m_1000.json"
    confirmation_sample_name: str = "btcusdt_1h_1000"
    confirmation_fixture_path: str = "data/historical/btcusdt_1h_1000.json"
    evaluation_mode: str = "latest_closed_candle"
    dry_run_only: bool = True
    allow_trade_creation: bool = False
    allow_order_submission: bool = False
    allow_exchange_connection: bool = False
    allow_state_mutation: bool = False
    require_runtime_config_pass: bool = True
    require_monitoring_config_pass: bool = True
    require_runner_config_pass: bool = True
    require_validation_baseline: bool = True
    require_kill_switch_enabled: bool = True
    min_candles: int = 1000
    max_evaluation_window: int = 500
    decision_threshold: float = 0.65
    status_export_dir: str = "reports/paper_signal_evaluation"
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperSignalEvaluationIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperSignalEvaluationResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    strategy_profile: str = "balanced_smc_decision_065"
    sample_name: str = "btcusdt_15m_1000"
    confirmation_sample_name: str = "btcusdt_1h_1000"
    evaluation_mode: str = "latest_closed_candle"
    status: str = BTCPaperSignalEvaluationStatus.FAIL.value
    decision: str = BTCPaperSignalEvaluationDecision.ERROR.value
    candle_count: int = 0
    confirmation_candle_count: int = 0
    latest_timestamp: str | None = None
    confirmation_latest_timestamp: str | None = None
    direction: str | None = None
    score: float | None = None
    threshold: float = 0.65
    reason: str = ""
    setup_summary: dict[str, Any] = field(default_factory=dict)
    safety_summary: dict[str, Any] = field(default_factory=dict)
    runtime_config_status: str = "UNKNOWN"
    monitoring_config_status: str = "UNKNOWN"
    runner_config_status: str = "UNKNOWN"
    dry_run_only: bool = True
    trade_created: bool = False
    order_submitted: bool = False
    exchange_connected: bool = False
    state_mutated: bool = False
    issues: list[BTCPaperSignalEvaluationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class BTCPaperSignalEvaluationValidationReport:
    schema_version: str = "1.0"
    config_path: str | None = None
    created_at: str | None = None
    status: str = BTCPaperSignalEvaluationStatus.FAIL.value
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BTCPaperSignalEvaluationConfig | None = None
    issues: list[BTCPaperSignalEvaluationIssue] = field(default_factory=list)
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
