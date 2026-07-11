from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.binance_futures_testnet_adapter_engine import BinanceFuturesTestnetAdapterEngine
from models.binance_futures_testnet_adapter import (
    BinanceFuturesTestnetAdapterAction,
    BinanceFuturesTestnetAdapterDecision,
    BinanceFuturesTestnetAdapterResult,
    BinanceFuturesTestnetAdapterStatus,
    BinanceFuturesTestnetIssue,
)
from reporting.binance_futures_testnet_adapter_report import (
    format_binance_futures_testnet_adapter_result,
    format_binance_futures_testnet_adapter_validation_report,
)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    engine = BinanceFuturesTestnetAdapterEngine(repo_root=ROOT_DIR, env=os.environ)
    actions = _selected_actions(args)
    if len(actions) > 1:
        return _emit_result(_invalid_result("Choose only one Binance futures testnet adapter action."), args)
    action = actions[0] if actions else "validate"
    try:
        if action == "validate":
            report = engine.validate(args.config, expected_profile=args.expected_profile)
            payload = report.to_dict()
            rendered = format_binance_futures_testnet_adapter_validation_report(report)
            status = report.status
            _emit_payload(payload, rendered, args)
            if status == "FAIL":
                return 1
            if args.strict and status == "WARNING":
                return 1
            return 0
        if action == "ping_testnet":
            return _emit_result(engine.ping_testnet(args.config, args.expected_profile), args)
        if action == "fetch_server_time":
            return _emit_result(engine.fetch_server_time(args.config, args.expected_profile), args)
        if action == "fetch_exchange_info":
            return _emit_result(engine.fetch_exchange_info(args.config, args.expected_profile), args)
        if action == "check_credentials":
            return _emit_result(engine.check_credentials(args.config, args.expected_profile), args)
        if action == "signed_request_preview":
            if not args.preview_path:
                return _emit_result(_invalid_result("Missing required signed-request-preview argument: preview-path"), args)
            return _emit_result(engine.signed_request_preview(args.preview_path, config_path=args.config, expected_profile=args.expected_profile), args)
        if action == "build_order_intent":
            missing = [name for name in ("intent_id", "side", "order_type", "quantity") if getattr(args, name) is None]
            if missing:
                return _emit_result(_invalid_result(f"Missing required order-intent arguments: {', '.join(name.replace('_', '-') for name in missing)}"), args)
            return _emit_result(engine.build_order_intent(args.intent_id, args.side, args.order_type, args.quantity, args.price, args.stop_price, args.time_in_force, args.reduce_only, args.close_position, args.config, args.expected_profile), args)
    except Exception as exc:
        return _emit_result(_invalid_result(f"Operation failed safely: {exc}"), args)
    return _emit_result(_invalid_result("Unsupported action."), args)


def _emit_result(result: BinanceFuturesTestnetAdapterResult, args: argparse.Namespace) -> int:
    _emit_payload(result.to_dict(), format_binance_futures_testnet_adapter_result(result), args)
    if result.status == "FAIL":
        return 1
    if args.strict and result.status == "WARNING":
        return 1
    return 0


def _emit_payload(payload: dict, rendered: str, args: argparse.Namespace) -> None:
    if args.export_json:
        _atomic_write(args.export_json, json.dumps(payload, indent=2))
        print(f"[binance-futures-testnet-adapter] wrote {args.export_json}", file=sys.stderr if args.json else sys.stdout)
    if args.export_md:
        _atomic_write(args.export_md, rendered)
        print(f"[binance-futures-testnet-adapter] wrote {args.export_md}", file=sys.stderr if args.json else sys.stdout)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(rendered)


def _invalid_result(message: str) -> BinanceFuturesTestnetAdapterResult:
    return BinanceFuturesTestnetAdapterResult(
        action=BinanceFuturesTestnetAdapterAction.VALIDATE.value,
        status=BinanceFuturesTestnetAdapterStatus.FAIL.value,
        decision=BinanceFuturesTestnetAdapterDecision.OPERATION_FAILED.value,
        reason=message,
        issues=[BinanceFuturesTestnetIssue("invalid_cli_request", "FAIL", message)],
    )


def _selected_actions(args: argparse.Namespace) -> list[str]:
    names = ["ping_testnet", "fetch_server_time", "fetch_exchange_info", "check_credentials", "signed_request_preview", "build_order_intent"]
    return [name for name in names if getattr(args, name)]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Binance USD-M Futures Testnet adapter disabled-boundary diagnostics.")
    parser.add_argument("--config", default="configs/binance_futures_testnet_adapter.json")
    parser.add_argument("--expected-profile", default="balanced_smc_decision_065")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--export-json", default=None)
    parser.add_argument("--export-md", default=None)
    parser.add_argument("--ping-testnet", action="store_true")
    parser.add_argument("--fetch-server-time", action="store_true")
    parser.add_argument("--fetch-exchange-info", action="store_true")
    parser.add_argument("--check-credentials", action="store_true")
    parser.add_argument("--signed-request-preview", action="store_true")
    parser.add_argument("--preview-path", default=None)
    parser.add_argument("--build-order-intent", action="store_true")
    parser.add_argument("--intent-id", default=None)
    parser.add_argument("--side", choices=["BUY", "SELL"])
    parser.add_argument("--order-type", default=None)
    parser.add_argument("--quantity", type=float)
    parser.add_argument("--price", type=float)
    parser.add_argument("--stop-price", type=float)
    parser.add_argument("--time-in-force", default=None)
    parser.add_argument("--reduce-only", action="store_true")
    parser.add_argument("--close-position", action="store_true")
    return parser


def _atomic_write(path_text: str, content: str) -> None:
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
