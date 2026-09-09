from __future__ import annotations

from models.binance_futures_testnet_forward_test import (
    BinanceFuturesTestnetForwardTestResult,
    BinanceFuturesTestnetForwardTestValidationReport,
)


def format_binance_futures_testnet_forward_test_validation_report(report: BinanceFuturesTestnetForwardTestValidationReport) -> str:
    config = report.config
    lines = [
        "===== BINANCE FUTURES TESTNET FORWARD TEST VALIDATION =====",
        f"Config Path                : {report.config_path}",
        f"Status                     : {report.status}",
        f"Decision                   : {report.decision}",
        f"Reason                     : {report.reason}",
        f"Environment                : {_get(config, 'environment')}",
        f"Symbol                     : {_get(config, 'exchange_symbol')}",
        f"REST Base URL              : {_get(config, 'rest_base_url')}",
        f"Feature Enabled            : {_fmt_bool(_get(config, 'feature_enabled'))}",
        f"Execution Enabled          : {_fmt_bool(_get(config, 'execution_enabled'))}",
        f"Local Evidence Only        : {_fmt_bool(_get(config, 'local_evidence_only'))}",
        f"Production Endpoint        : {_fmt_bool(_get(config, 'allow_production_endpoint'))}",
        f"Production Credentials     : {_fmt_bool(_get(config, 'allow_production_credentials'))}",
        f"Real Funds                 : {_fmt_bool(_get(config, 'allow_real_funds'))}",
        f"POST Retry Count           : {_get(config, 'post_retry_count')}",
        f"DELETE Retry Count         : {_get(config, 'delete_retry_count')}",
        f"Forward Loop Config        : {report.diagnostics.get('forward_loop_status', 'UNKNOWN')}",
        f"Order-Test Boundary        : {report.diagnostics.get('order_test_status', 'UNKNOWN')}",
        f"Lifecycle Boundary         : {report.diagnostics.get('order_lifecycle_status', 'UNKNOWN')}",
        f"Protective Boundary        : {report.diagnostics.get('protective_orders_status', 'UNKNOWN')}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    lines.extend(_issue_lines(report.issues))
    return "\n".join(lines)


def format_binance_futures_testnet_forward_test_result(result: BinanceFuturesTestnetForwardTestResult) -> str:
    evidence = result.evidence
    lines = [
        "===== BINANCE FUTURES TESTNET FORWARD TEST RESULT =====",
        f"Action                     : {result.action}",
        f"Status                     : {result.status}",
        f"Decision                   : {result.decision}",
        f"Reason                     : {result.reason}",
        f"Transport Mode             : {_get(evidence, 'transport_mode')}",
        f"Execution Mode             : {_get(evidence, 'execution_mode')}",
        f"Execution Authorized       : {_fmt_bool(_get(evidence, 'execution_authorized'))}",
        f"ORDER_TEST Requested       : {_get(evidence, 'order_test_requested_count')}",
        f"Actual Binance Demo        : {_fmt_bool(_get(evidence, 'actual_binance_demo_execution'))}",
        f"Production Disabled        : {_fmt_bool(_get(evidence, 'production_disabled'))}",
        f"Execution Enabled          : {_fmt_bool(_get(evidence, 'execution_enabled'))}",
        f"Environment                : {_get(evidence, 'environment')}",
        f"Symbol                     : {_get(evidence, 'symbol')}",
        "",
        "Run-Level Evidence:",
        f"Run ID                     : {_get(evidence, 'run_id')}",
        f"Start Timestamp            : {_get(evidence, 'start_timestamp')}",
        f"End Timestamp              : {_get(evidence, 'end_timestamp')}",
        f"Strategy Decisions         : {_get(evidence, 'strategy_decision_count')}",
        f"Permit References          : {_get(evidence, 'permit_reference_count')}",
        f"Permits Consumed           : {_get(evidence, 'permit_consumed_count')}",
        f"Signing Count              : {_get(evidence, 'signing_count')}",
        f"POST Count                 : {_get(evidence, 'post_count')}",
        f"DELETE Count               : {_get(evidence, 'delete_count')}",
        f"POST Retry Count           : {_get(evidence, 'post_retry_count')}",
        f"DELETE Retry Count         : {_get(evidence, 'delete_retry_count')}",
        f"Accepted Mutations         : {_get(evidence, 'accepted_mutation_count')}",
        f"Rejected Mutations         : {_get(evidence, 'rejected_mutation_count')}",
        f"Canceled Mutations         : {_get(evidence, 'canceled_mutation_count')}",
        f"Uncertain Mutations        : {_get(evidence, 'uncertain_mutation_count')}",
        f"Reconciliations            : {_get(evidence, 'reconciliation_count')}",
        f"Duplicate Mutations        : {_get(evidence, 'duplicate_mutation_count')}",
        f"Risk Denials               : {_get(evidence, 'risk_denial_count')}",
        f"Kill-Switch Denials        : {_get(evidence, 'kill_switch_denial_count')}",
        f"Restart Count              : {_get(evidence, 'restart_count')}",
        f"Sanitized Error Count      : {_get(evidence, 'sanitized_error_count')}",
        f"Final Position State       : {_get(evidence, 'final_position_state')}",
        f"Final Persisted State      : {_get(evidence, 'final_persisted_state')}",
        f"Evidence Complete          : {_fmt_bool(_get(evidence, 'evidence_complete'))}",
        "",
        "Execution Classification:",
        "ACTUAL_BINANCE_DEMO_ORDER_TEST" if _get(evidence, 'actual_binance_demo_execution') else "LOCAL TEST / SIMULATED TRANSPORT",
        f"ACTUAL BINANCE DEMO EXECUTION: {_fmt_bool(_get(evidence, 'actual_binance_demo_execution'))}",
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
