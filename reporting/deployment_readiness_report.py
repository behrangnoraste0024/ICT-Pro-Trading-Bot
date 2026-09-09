from __future__ import annotations

from models.deployment_readiness import DeploymentReadinessReport


def format_deployment_readiness_report(report: DeploymentReadinessReport) -> str:
    lines = [
        "===== DEPLOYMENT READINESS DIAGNOSTIC =====",
        f"Readiness Status : {report.readiness_status}",
        f"Total Checks     : {report.total_checks}",
        f"Passed Checks    : {report.passed_checks}",
        f"Failed Checks    : {report.failed_checks}",
        "",
        "Checks:",
    ]
    for check in report.checks:
        path = check.path or "N/A"
        lines.append(
            f"{check.check_id} | {check.evidence_type} | {check.status} | "
            f"{check.reason_code} | {path} | {check.description}"
        )
    lines.append("===========================================")
    return "\n".join(lines)
