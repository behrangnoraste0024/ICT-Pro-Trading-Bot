from __future__ import annotations

from models.btc_futures_risk_model import BTCFuturesLeverageComparisonResult, BTCFuturesRiskResult, BTCFuturesRiskValidationReport


def format_btc_futures_risk_validation_report(report: BTCFuturesRiskValidationReport) -> str:
    config = report.config
    lines = [
        "===== BTC FUTURES RISK MODEL CONFIG VALIDATION =====",
        f"Config Path           : {report.config_path}",
        f"Status                : {report.status}",
        f"Symbol                : {_get(config, 'symbol')}",
        f"Exchange Symbol       : {_get(config, 'exchange_symbol')}",
        f"Market Type           : {_get(config, 'market_type')}",
        f"Contract Type         : {_get(config, 'futures_contract_type')}",
        f"Profile               : {_get(config, 'strategy_profile')}",
        f"Simulation Only       : {_fmt_bool(_get(config, 'simulation_only'))}",
        f"Dry Run Only          : {_fmt_bool(_get(config, 'dry_run_only'))}",
        f"Model                 : {_get(config, 'model_name')}",
        f"Model Accuracy        : {_get(config, 'model_accuracy')}",
        f"Exchange Exact        : {_fmt_bool(_get(config, 'exchange_exact_liquidation'))}",
        f"Margin Mode           : {_get(config, 'margin_mode')}",
        f"Position Mode         : {_get(config, 'position_mode')}",
        f"Allowed Leverage      : {_leverage_list(_get(config, 'allowed_leverage'))}",
        f"Maximum Leverage      : {_get(config, 'max_leverage')}x",
        f"Leverage Simulation   : {_fmt_bool(_get(config, 'allow_leverage_simulation'))}",
        f"Liquidation Modeling  : {_fmt_bool(_get(config, 'allow_liquidation_modeling'))}",
        f"Private API           : {_fmt_bool(_get(config, 'allow_private_api'))}",
        f"API Key Usage         : {_fmt_bool(_get(config, 'allow_api_key_usage'))}",
        f"Trading API           : {_fmt_bool(_get(config, 'allow_trading_api'))}",
        f"Order Submission      : {_fmt_bool(_get(config, 'allow_order_submission'))}",
        f"Real Position         : {_fmt_bool(_get(config, 'allow_real_position_creation'))}",
        f"Paper Futures Position: {_fmt_bool(_get(config, 'allow_paper_futures_position_creation'))}",
        f"Paper Account Mutation: {_fmt_bool(_get(config, 'allow_paper_account_state_mutation'))}",
        f"Runner Mutation       : {_fmt_bool(_get(config, 'allow_runner_state_mutation'))}",
        f"Execution Mutation    : {_fmt_bool(_get(config, 'allow_execution_state_mutation'))}",
        f"Runtime Config        : {report.diagnostics.get('runtime_config_status', 'UNKNOWN')}",
        f"Monitoring Config     : {report.diagnostics.get('monitoring_config_status', 'UNKNOWN')}",
        f"Runner Config         : {report.diagnostics.get('runner_config_status', 'UNKNOWN')}",
        f"Futures Feed Config   : {report.diagnostics.get('futures_feed_config_status', 'UNKNOWN')}",
        f"Paper Account Config  : {report.diagnostics.get('paper_account_config_status', 'UNKNOWN')}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    lines.extend(_issue_lines(report.issues))
    return "\n".join(lines)


def format_btc_futures_risk_result(result: BTCFuturesRiskResult) -> str:
    scenario = result.scenario
    calc = result.calculation
    lines = [
        "===== BTC FUTURES LEVERAGE / LIQUIDATION RISK ANALYSIS =====",
        f"Project Scope        : {result.project_scope}",
        f"Symbol               : {result.symbol}",
        f"Side                 : {_get(scenario, 'side')}",
        f"Status               : {result.status}",
        f"Decision             : {result.decision}",
        f"Reason               : {result.reason}",
        f"Model                : {result.model_name}",
        f"Model Accuracy       : {result.model_accuracy}",
        f"Exchange Exact       : {_fmt_bool(result.exchange_exact_liquidation)}",
        "",
        "Scenario:",
        f"Entry Price          : {_get(scenario, 'entry_price')}",
        f"Mark Price           : {_get(scenario, 'mark_price')}",
        f"Stop Loss            : {_get(scenario, 'stop_loss')}",
        f"Take Profit          : {_get(scenario, 'take_profit')}",
        f"Notional             : {_get(scenario, 'notional_value')}",
        f"Account Equity       : {_get(scenario, 'account_equity')}",
        f"Leverage             : {_get(scenario, 'leverage')}x",
        f"Funding Rate         : {_get(scenario, 'funding_rate')}",
        f"Funding Periods      : {_get(scenario, 'funding_periods')}",
        "",
        "Risk Calculation:",
        f"Quantity             : {_fmt_num(_get(calc, 'quantity'))}",
        f"Initial Margin       : {_fmt_num(_get(calc, 'initial_margin'))}",
        f"Initial Margin %     : {_fmt_num(_get(calc, 'initial_margin_pct_of_equity'))}",
        f"Maintenance Margin   : {_fmt_num(_get(calc, 'maintenance_margin_at_mark'))}",
        f"Liquidation Reserve  : {_fmt_num(_get(calc, 'liquidation_fee_reserve_at_mark'))}",
        f"Estimated Liquidation: {_fmt_num(_get(calc, 'estimated_liquidation_price'))}",
        f"Liquidation Distance : {_fmt_num(_get(calc, 'liquidation_distance_pct'))}%",
        f"Unrealized PnL       : {_fmt_num(_get(calc, 'unrealized_pnl_at_mark'))}",
        f"Equity At Mark       : {_fmt_num(_get(calc, 'equity_at_mark'))}",
        f"Margin Ratio         : {_fmt_num(_get(calc, 'margin_ratio'))}",
        f"Risk To Stop         : {_fmt_num(_get(calc, 'risk_amount_to_stop'))}",
        f"Reward To TP         : {_fmt_num(_get(calc, 'reward_amount_to_take_profit'))}",
        f"Risk/Reward          : {_fmt_num(_get(calc, 'risk_reward_ratio'))}",
        f"Stop Before Liq      : {_fmt_bool(_get(calc, 'stop_before_liquidation'))}",
        f"Funding Per Period   : {_fmt_num(_get(calc, 'funding_payment_per_period'))}",
        f"Total Funding        : {_fmt_num(_get(calc, 'total_funding_estimate'))}",
        "",
        "Safety:",
        f"Simulation Only      : {_fmt_bool(result.simulation_only)}",
        f"Dry Run Only         : {_fmt_bool(result.dry_run_only)}",
        f"Private API Used     : {_fmt_bool(result.private_api_used)}",
        f"API Key Used         : {_fmt_bool(result.api_key_used)}",
        f"Trading API Used     : {_fmt_bool(result.trading_api_used)}",
        f"Exchange Leverage Set: {_fmt_bool(result.exchange_leverage_changed)}",
        f"Margin Mode Changed  : {_fmt_bool(result.exchange_margin_mode_changed)}",
        f"Order Submitted      : {_fmt_bool(result.order_submitted)}",
        f"Order Cancelled      : {_fmt_bool(result.order_cancelled)}",
        f"Real Position        : {_fmt_bool(result.real_position_created)}",
        f"Paper Futures Pos    : {_fmt_bool(result.paper_futures_position_created)}",
        f"Executable Trade     : {_fmt_bool(result.executable_trade_created)}",
        f"Paper Account Mutated: {_fmt_bool(result.paper_account_state_mutated)}",
        f"Runner Mutated       : {_fmt_bool(result.runner_state_mutated)}",
        f"Execution Mutated    : {_fmt_bool(result.execution_state_mutated)}",
        "",
        "Assumptions:",
    ]
    lines.extend(f"- {item}" for item in (_get(calc, "assumptions") or ["APPROXIMATE_CONSERVATIVE model; no exact exchange liquidation guarantee."]))
    lines.extend(["", "Issues:", "Name | Severity | Message"])
    lines.extend(_issue_lines(result.issues))
    return "\n".join(lines)


def format_btc_futures_leverage_comparison(result: BTCFuturesLeverageComparisonResult) -> str:
    lines = [
        "===== BTC FUTURES LEVERAGE COMPARISON =====",
        f"Symbol                   : {result.symbol}",
        f"Side                     : {result.side}",
        f"Entry Price              : {result.entry_price}",
        f"Mark Price               : {result.mark_price}",
        f"Notional                 : {result.notional_value}",
        f"Account Equity           : {result.account_equity}",
        f"Safest Leverage          : {result.safest_leverage}",
        f"Highest Accepted Leverage: {result.highest_accepted_leverage}",
        f"Status                   : {result.status}",
        "",
        "Leverage | Status | Decision | Initial Margin | Liq Price | Liq Distance % | Margin Ratio | Stop Before Liq | Funding Estimate | Reason",
    ]
    for row in result.rows:
        lines.append(f"{row.leverage}x | {row.status} | {row.decision} | {_fmt_num(row.initial_margin)} | {_fmt_num(row.estimated_liquidation_price)} | {_fmt_num(row.liquidation_distance_pct)} | {_fmt_num(row.margin_ratio)} | {_fmt_bool(row.stop_before_liquidation)} | {_fmt_num(row.total_funding_estimate)} | {row.reason}")
    lines.extend(["", "Issues:", "Name | Severity | Message"])
    lines.extend(_issue_lines(result.issues))
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


def _fmt_num(value) -> str:
    if value is None:
        return "None"
    return f"{float(value):.6f}"


def _leverage_list(values) -> str:
    if not values:
        return "None"
    return ", ".join(f"{item}x" for item in values)
