from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.binance_futures_testnet_protective_orders_engine import BinanceFuturesTestnetProtectiveOrdersEngine
from models.binance_futures_testnet_protective_orders import BinanceFuturesTestnetProtectiveIssue, BinanceFuturesTestnetProtectiveResult
from models.live_execution_permit_enforcement import LiveExecutionPermitReference
from reporting.binance_futures_testnet_protective_orders_report import (
    format_binance_futures_testnet_protective_orders_result,
    format_binance_futures_testnet_protective_orders_validation_report,
)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    actions = _selected_actions(args)
    if len(actions) > 1:
        return _emit_result(_invalid_result("Choose only one Binance futures testnet protective action."), args)
    action = actions[0] if actions else "validate"
    try:
        stop_create_permit = None
        take_profit_create_permit = None
        take_profit_cancel_permit = None
        stop_cancel_permit = None
        if action == "run_protective_lifecycle":
            stop_create_permit = _required_permit_reference(args.stop_create_permit_id, args.stop_create_permit_version)
            take_profit_create_permit = _required_permit_reference(args.take_profit_create_permit_id, args.take_profit_create_permit_version)
            take_profit_cancel_permit = _required_permit_reference(args.take_profit_cancel_permit_id, args.take_profit_cancel_permit_version)
            stop_cancel_permit = _required_permit_reference(args.stop_cancel_permit_id, args.stop_cancel_permit_version)
        engine = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=ROOT_DIR, env=os.environ)
        if action == "validate":
            report = engine.validate(args.config, args.expected_profile)
            _emit_payload(report.to_dict(), format_binance_futures_testnet_protective_orders_validation_report(report), args)
            if report.status == "FAIL" or (args.strict and report.status == "WARNING"):
                return 1
            return 0
        if action == "check_credentials":
            return _emit_result(engine.check_credentials(args.config, args.expected_profile), args)
        if action == "build_preview":
            return _emit_result(
                engine.build_preview(
                    args.pair_id,
                    args.stop_client_algo_id,
                    args.take_profit_client_algo_id,
                    args.preview_position_amount,
                    args.preview_mark_price,
                    args.preview_entry_price,
                    args.preview_tick_size,
                    args.stop_offset_bps,
                    args.take_profit_offset_bps,
                    args.config,
                    args.expected_profile,
                ),
                args,
            )
        if action == "run_protective_lifecycle":
            return _emit_result(
                engine.run_protective_lifecycle(
                    args.pair_id,
                    args.stop_client_algo_id,
                    args.take_profit_client_algo_id,
                    args.stop_offset_bps,
                    args.take_profit_offset_bps,
                    args.confirm_testnet_protective_pair,
                    args.config,
                    args.expected_profile,
                    stop_create_permit=stop_create_permit,
                    take_profit_create_permit=take_profit_create_permit,
                    take_profit_cancel_permit=take_profit_cancel_permit,
                    stop_cancel_permit=stop_cancel_permit,
                ),
                args,
            )
        if action == "query_protective_pair":
            return _emit_result(engine.query_protective_pair(args.stop_client_algo_id, args.take_profit_client_algo_id, args.config, args.expected_profile), args)
        if action == "recover_protective_pair":
            return _emit_result(
                engine.recover_protective_pair(
                    args.stop_client_algo_id,
                    args.take_profit_client_algo_id,
                    args.confirm_testnet_protective_recovery,
                    args.config,
                    args.expected_profile,
                    stop_cancel_permit=_permit_reference(args.stop_cancel_permit_id, args.stop_cancel_permit_version),
                    take_profit_cancel_permit=_permit_reference(args.take_profit_cancel_permit_id, args.take_profit_cancel_permit_version),
                ),
                args,
            )
    except Exception as exc:
        return _emit_result(_invalid_result(f"Operation failed safely: {_sanitize_cli_error(str(exc))}"), args)
    return _emit_result(_invalid_result("Unsupported action."), args)

def _emit_result(result: BinanceFuturesTestnetProtectiveResult, args: argparse.Namespace) -> int:
    _emit_payload(result.to_dict(), format_binance_futures_testnet_protective_orders_result(result), args)
    if result.status in ("FAIL", "CRITICAL") or (args.strict and result.status == "WARNING"):
        return 1
    return 0


