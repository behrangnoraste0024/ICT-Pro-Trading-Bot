from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.binance_futures_testnet_order_lifecycle_engine import BinanceFuturesTestnetOrderLifecycleEngine
from models.binance_futures_testnet_order_lifecycle import (
    BinanceFuturesTestnetLifecycleIssue,
    BinanceFuturesTestnetLifecycleResult,
    LifecycleAction,
    LifecycleDecision,
)
from reporting.binance_futures_testnet_order_lifecycle_report import (
    format_binance_futures_testnet_order_lifecycle_result,
    format_binance_futures_testnet_order_lifecycle_validation_report,
)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    engine = BinanceFuturesTestnetOrderLifecycleEngine(repo_root=ROOT_DIR, env=os.environ)
    actions = _selected_actions(args)
    if len(actions) > 1:
        return _emit_result(_invalid_result("Choose only one Binance futures testnet lifecycle action."), args)
    action = actions[0] if actions else "validate"
    try:
        if action == "validate":
            report = engine.validate(args.config, expected_profile=args.expected_profile)
            _emit_payload(report.to_dict(), format_binance_futures_testnet_order_lifecycle_validation_report(report), args)
            if report.status == "FAIL" or (args.strict and report.status == "WARNING"):
                return 1
            return 0
        if action == "check_credentials":
            return _emit_result(engine.check_credentials(args.config, args.expected_profile), args)
        if action == "build_preview":
            return _emit_result(engine.build_preview(args.lifecycle_id, args.client_order_id, args.side, args.quantity, args.price_offset_bps, args.config, args.expected_profile), args)
        if action == "run_lifecycle":
            return _emit_result(engine.run_lifecycle(args.lifecycle_id, args.client_order_id, args.side, args.quantity, args.price_offset_bps, args.confirm_testnet_lifecycle, args.config, args.expected_profile), args)
        if action == "query_order":
            return _emit_result(engine.query_order(args.client_order_id, args.confirm_testnet_query, args.config, args.expected_profile), args)
        if action == "recovery_cancel":
            return _emit_result(engine.recovery_cancel(args.client_order_id, args.confirm_testnet_cancel, args.config, args.expected_profile), args)
    except Exception as exc:
        return _emit_result(_invalid_result(f"Operation failed safely: {_sanitize_cli_error(str(exc))}"), args)
    return _emit_result(_invalid_result("Unsupported action."), args)


def _emit_result(result: BinanceFuturesTestnetLifecycleResult, args: argparse.Namespace) -> int:
    _emit_payload(result.to_dict(), format_binance_futures_testnet_order_lifecycle_result(result), args)
    if result.status in ("FAIL", "CRITICAL") or (args.strict and result.status == "WARNING"):
        return 1
    return 0


def _emit_payload(payload: dict, rendered: str, args: argparse.Namespace) -> None:
    if args.export_json:
        _atomic_write(args.export_json, json.dumps(payload, indent=2))
        print(f"[binance-futures-testnet-order-lifecycle] wrote {args.export_json}", file=sys.stderr if args.json else sys.stdout)
    if args.export_md:
        _atomic_write(args.export_md, rendered)
        print(f"[binance-futures-testnet-order-lifecycle] wrote {args.export_md}", file=sys.stderr if args.json else sys.stdout)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(rendered)


def _invalid_result(message: str) -> BinanceFuturesTestnetLifecycleResult:
    return BinanceFuturesTestnetLifecycleResult(
        action=LifecycleAction.VALIDATE.value,
        status="FAIL",
        decision=LifecycleDecision.OPERATION_BLOCKED.value,
        reason=message,
        issues=[BinanceFuturesTestnetLifecycleIssue("invalid_cli_request", "FAIL", message)],
    )


def _selected_actions(args: argparse.Namespace) -> list[str]:
    names = ["check_credentials", "build_preview", "run_lifecycle", "query_order", "recovery_cancel"]
    return [name for name in names if getattr(args, name)]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Binance USD-M Futures Testnet manual post-only LIMIT lifecycle diagnostics.")
    parser.add_argument("--config", default="configs/binance_futures_testnet_order_lifecycle.json")
    parser.add_argument("--expected-profile", default="balanced_smc_decision_065")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--validate-only", action="store_true", help="Alias for default validation.")
    parser.add_argument("--export-json", default=None)
    parser.add_argument("--export-md", default=None)
    parser.add_argument("--check-credentials", action="store_true")
    parser.add_argument("--build-preview", action="store_true")
    parser.add_argument("--run-lifecycle", action="store_true")
    parser.add_argument("--query-order", action="store_true")
    parser.add_argument("--recovery-cancel", action="store_true")
    parser.add_argument("--lifecycle-id", default="lifecycle-local-001")
    parser.add_argument("--client-order-id", default="smcbot-lifecycle-001")
    parser.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--quantity", type=float, default=0.001)
    parser.add_argument("--price-offset-bps", type=int, default=100)
    parser.add_argument("--confirm-testnet-lifecycle", default=None)
    parser.add_argument("--confirm-testnet-query", default=None)
    parser.add_argument("--confirm-testnet-cancel", default=None)
    return parser


def _atomic_write(path_text: str, content: str) -> None:
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


def _sanitize_cli_error(text: str) -> str:
    for marker in ("signature=", "X-MBX-APIKEY", "BINANCE_FUTURES_TESTNET_API_KEY", "BINANCE_FUTURES_TESTNET_API_SECRET"):
        if marker in text:
            return "redacted authenticated lifecycle error"
    return text[:180]


if __name__ == "__main__":
    raise SystemExit(main())
