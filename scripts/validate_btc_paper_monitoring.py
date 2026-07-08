from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine
from reporting.btc_paper_monitoring_report import (
    format_btc_paper_monitoring_status_report,
    format_btc_paper_monitoring_validation_report,
)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    engine = BTCPaperMonitoringEngine(repo_root=ROOT_DIR)
    if args.status:
        result = engine.build_status(config_path=args.config, expected_profile=args.expected_profile)
        payload = result.to_dict()
        rendered = format_btc_paper_monitoring_status_report(result)
        status_value = result.monitoring_status
    else:
        result = engine.validate(config_path=args.config, expected_profile=args.expected_profile)
        payload = result.to_dict()
        rendered = format_btc_paper_monitoring_validation_report(result)
        status_value = result.status
    if args.export_json:
        _atomic_write(args.export_json, json.dumps(payload, indent=2))
        print(f"[btc-paper-monitoring] wrote {args.export_json}", file=sys.stderr if args.json else sys.stdout)
    if args.export_md:
        _atomic_write(args.export_md, rendered)
        print(f"[btc-paper-monitoring] wrote {args.export_md}", file=sys.stderr if args.json else sys.stdout)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(rendered)
    if status_value in ("FAIL", "BLOCKED"):
        return 1
    if args.strict and status_value in ("WARNING",):
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate BTC paper monitoring and pre-runner telemetry readiness.")
    parser.add_argument("--config", default="configs/btc_paper_monitoring.json")
    parser.add_argument("--expected-profile", default="balanced_smc_decision_065")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--status", action="store_true")
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
