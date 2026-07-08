from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class BTCPaperRunnerState(StrEnum):
    CREATED = "CREATED"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class BTCPaperRunnerAction(StrEnum):
    INITIALIZE = "INITIALIZE"
    START = "START"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    STOP = "STOP"
    HEARTBEAT = "HEARTBEAT"
    STATUS = "STATUS"
    RESET_ERROR = "RESET_ERROR"


@dataclass
class BTCPaperRunnerConfig:
    schema_version: str = "1.0"
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    strategy_profile: str = "balanced_smc_decision_065"
    runtime_config_path: str = "configs/btc_paper_runtime.json"
    monitoring_config_path: str = "configs/btc_paper_monitoring.json"
    runner_enabled: bool = False
    dry_run_only: bool = True
    allow_signal_generation: bool = False
    allow_paper_trade_creation: bool = False
    allow_order_submission: bool = False
    allow_exchange_connection: bool = False
    require_runtime_config_pass: bool = True
    require_monitoring_config_pass: bool = True
    require_kill_switch_enabled: bool = True
    heartbeat_interval_seconds: int = 30
    state_export_dir: str = "reports/paper_runner"
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperRunnerIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperRunnerStatus:
    schema_version: str = "1.0"
    created_at: str | None = None
    updated_at: str | None = None
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    strategy_profile: str = "balanced_smc_decision_065"
    state: str = BTCPaperRunnerState.CREATED.value
    previous_state: str | None = None
    last_action: str | None = None
    last_heartbeat_at: str | None = None
    started_at: str | None = None
    stopped_at: str | None = None
    paused_at: str | None = None
    resumed_at: str | None = None
    error_message: str | None = None
    consecutive_errors: int = 0
    dry_run_only: bool = True
    runner_enabled: bool = False
    signal_generation_enabled: bool = False
    paper_trade_creation_enabled: bool = False
    order_submission_enabled: bool = False
    exchange_connection_enabled: bool = False
    runtime_config_status: str = "UNKNOWN"
    monitoring_config_status: str = "UNKNOWN"
    kill_switch_enabled: bool = True
    notes: list[str] = field(default_factory=list)
    issues: list[BTCPaperRunnerIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "issues": [issue.to_dict() for issue in self.issues],
        }

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "BTCPaperRunnerStatus":
        issues = [BTCPaperRunnerIssue(**issue) for issue in values.get("issues", [])]
        payload = {**values, "issues": issues}
        return cls(**{**cls().to_dict(), **payload})


@dataclass
class BTCPaperRunnerTransitionResult:
    action: str
    accepted: bool
    previous_state: str
    current_state: str
    status: BTCPaperRunnerStatus
    message: str
    issues: list[BTCPaperRunnerIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "accepted": self.accepted,
            "previous_state": self.previous_state,
            "current_state": self.current_state,
            "status": self.status.to_dict(),
            "message": self.message,
            "issues": [issue.to_dict() for issue in self.issues],
        }
