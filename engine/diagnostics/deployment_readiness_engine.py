from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.deployment_readiness import (
    NOT_READY,
    READY,
    DeploymentReadinessCheck,
    DeploymentReadinessCriterion,
    DeploymentReadinessReport,
)


DEFAULT_DEPLOYMENT_READINESS_CRITERIA: tuple[DeploymentReadinessCriterion, ...] = (
    DeploymentReadinessCriterion(
        check_id="backup_runbook",
        description="Backup procedure documentation is present.",
        evidence_type="text_contains_any",
        path="docs/deployment_operations_runbook.md",
        expected_terms=("backup",),
    ),
    DeploymentReadinessCriterion(
        check_id="database_migrations",
        description="Database migration surface is present.",
        evidence_type="path_exists",
        path="alembic/versions",
    ),
    DeploymentReadinessCriterion(
        check_id="deployment_runbook",
        description="Deployment runbook documentation is present.",
        evidence_type="text_contains_any",
        path="docs/deployment_operations_runbook.md",
        expected_terms=("deployment",),
    ),
    DeploymentReadinessCriterion(
        check_id="disaster_recovery_runbook",
        description="Disaster recovery documentation is present.",
        evidence_type="text_contains_any",
        path="docs/deployment_operations_runbook.md",
        expected_terms=("disaster recovery",),
    ),
    DeploymentReadinessCriterion(
        check_id="environment_variable_names",
        description="Expected environment variable names are defined without value inspection.",
        evidence_type="env_name_expectation",
        expected_env_names=("ICT_DATABASE_URL", "ICT_RUNTIME_ENV"),
    ),
    DeploymentReadinessCriterion(
        check_id="health_surface",
        description="Backend health or status surface is represented in repository code.",
        evidence_type="text_contains_any",
        path="api/live_control_plane_routes.py",
        expected_terms=("operator/status", "kill-switch/status", "recovery/status"),
    ),
    DeploymentReadinessCriterion(
        check_id="monitoring_surface",
        description="Operational metrics surface is represented in repository code.",
        evidence_type="path_exists",
        path="infrastructure/observability/operational_metrics.py",
    ),
    DeploymentReadinessCriterion(
        check_id="operator_access_control",
        description="Operator access-control policy documentation is present.",
        evidence_type="text_contains_any",
        path="docs/deployment_operations_runbook.md",
        expected_terms=("operator access control", "operator access"),
    ),
    DeploymentReadinessCriterion(
        check_id="process_supervision",
        description="Process supervision definition is represented in repository.",
        evidence_type="text_contains_any",
        path="docs/deployment_operations_runbook.md",
        expected_terms=("process supervision", "supervisor"),
    ),
    DeploymentReadinessCriterion(
        check_id="restore_runbook",
        description="Restore procedure documentation is present.",
        evidence_type="text_contains_any",
        path="docs/deployment_operations_runbook.md",
        expected_terms=("restore",),
    ),
    DeploymentReadinessCriterion(
        check_id="rollback_runbook",
        description="Rollback procedure documentation is present.",
        evidence_type="text_contains_any",
        path="docs/deployment_operations_runbook.md",
        expected_terms=("rollback",),
    ),
    DeploymentReadinessCriterion(
        check_id="versioned_configuration",
        description="Versioned configuration schema is present.",
        evidence_type="json_key",
        path="configs/validation_baseline.json",
        key_path=("schema_version",),
    ),
)


class DeploymentReadinessEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        criteria: tuple[DeploymentReadinessCriterion, ...] | None = None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.criteria = criteria or DEFAULT_DEPLOYMENT_READINESS_CRITERIA

    def evaluate(self) -> DeploymentReadinessReport:
        checks = [self._evaluate_criterion(criterion) for criterion in self._ordered_criteria()]
        passed = sum(1 for check in checks if check.status == READY)
        failed = len(checks) - passed
        readiness_status = READY if checks and failed == 0 else NOT_READY
        return DeploymentReadinessReport(
            readiness_status=readiness_status,
            total_checks=len(checks),
            passed_checks=passed,
            failed_checks=failed,
            checks=checks,
        )

    def _ordered_criteria(self) -> list[DeploymentReadinessCriterion]:
        return sorted(self.criteria, key=lambda criterion: criterion.check_id)

    def _evaluate_criterion(self, criterion: DeploymentReadinessCriterion) -> DeploymentReadinessCheck:
        try:
            if criterion.evidence_type == "path_exists":
                return self._path_exists(criterion)
            if criterion.evidence_type == "json_key":
                return self._json_key(criterion)
            if criterion.evidence_type == "text_contains_any":
                return self._text_contains_any(criterion)
            if criterion.evidence_type == "env_name_expectation":
                return self._env_name_expectation(criterion)
            return self._check(criterion, NOT_READY, "UNSUPPORTED_EVIDENCE_TYPE")
        except (OSError, UnicodeError, json.JSONDecodeError):
            return self._check(criterion, NOT_READY, "EVIDENCE_UNREADABLE")

    def _path_exists(self, criterion: DeploymentReadinessCriterion) -> DeploymentReadinessCheck:
        if not criterion.path:
            return self._check(criterion, NOT_READY, "PATH_NOT_SPECIFIED")
        path = self._resolve_path(criterion.path)
        if path.exists():
            return self._check(criterion, READY, "EVIDENCE_PRESENT")
        return self._check(criterion, NOT_READY, "EVIDENCE_MISSING")

    def _json_key(self, criterion: DeploymentReadinessCriterion) -> DeploymentReadinessCheck:
        if not criterion.path:
            return self._check(criterion, NOT_READY, "PATH_NOT_SPECIFIED")
        if not criterion.key_path:
            return self._check(criterion, NOT_READY, "JSON_KEY_NOT_SPECIFIED")
        path = self._resolve_path(criterion.path)
        if not path.exists():
            return self._check(criterion, NOT_READY, "EVIDENCE_MISSING")
        payload = json.loads(path.read_text(encoding="utf-8"))
        current: Any = payload
        for key in criterion.key_path:
            if not isinstance(current, dict) or key not in current:
                return self._check(criterion, NOT_READY, "JSON_KEY_MISSING")
            current = current[key]
        if current in (None, "", [], {}):
            return self._check(criterion, NOT_READY, "JSON_KEY_EMPTY")
        return self._check(criterion, READY, "EVIDENCE_PRESENT")

    def _text_contains_any(self, criterion: DeploymentReadinessCriterion) -> DeploymentReadinessCheck:
        if not criterion.path:
            return self._check(criterion, NOT_READY, "PATH_NOT_SPECIFIED")
        if not criterion.expected_terms:
            return self._check(criterion, NOT_READY, "TEXT_MARKER_NOT_SPECIFIED")
        path = self._resolve_path(criterion.path)
        if not path.exists():
            return self._check(criterion, NOT_READY, "EVIDENCE_MISSING")
        text = path.read_text(encoding="utf-8").casefold()
        if any(term.casefold() in text for term in criterion.expected_terms):
            return self._check(criterion, READY, "EVIDENCE_PRESENT")
        return self._check(criterion, NOT_READY, "TEXT_MARKER_MISSING")

    def _env_name_expectation(self, criterion: DeploymentReadinessCriterion) -> DeploymentReadinessCheck:
        names = criterion.expected_env_names
        if not names:
            return self._check(criterion, NOT_READY, "ENV_NAMES_MISSING")
        if any(not name or "=" in name or name.strip() != name for name in names):
            return self._check(criterion, NOT_READY, "ENV_NAME_INVALID")
        if tuple(sorted(names)) != names:
            return self._check(criterion, NOT_READY, "ENV_NAMES_NOT_STABLE")
        return self._check(criterion, READY, "ENV_NAMES_DEFINED")

    def _resolve_path(self, path_text: str) -> Path:
        path = Path(path_text)
        if path.is_absolute():
            return path
        return self.repo_root / path

    def _check(
        self,
        criterion: DeploymentReadinessCriterion,
        status: str,
        reason_code: str,
    ) -> DeploymentReadinessCheck:
        return DeploymentReadinessCheck(
            check_id=criterion.check_id,
            status=status,
            reason_code=reason_code,
            description=criterion.description,
            evidence_type=criterion.evidence_type,
            path=criterion.path,
        )
