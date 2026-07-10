from __future__ import annotations

from models.btc_paper_account import BTCPaperAccountActionResult, BTCPaperAccountLedgerSummary, BTCPaperAccountValidationReport


def format_btc_paper_account_validation_report(report: BTCPaperAccountValidationReport) -> str:
    config = report.config
    lines = [
        "===== BTC LOCAL PAPER ACCOUNT CONFIG VALIDATION =====",
        f"Config Path       : {report.config_path}",
        f"Status            : {report.status}",
        f"Symbol            : {_get(config, 'symbol')}",
        f"Profile           : {_get(config, 'strategy_profile')}",
        f"Simulation Only   : {_fmt_bool(_get(config, 'simulation_only'))}",
        f"Dry Run Only      : {_fmt_bool(_get(config, 'dry_run_only'))}",
        f"Paper Enabled     : {_fmt_bool(_get(config, 'paper_account_enabled'))}",
        f"Initial Balance   : {_money(_get(config, 'initial_balance'))} USDT",
        f"Risk/Trade        : {_pct(_get(config, 'risk_per_trade_pct'))}",
        f"Max Open Positions: {_get(config, 'max_open_virtual_positions')}",
        f"Max Trades/Day    : {_get(config, 'max_virtual_trades_per_day')}",
        f"Local State Write : {_fmt_bool(_get(config, 'allow_local_paper_state_write'))}",
        f"Local Ledger Write: {_fmt_bool(_get(config, 'allow_local_paper_ledger_write'))}",
        f"Virtual Orders    : {_fmt_bool(_get(config, 'allow_virtual_order_creation'))}",
        f"Virtual Positions : {_fmt_bool(_get(config, 'allow_virtual_position_creation'))}",
        f"Private API       : {_fmt_bool(_get(config, 'allow_private_api'))}",
        f"API Key Usage     : {_fmt_bool(_get(config, 'allow_api_key_usage'))}",
        f"Trading API       : {_fmt_bool(_get(config, 'allow_trading_api'))}",
        f"Real Orders       : {_fmt_bool(_get(config, 'allow_real_order_submission'))}",
        f"Real Positions    : {_fmt_bool(_get(config, 'allow_real_position_creation'))}",
        f"Executable Trade  : {_fmt_bool(_get(config, 'allow_executable_trade_creation'))}",
        f"Runner Mutation   : {_fmt_bool(_get(config, 'allow_runner_state_mutation'))}",
        f"Execution Mutation: {_fmt_bool(_get(config, 'allow_execution_state_mutation'))}",
        f"Runtime Config    : {report.diagnostics.get('runtime_config_status', 'UNKNOWN')}",
        f"Monitoring Config : {report.diagnostics.get('monitoring_config_status', 'UNKNOWN')}",
        f"Runner Config     : {report.diagnostics.get('runner_config_status', 'UNKNOWN')}",
        f"Signal Config     : {report.diagnostics.get('signal_config_status', 'UNKNOWN')}",
        f"Candidate Config  : {report.diagnostics.get('trade_candidate_config_status', 'UNKNOWN')}",
        f"Journal Config    : {report.diagnostics.get('candidate_journal_config_status', 'UNKNOWN')}",
        f"Forward Config    : {report.diagnostics.get('forward_test_config_status', 'UNKNOWN')}",
        f"Live Feed Config  : {report.diagnostics.get('live_market_feed_config_status', 'UNKNOWN')}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    lines.extend(_issue_lines(report.issues))
    return "\n".join(lines)


def format_btc_paper_account_action_result(result: BTCPaperAccountActionResult) -> str:
    state = result.account_state
    safety = result.safety_summary
    lines = [
        "===== BTC LOCAL PAPER ACCOUNT =====",
        f"Action             : {result.action}",
        f"Status             : {result.status}",
        f"Decision           : {result.decision}",
        f"State Path         : {result.state_path}",
        f"Ledger Path        : {result.ledger_path}",
        f"State Exists       : {_fmt_bool(result.state_exists)}",
        f"Reason             : {result.reason}",
        "",
        "Account:",
        f"Initial Balance    : {_money(_get(state, 'initial_balance'))}",
        f"Cash Balance       : {_money(_get(state, 'cash_balance'))}",
        f"Equity             : {_money(_get(state, 'equity'))}",
        f"Realized PnL       : {_money(_get(state, 'realized_pnl'))}",
        f"Unrealized PnL     : {_money(_get(state, 'unrealized_pnl'))}",
        f"Total Fees         : {_money(_get(state, 'total_fees'))}",
        f"Total Slippage     : {_money(_get(state, 'total_slippage'))}",
        f"Open Positions     : {_count(_get(state, 'open_positions'))}",
        f"Closed Positions   : {_count(_get(state, 'closed_positions'))}",
        f"Pending Orders     : {_count(_get(state, 'pending_orders'))}",
        f"Filled Orders      : {_count(_get(state, 'filled_orders'))}",
        f"No-Action Events   : {_get(state, 'total_no_action_events')}",
        f"Risk Rejections    : {_get(state, 'total_risk_rejections')}",
        "",
        "Last Action:",
        f"Virtual Order      : {_fmt_bool(result.virtual_order_created)}",
        f"Virtual Position   : {_fmt_bool(result.virtual_position_created)}",
        f"No Action Recorded : {_fmt_bool(result.no_action_recorded)}",
        f"Mark Updated       : {_fmt_bool(result.mark_to_market_updated)}",
        "",
        "Safety:",
        f"Simulation Only    : {_fmt_bool(safety.get('simulation_only'))}",
        f"Dry Run Only       : {_fmt_bool(safety.get('dry_run_only'))}",
        f"Private API Used   : {_fmt_bool(safety.get('private_api_used'))}",
        f"API Key Used       : {_fmt_bool(safety.get('api_key_used'))}",
        f"Trading API Used   : {_fmt_bool(safety.get('trading_api_used'))}",
        f"Account Data Used  : {_fmt_bool(safety.get('account_data_used'))}",
        f"Balance Fetch Used : {_fmt_bool(safety.get('balance_fetch_used'))}",
        f"Position Fetch Used: {_fmt_bool(safety.get('position_fetch_used'))}",
        f"Real Order Sent    : {_fmt_bool(safety.get('real_order_submitted'))}",
        f"Order Cancelled    : {_fmt_bool(safety.get('order_cancelled'))}",
        f"Real Position      : {_fmt_bool(safety.get('real_position_created'))}",
        f"Trading Connection : {_fmt_bool(safety.get('exchange_connected_for_trading'))}",
        f"Executable Trade   : {_fmt_bool(safety.get('executable_trade_created'))}",
        f"Runner Mutated     : {_fmt_bool(safety.get('runner_state_mutated'))}",
        f"Execution Mutated  : {_fmt_bool(safety.get('execution_state_mutated'))}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    lines.extend(_issue_lines(result.issues))
    return "\n".join(lines)


def format_btc_paper_account_ledger_summary(summary: BTCPaperAccountLedgerSummary) -> str:
    lines = [
        "===== BTC LOCAL PAPER ACCOUNT LEDGER SUMMARY =====",
        f"Ledger Path        : {summary.ledger_path}",
        f"Status             : {summary.status}",
        f"Entries Read       : {summary.entries_read}",
        f"Account Init       : {summary.account_initialized}",
        f"No Action          : {summary.no_action}",
        f"Virtual Orders     : {summary.virtual_orders}",
        f"Virtual Positions  : {summary.virtual_positions}",
        f"Mark To Market     : {summary.mark_to_market}",
        f"Risk Rejections    : {summary.risk_rejections}",
        f"Errors             : {summary.errors}",
        f"Latest Entry       : {summary.latest_entry_at}",
        "",
        "Entries:",
        "Created At | Type | Decision | Balance After | Equity After | Reason",
    ]
    if summary.entries:
        lines.extend(f"{entry.created_at} | {entry.entry_type} | {entry.decision} | {entry.balance_after} | {entry.equity_after} | {entry.reason}" for entry in summary.entries)
    else:
        lines.append("None | None | None | None | None | No entries.")
    lines.extend(["", "Issues:", "Name | Severity | Message"])
    lines.extend(_issue_lines(summary.issues))
    return "\n".join(lines)


def _issue_lines(issues) -> list[str]:
    if not issues:
        return ["None | INFO | No issues found."]
    return [f"{issue.name} | {issue.severity} | {issue.message}" for issue in issues]


def _get(obj, name: str):
    if obj is None:
        return None
    return getattr(obj, name)


def _fmt_bool(value) -> str:
    if value is None:
        return "None"
    return str(bool(value)).lower()


def _money(value) -> str:
    if value is None:
        return "None"
    return f"{float(value):.2f}"


def _pct(value) -> str:
    if value is None:
        return "None"
    return f"{float(value):.2f}%"


def _count(value) -> int | str:
    if value is None:
        return "None"
    return len(value)
