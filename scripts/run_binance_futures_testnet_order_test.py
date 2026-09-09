from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.binance_futures_testnet_order_test_engine import BinanceFuturesTestnetOrderTestEngine
from infrastructure.observability.operational_metrics import OperationalCounterRegistry
from models.live_execution_permit_enforcement import LiveExecutionPermitReference
from models.binance_futures_testnet_order_test import (
    BinanceFuturesTestnetOrderTestAction,
    BinanceFuturesTestnetOrderTestDecision,
    BinanceFuturesTestnetOrderTestIssue,
    BinanceFuturesTestnetOrderTestResult,
    BinanceFuturesTestnetOrderTestStatus,
)
from reporting.binance_futures_testnet_order_test_report import (
    format_binance_futures_testnet_order_test_result,
    format_binance_futures_testnet_order_test_validation_report,
)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    actions = _selected_actions(args)
    if len(actions) > 1:
        return _emit_result(_invalid_result("Choose only one Binance futures testnet order-test action."), args)
    action = actions[0] if actions else "validate"
    try:
        permit = None
        if action == "submit_test_order":
            permit = _required_permit_reference(args.permit_id, args.permit_version)
        operational_counter_registry = OperationalCounterRegistry()
        engine = BinanceFuturesTestnetOrderTestEngine(repo_root=ROOT_DIR, env=os.environ, operational_counter_registry=operational_counter_registry)
        if action == "validate":
            report = engine.validate(args.config, expected_profile=args.expected_profile)
            _emit_payload(report.to_dict(), format_binance_futures_testnet_order_test_validation_report(report), args)
            if report.status == "FAIL" or (args.strict and report.status == "WARNING"):
                return 1
            return 0
        if action == "check_credentials":
            return _emit_result(engine.check_credentials(args.config, args.expected_profile), args)
        if action == "build_preview":
            return _emit_result(
                engine.build_preview(args.client_order_id, args.side, args.order_type, args.quantity, args.price, args.time_in_force, args.reduce_only, args.config, args.expected_profile),
                args,
            )
        if action == "submit_test_order":
            return _emit_result(
                engine.submit_test_order(
                    args.client_order_id,
                    args.side,
                    args.order_type,
                    args.quantity,
                    args.price,
                    args.time_in_force,
                    args.reduce_only,
                    args.confirm_testnet_order_test,
                    args.config,
                    args.expected_profile,
                    permit=permit,
                ),
                args,
            )
    except Exception as exc:
        return _emit_result(_invalid_result(f"Operation failed safely: {_sanitize_cli_error(str(exc))}"), args)
    return _emit_result(_invalid_result("Unsupported action."), args)

def _emit_result(result: BinanceFuturesTestnetOrderTestResult, args: argparse.Namespace) -> int:
    _emit_payload(result.to_dict(), format_binance_futures_testnet_order_test_result(result), args)
    if result.status == "FAIL" or (args.strict and result.status == "WARNING"):
        return 1
    return 0


def _emit_payload(payload: dict, rendered: str, args: argparse.Namespace) -> None:
    if args.export_json:
        _atomic_write(args.export_json, json.dumps(payload, indent=2))
        print(f"[binance-futures-testnet-order-test] wrote {args.export_json}", file=sys.stderr if args.json else sys.stdout)
    if args.export_md:
        _atomic_write(args.export_md, rendered)
        print(f"[binance-futures-testnet-order-test] wrote {args.export_md}", file=sys.stderr if args.json else sys.stdout)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(rendered)


def _invalid_result(message: str) -> BinanceFuturesTestnetOrderTestResult:
    return BinanceFuturesTestnetOrderTestResult(
        action=BinanceFuturesTestnetOrderTestAction.VALIDATE.value,
        status=BinanceFuturesTestnetOrderTestStatus.FAIL.value,
        decision=BinanceFuturesTestnetOrderTestDecision.ACTUAL_ORDER_OPERATION_BLOCKED.value,
        reason=message,
        issues=[BinanceFuturesTestnetOrderTestIssue("invalid_cli_request", "FAIL", message)],
    )


def _selected_actions(args: argparse.Namespace) -> list[str]:
    names = ["check_credentials", "build_preview", "submit_test_order"]
    return [name for name in names if getattr(args, name)]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Binance USD-M Futures Testnet Test Order preflight diagnostics.")
    parser.add_argument("--config", default="configs/binance_futures_testnet_order_test.json")
    parser.add_argument("--expected-profile", default="balanced_smc_decision_065")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--validate-only", action="store_true", help="Alias for default validation.")
    parser.add_argument("--export-json", default=None)
    parser.add_argument("--export-md", default=None)
    parser.add_argument("--check-credentials", action="store_true")
    parser.add_argument("--build-preview", action="store_true")
    parser.add_argument("--submit-test-order", action="store_true")
    parser.add_argument("--client-order-id", default="smcbot-test-preview-001")
    parser.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--order-type", choices=["MARKET", "LIMIT"], default="MARKET")
    parser.add_argument("--quantity", type=float, default=0.001)
    parser.add_argument("--price", type=float, default=None)
    parser.add_argument("--time-in-force", choices=["GTC", "IOC", "FOK"], default=None)
    parser.add_argument("--reduce-only", action="store_true")
    parser.add_argument("--confirm-testnet-order-test", default=None)
    parser.add_argument("--permit-id", default=None)
    parser.add_argument("--permit-version", type=int, default=None)
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
            return "redacted authenticated test order error"
    return text[:180]


if __name__ == "__main__":
    raise SystemExit(main())
