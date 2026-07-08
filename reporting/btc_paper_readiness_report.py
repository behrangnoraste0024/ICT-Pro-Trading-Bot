from __future__ import annotations

from models.btc_paper_readiness import BTCPaperReadinessReport


def format_btc_paper_readiness_report(report: BTCPaperReadinessReport) -> str:
    lines = [
        "===== BTC PAPER TRADING READINESS =====",
        f"Project Scope       : {report.project_scope}",
        f"Recommended Profile: {report.recommended_profile}",
        f"Readiness Status   : {report.readiness_status}",
        f"Checks             : pass={report.passed_checks} warning={report.warning_checks} fail={report.failed_checks} skipped={report.skipped_checks}",
        "",
        "Checks:",
        "Name | Severity | Status | Message",
    ]
    for check in report.checks:
        lines.append(f"{check.name} | {check.severity} | {check.status} | {check.message}")
    lines.extend(["", "Next Actions:"])
    if report.next_actions:
        lines.extend(f"- {action}" for action in report.next_actions)
    else:
        lines.append("- None")
    return "\n".join(lines)
