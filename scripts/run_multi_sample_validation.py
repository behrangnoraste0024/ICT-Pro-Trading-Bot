from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.backtest.strategy_comparison_engine import build_recommended_decision_profile_with_cost_specs
from engine.diagnostics.multi_sample_validation_engine import (
    MultiSampleValidationEngine,
)
from engine.diagnostics.validation_sample_scope_engine import SAMPLE_SCOPE_CHOICES, ValidationSampleScopeEngine
from engine.diagnostics.validation_snapshot_engine import ValidationSnapshotEngine
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
    try:
        scope = ValidationSampleScopeEngine(repo_root=ROOT_DIR).select(
            registry_path=args.sample_registry,
            sample_scope=args.sample_scope,
            sample_names=args.sample,
        )
    except Exception as exc:
        print(f"Error: {exc}")
        return 1

    result = MultiSampleValidationEngine().validate(
        samples=scope.selected_samples,
        excluded_samples=scope.excluded_samples,
        sample_scope=scope.sample_scope,
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
    if args.export_snapshot:
        try:
            snapshot = ValidationSnapshotEngine().build_snapshot(
                result=result,
                strategy_set=args.strategy_set,
                sort_by=args.sort_by,
                recommended_profile=args.recommended_profile,
                cache_enabled=args.use_cache or args.refresh_cache,
                cache_dir=args.cache_dir if args.use_cache or args.refresh_cache else None,
                max_windows=args.max_windows,
                fast=args.fast,
                command=_command_text(argv),
                diagnostics=scope.diagnostics,
            )
            paths = ValidationSnapshotEngine().export(snapshot, args.snapshot_dir, args.snapshot_format)
            for path in paths:
                print(f"[snapshot] wrote {path}")
        except Exception as exc:
            print(f"[snapshot] warning failed to write snapshot: {exc}")
    return 0


def _print_progress(payload: dict) -> None:
    event = payload.get("event")
    if event == "start":
        print(
            f"[multi-sample] samples={payload['samples']} "
            f"scope={payload.get('sample_scope', 'all_registry')} "
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
        print(f"[cache] hit path={payload['cache_path']} key={payload.get('cache_key_hash')}", flush=True)
        print(
            "[cache] diagnostics "
            f"age={_fmt_seconds(payload.get('cache_age_seconds'))}s "
            f"original_elapsed={_fmt_seconds(payload.get('original_elapsed_seconds'))}s "
            f"read_elapsed={_fmt_seconds(payload.get('cache_read_elapsed_seconds'))}s "
            f"saved_estimate={_fmt_seconds(payload.get('estimated_saved_seconds'))}s",
            flush=True,
        )
        return
    if event == "cache_miss":
        print(f"[cache] miss key={payload.get('cache_key_hash')}", flush=True)
        return
    if event == "cache_refresh":
        print(f"[cache] refresh key={payload.get('cache_key_hash')}", flush=True)
        return
    if event == "cache_wrote":
        print(
            f"[cache] wrote path={payload['cache_path']} "
            f"compute_elapsed={_fmt_seconds(payload.get('current_compute_elapsed_seconds'))}s",
            flush=True,
        )
        return
    if event == "sample_finish":
        if payload.get("cache_status") == "HIT":
            print(
                f"[multi-sample] finished {payload['sample']} status={payload['status']} "
                f"original_elapsed={_fmt_seconds(payload.get('original_elapsed_seconds'))}s "
                f"cache_read_elapsed={_fmt_seconds(payload.get('cache_read_elapsed_seconds'))}s "
                f"saved_estimate={_fmt_seconds(payload.get('estimated_saved_seconds'))}s "
                f"trades={payload['trades']} net_after_costs={payload['net_pnl_after_costs']:.2f}",
                flush=True,
            )
            return
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


def _fmt_seconds(value) -> str:
    if value is None:
        return "None"
    return f"{float(value):.2f}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run multi-sample recommended profile validation.")
    parser.add_argument("--sample-set", choices=["default"], default="default")
    parser.add_argument("--strategy-set", choices=["recommended_decision_profiles_with_costs"], default="recommended_decision_profiles_with_costs")
    parser.add_argument("--sort-by", choices=["net_pnl_after_costs"], default="net_pnl_after_costs")
    parser.add_argument("--sample-registry", default="configs/historical_sample_registry.json")
    parser.add_argument("--sample-scope", choices=SAMPLE_SCOPE_CHOICES, default="all_registry")
    parser.add_argument("--sample", action="append", default=None)
    parser.add_argument("--recommended-profile", default="balanced_smc_decision_065")
    parser.add_argument("--show-details", action="store_true")
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--max-windows", type=int, default=None)
    parser.add_argument("--use-cache", action="store_true")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--cache-dir", default=".cache/backtests")
    parser.add_argument("--export-snapshot", action="store_true")
    parser.add_argument("--snapshot-dir", default="reports/validation_snapshots")
    parser.add_argument("--snapshot-format", choices=["json", "md", "both"], default="both")
    return parser


def _command_text(argv: list[str] | None) -> str:
    if argv is None:
        return " ".join(sys.argv)
    return "run_multi_sample_validation.py " + " ".join(argv)


if __name__ == "__main__":
    raise SystemExit(main())
