from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.historical_sample_download_engine import HistoricalSampleDownloadEngine
from engine.diagnostics.historical_sample_registry_engine import HistoricalSampleRegistryEngine
from reporting.historical_sample_download_report import format_historical_sample_download_report
from reporting.historical_sample_registry_report import format_historical_sample_registry_report


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        engine = HistoricalSampleDownloadEngine(repo_root=ROOT_DIR)
        plan = engine.download(
            args.registry,
            exchange=args.exchange,
            sample_names=args.sample,
            limit=args.limit,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
            include_existing=args.include_existing,
            allow_too_few=args.allow_too_few,
            write_metadata=args.write_metadata,
        )
        if args.json:
            print(json.dumps(plan.to_dict(), indent=2))
        else:
            print(format_historical_sample_download_report(plan))
        failed = [result for result in plan.results if result.status == "FAILED"]
        if args.validate_after_download:
            availability = HistoricalSampleRegistryEngine(repo_root=ROOT_DIR).check(args.registry)
            print(format_historical_sample_registry_report(availability))
            if args.fail_if_missing_after:
                selected = set(args.sample or [])
                samples = availability.samples if not selected else [sample for sample in availability.samples if sample.sample_name in selected]
                if any(sample.status != "AVAILABLE" for sample in samples):
                    return 1
        if failed:
            return 1
    except Exception as exc:
        print(f"Error: {exc}")
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download missing historical samples from a registry.")
    parser.add_argument("--registry", default="configs/historical_sample_registry.json")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--sample", action="append", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--include-existing", action="store_true")
    parser.add_argument("--allow-too-few", action="store_true")
    parser.add_argument("--write-metadata", action="store_true")
    parser.add_argument("--validate-after-download", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-if-missing-after", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
