from __future__ import annotations

from models.btc_paper_candidate_journal import (
    BTCPaperCandidateJournalEntry,
    BTCPaperCandidateJournalRecordResult,
    BTCPaperCandidateJournalSummary,
    BTCPaperCandidateJournalValidationReport,
)
from reporting.btc_paper_candidate_journal_report import (
    format_btc_paper_candidate_journal_record_result,
    format_btc_paper_candidate_journal_summary,
    format_btc_paper_candidate_journal_validation_report,
)


def test_validation_report_displays_config_statuses() -> None:
    report = BTCPaperCandidateJournalValidationReport(
        config_path="configs/btc_paper_candidate_journal.json",
        status="PASS",
        diagnostics={
            "runtime_config_status": "PASS",
            "monitoring_config_status": "PASS",
            "runner_config_status": "PASS",
            "signal_config_status": "PASS",
            "trade_candidate_config_status": "PASS",
        },
    )

    rendered = format_btc_paper_candidate_journal_validation_report(report)

    assert "BTC PAPER CANDIDATE JOURNAL CONFIG VALIDATION" in rendered
    assert "Candidate Config  : PASS" in rendered


def test_record_report_displays_entry_and_safety_flags() -> None:
    entry = BTCPaperCandidateJournalEntry(
        entry_id="BTC-JOURNAL-1",
        created_at="2026-01-01T00:00:00+00:00",
        signal_decision="APPROVED_DRY_RUN",
        signal_score=0.8,
        signal_threshold=0.65,
        candidate_decision="CANDIDATE_CREATED_DRY_RUN",
        candidate_created=True,
        candidate_id="BTC-DRYRUN-1",
    )
    result = BTCPaperCandidateJournalRecordResult(status="PASS", entry_written=True, journal_path="journal.jsonl", entry=entry)

    rendered = format_btc_paper_candidate_journal_record_result(result)

    assert "BTC PAPER CANDIDATE JOURNAL DRY-RUN RECORD" in rendered
    assert "Entry Written       : true" in rendered
    assert "Candidate Created   : true" in rendered
    assert "Order Submitted     : false" in rendered


def test_summary_report_displays_entry_table() -> None:
    summary = BTCPaperCandidateJournalSummary(
        journal_path="journal.jsonl",
        total_entries_read=1,
        candidate_created_count=0,
        candidate_rejected_count=1,
        entries=[BTCPaperCandidateJournalEntry(created_at="2026-01-01T00:00:00+00:00", candidate_created=False, rejection_reason="too low")],
    )

    rendered = format_btc_paper_candidate_journal_summary(summary)

    assert "BTC PAPER CANDIDATE JOURNAL SUMMARY" in rendered
    assert "Entries Read        : 1" in rendered
    assert "too low" in rendered
