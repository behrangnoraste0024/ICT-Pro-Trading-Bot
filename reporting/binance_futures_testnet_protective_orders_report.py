from __future__ import annotations

from models.binance_futures_testnet_protective_orders import (
    BinanceFuturesTestnetProtectiveResult,
    BinanceFuturesTestnetProtectiveValidationReport,
)


def format_binance_futures_testnet_protective_orders_validation_report(report: BinanceFuturesTestnetProtectiveValidationReport) -> str:
    config = report.config
    lines = [
        "===== BINANCE FUTURES TESTNET PROTECTIVE SL/TP VALIDATION =====",
        f"Config Path                  : {report.config_path}",
        f"Status                       : {report.status}",
        f"Feature Enabled              : {_fmt_bool(_get(config, 'feature_enabled'))}",
        f"Manual Only                  : {_fmt_bool(_get(config, 'manual_only'))}",
        f"Testnet Only                 : {_fmt_bool(_get(config, 'testnet_only'))}",
        f"Symbol                       : {_get(config, 'exchange_symbol')}",
        f"Algo Path                    : {_get(config, 'algo_order_path')}",
        f"Allowed Types                : {_get(config, 'allowed_order_types')}",
        f"Allowed Methods              : {_get(config, 'allowed_methods')}",
        f"Create Retries               : {_get(config, 'max_create_retries')}",
        f"Cancel Retries               : {_get(config, 'max_cancel_retries')}",
        f"Position Entry               : {_fmt_bool(_get(config, 'allow_position_entry'))}",
        f"Position Close               : {_fmt_bool(_get(config, 'allow_position_close'))}",
        f"Production Endpoint          : {_fmt_bool(_get(config, 'allow_production_endpoint'))}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    lines.extend(_issue_lines(report.issues))
    return "\n".join(lines)


def format_binance_futures_testnet_protective_orders_result(result: BinanceFuturesTestnetProtectiveResult) -> str:
    lines = [
        "===== BINANCE FUTURES TESTNET PROTECTIVE SL/TP LIFECYCLE =====",
        f"Action                    : {result.action}",
        f"Status                    : {result.status}",
        f"Decision                  : {result.decision}",
        f"Reason                    : {result.reason}",
        f"Pair ID                   : {result.pair_id}",
        f"Phase                     : {result.phase}",
        f"STOP Client Algo ID       : {result.stop_client_algo_id}",
        f"TAKE_PROFIT Client Algo ID: {result.take_profit_client_algo_id}",
    ]
    if result.preview is not None:
        lines.extend(
            [
                "",
                "Protective Preview:",
                f"Position Direction        : {result.preview.position_direction}",
                f"Position Amount           : {result.preview.position_amount}",
                f"Entry Price               : {result.preview.entry_price}",
                f"Mark Price                : {result.preview.mark_price}",
                f"Protective Side           : {result.preview.protective_side}",
                f"Stop Trigger              : {result.preview.stop_trigger}",
                f"Take Profit Trigger       : {result.preview.take_profit_trigger}",
                f"Transmission Ready        : {_fmt_bool(result.preview.transmission_ready)}",
            ]
        )
    lines.extend(
        [
            "",
            "Lifecycle:",
            f"STOP Status               : {_order_attr(result.final_stop_order or result.stop_order, 'algo_status')}",
            f"STOP Algo ID              : {_order_attr(result.final_stop_order or result.stop_order, 'algo_id')}",
            f"TAKE_PROFIT Status        : {_order_attr(result.final_take_profit_order or result.take_profit_order, 'algo_status')}",
            f"TAKE_PROFIT Algo ID       : {_order_attr(result.final_take_profit_order or result.take_profit_order, 'algo_id')}",
            f"Create Transmitted        : {_fmt_bool(result.create_request_transmitted)}",
            f"Query Transmitted         : {_fmt_bool(result.query_request_transmitted)}",
            f"Cancel Transmitted        : {_fmt_bool(result.cancel_request_transmitted)}",
            f"Lifecycle Complete        : {_fmt_bool(result.lifecycle_complete)}",
            f"Recovery Required         : {_fmt_bool(result.recovery_required)}",
            f"Unexpected Trigger        : {_fmt_bool(result.unexpected_trigger)}",
            f"Unexpected Position Change: {_fmt_bool(result.unexpected_position_change)}",
            "",
            "Mutation Reconciliation:",
            "Label | Kind | ClientAlgoId | State | Result | Resolved | Recovery | Reason",
        ]
    )
    lines.extend(_reconciliation_lines(result.reconciliation_results))
    lines.extend(
        [
            "",
            "Safety:",
            f"Production Endpoint Used  : {_fmt_bool(result.production_endpoint_used)}",
            f"Real Funds Used           : {_fmt_bool(result.real_funds_used)}",
            f"Secrets Exposed           : {_fmt_bool(result.secrets_exposed)}",
            "",
            "Issues:",
            "Name | Severity | Message",
        ]
    )
    lines.extend(_issue_lines(result.issues))
    return "\n".join(lines)



def _reconciliation_lines(results) -> list[str]:
    if not results:
        return ["None | INFO | No mutation reconciliation results."]
    return [
        f"{item.label} | {item.mutation_kind} | {item.client_algo_id} | {item.reconciliation_state} | {item.interpreted_mutation_result} | {_fmt_bool(item.resolved)} | {_fmt_bool(item.recovery_required)} | {item.reason}"
        for item in results
    ]

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