def _emit_payload(payload: dict, rendered: str, args: argparse.Namespace) -> None:
    if args.export_json:
        _atomic_write(args.export_json, json.dumps(payload, indent=2))
        print(f"[binance-futures-testnet-protective-orders] wrote {args.export_json}", file=sys.stderr if args.json else sys.stdout)
    if args.export_md:
        _atomic_write(args.export_md, rendered)
        print(f"[binance-futures-testnet-protective-orders] wrote {args.export_md}", file=sys.stderr if args.json else sys.stdout)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(rendered)


def _invalid_result(message: str) -> BinanceFuturesTestnetProtectiveResult:
    return BinanceFuturesTestnetProtectiveResult(
        action="VALIDATE",
        status="FAIL",
        decision="OPERATION_BLOCKED",
        reason=message,
        issues=[BinanceFuturesTestnetProtectiveIssue("invalid_cli_request", "FAIL", message)],
    )


def _selected_actions(args: argparse.Namespace) -> list[str]:
    names = ["check_credentials", "build_preview", "run_protective_lifecycle", "query_protective_pair", "recover_protective_pair"]
    return [name for name in names if getattr(args, name)]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Binance USD-M Futures Testnet protective SL/TP lifecycle diagnostics.")
    parser.add_argument("--config", default="configs/binance_futures_testnet_protective_orders.json")
    parser.add_argument("--expected-profile", default="balanced_smc_decision_065")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--export-json", default=None)
    parser.add_argument("--export-md", default=None)
    parser.add_argument("--check-credentials", action="store_true")
    parser.add_argument("--build-preview", action="store_true")
    parser.add_argument("--run-protective-lifecycle", action="store_true")
    parser.add_argument("--query-protective-pair", action="store_true")
    parser.add_argument("--recover-protective-pair", action="store_true")
    parser.add_argument("--pair-id", default="protective-local-001")
    parser.add_argument("--stop-client-algo-id", default="")
    parser.add_argument("--take-profit-client-algo-id", default="")
    parser.add_argument("--stop-offset-bps", type=int, default=1000)
    parser.add_argument("--take-profit-offset-bps", type=int, default=1000)
    parser.add_argument("--confirm-testnet-protective-pair", default=None)
    parser.add_argument("--confirm-testnet-protective-recovery", default=None)
    parser.add_argument("--preview-position-amount", default="0.001")
    parser.add_argument("--preview-mark-price", default="50000")
    parser.add_argument("--preview-entry-price", default="49000")
    parser.add_argument("--preview-tick-size", default="0.10")
    parser.add_argument("--stop-create-permit-id", default=None)
    parser.add_argument("--stop-create-permit-version", type=int, default=None)
    parser.add_argument("--take-profit-create-permit-id", default=None)
    parser.add_argument("--take-profit-create-permit-version", type=int, default=None)
    parser.add_argument("--take-profit-cancel-permit-id", default=None)
    parser.add_argument("--take-profit-cancel-permit-version", type=int, default=None)
    parser.add_argument("--stop-cancel-permit-id", default=None)
    parser.add_argument("--stop-cancel-permit-version", type=int, default=None)
    return parser


def _required_permit_reference(permit_id: str | None, expected_version: int | None) -> LiveExecutionPermitReference:
    if permit_id is None or expected_version is None:
        raise ValueError("permit ID and expected version must be provided together")
    return LiveExecutionPermitReference(permit_id, expected_version)


def _permit_reference(permit_id: str | None, expected_version: int | None) -> LiveExecutionPermitReference | None:
    if permit_id is None and expected_version is None:
        return None
    return _required_permit_reference(permit_id, expected_version)

def _atomic_write(path_text: str, content: str) -> None:
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


def _sanitize_cli_error(text: str) -> str:
    for marker in ("signature=", "X-MBX-APIKEY", "BINANCE_FUTURES_TESTNET_API_KEY", "BINANCE_FUTURES_TESTNET_API_SECRET"):
        if marker in text:
            return "redacted authenticated protective-order error"
    return text[:180]


if __name__ == "__main__":
    raise SystemExit(main())
