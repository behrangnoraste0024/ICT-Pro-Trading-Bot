from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.binance_futures_testnet_forward_test_engine import BinanceFuturesTestnetForwardTestEngine
from models.live_execution_permit_enforcement import LiveExecutionPermitReference
from reporting.binance_futures_testnet_forward_test_report import (
    format_binance_futures_testnet_forward_test_result,
    format_binance_futures_testnet_forward_test_validation_report,
)


def main(argv: list[str] | None = None, *, order_test_engine=None) -> int:
    args = _parser().parse_args(argv)
    engine = BinanceFuturesTestnetForwardTestEngine(repo_root=ROOT_DIR, order_test_engine=order_test_engine)
    try:
        if args.run:
            permit_references = _permit_references(args.permit_id, args.permit_version)
            runtime_environment = _runtime_environment_from_process() if args.enable_testnet_order_test_network else None
            result = engine.run(
                args.config,
                args.expected_profile,
                execution_authorized=args.authorize_supervised_testnet_order_test,
                execution_mode="SUPERVISED_TESTNET_ORDER_TEST" if args.supervised_testnet_order_test else None,
                confirmation=args.order_test_confirmation,
                api_key_identifier=args.testnet_api_key_identifier,
                api_secret_identifier=args.testnet_api_secret_identifier,
                testnet_order_test_network_enabled=args.enable_testnet_order_test_network,
                runtime_environment=runtime_environment,
                order_test_request={
                    "client_order_id": args.order_test_client_id,
                    "side": args.order_test_side,
                    "order_type": args.order_test_type,
                    "quantity": args.order_test_quantity,
                    "price": args.order_test_price,
                    "time_in_force": args.order_test_time_in_force,
                } if args.supervised_testnet_order_test else None,
                permit_references=permit_references,
                local_simulated_transport=args.local_simulated_transport,
                strategy_decision_count=args.strategy_decisions,
                risk_denial_count=args.risk_denials,
                kill_switch_denial_count=args.kill_switch_denials,
                restart_count=args.restart_count,
            )
            _emit_payload(result.to_dict(), format_binance_futures_testnet_forward_test_result(result), args)
            return 1 if result.status == "FAIL" or (args.strict and result.status == "WARNING") else 0
        report = engine.validate(args.config, args.expected_profile)
        _emit_payload(report.to_dict(), format_binance_futures_testnet_forward_test_validation_report(report), args)
        return 1 if report.status == "FAIL" or (args.strict and report.status == "WARNING") else 0
    except Exception:
        payload = {
            "schema_version": "1.0",
            "status": "FAIL",
            "decision": "CONFIG_INVALID",
            "reason": "sanitized forward-test error",
        }
        _emit_payload(payload, "===== BINANCE FUTURES TESTNET FORWARD TEST RESULT =====\nStatus                     : FAIL\nDecision                   : CONFIG_INVALID\nReason                     : sanitized forward-test error", args)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run disabled Binance Futures Testnet forward-test orchestration evidence checks.")
    parser.add_argument("--config", default="configs/binance_futures_testnet_forward_test.json")
    parser.add_argument("--expected-profile", default="balanced_smc_decision_065")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--supervised-testnet-order-test", action="store_true")
    parser.add_argument("--authorize-supervised-testnet-order-test", action="store_true")
    parser.add_argument("--enable-testnet-order-test-network", action="store_true")
    parser.add_argument("--order-test-confirmation", default=None)
    parser.add_argument("--testnet-api-key-identifier", default=None)
    parser.add_argument("--testnet-api-secret-identifier", default=None)
    parser.add_argument("--order-test-client-id", default=None)
    parser.add_argument("--order-test-side", default=None)
    parser.add_argument("--order-test-type", default=None)
    parser.add_argument("--order-test-quantity", type=float, default=None)
    parser.add_argument("--order-test-price", type=float, default=None)
    parser.add_argument("--order-test-time-in-force", default=None)
    parser.add_argument("--local-simulated-transport", action="store_true")
    parser.add_argument("--strategy-decisions", type=int, default=0)
    parser.add_argument("--risk-denials", type=int, default=0)
    parser.add_argument("--kill-switch-denials", type=int, default=0)
    parser.add_argument("--restart-count", type=int, default=0)
    parser.add_argument("--permit-id", action="append", default=[])
    parser.add_argument("--permit-version", action="append", type=int, default=[])
    parser.add_argument("--export-json", default=None)
    parser.add_argument("--export-md", default=None)
    return parser


def _runtime_environment_from_process() -> dict[str, str]:
    allowed = (
        "BINANCE_FUTURES_TESTNET_API_KEY",
        "BINANCE_FUTURES_TESTNET_API_SECRET",
        "ICT_DATABASE_URL",
        "DATABASE_URL",
    )
    return {key: value for key in allowed if isinstance((value := os.environ.get(key)), str)}


def _permit_references(permit_ids: list[str], versions: list[int]) -> list[LiveExecutionPermitReference]:
    if len(permit_ids) != len(versions):
        raise ValueError("permit IDs and versions must be supplied in matching counts")
    return [LiveExecutionPermitReference(permit_id, version) for permit_id, version in zip(permit_ids, versions)]


def _emit_payload(payload: dict, rendered: str, args: argparse.Namespace) -> None:
    if args.export_json:
        _atomic_write(args.export_json, json.dumps(payload, indent=2))
        print(f"[binance-futures-testnet-forward-test] wrote {args.export_json}", file=sys.stderr if args.json else sys.stdout)
    if args.export_md:
        _atomic_write(args.export_md, rendered)
        print(f"[binance-futures-testnet-forward-test] wrote {args.export_md}", file=sys.stderr if args.json else sys.stdout)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(rendered)


def _atomic_write(path_text: str, content: str) -> None:
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
