from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BTCPaperMonitoringConfig:
    schema_version: str = "1.0"
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    strategy_profile: str = "balanced_smc_decision_065"
    runtime_config_path: str = "configs/btc_paper_runtime.json"
    enabled: bool = True
    monitoring_only: bool = True
    paper_execution_expected: bool = False
    live_trading_expected: bool = False
    order_submission_expected: bool = False
    heartbeat_stale_after_seconds: int = 120
    signal_stale_after_minutes: int = 60
    validation_gate_stale_after_hours: int = 24
    runtime_config_stale_after_hours: int = 24
    max_consecutive_errors: int = 3
    require_kill_switch_visible: bool = True
    require_execution_state_visible: bool = True
    require_runtime_config_visible: bool = True
    require_validation_gate_status_visible: bool = True
    require_last_signal_visible: bool = False
    status_export_dir: str = "reports/paper_monitoring"
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperMonitoringIssue:
    name: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperMonitoringValidationReport:
    schema_version: str = "1.0"
    config_path: str | None = None
    created_at: str | None = None
    status: str = "FAIL"
    issue_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    config: BTCPaperMonitoringConfig | None = None
    issues: list[BTCPaperMonitoringIssue] = field(default_factory=list)
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
class BTCPaperMonitoringStatus:
    schema_version: str = "1.0"
    created_at: str | None = None
    project_scope: str = "BTC_ONLY"
    symbol: str = "BTC/USDT"
    strategy_profile: str = "balanced_smc_decision_065"
    monitoring_status: str = "BLOCKED"
    runtime_config_status: str = "UNKNOWN"
    validation_gate_status: str = "UNKNOWN"
    paper_execution_enabled: bool = False
    live_trading_enabled: bool = False
    order_submission_enabled: bool = False
    dry_run: bool = True
    kill_switch_enabled: bool = True
    last_heartbeat_at: str | None = None
    last_signal_at: str | None = None
    last_error_at: str | None = None
    consecutive_errors: int = 0
    notes: list[str] = field(default_factory=list)
    issues: list[BTCPaperMonitoringIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "project_scope": self.project_scope,
            "symbol": self.symbol,
            "strategy_profile": self.strategy_profile,
            "monitoring_status": self.monitoring_status,
            "runtime_config_status": self.runtime_config_status,
            "validation_gate_status": self.validation_gate_status,
            "paper_execution_enabled": self.paper_execution_enabled,
            "live_trading_enabled": self.live_trading_enabled,
            "order_submission_enabled": self.order_submission_enabled,
            "dry_run": self.dry_run,
            "kill_switch_enabled": self.kill_switch_enabled,
            "last_heartbeat_at": self.last_heartbeat_at,
            "last_signal_at": self.last_signal_at,
            "last_error_at": self.last_error_at,
            "consecutive_errors": self.consecutive_errors,
            "notes": list(self.notes),
            "issues": [issue.to_dict() for issue in self.issues],
        }
