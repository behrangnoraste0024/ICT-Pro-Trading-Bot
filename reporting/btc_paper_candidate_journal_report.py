from __future__ import annotations

from models.btc_paper_candidate_journal import (
    BTCPaperCandidateJournalRecordResult,
    BTCPaperCandidateJournalSummary,
    BTCPaperCandidateJournalValidationReport,
)


def format_btc_paper_candidate_journal_validation_report(report: BTCPaperCandidateJournalValidationReport) -> str:
    config = report.config
    journal_path = None if config is None else f"{config.journal_dir}/{config.journal_file_name}"
    lines = [
        "===== BTC PAPER CANDIDATE JOURNAL CONFIG VALIDATION =====",
        f"Config Path       : {report.config_path}",
        f"Status            : {report.status}",
        f"Symbol            : {_get(config, 'symbol')}",
        f"Profile           : {_get(config, 'strategy_profile')}",
        f"Dry Run Only      : {_fmt_bool(_get(config, 'dry_run_only'))}",
        f"Journal Write     : {_fmt_bool(_get(config, 'allow_journal_write'))}",
        f"Journal Format    : {_get(config, 'journal_format')}",
        f"Journal Path      : {journal_path}",
        f"Executable Trade  : {_fmt_bool(_get(config, 'allow_executable_trade_creation'))}",
        f"Paper Persistence : {_fmt_bool(_get(config, 'allow_paper_trade_persistence'))}",
        f"Position Creation : {_fmt_bool(_get(config, 'allow_position_creation'))}",
        f"Order Submission  : {_fmt_bool(_get(config, 'allow_order_submission'))}",
        f"Exchange Connect  : {_fmt_bool(_get(config, 'allow_exchange_connection'))}",
        f"State Mutation    : {_fmt_bool(_get(config, 'allow_state_mutation'))}",
        f"Runtime Config    : {report.diagnostics.get('runtime_config_status', 'UNKNOWN')}",
        f"Monitoring Config : {report.diagnostics.get('monitoring_config_status', 'UNKNOWN')}",
        f"Runner Config     : {report.diagnostics.get('runner_config_status', 'UNKNOWN')}",
        f"Signal Config     : {report.diagnostics.get('signal_config_status', 'UNKNOWN')}",
        f"Candidate Config  : {report.diagnostics.get('trade_candidate_config_status', 'UNKNOWN')}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    if report.issues:
        lines.extend(f"{issue.name} | {issue.severity} | {issue.message}" for issue in report.issues)
    else:
        lines.append("None | INFO | No issues found.")
    return "\n".join(lines)


def format_btc_paper_candidate_journal_record_result(result: BTCPaperCandidateJournalRecordResult) -> str:
    entry = result.entry
    lines = [
        "===== BTC PAPER CANDIDATE JOURNAL DRY-RUN RECORD =====",
        f"Status              : {result.status}",
        f"Action              : {result.action}",
        f"Entry Written       : {_fmt_bool(result.entry_written)}",
        f"Journal Path        : {result.journal_path}",
        f"Reason              : {result.reason}",
        "",
        "Entry:",
        f"Entry ID            : {_get(entry, 'entry_id')}",
        f"Created At          : {_get(entry, 'created_at')}",
        f"Symbol              : {_get(entry, 'symbol')}",
        f"Profile             : {_get(entry, 'strategy_profile')}",
        f"Source              : {_get(entry, 'source')}",
        f"Signal Decision     : {_get(entry, 'signal_decision')}",
        f"Signal Score        : {_get(entry, 'signal_score')}",
        f"Signal Threshold    : {_get(entry, 'signal_threshold')}",
        f"Candidate Decision  : {_get(entry, 'candidate_decision')}",
        f"Candidate Created   : {_fmt_bool(_get(entry, 'candidate_created'))}",
        f"Candidate ID        : {_get(entry, 'candidate_id')}",
        f"Rejection Reason    : {_get(entry, 'rejection_reason')}",
        "",
        "Safety:",
        f"Dry Run Only        : {_fmt_bool(result.dry_run_only)}",
        f"Executable Trade    : {_fmt_bool(result.executable_trade_created)}",
        f"Paper Persisted     : {_fmt_bool(result.paper_trade_persisted)}",
        f"Position Created    : {_fmt_bool(result.position_created)}",
        f"Order Submitted     : {_fmt_bool(result.order_submitted)}",
        f"Exchange Connected  : {_fmt_bool(result.exchange_connected)}",
        f"State Mutated       : {_fmt_bool(result.state_mutated)}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    if result.issues:
        lines.extend(f"{issue.name} | {issue.severity} | {issue.message}" for issue in result.issues)
    else:
        lines.append("None | INFO | No issues found.")
    return "\n".join(lines)


def format_btc_paper_candidate_journal_summary(summary: BTCPaperCandidateJournalSummary) -> str:
    lines = [
        "===== BTC PAPER CANDIDATE JOURNAL SUMMARY =====",
        f"Journal Path        : {summary.journal_path}",
        f"Status              : {summary.status}",
        f"Entries Read        : {summary.total_entries_read}",
        f"Candidates Created  : {summary.candidate_created_count}",
        f"Candidates Rejected : {summary.candidate_rejected_count}",
        f"Warnings            : {summary.warning_count}",
        f"Failures            : {summary.fail_count}",
        f"Latest Entry        : {summary.latest_entry_at}",
        "",
        "Entries:",
        "Created At | Source | Signal Decision | Score | Candidate Decision | Candidate Created | Reason",
    ]
    if summary.entries:
        lines.extend(
            f"{entry.created_at} | {entry.source} | {entry.signal_decision} | {entry.signal_score} | {entry.candidate_decision} | {_fmt_bool(entry.candidate_created)} | {entry.rejection_reason}"
            for entry in summary.entries
        )
    else:
        lines.append("None | None | None | None | None | false | No journal entries found.")
    if summary.issues:
        lines.extend(["", "Issues:", "Name | Severity | Message"])
        lines.extend(f"{issue.name} | {issue.severity} | {issue.message}" for issue in summary.issues)
    return "\n".join(lines)


def _get(obj, name: str):
    if obj is None:
        return None
    return getattr(obj, name)


def _fmt_bool(value) -> str:
    if value is None:
        return "None"
    return str(bool(value)).lower()
