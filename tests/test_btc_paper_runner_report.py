from __future__ import annotations

from models.btc_paper_runner import BTCPaperRunnerStatus, BTCPaperRunnerTransitionResult
from reporting.btc_paper_runner_report import format_btc_paper_runner_status_report


def test_runner_report_renders_status_and_transition() -> None:
    status = BTCPaperRunnerStatus(state="RUNNING", runtime_config_status="PASS", monitoring_config_status="PASS")
    transition = BTCPaperRunnerTransitionResult(
        action="START",
        accepted=True,
        previous_state="READY",
        current_state="RUNNING",
        status=status,
        message="Dry-run lifecycle only. No signals, trades, orders, or exchange connections were executed.",
    )

    rendered = format_btc_paper_runner_status_report(status, transition)

    assert "BTC PAPER RUNNER DRY-RUN STATUS" in rendered
    assert "State               : RUNNING" in rendered
    assert "Order Submission    : false" in rendered
    assert "Transition:" in rendered
    assert "Accepted            : true" in rendered
