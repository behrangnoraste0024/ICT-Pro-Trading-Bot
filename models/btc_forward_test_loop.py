from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class BTCForwardTestStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class BTCForwardTestAction(StrEnum):
    VALIDATE = "VALIDATE"
    RUN = "RUN"
    SUMMARY = "SUMMARY"
    RESET_STATE = "RESET_STATE"


class BTCForwardTestCycleDecision(StrEnum):
    JOURNALED_REJECTION = "JOURNALED_REJECTION"
    JOURNALED_CANDIDATE = "JOURNALED_CANDIDATE"
    NO_JOURNAL = "NO_JOURNAL"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


@dataclass
class BTCForwardTestConfig:
    schema_version: str = "1.0"
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    strategy_profile: str = "balanced_smc_decision_065"
    runtime_config_path: str = "configs/btc_paper_runtime.json"
    monitoring_config_path: str = "configs/btc_paper_monitoring.json"
    runner_config_path: str = "configs/btc_paper_runner.json"
    signal_evaluation_config_path: str = "configs/btc_paper_signal_evaluation.json"
    trade_candidate_config_path: str = "configs/btc_paper_trade_candidate.json"
    candidate_journal_config_path: str = "configs/btc_paper_candidate_journal.json"
    fixture_path: str = "data/historical/btcusdt_15m_1000.json"
    confirmation_fixture_path: str = "data/historical/btcusdt_1h_1000.json"
    dry_run_only: bool = True
    allow_forward_loop: bool = True
    allow_journal_write: bool = True
    allow_live_market_data: bool = False
    allow_exchange_connection: bool = False
    allow_order_submission: bool = False
    allow_position_creation: bool = False
    allow_paper_trade_persistence: bool = False
    allow_executable_trade_creation: bool = False
    allow_state_mutation: bool = False
    require_runtime_config_pass: bool = True
    require_monitoring_config_pass: bool = True
    require_runner_config_pass: bool = True
    require_signal_config_pass: bool = True
    require_trade_candidate_config_pass: bool = True
    require_candidate_journal_config_pass: bool = True
    require_kill_switch_enabled: bool = True
    cycle_mode: str = "historical_cursor"
    start_index: int = 500
    max_cycles: int = 5
    min_candles: int = 1000
    evaluation_window: int = 500
    cycle_interval_seconds: int = 0
    max_run_seconds: int = 60
    state_export_dir: str = "reports/forward_test"
    report_export_dir: str = "reports/forward_test"
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCForwardTestIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCForwardTestCycleResult:
    schema_version: str = "1.0"
    cycle_id: str = ""
    created_at: str = ""
    cycle_number: int = 0
    cursor_index: int = 0
    symbol: str = "BTC/USDT"
    strategy_profile: str = "balanced_smc_decision_065"
    candle_timestamp: str | None = None
    signal_status: str | None = None
    signal_decision: str | None = None
    signal_score: float | None = None
    candidate_status: str | None = None
    candidate_decision: str | None = None
    candidate_created: bool = False
    journal_entry_written: bool = False
    journal_entry_id: str | None = None
    cycle_decision: str = BTCForwardTestCycleDecision.SKIPPED.value
    reason: str = ""
    dry_run_only: bool = True
    live_market_data_used: bool = False
    executable_trade_created: bool = False
    paper_trade_persisted: bool = False
    position_created: bool = False
    order_submitted: bool = False
    exchange_connected: bool = False
    state_mutated: bool = False
    issues: list[BTCForwardTestIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "issues": [issue.to_dict() for issue in self.issues]}


@dataclass
class BTCForwardTestRunResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    strategy_profile: str = "balanced_smc_decision_065"
    status: str = BTCForwardTestStatus.FAIL.value
    cycles_requested: int = 0
    cycles_completed: int = 0
    cycles_failed: int = 0
    candidates_created: int = 0
    candidates_rejected: int = 0
    journal_entries_written: int = 0
    warnings: int = 0
    failures: int = 0
    start_index: int = 0
    end_index: int = 0
    runtime_config_status: str = "UNKNOWN"
    monitoring_config_status: str = "UNKNOWN"
    runner_config_status: str = "UNKNOWN"
    signal_config_status: str = "UNKNOWN"
    trade_candidate_config_status: str = "UNKNOWN"
    candidate_journal_config_status: str = "UNKNOWN"
    dry_run_only: bool = True
    live_market_data_used: bool = False
    executable_trade_created: bool = False
    paper_trade_persisted: bool = False
    position_created: bool = False
    order_submitted: bool = False
    exchange_connected: bool = False
    state_mutated: bool = False
    cycles: list[BTCForwardTestCycleResult] = field(default_factory=list)
    issues: list[BTCForwardTestIssue] = field(default_factory=list)
    safety_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "cycles": [cycle.to_dict() for cycle in self.cycles],
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class BTCForwardTestValidationReport:
    schema_version: str = "1.0"
    config_path: str | None = None
    created_at: str | None = None
    status: str = BTCForwardTestStatus.FAIL.value
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BTCForwardTestConfig | None = None
    issues: list[BTCForwardTestIssue] = field(default_factory=list)
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
class BTCForwardTestState:
    schema_version: str = "1.0"
    created_at: str | None = None
    updated_at: str | None = None
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    strategy_profile: str = "balanced_smc_decision_065"
    last_cursor_index: int = 0
    last_cycle_at: str | None = None
    total_cycles_completed: int = 0
    total_candidates_created: int = 0
    total_candidates_rejected: int = 0
    total_journal_entries_written: int = 0
    last_status: str = BTCForwardTestStatus.WARNING.value
    last_reason: str | None = None
    dry_run_only: bool = True
    executable_trade_created: bool = False
    paper_trade_persisted: bool = False
    position_created: bool = False
    order_submitted: bool = False
    exchange_connected: bool = False
    state_mutated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
