from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class BTCPaperCandidateJournalStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class BTCPaperCandidateJournalAction(StrEnum):
    VALIDATE = "VALIDATE"
    RECORD_SIGNAL_EVALUATION = "RECORD_SIGNAL_EVALUATION"
    RECORD_TRADE_CANDIDATE = "RECORD_TRADE_CANDIDATE"
    SIMULATE_AND_RECORD = "SIMULATE_AND_RECORD"
    SUMMARY = "SUMMARY"


@dataclass
class BTCPaperCandidateJournalConfig:
    schema_version: str = "1.0"
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    strategy_profile: str = "balanced_smc_decision_065"
    runtime_config_path: str = "configs/btc_paper_runtime.json"
    monitoring_config_path: str = "configs/btc_paper_monitoring.json"
    runner_config_path: str = "configs/btc_paper_runner.json"
    signal_evaluation_config_path: str = "configs/btc_paper_signal_evaluation.json"
    trade_candidate_config_path: str = "configs/btc_paper_trade_candidate.json"
    dry_run_only: bool = True
    allow_journal_write: bool = True
    allow_executable_trade_creation: bool = False
    allow_paper_trade_persistence: bool = False
    allow_position_creation: bool = False
    allow_order_submission: bool = False
    allow_exchange_connection: bool = False
    allow_state_mutation: bool = False
    journal_format: str = "jsonl"
    journal_dir: str = "reports/paper_candidate_journal"
    journal_file_name: str = "btc_paper_candidate_journal.jsonl"
    max_entries_to_read: int = 50
    require_runtime_config_pass: bool = True
    require_monitoring_config_pass: bool = True
    require_runner_config_pass: bool = True
    require_signal_config_pass: bool = True
    require_trade_candidate_config_pass: bool = True
    require_kill_switch_enabled: bool = True
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperCandidateJournalIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperCandidateJournalEntry:
    schema_version: str = "1.0"
    entry_id: str = ""
    created_at: str = ""
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    strategy_profile: str = "balanced_smc_decision_065"
    source: str = "TRADE_CANDIDATE"
    runner_state: str | None = None
    signal_decision: str | None = None
    signal_status: str | None = None
    signal_score: float | None = None
    signal_threshold: float | None = None
    signal_direction: str | None = None
    candidate_decision: str | None = None
    candidate_status: str | None = None
    candidate_created: bool = False
    candidate_id: str | None = None
    candidate_direction: str | None = None
    candidate_entry_price: float | None = None
    candidate_stop_loss: float | None = None
    candidate_take_profit: float | None = None
    candidate_risk_reward: float | None = None
    rejection_reason: str | None = None
    runtime_config_status: str = "UNKNOWN"
    monitoring_config_status: str = "UNKNOWN"
    runner_config_status: str = "UNKNOWN"
    signal_config_status: str = "UNKNOWN"
    trade_candidate_config_status: str = "UNKNOWN"
    dry_run_only: bool = True
    executable_trade_created: bool = False
    paper_trade_persisted: bool = False
    position_created: bool = False
    order_submitted: bool = False
    exchange_connected: bool = False
    state_mutated: bool = False
    safety_summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    issues: list[BTCPaperCandidateJournalIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class BTCPaperCandidateJournalValidationReport:
    schema_version: str = "1.0"
    config_path: str | None = None
    created_at: str | None = None
    status: str = BTCPaperCandidateJournalStatus.FAIL.value
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BTCPaperCandidateJournalConfig | None = None
    issues: list[BTCPaperCandidateJournalIssue] = field(default_factory=list)
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
class BTCPaperCandidateJournalRecordResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    status: str = BTCPaperCandidateJournalStatus.FAIL.value
    action: str = BTCPaperCandidateJournalAction.SIMULATE_AND_RECORD.value
    entry_written: bool = False
    journal_path: str | None = None
    entry: BTCPaperCandidateJournalEntry | None = None
    reason: str = ""
    dry_run_only: bool = True
    executable_trade_created: bool = False
    paper_trade_persisted: bool = False
    position_created: bool = False
    order_submitted: bool = False
    exchange_connected: bool = False
    state_mutated: bool = False
    issues: list[BTCPaperCandidateJournalIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "entry": None if self.entry is None else self.entry.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class BTCPaperCandidateJournalSummary:
    schema_version: str = "1.0"
    created_at: str | None = None
    journal_path: str = ""
    status: str = BTCPaperCandidateJournalStatus.PASS.value
    total_entries_read: int = 0
    candidate_created_count: int = 0
    candidate_rejected_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    latest_entry_at: str | None = None
    entries: list[BTCPaperCandidateJournalEntry] = field(default_factory=list)
    issues: list[BTCPaperCandidateJournalIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "entries": [entry.to_dict() for entry in self.entries],
            "issues": [issue.to_dict() for issue in self.issues],
        }
