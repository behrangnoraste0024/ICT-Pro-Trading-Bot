from __future__ import annotations

from models.binance_futures_testnet_read_only import BinanceFuturesTestnetReadOnlyResult, BinanceFuturesTestnetReadOnlyValidationReport


def format_binance_futures_testnet_read_only_validation_report(report: BinanceFuturesTestnetReadOnlyValidationReport) -> str:
    config = report.config
    lines = [
        "===== BINANCE FUTURES TESTNET READ-ONLY VALIDATION =====",
        f"Config Path                  : {report.config_path}",
        f"Status                       : {report.status}",
        f"Symbol                       : {_get(config, 'symbol')}",
        f"Exchange Symbol              : {_get(config, 'exchange_symbol')}",
        f"REST Base URL                : {_get(config, 'rest_base_url')}",
        f"Feature Enabled              : {_fmt_bool(_get(config, 'feature_enabled'))}",
        f"Explicit CLI Only            : {_fmt_bool(_get(config, 'explicit_cli_only'))}",
        f"Authenticated Read-Only      : {_fmt_bool(_get(config, 'authenticated_read_only_available'))}",
        f"Confirmation Required        : {_fmt_bool(_get(config, 'require_explicit_network_confirmation'))}",
        f"Allowed Methods              : {_get(config, 'allowed_http_methods')}",
        f"Allowed Paths                : {_get(config, 'allowed_authenticated_paths')}",
        f"Order Submission             : {_fmt_bool(_get(config, 'allow_testnet_order_submission'))}",
        f"Order Query                  : {_fmt_bool(_get(config, 'allow_order_query'))}",
        f"Trade Query                  : {_fmt_bool(_get(config, 'allow_trade_query'))}",
        f"Leverage Change              : {_fmt_bool(_get(config, 'allow_testnet_leverage_change'))}",
        f"Margin Mode Change           : {_fmt_bool(_get(config, 'allow_testnet_margin_mode_change'))}",
        f"Production Endpoint          : {_fmt_bool(_get(config, 'allow_production_endpoint'))}",
        f"Raw Response Persistence     : {_fmt_bool(_get(config, 'allow_raw_authenticated_response_persistence'))}",
        f"Futures Paper State Mutation : {_fmt_bool(_get(config, 'allow_futures_paper_state_mutation'))}",
        f"Runtime Config               : {report.diagnostics.get('runtime_config_status', 'UNKNOWN')}",
        f"Monitoring Config            : {report.diagnostics.get('monitoring_config_status', 'UNKNOWN')}",
        f"Runner Config                : {report.diagnostics.get('runner_config_status', 'UNKNOWN')}",
        f"2.77 Adapter Config          : {report.diagnostics.get('testnet_adapter_config_status', 'UNKNOWN')}",
        f"Futures Feed Config          : {report.diagnostics.get('futures_feed_config_status', 'UNKNOWN')}",
        f"Risk Model Config            : {report.diagnostics.get('futures_risk_model_config_status', 'UNKNOWN')}",
        f"Futures Paper Config         : {report.diagnostics.get('futures_paper_position_config_status', 'UNKNOWN')}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    lines.extend(_issue_lines(report.issues))
    return "\n".join(lines)


def format_binance_futures_testnet_read_only_result(result: BinanceFuturesTestnetReadOnlyResult) -> str:
    lines = [
        "===== BINANCE FUTURES TESTNET READ-ONLY DIAGNOSTIC =====",
        f"Action                       : {result.action}",
        f"Status                       : {result.status}",
        f"Decision                     : {result.decision}",
        f"Reason                       : {result.reason}",
    ]
    if result.credential_metadata is not None:
        lines.extend(
            [
                "",
                "Credential Metadata:",
                f"API Key Present              : {_fmt_bool(result.credential_metadata.api_key_present)}",
                f"API Secret Present           : {_fmt_bool(result.credential_metadata.api_secret_present)}",
                f"API Key Length               : {result.credential_metadata.api_key_length}",
                f"API Secret Length            : {result.credential_metadata.api_secret_length}",
                f"Credentials Complete         : {_fmt_bool(result.credential_metadata.credentials_complete)}",
                f"Values Redacted              : {_fmt_bool(result.credential_metadata.values_redacted)}",
            ]
        )
    if result.request_metadata is not None:
        lines.extend(
            [
                "",
                "Request Metadata:",
                f"Method                       : {result.request_metadata.method}",
                f"Host                         : {result.request_metadata.host}",
                f"Path                         : {result.request_metadata.path}",
                f"Parameters                   : {result.request_metadata.parameter_names}",
                f"Signature Generated          : {_fmt_bool(result.request_metadata.signature_generated)}",
                f"Signature Redacted           : {_fmt_bool(result.request_metadata.signature_redacted)}",
                f"API Key Header Used          : {_fmt_bool(result.request_metadata.api_key_header_used)}",
                f"Request Transmitted          : {_fmt_bool(result.request_metadata.request_transmitted)}",
                f"Final Host Validated         : {_fmt_bool(result.request_metadata.final_host_validated)}",
                f"Raw URL Exposed              : {_fmt_bool(result.request_metadata.raw_url_exposed)}",
                f"Raw Headers Exposed          : {_fmt_bool(result.request_metadata.raw_headers_exposed)}",
                f"Raw Response Included        : {_fmt_bool(result.request_metadata.raw_response_included)}",
            ]
        )
    if result.account_summary is not None:
        lines.extend(["", "Account Summary:"])
        for key, value in result.account_summary.to_dict().items():
            lines.append(f"{key}: {value}")
    if result.balance_summary is not None:
        lines.extend(["", "Balance Summary:"])
        for key, value in result.balance_summary.to_dict().items():
            lines.append(f"{key}: {value}")
    if result.position_summary is not None:
        lines.extend(["", "Position Summary:"])
        for key, value in result.position_summary.to_dict().items():
            lines.append(f"{key}: {value}")
    if result.payload:
        lines.extend(["", "Payload:"])
        for key, value in result.payload.items():
            lines.append(f"{key}: {value}")
    lines.extend(
        [
            "",
            "Safety:",
            f"Server Time Request Used     : {_fmt_bool(result.public_server_time_request_used)}",
            f"Credentials Inspected        : {_fmt_bool(result.credentials_inspected)}",
            f"Signature Generated          : {_fmt_bool(result.signature_generated)}",
            f"Authenticated Transport      : {_fmt_bool(result.authenticated_transport_invoked)}",
            f"Authenticated Testnet Request: {_fmt_bool(result.authenticated_testnet_request_used)}",
            f"Request Transmitted          : {_fmt_bool(result.request_transmitted)}",
            f"API Key Header Used          : {_fmt_bool(result.api_key_header_used)}",
            f"API Secret Transmitted       : {_fmt_bool(result.api_secret_transmitted)}",
            f"Account Read Used            : {_fmt_bool(result.authenticated_account_read_used)}",
            f"Balance Read Used            : {_fmt_bool(result.authenticated_balance_read_used)}",
            f"Position Read Used           : {_fmt_bool(result.authenticated_position_read_used)}",
            f"Order Query Used             : {_fmt_bool(result.order_query_used)}",
            f"Trade Query Used             : {_fmt_bool(result.trade_query_used)}",
            f"Order Submitted              : {_fmt_bool(result.order_submitted)}",
            f"Test Order Submitted         : {_fmt_bool(result.test_order_submitted)}",
            f"Order Cancelled              : {_fmt_bool(result.order_cancelled)}",
            f"Leverage Changed             : {_fmt_bool(result.leverage_changed)}",
            f"Margin Mode Changed          : {_fmt_bool(result.margin_mode_changed)}",
            f"Position Created             : {_fmt_bool(result.position_created)}",
            f"Position Closed              : {_fmt_bool(result.position_closed)}",
            f"User Stream Opened           : {_fmt_bool(result.user_data_stream_opened)}",
            f"Listen Key Created           : {_fmt_bool(result.listen_key_created)}",
            f"WebSocket Opened             : {_fmt_bool(result.websocket_opened)}",
            f"Production Endpoint Used     : {_fmt_bool(result.production_endpoint_used)}",
            f"Real Funds Used              : {_fmt_bool(result.real_funds_used)}",
            f"Futures Paper State Mutated  : {_fmt_bool(result.futures_paper_state_mutated)}",
            f"Spot Paper Account Mutated   : {_fmt_bool(result.spot_paper_account_state_mutated)}",
            f"Runner Mutated               : {_fmt_bool(result.runner_state_mutated)}",
            f"Execution Mutated            : {_fmt_bool(result.execution_state_mutated)}",
            f"Exchange State Mutated       : {_fmt_bool(result.exchange_state_mutated)}",
            f"API Key Exposed              : {_fmt_bool(result.api_key_exposed)}",
            f"API Secret Exposed           : {_fmt_bool(result.api_secret_exposed)}",
            f"Signature Exposed            : {_fmt_bool(result.signature_exposed)}",
            f"Signed URL Exposed           : {_fmt_bool(result.signed_url_exposed)}",
            f"Authenticated Headers Exposed: {_fmt_bool(result.authenticated_headers_exposed)}",
            f"Raw Response Persisted       : {_fmt_bool(result.raw_response_persisted)}",
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
