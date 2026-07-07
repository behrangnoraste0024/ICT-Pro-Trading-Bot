from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.backtest.strategy_comparison_engine import build_recommended_decision_profile_with_cost_specs
from engine.diagnostics.multi_sample_validation_engine import (
    DEFAULT_MULTI_SAMPLE_DEFINITIONS,
    MultiSampleValidationEngine,
)
from reporting.multi_sample_validation_report import format_multi_sample_validation_report


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.sample_set != "default":
        print(f"Error: unsupported sample set: {args.sample_set}")
        return 1
    if args.strategy_set != "recommended_decision_profiles_with_costs":
        print(f"Error: unsupported strategy set: {args.strategy_set}")
        return 1
    if args.sort_by != "net_pnl_after_costs":
        print(f"Error: unsupported sort-by: {args.sort_by}")
        return 1
    if args.max_windows is not None and args.max_windows <= 0:
        print("Error: --max-windows must be greater than 0.")
        return 1

    result = MultiSampleValidationEngine().validate(
        samples=DEFAULT_MULTI_SAMPLE_DEFINITIONS,
        strategy_specs=build_recommended_decision_profile_with_cost_specs(),
        sort_by=args.sort_by,
        recommended_profile=args.recommended_profile,
        fast=args.fast,
        max_windows=args.max_windows,
        progress_callback=_print_progress,
        use_cache=args.use_cache,
        refresh_cache=args.refresh_cache,
        cache_dir=args.cache_dir,
    )
    print(format_multi_sample_validation_report(result, show_details=args.show_details))
    return 0


def _print_progress(payload: dict) -> None:
    event = payload.get("event")
    if event == "start":
        print(
            f"[multi-sample] samples={payload['samples']} "
            f"strategy_set={payload['strategy_set']} sort_by={payload['sort_by']}",
            flush=True,
        )
        return
    if event == "skip_missing":
        print(
            f"[multi-sample] skipping {payload['sample']} missing file {payload['fixture']}",
            flush=True,
        )
        return
    if event == "sample_start":
        print(
            f"[multi-sample] starting {payload['sample']} {payload['symbol']} {payload['timeframe']} "
            f"fixture={payload['fixture']}",
            flush=True,
        )
        return
    if event == "running_validation":
        print(f"[multi-sample] running validation for {payload['sample']} ...", flush=True)
        return
    if event == "cache_hit":
        print(f"[cache] hit {payload['cache_path']}", flush=True)
        return
    if event == "cache_miss":
        print("[cache] miss", flush=True)
        return
    if event == "cache_wrote":
        print(f"[cache] wrote {payload['cache_path']}", flush=True)
        return
    if event == "sample_finish":
        print(
            f"[multi-sample] finished {payload['sample']} status={payload['status']} "
            f"elapsed={payload['elapsed_seconds']:.2f}s trades={payload['trades']} "
            f"net_after_costs={payload['net_pnl_after_costs']:.2f}",
            flush=True,
        )
        return
    if event == "complete":
        print(
            f"[multi-sample] completed samples={payload['completed']} "
            f"skipped={payload['skipped']} errors={payload['errors']}",
            flush=True,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run multi-sample recommended profile validation.")
    parser.add_argument("--sample-set", choices=["default"], default="default")
    parser.add_argument("--strategy-set", choices=["recommended_decision_profiles_with_costs"], default="recommended_decision_profiles_with_costs")
    parser.add_argument("--sort-by", choices=["net_pnl_after_costs"], default="net_pnl_after_costs")
    parser.add_argument("--recommended-profile", default="balanced_smc_decision_065")
    parser.add_argument("--show-details", action="store_true")
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--max-windows", type=int, default=None)
    parser.add_argument("--use-cache", action="store_true")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--cache-dir", default=".cache/backtests")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
