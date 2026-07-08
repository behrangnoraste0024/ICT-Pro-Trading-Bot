from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BTCPaperReadinessCheck:
    name: str
    status: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BTCPaperReadinessReport:
    schema_version: str = "1.0"
    created_at: str | None = None
    project_scope: str = "BTC_ONLY"
    recommended_profile: str = "balanced_smc_decision_065"
    readiness_status: str = "WARNING"
    passed_checks: int = 0
    warning_checks: int = 0
    failed_checks: int = 0
    skipped_checks: int = 0
    checks: list[BTCPaperReadinessCheck] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "project_scope": self.project_scope,
            "recommended_profile": self.recommended_profile,
            "readiness_status": self.readiness_status,
            "passed_checks": self.passed_checks,
            "warning_checks": self.warning_checks,
            "failed_checks": self.failed_checks,
            "skipped_checks": self.skipped_checks,
            "checks": [check.to_dict() for check in self.checks],
            "next_actions": list(self.next_actions),
        }
