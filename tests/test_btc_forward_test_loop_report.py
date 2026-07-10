from __future__ import annotations

from models.btc_forward_test_loop import BTCForwardTestCycleResult, BTCForwardTestRunResult, BTCForwardTestState, BTCForwardTestValidationReport
from reporting.btc_forward_test_loop_report import (
    format_btc_forward_test_run_result,
    format_btc_forward_test_state,
    format_btc_forward_test_validation_report,
)


def test_validation_report_displays_dependency_statuses() -> None:
    report = BTCForwardTestValidationReport(
        config_path="configs/btc_forward_test_loop.json",
        status="PASS",
        diagnostics={
            "runtime_config_status": "PASS",
            "monitoring_config_status": "PASS",
            "runner_config_status": "PASS",
            "signal_config_status": "PASS",
            "trade_candidate_config_status": "PASS",
            "candidate_journal_config_status": "PASS",
        },
    )

    rendered = format_btc_forward_test_validation_report(report)

    assert "BTC FORWARD TEST LOOP CONFIG VALIDATION" in rendered
    assert "Journal Config    : PASS" in rendered


def test_run_report_displays_cycles_and_safety() -> None:
    result = BTCForwardTestRunResult(
        status="PASS",
        cycles_requested=1,
        cycles_completed=1,
        cycles=[BTCForwardTestCycleResult(cycle_number=1, cursor_index=500, signal_decision="APPROVED_DRY_RUN", candidate_created=True, journal_entry_written=True)],
    )

    rendered = format_btc_forward_test_run_result(result)

    assert "BTC FORWARD TEST LOOP DRY-RUN" in rendered
    assert "Order Submitted     : false" in rendered
    assert "APPROVED_DRY_RUN" in rendered


def test_state_report_displays_state_summary() -> None:
    state = BTCForwardTestState(last_cursor_index=502, total_cycles_completed=3, total_journal_entries_written=3)

    rendered = format_btc_forward_test_state(state, "reports/forward_test/state.json")

    assert "BTC FORWARD TEST LOOP STATE" in rendered
    assert "Last Cursor         : 502" in rendered
    assert "Journal Entries     : 3" in rendered
