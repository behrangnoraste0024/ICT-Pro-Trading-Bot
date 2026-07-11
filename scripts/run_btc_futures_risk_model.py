from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.btc_futures_risk_model_engine import BTCFuturesRiskModelEngine
from models.btc_futures_risk_model import (
    BTCFuturesRiskDecision,
    BTCFuturesRiskIssue,
    BTCFuturesRiskResult,
    BTCFuturesRiskScenarioInput,
    BTCFuturesRiskStatus,
)
from reporting.btc_futures_risk_model_report import (
    format_btc_futures_leverage_comparison,
    format_btc_futures_risk_result,
    format_btc_futures_risk_validation_report,
)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    engine = BTCFuturesRiskModelEngine(repo_root=ROOT_DIR)
    action_count = sum(bool(value) for value in (args.analyze_scenario, args.analyze_live, args.compare_leverage))
    if action_count > 1:
        result = _invalid_request_result("Choose only one risk model action.")
        return _emit_risk_result(result, args)
    if args.analyze_scenario:
        try:
            scenario = _scenario_from_args(args, source="manual")
        except ValueError as exc:
            result = _invalid_request_result(str(exc))
            return _emit_risk_result(result, args)
        result = engine.analyze_scenario(scenario, config_path=args.config, expected_profile=args.expected_profile)
        payload = result.to_dict()
        rendered = format_btc_futures_risk_result(result)
        status = result.status
    elif args.analyze_live:
        result = engine.analyze_live(
            side=args.side,
            stop_loss=args.stop_loss,
            take_profit=args.take_profit,
            notional=args.notional,
            account_equity=args.account_equity or 10000.0,
            leverage=args.leverage,
            config_path=args.config,
            expected_profile=args.expected_profile,
        )
        payload = result.to_dict()
        rendered = format_btc_futures_risk_result(result)
        status = result.status
    elif args.compare_leverage:
        try:
            scenario = _scenario_from_args(args, source="comparison", require_leverage=False)
        except ValueError as exc:
            result = _invalid_request_result(str(exc))
            return _emit_risk_result(result, args)
        result = engine.compare_leverage(scenario, config_path=args.config, expected_profile=args.expected_profile)
        payload = result.to_dict()
        rendered = format_btc_futures_leverage_comparison(result)
        status = result.status
    else:
        result = engine.validate(config_path=args.config, expected_profile=args.expected_profile)
        payload = result.to_dict()
        rendered = format_btc_futures_risk_validation_report(result)
        status = result.status
    if args.export_json:
        _atomic_write(args.export_json, json.dumps(payload, indent=2))
        print(f"[btc-futures-risk-model] wrote {args.export_json}", file=sys.stderr if args.json else sys.stdout)
    if args.export_md:
        _atomic_write(args.export_md, rendered)
        print(f"[btc-futures-risk-model] wrote {args.export_md}", file=sys.stderr if args.json else sys.stdout)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(rendered)
    if status == "FAIL":
        return 1
    if args.strict and status == "WARNING":
        return 1
    return 0


def _scenario_from_args(args: argparse.Namespace, source: str, require_leverage: bool = True) -> BTCFuturesRiskScenarioInput:
    missing = []
    for name in ("side", "entry_price", "mark_price", "stop_loss", "take_profit", "notional", "account_equity"):
        if getattr(args, name) is None:
            missing.append(name.replace("_", "-"))
    if require_leverage and args.leverage is None:
        missing.append("leverage")
    if missing:
        raise ValueError(f"Missing required scenario arguments: {', '.join(missing)}")
    return BTCFuturesRiskScenarioInput(
        side=str(args.side).upper(),
        entry_price=float(args.entry_price),
        mark_price=float(args.mark_price),
        stop_loss=float(args.stop_loss),
        take_profit=float(args.take_profit),
        notional_value=float(args.notional),
        leverage=int(args.leverage or 1),
        account_equity=float(args.account_equity),
        funding_rate=args.funding_rate,
        funding_periods=int(args.funding_periods or 3),
        source=source,
    )


def _invalid_request_result(message: str) -> BTCFuturesRiskResult:
    return BTCFuturesRiskResult(
        status=BTCFuturesRiskStatus.FAIL.value,
        decision=BTCFuturesRiskDecision.INVALID_SCENARIO.value,
        reason=message,
        issues=[
            BTCFuturesRiskIssue(
                name="invalid_cli_request",
                severity=BTCFuturesRiskStatus.FAIL.value,
                message=message,
            )
        ],
        safety_summary={
            "private_api_used": False,
            "api_key_used": False,
            "trading_api_used": False,
            "account_data_used": False,
            "balance_fetch_used": False,
            "position_fetch_used": False,
            "exchange_leverage_changed": False,
            "exchange_margin_mode_changed": False,
            "order_submitted": False,
            "order_cancelled": False,
            "real_position_created": False,
            "paper_futures_position_created": False,
            "paper_trade_persisted": False,
            "executable_trade_created": False,
            "paper_account_state_mutated": False,
            "runner_state_mutated": False,
            "execution_state_mutated": False,
        },
    )


def _emit_risk_result(result: BTCFuturesRiskResult, args: argparse.Namespace) -> int:
    payload = result.to_dict()
    rendered = format_btc_futures_risk_result(result)
    if args.export_json:
        _atomic_write(args.export_json, json.dumps(payload, indent=2))
        print(f"[btc-futures-risk-model] wrote {args.export_json}", file=sys.stderr if args.json else sys.stdout)
    if args.export_md:
        _atomic_write(args.export_md, rendered)
        print(f"[btc-futures-risk-model] wrote {args.export_md}", file=sys.stderr if args.json else sys.stdout)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(rendered)
    return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run BTC futures leverage/liquidation risk model diagnostics.")
    parser.add_argument("--config", default="configs/btc_futures_risk_model.json")
    parser.add_argument("--expected-profile", default="balanced_smc_decision_065")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--analyze-scenario", action="store_true")
    parser.add_argument("--analyze-live", action="store_true")
    parser.add_argument("--compare-leverage", action="store_true")
    parser.add_argument("--side", choices=["LONG", "SHORT"])
    parser.add_argument("--entry-price", type=float)
    parser.add_argument("--mark-price", type=float)
    parser.add_argument("--stop-loss", type=float)
    parser.add_argument("--take-profit", type=float)
    parser.add_argument("--notional", type=float)
    parser.add_argument("--account-equity", type=float)
    parser.add_argument("--leverage", type=int)
    parser.add_argument("--funding-rate", type=float)
    parser.add_argument("--funding-periods", type=int)
    parser.add_argument("--export-json", default=None)
    parser.add_argument("--export-md", default=None)
    return parser


def _atomic_write(path_text: str, content: str) -> None:
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
