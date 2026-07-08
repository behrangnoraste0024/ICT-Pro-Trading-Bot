from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.historical_sample_registry_engine import HistoricalSampleRegistryEngine
from reporting.historical_sample_registry_report import format_historical_sample_registry_report


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        report = HistoricalSampleRegistryEngine(repo_root=ROOT_DIR).check(args.registry)
    except Exception as exc:
        print(f"Error: {exc}")
        return 1
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_historical_sample_registry_report(report, quiet=args.quiet))
    if args.fail_missing_required_full and not report.required_full_available:
        return 1
    if args.fail_missing_required_ci and not report.required_ci_available:
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check historical validation sample availability.")
    parser.add_argument("--registry", default="configs/historical_sample_registry.json")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-missing-required-full", action="store_true")
    parser.add_argument("--fail-missing-required-ci", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
