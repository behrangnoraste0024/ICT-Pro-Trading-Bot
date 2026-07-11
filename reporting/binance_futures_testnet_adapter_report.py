from __future__ import annotations

from models.binance_futures_testnet_adapter import BinanceFuturesTestnetAdapterResult, BinanceFuturesTestnetAdapterValidationReport


def format_binance_futures_testnet_adapter_validation_report(report: BinanceFuturesTestnetAdapterValidationReport) -> str:
    config = report.config
    lines = [
        "===== BINANCE FUTURES TESTNET ADAPTER VALIDATION =====",
        f"Config Path                 : {report.config_path}",
        f"Status                      : {report.status}",
        f"Symbol                      : {_get(config, 'symbol')}",
        f"Exchange Symbol             : {_get(config, 'exchange_symbol')}",
        f"REST Base URL               : {_get(config, 'rest_base_url')}",
        f"Adapter Enabled             : {_fmt_bool(_get(config, 'adapter_enabled'))}",
        f"Connection Mode             : {_get(config, 'connection_mode')}",
        f"Testnet Only                : {_fmt_bool(_get(config, 'testnet_only'))}",
        f"Dry Run Only                : {_fmt_bool(_get(config, 'dry_run_only'))}",
        f"API Key Env                 : {_get(config, 'api_key_env_var')}",
        f"API Secret Env              : {_get(config, 'api_secret_env_var')}",
        f"Authenticated Request       : {_fmt_bool(_get(config, 'allow_authenticated_testnet_request'))}",
        f"Account Read                : {_fmt_bool(_get(config, 'allow_authenticated_account_read'))}",
        f"Balance Read                : {_fmt_bool(_get(config, 'allow_authenticated_balance_read'))}",
        f"Position Read               : {_fmt_bool(_get(config, 'allow_authenticated_position_read'))}",
        f"Order Submission            : {_fmt_bool(_get(config, 'allow_testnet_order_submission'))}",
        f"Order Cancellation          : {_fmt_bool(_get(config, 'allow_testnet_order_cancellation'))}",
        f"Leverage Change             : {_fmt_bool(_get(config, 'allow_testnet_leverage_change'))}",
        f"Margin Mode Change          : {_fmt_bool(_get(config, 'allow_testnet_margin_mode_change'))}",
        f"Production Endpoint         : {_fmt_bool(_get(config, 'allow_production_endpoint'))}",
        f"Futures Paper State Mutation: {_fmt_bool(_get(config, 'allow_futures_paper_state_mutation'))}",
        f"Runner Mutation             : {_fmt_bool(_get(config, 'allow_runner_state_mutation'))}",
        f"Execution Mutation          : {_fmt_bool(_get(config, 'allow_execution_state_mutation'))}",
        f"Runtime Config              : {report.diagnostics.get('runtime_config_status', 'UNKNOWN')}",
        f"Monitoring Config           : {report.diagnostics.get('monitoring_config_status', 'UNKNOWN')}",
        f"Runner Config               : {report.diagnostics.get('runner_config_status', 'UNKNOWN')}",
        f"Futures Feed Config         : {report.diagnostics.get('futures_feed_config_status', 'UNKNOWN')}",
        f"Risk Model Config           : {report.diagnostics.get('futures_risk_model_config_status', 'UNKNOWN')}",
        f"Futures Paper Config        : {report.diagnostics.get('futures_paper_position_config_status', 'UNKNOWN')}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    lines.extend(_issue_lines(report.issues))
    return "\n".join(lines)


def format_binance_futures_testnet_adapter_result(result: BinanceFuturesTestnetAdapterResult) -> str:
    lines = [
        "===== BINANCE FUTURES TESTNET ADAPTER DIAGNOSTIC =====",
        f"Action                       : {result.action}",
        f"Status                       : {result.status}",
        f"Decision                     : {result.decision}",
        f"Reason                       : {result.reason}",
        "",
        "Payload:",
    ]
    if result.payload:
        for key, value in result.payload.items():
            lines.append(f"{key}: {value}")
    else:
        lines.append("None: None")
    lines.extend(
        [
            "",
            "Safety:",
            f"Public Request Used          : {_fmt_bool(result.public_request_used)}",
            f"Credentials Inspected        : {_fmt_bool(result.credentials_inspected)}",
            f"Signature Generated          : {_fmt_bool(result.signature_generated)}",
            f"Request Signed               : {_fmt_bool(result.request_signed)}",
            f"Request Transmitted          : {_fmt_bool(result.request_transmitted)}",
            f"Authenticated Transport      : {_fmt_bool(result.authenticated_transport_invoked)}",
            f"Account Read Used            : {_fmt_bool(result.authenticated_account_read_used)}",
            f"Balance Read Used            : {_fmt_bool(result.authenticated_balance_read_used)}",
            f"Position Read Used           : {_fmt_bool(result.authenticated_position_read_used)}",
            f"Testnet Order Submitted      : {_fmt_bool(result.testnet_order_submitted)}",
            f"Testnet Order Cancelled      : {_fmt_bool(result.testnet_order_cancelled)}",
            f"Exchange Leverage Changed    : {_fmt_bool(result.exchange_leverage_changed)}",
            f"Exchange Margin Changed      : {_fmt_bool(result.exchange_margin_mode_changed)}",
            f"User Stream Opened           : {_fmt_bool(result.user_data_stream_opened)}",
            f"WebSocket Opened             : {_fmt_bool(result.websocket_opened)}",
            f"Production Endpoint Used     : {_fmt_bool(result.production_endpoint_used)}",
            f"Futures Paper State Mutated  : {_fmt_bool(result.futures_paper_state_mutated)}",
            f"Spot Paper Account Mutated   : {_fmt_bool(result.spot_paper_account_state_mutated)}",
            f"Runner Mutated               : {_fmt_bool(result.runner_state_mutated)}",
            f"Execution Mutated            : {_fmt_bool(result.execution_state_mutated)}",
            f"Exchange State Mutated       : {_fmt_bool(result.exchange_state_mutated)}",
            f"Secrets Logged               : {_fmt_bool(result.secrets_logged)}",
            f"Secrets Persisted            : {_fmt_bool(result.secrets_persisted)}",
            "",
            "Issues:",
            "Name | Severity | Message",
        ]
    )
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
