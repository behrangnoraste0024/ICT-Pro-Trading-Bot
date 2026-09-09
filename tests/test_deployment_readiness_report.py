from __future__ import annotations

from models.deployment_readiness import DeploymentReadinessCheck, DeploymentReadinessReport
from reporting.deployment_readiness_report import format_deployment_readiness_report


def test_report_rendering_is_deterministic_and_sanitized() -> None:
    report = DeploymentReadinessReport(
        readiness_status="NOT_READY",
        total_checks=2,
        passed_checks=1,
        failed_checks=1,
        checks=[
            DeploymentReadinessCheck(
                check_id="a_check",
                status="READY",
                reason_code="EVIDENCE_PRESENT",
                description="Safe local evidence exists.",
                evidence_type="path_exists",
                path="safe/path",
            ),
            DeploymentReadinessCheck(
                check_id="b_check",
                status="NOT_READY",
                reason_code="EVIDENCE_MISSING",
                description="Safe local evidence is missing.",
                evidence_type="path_exists",
                path="missing/path",
            ),
        ],
    )

    first = format_deployment_readiness_report(report)
    second = format_deployment_readiness_report(report)

    assert first == second
    assert "===== DEPLOYMENT READINESS DIAGNOSTIC =====" in first
    assert "Readiness Status : NOT_READY" in first
    assert "a_check | path_exists | READY | EVIDENCE_PRESENT | safe/path" in first
    assert "b_check | path_exists | NOT_READY | EVIDENCE_MISSING | missing/path" in first
    assert "secret" not in first.casefold()
    assert "traceback" not in first.casefold()
    assert "authorization:" not in first.casefold()
    assert "signature=" not in first.casefold()
