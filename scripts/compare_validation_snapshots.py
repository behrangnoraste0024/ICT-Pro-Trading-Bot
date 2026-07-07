from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.snapshot_comparison_engine import SnapshotComparisonEngine
from reporting.snapshot_comparison_report import format_snapshot_comparison_report


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = SnapshotComparisonEngine().compare_files(args.baseline, args.candidate)
    except Exception as exc:
        print(f"Error: {exc}")
        return 1
    report = format_snapshot_comparison_report(result)
    print(report)
    if args.export_json:
        _write_text(args.export_json, json.dumps(result.to_dict(), indent=2))
        print(f"[snapshot-comparison] wrote {args.export_json}")
    if args.export_md:
        _write_text(args.export_md, report)
        print(f"[snapshot-comparison] wrote {args.export_md}")
    if args.fail_on_regression and result.regression_status == "FAIL":
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare validation snapshot JSON files.")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--fail-on-regression", action="store_true")
    parser.add_argument("--export-json", default=None)
    parser.add_argument("--export-md", default=None)
    return parser


def _write_text(path: str, text: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
