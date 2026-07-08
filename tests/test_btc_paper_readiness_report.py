from __future__ import annotations

from models.btc_paper_readiness import BTCPaperReadinessCheck, BTCPaperReadinessReport
from reporting.btc_paper_readiness_report import format_btc_paper_readiness_report


def test_report_formats_readiness_section() -> None:
    report = BTCPaperReadinessReport(
        project_scope="BTC_ONLY",
        recommended_profile="balanced_smc_decision_065",
        readiness_status="WARNING",
        passed_checks=1,
        warning_checks=1,
        checks=[
            BTCPaperReadinessCheck("sample", "PASS", "REQUIRED", "ok"),
            BTCPaperReadinessCheck("risk", "WARNING", "RECOMMENDED", "needs config"),
        ],
        next_actions=["Create BTC paper runtime config before executing paper trades."],
    )

    output = format_btc_paper_readiness_report(report)

    assert "===== BTC PAPER TRADING READINESS =====" in output
    assert "Project Scope       : BTC_ONLY" in output
    assert "Readiness Status   : WARNING" in output
    assert "sample | REQUIRED | PASS | ok" in output
    assert "- Create BTC paper runtime config" in output
