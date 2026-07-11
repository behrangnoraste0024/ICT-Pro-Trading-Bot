from __future__ import annotations

from models.btc_futures_paper_position import (
    BTCFuturesPaperActionResult,
    BTCFuturesPaperLedgerSummary,
    BTCFuturesPaperValidationReport,
)


def format_btc_futures_paper_validation_report(report: BTCFuturesPaperValidationReport) -> str:
    config = report.config
    lines = [
        "===== BTC FUTURES PAPER POSITION CONFIG VALIDATION =====",
        f"Config Path              : {report.config_path}",
        f"Status                   : {report.status}",
        f"Symbol                   : {_get(config, 'symbol')}",
        f"Exchange Symbol          : {_get(config, 'exchange_symbol')}",
        f"Market Type              : {_get(config, 'market_type')}",
        f"Contract Type            : {_get(config, 'futures_contract_type')}",
        f"Profile                  : {_get(config, 'strategy_profile')}",
        f"Simulation Enabled       : {_fmt_bool(_get(config, 'position_simulation_enabled'))}",
        f"Simulation Only          : {_fmt_bool(_get(config, 'simulation_only'))}",
        f"Dry Run Only             : {_fmt_bool(_get(config, 'dry_run_only'))}",
        f"Margin Mode              : {_get(config, 'margin_mode')}",
        f"Position Mode            : {_get(config, 'position_mode')}",
        f"Allowed Leverage         : {_leverage_list(_get(config, 'allowed_leverage'))}",
        f"Default Leverage         : {_get(config, 'default_leverage')}x",
        f"Initial Balance          : {_fmt_num(_get(config, 'initial_account_balance'))}",
        f"State Path               : {_get(config, 'state_path')}",
        f"Ledger Path              : {_get(config, 'ledger_path')}",
        f"Local State Write        : {_fmt_bool(_get(config, 'allow_local_futures_state_write'))}",
        f"Local Ledger Write       : {_fmt_bool(_get(config, 'allow_local_futures_ledger_write'))}",
        f"Local Position Creation  : {_fmt_bool(_get(config, 'allow_local_paper_futures_position_creation'))}",
        f"Private API              : {_fmt_bool(_get(config, 'allow_private_api'))}",
        f"Trading API              : {_fmt_bool(_get(config, 'allow_trading_api'))}",
        f"Real Orders              : {_fmt_bool(_get(config, 'allow_real_order_submission'))}",
        f"Exchange Position        : {_fmt_bool(_get(config, 'allow_real_position_creation'))}",
        f"Testnet Orders           : {_fmt_bool(_get(config, 'allow_testnet_order_submission'))}",
        f"Runner Mutation          : {_fmt_bool(_get(config, 'allow_runner_state_mutation'))}",
        f"Execution Mutation       : {_fmt_bool(_get(config, 'allow_execution_state_mutation'))}",
        f"Runtime Config           : {report.diagnostics.get('runtime_config_status', 'UNKNOWN')}",
        f"Monitoring Config        : {report.diagnostics.get('monitoring_config_status', 'UNKNOWN')}",
        f"Runner Config            : {report.diagnostics.get('runner_config_status', 'UNKNOWN')}",
        f"Futures Feed Config      : {report.diagnostics.get('futures_feed_config_status', 'UNKNOWN')}",
        f"Risk Model Config        : {report.diagnostics.get('futures_risk_model_config_status', 'UNKNOWN')}",
        f"Spot Paper Account Config: {report.diagnostics.get('spot_paper_account_config_status', 'UNKNOWN')}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    lines.extend(_issue_lines(report.issues))
    return "\n".join(lines)


def format_btc_futures_paper_action_result(result: BTCFuturesPaperActionResult) -> str:
    state = result.account_state
    position = result.position
    lines = [
        "===== BTC FUTURES LOCAL PAPER POSITION =====",
        f"Action                  : {result.action}",
        f"Status                  : {result.status}",
        f"Decision                : {result.decision}",
        f"Reason                  : {result.reason}",
        f"State Path              : {result.state_path}",
        f"Ledger Path             : {result.ledger_path}",
        "",
        "Account:",
        f"Account Status          : {_get(state, 'account_status')}",
        f"Wallet Balance          : {_fmt_num(_get(state, 'wallet_balance'))}",
        f"Available Balance       : {_fmt_num(_get(state, 'available_balance'))}",
        f"Equity                  : {_fmt_num(_get(state, 'equity'))}",
        f"Peak Equity             : {_fmt_num(_get(state, 'peak_equity'))}",
        f"Drawdown %              : {_fmt_num(_get(state, 'current_drawdown_pct'))}",
        f"Margin Used             : {_fmt_num(_get(state, 'margin_used'))}",
        f"Unrealized PnL          : {_fmt_num(_get(state, 'unrealized_pnl'))}",
        f"Realized PnL            : {_fmt_num(_get(state, 'realized_pnl'))}",
        f"Funding PnL             : {_fmt_num(_get(state, 'funding_pnl'))}",
        f"Total Fees Paid         : {_fmt_num(_get(state, 'total_fees_paid'))}",
        f"Trades Today            : {_get(state, 'trades_today')}",
        "",
        "Position:",
        f"Position ID             : {_get(position, 'position_id')}",
        f"Virtual Order ID        : {_get(position, 'virtual_order_id')}",
        f"Side                    : {_get(position, 'side')}",
        f"Position Status         : {_get(position, 'status')}",
        f"Leverage                : {_get(position, 'leverage')}x",
        f"Quantity                : {_fmt_num(_get(position, 'quantity'))}",
        f"Entry Price             : {_fmt_num(_get(position, 'entry_price'))}",
        f"Mark Price              : {_fmt_num(_get(position, 'mark_price'))}",
        f"Stop Loss               : {_fmt_num(_get(position, 'stop_loss'))}",
        f"Take Profit             : {_fmt_num(_get(position, 'take_profit'))}",
        f"Initial Margin          : {_fmt_num(_get(position, 'initial_margin'))}",
        f"Estimated Liquidation   : {_fmt_num(_get(position, 'estimated_liquidation_price'))}",
        f"Liquidation Distance %  : {_fmt_num(_get(position, 'liquidation_distance_pct'))}",
        f"Position Unrealized PnL : {_fmt_num(_get(position, 'unrealized_pnl'))}",
        f"Position Realized PnL   : {_fmt_num(_get(position, 'realized_pnl'))}",
        f"Entry Fee               : {_fmt_num(_get(position, 'entry_fee'))}",
        f"Exit Fee                : {_fmt_num(_get(position, 'exit_fee'))}",
        f"Total Fees              : {_fmt_num(_get(position, 'total_fees'))}",
        f"Close Price             : {_fmt_num(_get(position, 'close_price'))}",
        f"Close Reason            : {_get(position, 'close_reason')}",
        "",
        "Safety:",
        f"State Written           : {_fmt_bool(result.state_written)}",
        f"Ledger Written          : {_fmt_bool(result.ledger_written)}",
        f"Local Virtual Order     : {_fmt_bool(result.local_virtual_order_created)}",
        f"Local Futures Position  : {_fmt_bool(result.local_paper_futures_position_created)}",
        f"Local Position Closed   : {_fmt_bool(result.local_position_closed)}",
        f"Local Liquidation       : {_fmt_bool(result.local_simulated_liquidation_applied)}",
        f"Local Funding Applied   : {_fmt_bool(result.local_funding_applied)}",
        f"Public Mark Used        : {_fmt_bool(result.public_mark_price_used)}",
        f"Public Funding Used     : {_fmt_bool(result.public_funding_used)}",
        f"Private API Used        : {_fmt_bool(result.private_api_used)}",
        f"API Key Used            : {_fmt_bool(result.api_key_used)}",
        f"Trading API Used        : {_fmt_bool(result.trading_api_used)}",
        f"Account Data Used       : {_fmt_bool(result.account_data_used)}",
        f"Balance Fetch Used      : {_fmt_bool(result.balance_fetch_used)}",
        f"Position Fetch Used     : {_fmt_bool(result.position_fetch_used)}",
        f"Real Order Submitted    : {_fmt_bool(result.real_order_submitted)}",
        f"Testnet Order Submitted : {_fmt_bool(result.testnet_order_submitted)}",
        f"Real Position Created   : {_fmt_bool(result.real_position_created)}",
        f"Exchange Paper Position : {_fmt_bool(result.exchange_paper_position_created)}",
        f"Spot Account Mutated    : {_fmt_bool(result.spot_paper_account_state_mutated)}",
        f"Runner Mutated          : {_fmt_bool(result.runner_state_mutated)}",
        f"Execution Mutated       : {_fmt_bool(result.execution_state_mutated)}",
        f"Exchange State Mutated  : {_fmt_bool(result.exchange_state_mutated)}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    lines.extend(_issue_lines(result.issues))
    return "\n".join(lines)


def format_btc_futures_paper_ledger_summary(summary: BTCFuturesPaperLedgerSummary) -> str:
    return "\n".join(
        [
            "===== BTC FUTURES PAPER LEDGER SUMMARY =====",
            f"Total Entries          : {summary.total_entries}",
            f"Initialized Events     : {summary.initialized_events}",
            f"Position Opened Events : {summary.position_opened_events}",
            f"Mark Events            : {summary.mark_events}",
            f"Funding Events         : {summary.funding_events}",
            f"Manual Close Events    : {summary.manual_close_events}",
            f"Stop Loss Events       : {summary.stop_loss_events}",
            f"Take Profit Events     : {summary.take_profit_events}",
            f"Liquidation Events     : {summary.liquidation_events}",
            f"Rejected Events        : {summary.rejected_events}",
            f"Realized PnL Total     : {_fmt_num(summary.realized_pnl_total)}",
            f"Funding PnL Total      : {_fmt_num(summary.funding_pnl_total)}",
            f"Fee Total              : {_fmt_num(summary.fee_total)}",
            f"Latest Event At        : {summary.latest_event_at}",
            f"Latest Event ID        : {summary.latest_event_id}",
        ]
    )


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


def _fmt_num(value) -> str:
    if value is None:
        return "None"
    return f"{float(value):.6f}"


def _leverage_list(values) -> str:
    if not values:
        return "None"
    return ", ".join(f"{item}x" for item in values)
