from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.btc_futures_paper_position_engine import BTCFuturesPaperPositionEngine
from models.btc_futures_paper_position import (
    BTCFuturesPaperAction,
    BTCFuturesPaperActionResult,
    BTCFuturesPaperDecision,
    BTCFuturesPaperIssue,
    BTCFuturesPaperStatus,
)
from reporting.btc_futures_paper_position_report import (
    format_btc_futures_paper_action_result,
    format_btc_futures_paper_ledger_summary,
    format_btc_futures_paper_validation_report,
)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    engine = BTCFuturesPaperPositionEngine(repo_root=ROOT_DIR)
    selected = _selected_actions(args)
    if len(selected) > 1:
        return _emit_action_result(_invalid_result("Choose only one futures paper position action.", args), args)
    action = selected[0] if selected else "validate"
    try:
        if action == "validate":
            report = engine.validate(args.config, expected_profile=args.expected_profile)
            payload = report.to_dict()
            rendered = format_btc_futures_paper_validation_report(report)
            status = report.status
        elif action == "status":
            result = engine.status(args.config, expected_profile=args.expected_profile)
            return _emit_action_result(result, args)
        elif action == "initialize":
            result = engine.initialize(args.config, expected_profile=args.expected_profile, force=args.force)
            return _emit_action_result(result, args)
        elif action == "reset":
            result = engine.reset(args.config, expected_profile=args.expected_profile, force=args.force)
            return _emit_action_result(result, args)
        elif action == "open_position":
            missing = _missing(args, "side", "entry_price", "mark_price", "stop_loss", "take_profit", "notional", "leverage")
            if missing:
                return _emit_action_result(_invalid_result(f"Missing required open-position arguments: {', '.join(missing)}", args), args)
            result = engine.open_position(args.side, args.entry_price, args.mark_price, args.stop_loss, args.take_profit, args.notional, args.leverage, args.action_id, args.config, args.expected_profile)
            return _emit_action_result(result, args)
        elif action == "mark_to_market":
            if args.mark_price is None:
                return _emit_action_result(_invalid_result("Missing required mark-to-market argument: mark-price", args), args)
            result = engine.mark_to_market(args.mark_price, args.action_id, args.config, args.expected_profile)
            return _emit_action_result(result, args)
        elif action == "mark_to_market_live":
            result = engine.mark_to_market_live(args.action_id, args.config, args.expected_profile)
            return _emit_action_result(result, args)
        elif action == "apply_funding":
            if args.funding_rate is None:
                return _emit_action_result(_invalid_result("Missing required apply-funding argument: funding-rate", args), args)
            result = engine.apply_funding(args.funding_rate, args.funding_periods, args.action_id, args.config, args.expected_profile)
            return _emit_action_result(result, args)
        elif action == "apply_funding_live":
            result = engine.apply_funding_live(args.action_id, args.config, args.expected_profile)
            return _emit_action_result(result, args)
        elif action == "close_position":
            if args.close_price is None:
                return _emit_action_result(_invalid_result("Missing required close-position argument: close-price", args), args)
            result = engine.close_position(args.close_price, args.close_reason, args.action_id, args.config, args.expected_profile)
            return _emit_action_result(result, args)
        elif action == "ledger_summary":
            summary = engine.ledger_summary(args.config)
            payload = summary.to_dict()
            rendered = format_btc_futures_paper_ledger_summary(summary)
            status = "PASS"
        elif action == "simulate_lifecycle":
            result = engine.simulate_lifecycle(args.config, args.expected_profile)
            return _emit_action_result(result, args)
        else:
            return _emit_action_result(_invalid_result(f"Unsupported action: {action}", args), args)
    except Exception as exc:
        return _emit_action_result(_invalid_result(f"Operation failed safely: {exc}", args), args)
    _emit_payload(payload, rendered, args)
    if status == "FAIL":
        return 1
    if args.strict and status == "WARNING":
        return 1
    return 0


def _emit_action_result(result: BTCFuturesPaperActionResult, args: argparse.Namespace) -> int:
    _emit_payload(result.to_dict(), format_btc_futures_paper_action_result(result), args)
    if result.status == "FAIL":
        return 1
    if args.strict and result.status == "WARNING":
        return 1
    return 0


def _emit_payload(payload: dict, rendered: str, args: argparse.Namespace) -> None:
    if args.export_json:
        _atomic_write(args.export_json, json.dumps(payload, indent=2))
        print(f"[btc-futures-paper-position] wrote {args.export_json}", file=sys.stderr if args.json else sys.stdout)
    if args.export_md:
        _atomic_write(args.export_md, rendered)
        print(f"[btc-futures-paper-position] wrote {args.export_md}", file=sys.stderr if args.json else sys.stdout)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(rendered)


def _invalid_result(message: str, args: argparse.Namespace) -> BTCFuturesPaperActionResult:
    issue = BTCFuturesPaperIssue("invalid_cli_request", "FAIL", message)
    return BTCFuturesPaperActionResult(
        action=BTCFuturesPaperAction.STATUS.value,
        status=BTCFuturesPaperStatus.FAIL.value,
        decision=BTCFuturesPaperDecision.OPERATION_FAILED.value,
        reason=message,
        state_path="",
        ledger_path="",
        issues=[issue],
        safety_summary={
            "private_api_used": False,
            "api_key_used": False,
            "trading_api_used": False,
            "real_order_submitted": False,
            "real_position_created": False,
            "exchange_state_mutated": False,
        },
    )


def _selected_actions(args: argparse.Namespace) -> list[str]:
    names = [
        "status",
        "initialize",
        "reset",
        "open_position",
        "mark_to_market",
        "mark_to_market_live",
        "apply_funding",
        "apply_funding_live",
        "close_position",
        "ledger_summary",
        "simulate_lifecycle",
    ]
    return [name for name in names if getattr(args, name)]


def _missing(args: argparse.Namespace, *names: str) -> list[str]:
    return [name.replace("_", "-") for name in names if getattr(args, name) is None]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local BTC futures paper position simulation diagnostics.")
    parser.add_argument("--config", default="configs/btc_futures_paper_position.json")
    parser.add_argument("--expected-profile", default="balanced_smc_decision_065")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--export-json", default=None)
    parser.add_argument("--export-md", default=None)
    parser.add_argument("--action-id", default=None)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--open-position", action="store_true")
    parser.add_argument("--mark-to-market", action="store_true")
    parser.add_argument("--mark-to-market-live", action="store_true")
    parser.add_argument("--apply-funding", action="store_true")
    parser.add_argument("--apply-funding-live", action="store_true")
    parser.add_argument("--close-position", action="store_true")
    parser.add_argument("--ledger-summary", action="store_true")
    parser.add_argument("--simulate-lifecycle", action="store_true")
    parser.add_argument("--side", choices=["LONG", "SHORT"])
    parser.add_argument("--entry-price", type=float)
    parser.add_argument("--mark-price", type=float)
    parser.add_argument("--stop-loss", type=float)
    parser.add_argument("--take-profit", type=float)
    parser.add_argument("--notional", type=float)
    parser.add_argument("--leverage", type=int)
    parser.add_argument("--funding-rate", type=float)
    parser.add_argument("--funding-periods", type=int)
    parser.add_argument("--close-price", type=float)
    parser.add_argument("--close-reason", default="MANUAL")
    return parser


def _atomic_write(path_text: str, content: str) -> None:
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
