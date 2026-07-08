from __future__ import annotations

from models.btc_paper_monitoring import (
    BTCPaperMonitoringConfig,
    BTCPaperMonitoringStatus,
    BTCPaperMonitoringValidationReport,
)
from reporting.btc_paper_monitoring_report import (
    format_btc_paper_monitoring_status_report,
    format_btc_paper_monitoring_validation_report,
)


def test_validation_report_renders_human_output() -> None:
    report = BTCPaperMonitoringValidationReport(
        config_path="configs/btc_paper_monitoring.json",
        status="PASS",
        config=BTCPaperMonitoringConfig(),
        diagnostics={"runtime_config_status": "PASS"},
    )

    rendered = format_btc_paper_monitoring_validation_report(report)

    assert "BTC PAPER MONITORING CONFIG VALIDATION" in rendered
    assert "Runtime Config    : PASS" in rendered
    assert "Heartbeat Stale   : 120s" in rendered


def test_status_report_renders_human_output() -> None:
    status = BTCPaperMonitoringStatus(monitoring_status="READY", runtime_config_status="PASS")

    rendered = format_btc_paper_monitoring_status_report(status)

    assert "BTC PAPER MONITORING STATUS" in rendered
    assert "Monitoring Status  : READY" in rendered
    assert "Paper Execution    : false" in rendered
