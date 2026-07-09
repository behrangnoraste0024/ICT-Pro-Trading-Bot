from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.btc_paper_trade_candidate_engine import BTCPaperTradeCandidateEngine
from reporting.btc_paper_trade_candidate_report import (
    format_btc_paper_trade_candidate_result,
    format_btc_paper_trade_candidate_validation_report,
)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    engine = BTCPaperTradeCandidateEngine(repo_root=ROOT_DIR)
    if args.simulate:
        result = engine.simulate(config_path=args.config, expected_profile=args.expected_profile)
        payload = result.to_dict()
        rendered = format_btc_paper_trade_candidate_result(result)
        status = result.status
    else:
        result = engine.validate(config_path=args.config, expected_profile=args.expected_profile)
        payload = result.to_dict()
        rendered = format_btc_paper_trade_candidate_validation_report(result)
        status = result.status
    if args.export_json:
        _atomic_write(args.export_json, json.dumps(payload, indent=2))
        print(f"[btc-paper-trade-candidate] wrote {args.export_json}", file=sys.stderr if args.json else sys.stdout)
    if args.export_md:
        _atomic_write(args.export_md, rendered)
        print(f"[btc-paper-trade-candidate] wrote {args.export_md}", file=sys.stderr if args.json else sys.stdout)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(rendered)
    if status == "FAIL":
        return 1
    if args.strict and status == "WARNING":
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate or simulate BTC paper trade candidate dry-run diagnostics.")
    parser.add_argument("--config", default="configs/btc_paper_trade_candidate.json")
    parser.add_argument("--expected-profile", default="balanced_smc_decision_065")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--simulate", action="store_true")
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
