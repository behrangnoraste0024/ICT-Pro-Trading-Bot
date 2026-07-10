from __future__ import annotations

from models.btc_forward_test_loop import BTCForwardTestRunResult, BTCForwardTestState, BTCForwardTestValidationReport


def format_btc_forward_test_validation_report(report: BTCForwardTestValidationReport) -> str:
    config = report.config
    lines = [
        "===== BTC FORWARD TEST LOOP CONFIG VALIDATION =====",
        f"Config Path       : {report.config_path}",
        f"Status            : {report.status}",
        f"Symbol            : {_get(config, 'symbol')}",
        f"Profile           : {_get(config, 'strategy_profile')}",
        f"Dry Run Only      : {_fmt_bool(_get(config, 'dry_run_only'))}",
        f"Cycle Mode        : {_get(config, 'cycle_mode')}",
        f"Max Cycles        : {_get(config, 'max_cycles')}",
        f"Live Market Data  : {_fmt_bool(_get(config, 'allow_live_market_data'))}",
        f"Exchange Connect  : {_fmt_bool(_get(config, 'allow_exchange_connection'))}",
        f"Order Submission  : {_fmt_bool(_get(config, 'allow_order_submission'))}",
        f"Position Creation : {_fmt_bool(_get(config, 'allow_position_creation'))}",
        f"Executable Trade  : {_fmt_bool(_get(config, 'allow_executable_trade_creation'))}",
        f"State Mutation    : {_fmt_bool(_get(config, 'allow_state_mutation'))}",
        f"Runtime Config    : {report.diagnostics.get('runtime_config_status', 'UNKNOWN')}",
        f"Monitoring Config : {report.diagnostics.get('monitoring_config_status', 'UNKNOWN')}",
        f"Runner Config     : {report.diagnostics.get('runner_config_status', 'UNKNOWN')}",
        f"Signal Config     : {report.diagnostics.get('signal_config_status', 'UNKNOWN')}",
        f"Candidate Config  : {report.diagnostics.get('trade_candidate_config_status', 'UNKNOWN')}",
        f"Journal Config    : {report.diagnostics.get('candidate_journal_config_status', 'UNKNOWN')}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    if report.issues:
        lines.extend(f"{issue.name} | {issue.severity} | {issue.message}" for issue in report.issues)
    else:
        lines.append("None | INFO | No issues found.")
    return "\n".join(lines)


def format_btc_forward_test_run_result(result: BTCForwardTestRunResult) -> str:
    lines = [
        "===== BTC FORWARD TEST LOOP DRY-RUN =====",
        f"Project Scope       : {result.project_scope}",
        f"Symbol              : {result.symbol}",
        f"Profile             : {result.strategy_profile}",
        f"Status              : {result.status}",
        f"Cycles Requested    : {result.cycles_requested}",
        f"Cycles Completed    : {result.cycles_completed}",
        f"Cycles Failed       : {result.cycles_failed}",
        f"Candidates Created  : {result.candidates_created}",
        f"Candidates Rejected : {result.candidates_rejected}",
        f"Journal Entries     : {result.journal_entries_written}",
        f"Warnings            : {result.warnings}",
        f"Failures            : {result.failures}",
        f"Start Index         : {result.start_index}",
        f"End Index           : {result.end_index}",
        "",
        "Safety:",
        f"Dry Run Only        : {_fmt_bool(result.dry_run_only)}",
        f"Live Market Data    : {_fmt_bool(result.live_market_data_used)}",
        f"Executable Trade    : {_fmt_bool(result.executable_trade_created)}",
        f"Paper Persisted     : {_fmt_bool(result.paper_trade_persisted)}",
        f"Position Created    : {_fmt_bool(result.position_created)}",
        f"Order Submitted     : {_fmt_bool(result.order_submitted)}",
        f"Exchange Connected  : {_fmt_bool(result.exchange_connected)}",
        f"State Mutated       : {_fmt_bool(result.state_mutated)}",
        "",
        "Cycles:",
        "Cycle | Cursor | Timestamp | Signal Decision | Score | Candidate Decision | Candidate Created | Journal Written | Reason",
    ]
    if result.cycles:
        lines.extend(
            f"{cycle.cycle_number} | {cycle.cursor_index} | {cycle.candle_timestamp} | {cycle.signal_decision} | {cycle.signal_score} | {cycle.candidate_decision} | {_fmt_bool(cycle.candidate_created)} | {_fmt_bool(cycle.journal_entry_written)} | {cycle.reason}"
            for cycle in result.cycles
        )
    else:
        lines.append("None | None | None | None | None | None | false | false | No cycles ran.")
    lines.extend(["", "Issues:", "Name | Severity | Message"])
    if result.issues:
        lines.extend(f"{issue.name} | {issue.severity} | {issue.message}" for issue in result.issues)
    else:
        lines.append("None | INFO | No issues found.")
    return "\n".join(lines)


def format_btc_forward_test_state(state: BTCForwardTestState, state_path: str | None = None) -> str:
    return "\n".join(
        [
            "===== BTC FORWARD TEST LOOP STATE =====",
            f"State Path          : {state_path}",
            f"Status              : {state.last_status}",
            f"Last Cursor         : {state.last_cursor_index}",
            f"Total Cycles        : {state.total_cycles_completed}",
            f"Candidates Created  : {state.total_candidates_created}",
            f"Candidates Rejected : {state.total_candidates_rejected}",
            f"Journal Entries     : {state.total_journal_entries_written}",
            f"Last Cycle At       : {state.last_cycle_at}",
            f"Reason              : {state.last_reason}",
            "",
            "Safety:",
            f"Executable Trade    : {_fmt_bool(state.executable_trade_created)}",
            f"Paper Persisted     : {_fmt_bool(state.paper_trade_persisted)}",
            f"Position Created    : {_fmt_bool(state.position_created)}",
            f"Order Submitted     : {_fmt_bool(state.order_submitted)}",
            f"Exchange Connected  : {_fmt_bool(state.exchange_connected)}",
            f"State Mutated       : {_fmt_bool(state.state_mutated)}",
        ]
    )


def _get(obj, name: str):
    if obj is None:
        return None
    return getattr(obj, name)


def _fmt_bool(value) -> str:
    if value is None:
        return "None"
    return str(bool(value)).lower()
