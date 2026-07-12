from __future__ import annotations

from models.binance_futures_testnet_order_lifecycle import (
    BinanceFuturesTestnetLifecycleResult,
    BinanceFuturesTestnetLifecycleValidationReport,
)


def format_binance_futures_testnet_order_lifecycle_validation_report(report: BinanceFuturesTestnetLifecycleValidationReport) -> str:
    config = report.config
    lines = [
        "===== BINANCE FUTURES TESTNET MANUAL ORDER LIFECYCLE VALIDATION =====",
        f"Config Path                  : {report.config_path}",
        f"Status                       : {report.status}",
        f"Feature Enabled              : {_fmt_bool(_get(config, 'feature_enabled'))}",
        f"Manual Only                  : {_fmt_bool(_get(config, 'manual_lifecycle_only'))}",
        f"Testnet Only                 : {_fmt_bool(_get(config, 'testnet_only'))}",
        f"Single Order Only            : {_fmt_bool(_get(config, 'single_order_only'))}",
        f"Symbol                       : {_get(config, 'exchange_symbol')}",
        f"Order Type                   : {_get(config, 'allowed_order_types')}",
        f"Time In Force                : {_get(config, 'allowed_time_in_force')}",
        f"Maximum Quantity             : {_get(config, 'maximum_quantity')}",
        f"Maximum Notional             : {_get(config, 'maximum_lifecycle_notional_usdt')}",
        f"Create Retries               : {_get(config, 'max_create_retries')}",
        f"Cancel Retries               : {_get(config, 'max_cancel_retries')}",
        f"Standalone Create            : {_fmt_bool(_get(config, 'allow_standalone_create'))}",
        f"MARKET Orders                : {_fmt_bool(_get(config, 'allow_market_order'))}",
        f"Conditional Orders           : {_fmt_bool(_get(config, 'allow_conditional_order'))}",
        f"Algo Orders                  : {_fmt_bool(_get(config, 'allow_algo_order'))}",
        f"Batch Orders                 : {_fmt_bool(_get(config, 'allow_batch_order'))}",
        f"Automatic Execution          : {_fmt_bool(_get(config, 'automatic_execution_enabled'))}",
        f"Runner Execution             : {_fmt_bool(_get(config, 'allow_runner_order_creation'))}",
        f"Production Endpoint          : {_fmt_bool(_get(config, 'allow_production_endpoint'))}",
        f"Paper State Mutation         : {_fmt_bool(_get(config, 'allow_futures_paper_state_mutation'))}",
        f"Runner State Mutation        : {_fmt_bool(_get(config, 'allow_runner_state_mutation'))}",
        f"Raw Persistence              : {_fmt_bool(_get(config, 'allow_raw_response_persistence') or _get(config, 'allow_raw_request_persistence'))}",
        f"Runtime Config               : {report.diagnostics.get('runtime_config_status', 'UNKNOWN')}",
        f"Monitoring Config            : {report.diagnostics.get('monitoring_config_status', 'UNKNOWN')}",
        f"Runner Config                : {report.diagnostics.get('runner_config_status', 'UNKNOWN')}",
        f"2.77 Adapter Config          : {report.diagnostics.get('testnet_adapter_config_status', 'UNKNOWN')}",
        f"2.78 Read-Only Config        : {report.diagnostics.get('testnet_read_only_config_status', 'UNKNOWN')}",
        f"2.79 Test Order Config       : {report.diagnostics.get('testnet_order_test_config_status', 'UNKNOWN')}",
        f"Futures Feed Config          : {report.diagnostics.get('futures_feed_config_status', 'UNKNOWN')}",
        f"Risk Model Config            : {report.diagnostics.get('futures_risk_model_config_status', 'UNKNOWN')}",
        f"Futures Paper Config         : {report.diagnostics.get('futures_paper_position_config_status', 'UNKNOWN')}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    lines.extend(_issue_lines(report.issues))
    return "\n".join(lines)


def format_binance_futures_testnet_order_lifecycle_result(result: BinanceFuturesTestnetLifecycleResult) -> str:
    title = "===== BINANCE FUTURES TESTNET POST-ONLY LIMIT LIFECYCLE ====="
    lines = [
        title,
        f"Action                    : {result.action}",
        f"Status                    : {result.status}",
        f"Decision                  : {result.decision}",
        f"Reason                    : {result.reason}",
        f"Lifecycle ID              : {result.lifecycle_id}",
        f"Client Order ID           : {result.client_order_id}",
        f"Phase                     : {result.phase}",
    ]
    if result.credential_metadata is not None:
        lines.extend(
            [
                "",
                "Credential Metadata:",
                f"API Key Present           : {_fmt_bool(result.credential_metadata.api_key_present)}",
                f"API Secret Present        : {_fmt_bool(result.credential_metadata.api_secret_present)}",
                f"Credentials Complete      : {_fmt_bool(result.credential_metadata.credentials_complete)}",
                f"Values Redacted           : {_fmt_bool(result.credential_metadata.values_redacted)}",
            ]
        )
    if result.preview is not None:
        lines.extend(
            [
                "",
                "Lifecycle Preview:",
                f"Symbol                    : {result.preview.symbol}",
                f"Side                      : {result.preview.side}",
                f"Quantity                  : {result.preview.quantity}",
                f"Best Bid                  : {result.preview.best_bid}",
                f"Best Ask                  : {result.preview.best_ask}",
                f"Price Offset BPS          : {result.preview.price_offset_bps}",
                f"Derived Price             : {result.preview.derived_price}",
                f"Estimated Notional        : {_fmt_notional(result.preview.estimated_notional)}",
                f"Exchange Filters Valid    : {_fmt_bool(result.preview.exchange_filters_valid)}",
                f"Non-Marketable Price      : {_fmt_bool(result.preview.non_marketable_price_valid)}",
                f"Position Mode Valid       : {_fmt_bool(result.preview.position_mode_valid)}",
                f"Zero Position Precheck    : {_fmt_bool(result.preview.zero_position_precheck_valid)}",
                f"Transmission Ready        : {_fmt_bool(result.preview.transmission_ready)}",
            ]
        )
    lines.extend(
        [
            "",
            "Lifecycle:",
            f"Order Created             : {_fmt_bool(result.order_created)}",
            f"Order ID                  : {_order_attr(result.created_order, 'order_id')}",
            f"Initial Order Status      : {_order_attr(result.queried_order, 'status')}",
            f"Executed Quantity         : {_order_attr(result.queried_order or result.final_order, 'executed_quantity')}",
            f"Cancel Requested          : {_fmt_bool(result.cancel_request_transmitted)}",
            f"Cancel Result             : {_order_attr(result.cancel_order, 'status')}",
            f"Final Order Status        : {_order_attr(result.final_order, 'status')}",
            f"Lifecycle Complete        : {_fmt_bool(result.lifecycle_complete)}",
            f"Recovery Required         : {_fmt_bool(result.recovery_required)}",
            "",
            "Safety:",
            f"Testnet Host Used         : true",
            f"Explicit Confirmation     : {_fmt_bool(result.create_request_transmitted or result.query_request_transmitted or result.cancel_request_transmitted)}",
            f"Single Order Count        : {1 if result.order_created else 0}",
            f"LIMIT Only                : true",
            f"GTX Post Only             : true",
            f"MARKET Order Used         : {_fmt_bool(result.market_order_used)}",
            f"Conditional Order Used    : {_fmt_bool(result.conditional_order_created)}",
            f"Algo Order Used           : {_fmt_bool(result.algo_order_created)}",
            f"Batch Order Used          : {_fmt_bool(result.batch_order_created)}",
            f"Order Modified            : {_fmt_bool(result.order_modified)}",
            f"Cancel All Used           : {_fmt_bool(result.cancel_all_used)}",
            f"Leverage Changed          : {_fmt_bool(result.leverage_changed)}",
            f"Margin Changed            : {_fmt_bool(result.margin_mode_changed)}",
            f"Position Mode Changed     : {_fmt_bool(result.position_mode_changed)}",
            f"Unexpected Fill           : {_fmt_bool(result.unexpected_fill_detected)}",
            f"Unexpected Position       : {_fmt_bool(result.unexpected_position_detected)}",
            f"Production Endpoint Used  : {_fmt_bool(result.production_endpoint_used)}",
            f"Real Funds Used           : false",
            f"Futures Paper Mutated     : {_fmt_bool(result.futures_paper_state_mutated)}",
            f"Spot Paper Mutated        : {_fmt_bool(result.spot_paper_account_state_mutated)}",
            f"Runner Mutated            : {_fmt_bool(result.runner_state_mutated)}",
            f"Execution Mutated         : {_fmt_bool(result.execution_state_mutated)}",
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


def _order_attr(order, name: str):
    if order is None:
        return None
    return getattr(order, name)


def _fmt_bool(value) -> str:
    if value is None:
        return "None"
    return str(bool(value)).lower()


def _fmt_notional(value) -> str:
    if value is None:
        return "NOT_EVALUATED"
    return str(value)
