from __future__ import annotations

from models.btc_paper_runtime_config import BTCPaperRuntimeConfig, BTCPaperRuntimeConfigValidationReport
from reporting.btc_paper_runtime_config_report import format_btc_paper_runtime_config_report


def test_runtime_config_report_renders_human_output() -> None:
    report = BTCPaperRuntimeConfigValidationReport(
        config_path="configs/btc_paper_runtime.json",
        status="PASS",
        config=BTCPaperRuntimeConfig(),
    )

    output = format_btc_paper_runtime_config_report(report)

    assert "===== BTC PAPER RUNTIME CONFIG VALIDATION =====" in output
    assert "Status            : PASS" in output
    assert "Symbol            : BTC/USDT" in output
    assert "Execution Enabled : false" in output
    assert "Risk/Trade        : 0.50%" in output
    assert "None | INFO | No issues found." in output
