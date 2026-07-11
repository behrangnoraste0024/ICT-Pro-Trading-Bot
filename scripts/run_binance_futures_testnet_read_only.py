from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.binance_futures_testnet_read_only_engine import BinanceFuturesTestnetReadOnlyEngine
from models.binance_futures_testnet_read_only import (
    BinanceFuturesTestnetReadOnlyAction,
    BinanceFuturesTestnetReadOnlyDecision,
    BinanceFuturesTestnetReadOnlyIssue,
    BinanceFuturesTestnetReadOnlyResult,
    BinanceFuturesTestnetReadOnlyStatus,
)
from reporting.binance_futures_testnet_read_only_report import (
    format_binance_futures_testnet_read_only_result,
    format_binance_futures_testnet_read_only_validation_report,
)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    engine = BinanceFuturesTestnetReadOnlyEngine(repo_root=ROOT_DIR, env=os.environ)
    actions = _selected_actions(args)
    if len(actions) > 1:
        return _emit_result(_invalid_result("Choose only one Binance futures testnet read-only action."), args)
    action = actions[0] if actions else "validate"
    try:
        if action == "validate":
            report = engine.validate(args.config, expected_profile=args.expected_profile)
            _emit_payload(report.to_dict(), format_binance_futures_testnet_read_only_validation_report(report), args)
            if report.status == "FAIL" or (args.strict and report.status == "WARNING"):
                return 1
            return 0
        if action == "check_credentials":
            return _emit_result(engine.check_credentials(args.config, args.expected_profile), args)
        if action == "fetch_account":
            return _emit_result(engine.fetch_account(args.confirm_testnet_read_only, args.config, args.expected_profile), args)
        if action == "fetch_balance":
            return _emit_result(engine.fetch_balance(args.asset, args.confirm_testnet_read_only, args.config, args.expected_profile), args)
        if action == "fetch_position_risk":
            return _emit_result(engine.fetch_position_risk(args.symbol, args.confirm_testnet_read_only, args.config, args.expected_profile), args)
        if action == "fetch_account_snapshot":
            return _emit_result(engine.fetch_account_snapshot(args.confirm_testnet_read_only, args.config, args.expected_profile), args)
    except Exception as exc:
        return _emit_result(_invalid_result(f"Operation failed safely: {_sanitize_cli_error(str(exc))}"), args)
    return _emit_result(_invalid_result("Unsupported action."), args)


def _emit_result(result: BinanceFuturesTestnetReadOnlyResult, args: argparse.Namespace) -> int:
    _emit_payload(result.to_dict(), format_binance_futures_testnet_read_only_result(result), args)
    if result.status == "FAIL" or (args.strict and result.status == "WARNING"):
        return 1
    return 0


def _emit_payload(payload: dict, rendered: str, args: argparse.Namespace) -> None:
    if args.export_json:
        _atomic_write(args.export_json, json.dumps(payload, indent=2))
        print(f"[binance-futures-testnet-read-only] wrote {args.export_json}", file=sys.stderr if args.json else sys.stdout)
    if args.export_md:
        _atomic_write(args.export_md, rendered)
        print(f"[binance-futures-testnet-read-only] wrote {args.export_md}", file=sys.stderr if args.json else sys.stdout)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(rendered)


def _invalid_result(message: str) -> BinanceFuturesTestnetReadOnlyResult:
    return BinanceFuturesTestnetReadOnlyResult(
        action=BinanceFuturesTestnetReadOnlyAction.VALIDATE.value,
        status=BinanceFuturesTestnetReadOnlyStatus.FAIL.value,
        decision=BinanceFuturesTestnetReadOnlyDecision.OPERATION_BLOCKED.value,
        reason=message,
        issues=[BinanceFuturesTestnetReadOnlyIssue("invalid_cli_request", "FAIL", message)],
    )


def _selected_actions(args: argparse.Namespace) -> list[str]:
    names = ["check_credentials", "fetch_account", "fetch_balance", "fetch_position_risk", "fetch_account_snapshot"]
    return [name for name in names if getattr(args, name)]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Binance USD-M Futures Testnet authenticated read-only diagnostics.")
    parser.add_argument("--config", default="configs/binance_futures_testnet_read_only.json")
    parser.add_argument("--expected-profile", default="balanced_smc_decision_065")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--export-json", default=None)
    parser.add_argument("--export-md", default=None)
    parser.add_argument("--check-credentials", action="store_true")
    parser.add_argument("--fetch-account", action="store_true")
    parser.add_argument("--fetch-balance", action="store_true")
    parser.add_argument("--fetch-position-risk", action="store_true")
    parser.add_argument("--fetch-account-snapshot", action="store_true")
    parser.add_argument("--asset", default="USDT")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--confirm-testnet-read-only", default=None)
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
            return "redacted authenticated read-only error"
    return text[:180]


if __name__ == "__main__":
    raise SystemExit(main())
