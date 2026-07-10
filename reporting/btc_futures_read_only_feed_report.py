from __future__ import annotations

from models.btc_futures_read_only_feed import (
    BTCFuturesReadOnlyFeedResult,
    BTCFuturesReadOnlyObservationResult,
    BTCFuturesReadOnlyValidationReport,
)


def format_btc_futures_read_only_validation_report(report: BTCFuturesReadOnlyValidationReport) -> str:
    config = report.config
    lines = [
        "===== BTC FUTURES READ-ONLY FEED CONFIG VALIDATION =====",
        f"Config Path       : {report.config_path}",
        f"Status            : {report.status}",
        f"Symbol            : {_get(config, 'symbol')}",
        f"Exchange Symbol   : {_get(config, 'exchange_symbol')}",
        f"Exchange          : {_get(config, 'exchange')}",
        f"Market Type       : {_get(config, 'market_type')}",
        f"Contract Type     : {_get(config, 'futures_contract_type')}",
        f"Profile           : {_get(config, 'strategy_profile')}",
        f"Dry Run Only      : {_fmt_bool(_get(config, 'dry_run_only'))}",
        f"Feed Enabled      : {_fmt_bool(_get(config, 'feed_enabled'))}",
        f"Public Futures    : {_fmt_bool(_get(config, 'allow_public_futures_market_data_fetch'))}",
        f"Mark Price Fetch  : {_fmt_bool(_get(config, 'allow_public_futures_mark_price_fetch'))}",
        f"Funding Fetch     : {_fmt_bool(_get(config, 'allow_public_futures_funding_fetch'))}",
        f"Private API       : {_fmt_bool(_get(config, 'allow_private_api'))}",
        f"API Key Usage     : {_fmt_bool(_get(config, 'allow_api_key_usage'))}",
        f"Trading API       : {_fmt_bool(_get(config, 'allow_trading_api'))}",
        f"Account Data      : {_fmt_bool(_get(config, 'allow_account_data'))}",
        f"Order Submission  : {_fmt_bool(_get(config, 'allow_order_submission'))}",
        f"Order Cancel      : {_fmt_bool(_get(config, 'allow_order_cancellation'))}",
        f"Real Position     : {_fmt_bool(_get(config, 'allow_real_position_creation'))}",
        f"Paper Position    : {_fmt_bool(_get(config, 'allow_paper_position_creation'))}",
        f"Leverage          : {_fmt_bool(_get(config, 'allow_leverage'))}",
        f"Leverage Sim      : {_fmt_bool(_get(config, 'allow_leverage_simulation'))}",
        f"Liquidation Model : {_fmt_bool(_get(config, 'allow_liquidation_modeling'))}",
        f"Executable Trade  : {_fmt_bool(_get(config, 'allow_executable_trade_creation'))}",
        f"Runner Mutation   : {_fmt_bool(_get(config, 'allow_runner_state_mutation'))}",
        f"Execution Mutation: {_fmt_bool(_get(config, 'allow_execution_state_mutation'))}",
        f"Runtime Config    : {report.diagnostics.get('runtime_config_status', 'UNKNOWN')}",
        f"Monitoring Config : {report.diagnostics.get('monitoring_config_status', 'UNKNOWN')}",
        f"Runner Config     : {report.diagnostics.get('runner_config_status', 'UNKNOWN')}",
        f"Live Feed Config  : {report.diagnostics.get('live_market_feed_config_status', 'UNKNOWN')}",
        f"Paper Account     : {report.diagnostics.get('paper_account_config_status', 'UNKNOWN')}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    lines.extend(_issue_lines(report.issues))
    return "\n".join(lines)


def format_btc_futures_read_only_feed_result(result: BTCFuturesReadOnlyFeedResult) -> str:
    lines = [
        "===== BTC FUTURES READ-ONLY FEED FETCH =====",
        f"Project Scope       : {result.project_scope}",
        f"Symbol              : {result.symbol}",
        f"Exchange Symbol     : {result.exchange_symbol}",
        f"Exchange            : {result.exchange}",
        f"Market Type         : {result.market_type}",
        f"Contract Type       : {result.futures_contract_type}",
        f"Status              : {result.status}",
        f"Primary TF          : {result.primary_timeframe}",
        f"Confirmation TF     : {result.confirmation_timeframe}",
        f"Primary Candles     : {result.primary_candles}",
        f"Confirmation Candles: {result.confirmation_candles}",
        f"Primary Latest Time : {result.primary_latest_timestamp}",
        f"Confirmation Time   : {result.confirmation_latest_timestamp}",
        f"Primary Latest Close: {result.primary_latest_close}",
        f"Confirmation Close  : {result.confirmation_latest_close}",
        f"Mark Price          : {_get(result.mark_price, 'mark_price')}",
        f"Index Price         : {_get(result.mark_price, 'index_price')}",
        f"Funding Rate        : {_get(result.funding_info, 'funding_rate') if result.funding_info else _get(result.mark_price, 'funding_rate')}",
        f"Next Funding Time   : {_get(result.mark_price, 'next_funding_time')}",
        "",
        "Safety:",
        f"Public Futures Data : {_fmt_bool(result.public_futures_market_data_fetch_used)}",
        f"Mark Price Fetch    : {_fmt_bool(result.public_futures_mark_price_fetch_used)}",
        f"Funding Fetch       : {_fmt_bool(result.public_futures_funding_fetch_used)}",
        f"Private API Used    : {_fmt_bool(result.private_api_used)}",
        f"API Key Used        : {_fmt_bool(result.api_key_used)}",
        f"Trading API Used    : {_fmt_bool(result.trading_api_used)}",
        f"Account Data Used   : {_fmt_bool(result.account_data_used)}",
        f"Balance Fetch Used  : {_fmt_bool(result.balance_fetch_used)}",
        f"Position Fetch Used : {_fmt_bool(result.position_fetch_used)}",
        f"Order Submitted     : {_fmt_bool(result.order_submitted)}",
        f"Order Cancelled     : {_fmt_bool(result.order_cancelled)}",
        f"Real Position       : {_fmt_bool(result.real_position_created)}",
        f"Paper Position      : {_fmt_bool(result.paper_position_created)}",
        f"Leverage Used       : {_fmt_bool(result.leverage_used)}",
        f"Leverage Sim Used   : {_fmt_bool(result.leverage_simulation_used)}",
        f"Liquidation Model   : {_fmt_bool(result.liquidation_modeling_used)}",
        f"Trading Connection  : {_fmt_bool(result.exchange_connected_for_trading)}",
        f"Runner Mutated      : {_fmt_bool(result.runner_state_mutated)}",
        f"Execution Mutated   : {_fmt_bool(result.execution_state_mutated)}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    lines.extend(_issue_lines(result.issues))
    return "\n".join(lines)


def format_btc_futures_read_only_observation_result(result: BTCFuturesReadOnlyObservationResult) -> str:
    lines = [
        "===== BTC FUTURES READ-ONLY OBSERVATION DRY-RUN =====",
        f"Project Scope       : {result.project_scope}",
        f"Symbol              : {result.symbol}",
        f"Exchange Symbol     : {result.exchange_symbol}",
        f"Exchange            : {result.exchange}",
        f"Market Type         : {result.market_type}",
        f"Contract Type       : {result.futures_contract_type}",
        f"Profile             : {result.strategy_profile}",
        f"Status              : {result.status}",
        f"Decision            : {result.decision}",
        f"Feed Status         : {result.feed_status}",
        f"Reason              : {result.reason}",
        "",
        "Market Data:",
        "Primary TF          : 15m",
        "Confirmation TF     : 1h",
        f"Primary Candles     : {result.primary_candles}",
        f"Confirmation Candles: {result.confirmation_candles}",
        f"Primary Latest Time : {result.primary_latest_timestamp}",
        f"Confirmation Time   : {result.confirmation_latest_timestamp}",
        f"Primary Latest Close: {result.primary_latest_close}",
        f"Confirmation Close  : {result.confirmation_latest_close}",
        f"Mark Price          : {result.mark_price_value}",
        f"Funding Rate        : {result.funding_rate}",
        f"Next Funding Time   : {result.next_funding_time}",
        "",
        "Futures Modeling:",
        f"Leverage Model      : {_fmt_bool(result.metadata.get('leverage_model_available'))}",
        f"Liquidation Model   : {_fmt_bool(result.metadata.get('liquidation_model_available'))}",
        f"Paper Futures Pos   : {_fmt_bool(result.metadata.get('paper_futures_position_created'))}",
        f"Futures Pipeline    : {_fmt_bool(result.metadata.get('futures_trade_pipeline_invoked'))}",
        "",
        "Safety:",
        f"Dry Run Only        : {_fmt_bool(result.dry_run_only)}",
        f"Public Futures Data : {_fmt_bool(result.public_futures_market_data_fetch_used)}",
        f"Private API Used    : {_fmt_bool(result.private_api_used)}",
        f"API Key Used        : {_fmt_bool(result.api_key_used)}",
        f"Trading API Used    : {_fmt_bool(result.trading_api_used)}",
        f"Account Data Used   : {_fmt_bool(result.account_data_used)}",
        f"Balance Fetch Used  : {_fmt_bool(result.balance_fetch_used)}",
        f"Position Fetch Used : {_fmt_bool(result.position_fetch_used)}",
        f"Real Position       : {_fmt_bool(result.real_position_created)}",
        f"Paper Position      : {_fmt_bool(result.paper_position_created)}",
        f"Order Submitted     : {_fmt_bool(result.order_submitted)}",
        f"Order Cancelled     : {_fmt_bool(result.order_cancelled)}",
        f"Leverage Used       : {_fmt_bool(result.leverage_used)}",
        f"Leverage Sim Used   : {_fmt_bool(result.leverage_simulation_used)}",
        f"Liquidation Model   : {_fmt_bool(result.liquidation_modeling_used)}",
        f"Executable Trade    : {_fmt_bool(result.executable_trade_created)}",
        f"Trading Connection  : {_fmt_bool(result.exchange_connected_for_trading)}",
        f"Runner Mutated      : {_fmt_bool(result.runner_state_mutated)}",
        f"Execution Mutated   : {_fmt_bool(result.execution_state_mutated)}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
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
