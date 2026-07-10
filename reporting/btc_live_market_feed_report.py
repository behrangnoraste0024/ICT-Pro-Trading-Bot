from __future__ import annotations

from models.btc_live_market_feed import (
    BTCLiveMarketFeedResult,
    BTCLiveMarketFeedValidationReport,
    BTCLiveMarketObservationResult,
)


def format_btc_live_market_feed_validation_report(report: BTCLiveMarketFeedValidationReport) -> str:
    config = report.config
    lines = [
        "===== BTC LIVE MARKET READ-ONLY FEED CONFIG VALIDATION =====",
        f"Config Path       : {report.config_path}",
        f"Status            : {report.status}",
        f"Symbol            : {_get(config, 'symbol')}",
        f"Exchange          : {_get(config, 'exchange')}",
        f"Market Type       : {_get(config, 'market_type')}",
        f"Profile           : {_get(config, 'strategy_profile')}",
        f"Dry Run Only      : {_fmt_bool(_get(config, 'dry_run_only'))}",
        f"Feed Enabled      : {_fmt_bool(_get(config, 'feed_enabled'))}",
        f"Public Data Fetch : {_fmt_bool(_get(config, 'allow_public_market_data_fetch'))}",
        f"Private API       : {_fmt_bool(_get(config, 'allow_private_api'))}",
        f"API Key Usage     : {_fmt_bool(_get(config, 'allow_api_key_usage'))}",
        f"Trading API       : {_fmt_bool(_get(config, 'allow_trading_api'))}",
        f"Account Data      : {_fmt_bool(_get(config, 'allow_account_data'))}",
        f"Order Submission  : {_fmt_bool(_get(config, 'allow_order_submission'))}",
        f"Order Cancel      : {_fmt_bool(_get(config, 'allow_order_cancellation'))}",
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


def format_btc_live_market_feed_result(result: BTCLiveMarketFeedResult) -> str:
    lines = [
        "===== BTC LIVE MARKET READ-ONLY FEED FETCH =====",
        f"Project Scope       : {result.project_scope}",
        f"Symbol              : {result.symbol}",
        f"Exchange            : {result.exchange}",
        f"Market Type         : {result.market_type}",
        f"Status              : {result.status}",
        f"Primary TF          : {result.primary_timeframe}",
        f"Confirmation TF     : {result.confirmation_timeframe}",
        f"Primary Candles     : {result.primary_candles}",
        f"Confirmation Candles: {result.confirmation_candles}",
        f"Primary Latest Time : {result.primary_latest_timestamp}",
        f"Confirmation Time   : {result.confirmation_latest_timestamp}",
        f"Primary Latest Close: {result.primary_latest_close}",
        f"Confirmation Close  : {result.confirmation_latest_close}",
        "",
        "Safety:",
        f"Public Data Fetch   : {_fmt_bool(result.public_market_data_fetch_used)}",
        f"Private API Used    : {_fmt_bool(result.private_api_used)}",
        f"API Key Used        : {_fmt_bool(result.api_key_used)}",
        f"Trading API Used    : {_fmt_bool(result.trading_api_used)}",
        f"Account Data Used   : {_fmt_bool(result.account_data_used)}",
        f"Balance Fetch Used  : {_fmt_bool(result.balance_fetch_used)}",
        f"Position Fetch Used : {_fmt_bool(result.position_fetch_used)}",
        f"Order Submitted     : {_fmt_bool(result.order_submitted)}",
        f"Order Cancelled     : {_fmt_bool(result.order_cancelled)}",
        f"Trading Connection  : {_fmt_bool(result.exchange_connected_for_trading)}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    if result.issues:
        lines.extend(f"{issue.name} | {issue.severity} | {issue.message}" for issue in result.issues)
    else:
        lines.append("None | INFO | No issues found.")
    return "\n".join(lines)


def format_btc_live_market_observation_result(result: BTCLiveMarketObservationResult) -> str:
    lines = [
        "===== BTC LIVE MARKET READ-ONLY OBSERVATION DRY-RUN =====",
        f"Project Scope       : {result.project_scope}",
        f"Symbol              : {result.symbol}",
        f"Exchange            : {result.exchange}",
        f"Market Type         : {result.market_type}",
        f"Profile             : {result.strategy_profile}",
        f"Status              : {result.status}",
        f"Decision            : {result.decision}",
        f"Feed Status         : {result.feed_status}",
        f"Signal Decision     : {result.signal_decision}",
        f"Signal Score        : {result.signal_score}",
        f"Signal Threshold    : {result.signal_threshold}",
        f"Candidate Decision  : {result.candidate_decision}",
        f"Candidate Created   : {_fmt_bool(result.candidate_created)}",
        f"Journal Written     : {_fmt_bool(result.journal_entry_written)}",
        f"Journal Entry       : {result.journal_entry_id}",
        f"Reason              : {result.reason}",
        "",
        "Market Data:",
        "Primary TF          : 15m",
        "Confirmation TF     : 1h",
        f"Primary Candles     : {result.primary_candles}",
        f"Confirmation Candles: {result.confirmation_candles}",
        f"Primary Latest Time : {result.primary_latest_timestamp}",
        f"Confirmation Time   : {result.confirmation_latest_timestamp}",
        "",
        "Safety:",
        f"Dry Run Only        : {_fmt_bool(result.dry_run_only)}",
        f"Public Data Fetch   : {_fmt_bool(result.public_market_data_fetch_used)}",
        f"Private API Used    : {_fmt_bool(result.private_api_used)}",
        f"API Key Used        : {_fmt_bool(result.api_key_used)}",
        f"Trading API Used    : {_fmt_bool(result.trading_api_used)}",
        f"Account Data Used   : {_fmt_bool(result.account_data_used)}",
        f"Balance Fetch Used  : {_fmt_bool(result.balance_fetch_used)}",
        f"Position Fetch Used : {_fmt_bool(result.position_fetch_used)}",
        f"Executable Trade    : {_fmt_bool(result.executable_trade_created)}",
        f"Paper Persisted     : {_fmt_bool(result.paper_trade_persisted)}",
        f"Position Created    : {_fmt_bool(result.position_created)}",
        f"Order Submitted     : {_fmt_bool(result.order_submitted)}",
        f"Order Cancelled     : {_fmt_bool(result.order_cancelled)}",
        f"Trading Connection  : {_fmt_bool(result.exchange_connected_for_trading)}",
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


def _get(obj, name: str):
    if obj is None:
        return None
    return getattr(obj, name)


def _fmt_bool(value) -> str:
    if value is None:
        return "None"
    return str(bool(value)).lower()
