from __future__ import annotations

from models.binance_futures_testnet_order_test import BinanceFuturesTestnetOrderTestResult, BinanceFuturesTestnetOrderTestValidationReport


def format_binance_futures_testnet_order_test_validation_report(report: BinanceFuturesTestnetOrderTestValidationReport) -> str:
    config = report.config
    lines = [
        "===== BINANCE FUTURES TESTNET TEST ORDER VALIDATION =====",
        f"Config Path                  : {report.config_path}",
        f"Status                       : {report.status}",
        f"Symbol                       : {_get(config, 'exchange_symbol')}",
        f"REST Base URL                : {_get(config, 'rest_base_url')}",
        f"Feature Enabled              : {_fmt_bool(_get(config, 'feature_enabled'))}",
        f"Explicit CLI Only            : {_fmt_bool(_get(config, 'explicit_cli_only'))}",
        f"Testnet Only                 : {_fmt_bool(_get(config, 'testnet_only'))}",
        f"Test Order Only              : {_fmt_bool(_get(config, 'test_order_only'))}",
        f"Allowed Methods              : {_get(config, 'allowed_http_methods')}",
        f"Allowed Paths                : {_get(config, 'allowed_authenticated_paths')}",
        f"Actual Order Submission      : {_fmt_bool(_get(config, 'allow_actual_order_submission'))}",
        f"Order Cancellation           : {_fmt_bool(_get(config, 'allow_order_cancellation'))}",
        f"Order Modification           : {_fmt_bool(_get(config, 'allow_order_modification'))}",
        f"Conditional Orders           : {_fmt_bool(_get(config, 'allow_conditional_order'))}",
        f"Algo Orders                  : {_fmt_bool(_get(config, 'allow_algo_order'))}",
        f"Position Creation            : {_fmt_bool(_get(config, 'allow_position_creation'))}",
        f"Leverage Change              : {_fmt_bool(_get(config, 'allow_leverage_change'))}",
        f"Raw Request Persistence      : {_fmt_bool(_get(config, 'allow_raw_request_persistence'))}",
        f"Raw Response Persistence     : {_fmt_bool(_get(config, 'allow_raw_response_persistence'))}",
        f"Runtime Config               : {report.diagnostics.get('runtime_config_status', 'UNKNOWN')}",
        f"Monitoring Config            : {report.diagnostics.get('monitoring_config_status', 'UNKNOWN')}",
        f"Runner Config                : {report.diagnostics.get('runner_config_status', 'UNKNOWN')}",
        f"2.77 Adapter Config          : {report.diagnostics.get('testnet_adapter_config_status', 'UNKNOWN')}",
        f"2.78 Read-Only Config        : {report.diagnostics.get('testnet_read_only_config_status', 'UNKNOWN')}",
        f"Futures Feed Config          : {report.diagnostics.get('futures_feed_config_status', 'UNKNOWN')}",
        f"Risk Model Config            : {report.diagnostics.get('futures_risk_model_config_status', 'UNKNOWN')}",
        f"Futures Paper Config         : {report.diagnostics.get('futures_paper_position_config_status', 'UNKNOWN')}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    lines.extend(_issue_lines(report.issues))
    return "\n".join(lines)


def format_binance_futures_testnet_order_test_result(result: BinanceFuturesTestnetOrderTestResult) -> str:
    title = "===== BINANCE FUTURES TESTNET TEST ORDER RESULT =====" if result.action == "SUBMIT_TEST_ORDER" else "===== BINANCE FUTURES TESTNET TEST ORDER DIAGNOSTIC ====="
    lines = [
        title,
        f"Action                    : {result.action}",
        f"Status                    : {result.status}",
        f"Decision                  : {result.decision}",
        f"Reason                    : {result.reason}",
    ]
    if result.credential_metadata is not None:
        lines.extend(
            [
                "",
                "Credential Metadata:",
                f"API Key Present           : {_fmt_bool(result.credential_metadata.api_key_present)}",
                f"API Secret Present        : {_fmt_bool(result.credential_metadata.api_secret_present)}",
                f"API Key Length            : {result.credential_metadata.api_key_length}",
                f"API Secret Length         : {result.credential_metadata.api_secret_length}",
                f"Credentials Complete      : {_fmt_bool(result.credential_metadata.credentials_complete)}",
                f"Values Redacted           : {_fmt_bool(result.credential_metadata.values_redacted)}",
            ]
        )
    if result.exchange_filter_summary is not None:
        lines.extend(
            [
                "",
                "Exchange Filters:",
                f"Symbol                    : {result.exchange_filter_summary.symbol}",
                f"Price Tick                : {result.exchange_filter_summary.price_tick_size}",
                f"Lot Step                  : {result.exchange_filter_summary.lot_step_size}",
                f"Market Lot Step           : {result.exchange_filter_summary.market_lot_step_size}",
                f"Min Notional              : {result.exchange_filter_summary.min_notional}",
                f"Raw Response Included     : {_fmt_bool(result.exchange_filter_summary.raw_response_included)}",
            ]
        )
    if result.preview is not None:
        lines.extend(
            [
                "",
                "Order-Test Preview:",
                f"Client Order ID           : {result.preview.client_order_id}",
                f"Symbol                    : {result.preview.symbol}",
                f"Side                      : {result.preview.side}",
                f"Order Type                : {result.preview.order_type}",
                f"Quantity                  : {result.preview.quantity}",
                f"Price                     : {result.preview.price}",
                f"Time In Force             : {result.preview.time_in_force}",
                f"Reduce Only               : {_fmt_bool(result.preview.reduce_only)}",
                f"Estimated Notional        : {result.preview.estimated_notional}",
                f"Exchange Filters Valid    : {_fmt_bool(result.preview.exchange_filters_valid)}",
                f"Executable                : {_fmt_bool(result.preview.executable)}",
                f"Actual Order Endpoint     : {_fmt_bool(result.preview.actual_order_endpoint_used)}",
                f"Matching Engine Submission: {_fmt_bool(result.preview.matching_engine_submission)}",
                f"Exchange Order Created    : {_fmt_bool(result.preview.exchange_order_created)}",
                f"Exchange Order ID         : {result.preview.exchange_order_id}",
                f"Position Created          : {_fmt_bool(result.preview.position_created)}",
            ]
        )
    if result.request_metadata is not None:
        lines.extend(
            [
                "",
                "Request Metadata:",
                f"Host                      : {result.request_metadata.host}",
                f"Method                    : {result.request_metadata.method}",
                f"Path                      : {result.request_metadata.path}",
                f"Parameters                : {result.request_metadata.parameter_names}",
                f"Signature Generated       : {_fmt_bool(result.request_metadata.signature_generated)}",
                f"Signature Redacted        : {_fmt_bool(result.request_metadata.signature_redacted)}",
                f"API Key Header Used       : {_fmt_bool(result.request_metadata.api_key_header_used)}",
                f"Request Transmitted       : {_fmt_bool(result.request_metadata.request_transmitted)}",
                f"Response Empty Object     : {_fmt_bool(result.request_metadata.response_empty_object)}",
                f"Raw URL Exposed           : {_fmt_bool(result.request_metadata.raw_url_exposed)}",
                f"Raw Headers Exposed       : {_fmt_bool(result.request_metadata.raw_headers_exposed)}",
                f"Raw Request Included      : {_fmt_bool(result.request_metadata.raw_request_included)}",
                f"Raw Response Included     : {_fmt_bool(result.request_metadata.raw_response_included)}",
            ]
        )
    lines.extend(
        [
            "",
            "Safety:",
            f"Credentials Inspected     : {_fmt_bool(result.credentials_inspected)}",
            f"Server Time Request Used  : {_fmt_bool(result.public_server_time_request_used)}",
            f"Exchange Info Used        : {_fmt_bool(result.public_exchange_info_request_used)}",
            f"Signature Generated       : {_fmt_bool(result.signature_generated)}",
            f"Authenticated Request     : {_fmt_bool(result.authenticated_test_request_used)}",
            f"Test Request Transmitted  : {_fmt_bool(result.test_order_request_transmitted)}",
            f"Actual Order Submitted    : {_fmt_bool(result.actual_order_submitted)}",
            f"Actual Order Endpoint     : {_fmt_bool(result.actual_order_endpoint_used)}",
            f"Matching Engine Submission: {_fmt_bool(result.matching_engine_submission)}",
            f"Exchange Order Created    : {_fmt_bool(result.exchange_order_created)}",
            f"Exchange Order ID         : {result.exchange_order_id}",
            f"Order Cancelled           : {_fmt_bool(result.order_cancelled)}",
            f"Order Modified            : {_fmt_bool(result.order_modified)}",
            f"Position Created          : {_fmt_bool(result.position_created)}",
            f"Position Closed           : {_fmt_bool(result.position_closed)}",
            f"Leverage Changed          : {_fmt_bool(result.leverage_changed)}",
            f"Margin Mode Changed       : {_fmt_bool(result.margin_mode_changed)}",
            f"Conditional Order Created : {_fmt_bool(result.conditional_order_created)}",
            f"Algo Order Created        : {_fmt_bool(result.algo_order_created)}",
            f"Production Endpoint Used  : {_fmt_bool(result.production_endpoint_used)}",
            f"Futures Paper Mutated     : {_fmt_bool(result.futures_paper_state_mutated)}",
            f"Spot Account Mutated      : {_fmt_bool(result.spot_paper_account_state_mutated)}",
            f"Runner Mutated            : {_fmt_bool(result.runner_state_mutated)}",
            f"Execution Mutated         : {_fmt_bool(result.execution_state_mutated)}",
            f"Exchange State Mutated    : {_fmt_bool(result.exchange_state_mutated)}",
            f"Secrets Exposed           : {_fmt_bool(result.api_key_exposed or result.api_secret_exposed or result.signature_exposed or result.signed_url_exposed or result.authenticated_headers_exposed)}",
            f"Raw Request Persisted     : {_fmt_bool(result.raw_request_persisted)}",
            f"Raw Response Persisted    : {_fmt_bool(result.raw_response_persisted)}",
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
