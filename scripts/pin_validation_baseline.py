from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.validation_baseline_engine import ValidationBaselineEngine


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.snapshot and args.clear:
        print("Error: --snapshot and --clear cannot both be used.")
        return 1
    engine = ValidationBaselineEngine(repo_root=ROOT_DIR)
    try:
        if args.snapshot:
            config = engine.pin_snapshot(args.snapshot, args.config, dry_run=args.dry_run)
            _print_config(config)
            print(f"[baseline] pinned {config.baseline_snapshot_path}")
        if args.clear:
            config = engine.clear(args.config, dry_run=args.dry_run)
            _print_config(config)
            print("[baseline] cleared")
        if args.print_config or (not args.snapshot and not args.clear and not args.validate):
            _print_config(engine.load(args.config))
        if args.validate:
            resolved = engine.validate_baseline_path(engine.load(args.config))
            print(f"[baseline] valid {resolved}")
    except Exception as exc:
        print(f"Error: {exc}")
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pin or inspect validation baseline snapshot config.")
    parser.add_argument("--snapshot", default=None)
    parser.add_argument("--config", default="configs/validation_baseline.json")
    parser.add_argument("--print", dest="print_config", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _print_config(config) -> None:
    print(json.dumps(config.to_dict(), indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
