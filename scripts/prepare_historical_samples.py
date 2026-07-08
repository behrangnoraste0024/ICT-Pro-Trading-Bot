from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.historical_sample_preparation_engine import HistoricalSamplePreparationEngine
from reporting.historical_sample_preparation_report import format_historical_sample_preparation_report
from reporting.historical_sample_registry_report import format_historical_sample_registry_report
from engine.diagnostics.historical_sample_registry_engine import HistoricalSampleRegistryEngine


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    engine = HistoricalSamplePreparationEngine(repo_root=ROOT_DIR)
    try:
        if args.source and not args.sample:
            print("Error: --source requires --sample.")
            return 1
        if args.import_source and (not args.sample or not args.source):
            print("Error: --import-source requires --sample and --source.")
            return 1
        plan = engine.build_plan(args.registry, args.sample)
        if args.json and not args.import_source:
            print(json.dumps(plan.to_dict(), indent=2))
        else:
            print(format_historical_sample_preparation_report(plan))
        if args.import_source:
            result = engine.import_source(
                args.registry,
                args.sample,
                args.source,
                dry_run=args.dry_run,
                overwrite=args.overwrite,
                allow_too_few=args.allow_too_few,
            )
            if args.dry_run:
                print(f"[historical-samples] dry-run import accepted {result['source_path']} -> {result['destination_path']}")
            else:
                print(f"[historical-samples] imported {result['source_path']} -> {result['destination_path']}")
            if args.allow_too_few and result["candle_count"] < result["expected_min_candles"]:
                print(
                    "[historical-samples] warning: imported source has fewer candles than expected "
                    f"{result['candle_count']} < {result['expected_min_candles']}"
                )
            if args.validate_after_import:
                availability = HistoricalSampleRegistryEngine(repo_root=ROOT_DIR).check(args.registry)
                print(format_historical_sample_registry_report(availability))
        if args.fail_if_action_required and plan.action_required_samples > 0:
            return 1
        if args.fail_if_required_missing_full and not plan.required_full_ready:
            return 1
        if args.fail_if_required_missing_ci and not plan.required_ci_ready:
            return 1
    except Exception as exc:
        print(f"Error: {exc}")
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan and safely import historical validation samples.")
    parser.add_argument("--registry", default="configs/historical_sample_registry.json")
    parser.add_argument("--sample", default=None)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--source", default=None)
    parser.add_argument("--import-source", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--allow-too-few", action="store_true")
    parser.add_argument("--validate-after-import", action="store_true")
    parser.add_argument("--fail-if-action-required", action="store_true")
    parser.add_argument("--fail-if-required-missing-full", action="store_true")
    parser.add_argument("--fail-if-required-missing-ci", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
