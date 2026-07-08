from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from reporting.btc_paper_runtime_config_report import format_btc_paper_runtime_config_report


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = BTCPaperRuntimeConfigEngine(repo_root=ROOT_DIR).validate(
        config_path=args.config,
        expected_profile=args.expected_profile,
    )
    if args.export_json:
        _atomic_write(args.export_json, json.dumps(report.to_dict(), indent=2))
        print(f"[btc-runtime-config] wrote {args.export_json}", file=sys.stderr if args.json else sys.stdout)
    if args.export_md:
        _atomic_write(args.export_md, format_btc_paper_runtime_config_report(report))
        print(f"[btc-runtime-config] wrote {args.export_md}", file=sys.stderr if args.json else sys.stdout)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_btc_paper_runtime_config_report(report))
    if report.status == "FAIL":
        return 1
    if args.strict and report.status == "WARNING":
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate BTC paper runtime config and risk guardrails.")
    parser.add_argument("--config", default="configs/btc_paper_runtime.json")
    parser.add_argument("--expected-profile", default="balanced_smc_decision_065")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
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
