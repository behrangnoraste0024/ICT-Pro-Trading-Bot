from __future__ import annotations

from dataclasses import dataclass, field


READY = "READY"
NOT_READY = "NOT_READY"


@dataclass(frozen=True)
class DeploymentReadinessCriterion:
    check_id: str
    description: str
    evidence_type: str
    path: str | None = None
    key_path: tuple[str, ...] = field(default_factory=tuple)
    expected_terms: tuple[str, ...] = field(default_factory=tuple)
    expected_env_names: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "description": self.description,
            "evidence_type": self.evidence_type,
            "path": self.path,
            "key_path": list(self.key_path),
            "expected_terms": list(self.expected_terms),
            "expected_env_names": list(self.expected_env_names),
        }


@dataclass(frozen=True)
class DeploymentReadinessCheck:
    check_id: str
    status: str
    reason_code: str
    description: str
    evidence_type: str
    path: str | None = None

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "description": self.description,
            "evidence_type": self.evidence_type,
            "path": self.path,
        }


@dataclass(frozen=True)
class DeploymentReadinessReport:
    readiness_status: str
    total_checks: int
    passed_checks: int
    failed_checks: int
    checks: list[DeploymentReadinessCheck] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "readiness_status": self.readiness_status,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "checks": [check.to_dict() for check in self.checks],
        }
