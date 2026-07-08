from __future__ import annotations

from models.btc_paper_signal_evaluation import (
    BTCPaperSignalEvaluationConfig,
    BTCPaperSignalEvaluationResult,
    BTCPaperSignalEvaluationValidationReport,
)
from reporting.btc_paper_signal_evaluation_report import (
    format_btc_paper_signal_evaluation_result,
    format_btc_paper_signal_evaluation_validation_report,
)


def test_signal_validation_report_renders() -> None:
    report = BTCPaperSignalEvaluationValidationReport(
        config_path="configs/btc_paper_signal_evaluation.json",
        status="PASS",
        config=BTCPaperSignalEvaluationConfig(),
        diagnostics={"runtime_config_status": "PASS", "monitoring_config_status": "PASS", "runner_config_status": "PASS"},
    )

    rendered = format_btc_paper_signal_evaluation_validation_report(report)

    assert "BTC PAPER SIGNAL EVALUATION CONFIG VALIDATION" in rendered
    assert "Trade Creation    : false" in rendered
    assert "Runner Config     : PASS" in rendered


def test_signal_evaluation_result_renders() -> None:
    result = BTCPaperSignalEvaluationResult(status="PASS", decision="NONE", candle_count=1000)

    rendered = format_btc_paper_signal_evaluation_result(result)

    assert "BTC PAPER SIGNAL EVALUATION DRY-RUN" in rendered
    assert "Decision            : NONE" in rendered
    assert "Trade Created       : false" in rendered
