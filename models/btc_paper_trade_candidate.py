from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class BTCPaperTradeCandidateStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class BTCPaperTradeCandidateDecision(StrEnum):
    CANDIDATE_CREATED_DRY_RUN = "CANDIDATE_CREATED_DRY_RUN"
    NO_CANDIDATE_SIGNAL_NOT_APPROVED = "NO_CANDIDATE_SIGNAL_NOT_APPROVED"
    NO_CANDIDATE_SCORE_TOO_LOW = "NO_CANDIDATE_SCORE_TOO_LOW"
    NO_CANDIDATE_CONFIG_UNSAFE = "NO_CANDIDATE_CONFIG_UNSAFE"
    ERROR = "ERROR"


@dataclass
class BTCPaperTradeCandidateConfig:
    schema_version: str = "1.0"
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    strategy_profile: str = "balanced_smc_decision_065"
    runtime_config_path: str = "configs/btc_paper_runtime.json"
    monitoring_config_path: str = "configs/btc_paper_monitoring.json"
    runner_config_path: str = "configs/btc_paper_runner.json"
    signal_evaluation_config_path: str = "configs/btc_paper_signal_evaluation.json"
    dry_run_only: bool = True
    allow_candidate_creation: bool = True
    allow_executable_trade_creation: bool = False
    allow_paper_trade_persistence: bool = False
    allow_position_creation: bool = False
    allow_order_submission: bool = False
    allow_exchange_connection: bool = False
    allow_state_mutation: bool = False
    require_signal_approved: bool = True
    require_runtime_config_pass: bool = True
    require_monitoring_config_pass: bool = True
    require_runner_config_pass: bool = True
    require_signal_config_pass: bool = True
    require_kill_switch_enabled: bool = True
    min_signal_score: float = 0.65
    min_risk_reward: float = 1.5
    entry_price_source: str = "latest_close"
    stop_loss_mode: str = "diagnostic_atr_like"
    take_profit_mode: str = "fixed_rr"
    diagnostic_stop_loss_pct: float = 0.01
    max_candidate_notional_pct: float = 0.25
    status_export_dir: str = "reports/paper_trade_candidates"
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperTradeCandidateIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperTradeCandidate:
    candidate_id: str
    created_at: str
    symbol: str
    strategy_profile: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    signal_score: float
    signal_threshold: float
    account_currency: str
    starting_equity: float
    risk_per_trade_pct: float
    estimated_risk_amount: float
    estimated_position_size: float
    estimated_notional: float
    max_candidate_notional: float
    candidate_is_executable: bool = False
    candidate_is_persisted: bool = False
    candidate_opens_position: bool = False
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperTradeCandidateResult:
    schema_version: str = "1.0"
    created_at: str | None = None
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    strategy_profile: str = "balanced_smc_decision_065"
    status: str = BTCPaperTradeCandidateStatus.FAIL.value
    decision: str = BTCPaperTradeCandidateDecision.ERROR.value
    candidate_created: bool = False
    candidate: BTCPaperTradeCandidate | None = None
    signal_decision: str | None = None
    signal_score: float | None = None
    signal_threshold: float = 0.65
    reason: str = ""
    runtime_config_status: str = "UNKNOWN"
    monitoring_config_status: str = "UNKNOWN"
    runner_config_status: str = "UNKNOWN"
    signal_config_status: str = "UNKNOWN"
    dry_run_only: bool = True
    executable_trade_created: bool = False
    paper_trade_persisted: bool = False
    position_created: bool = False
    order_submitted: bool = False
    exchange_connected: bool = False
    state_mutated: bool = False
    safety_summary: dict[str, Any] = field(default_factory=dict)
    issues: list[BTCPaperTradeCandidateIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "candidate": None if self.candidate is None else self.candidate.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class BTCPaperTradeCandidateValidationReport:
    schema_version: str = "1.0"
    config_path: str | None = None
    created_at: str | None = None
    status: str = BTCPaperTradeCandidateStatus.FAIL.value
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BTCPaperTradeCandidateConfig | None = None
    issues: list[BTCPaperTradeCandidateIssue] = field(default_factory=list)
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
