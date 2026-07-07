from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.backtest.strategy_comparison_engine import build_recommended_decision_profile_with_cost_specs
from engine.diagnostics.multi_sample_validation_engine import (
    DEFAULT_MULTI_SAMPLE_DEFINITIONS,
    MultiSampleValidationEngine,
)
from engine.diagnostics.snapshot_comparison_engine import SnapshotComparisonEngine
from engine.diagnostics.validation_baseline_engine import ValidationBaselineEngine
from engine.diagnostics.validation_snapshot_engine import ValidationSnapshotEngine
from reporting.multi_sample_validation_report import format_multi_sample_validation_report
from reporting.snapshot_comparison_report import format_snapshot_comparison_report
from reporting.validation_gate_summary_report import format_validation_gate_summary
from models.validation_gate_summary import ValidationGateSummary


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.strategy_set != "recommended_decision_profiles_with_costs":
        print(f"Error: unsupported strategy set: {args.strategy_set}")
        return 1
    if args.sort_by != "net_pnl_after_costs":
        print(f"Error: unsupported sort-by: {args.sort_by}")
        return 1
    if args.max_windows is not None and args.max_windows <= 0:
        print("Error: --max-windows must be greater than 0.")
        return 1
    baseline_snapshot = _resolve_baseline_snapshot(args)
    if baseline_snapshot == "__ERROR__":
        return 1

    print("[validation-gate] starting")
    result = MultiSampleValidationEngine().validate(
        samples=DEFAULT_MULTI_SAMPLE_DEFINITIONS,
        strategy_specs=build_recommended_decision_profile_with_cost_specs(),
        sort_by=args.sort_by,
        recommended_profile=args.recommended_profile,
        fast=args.fast,
        max_windows=args.max_windows,
        progress_callback=_print_progress,
        use_cache=args.use_cache,
        cache_dir=args.cache_dir,
    )
    print(format_multi_sample_validation_report(result, show_details=args.show_details))

    snapshot_engine = ValidationSnapshotEngine()
    snapshot = snapshot_engine.build_snapshot(
        result=result,
        strategy_set=args.strategy_set,
        sort_by=args.sort_by,
        recommended_profile=args.recommended_profile,
        cache_enabled=args.use_cache,
        cache_dir=args.cache_dir if args.use_cache else None,
        max_windows=args.max_windows,
        fast=args.fast,
        command=_command_text(argv),
    )
    snapshot_paths = _export_snapshot(snapshot_engine, snapshot, args.snapshot_dir, args.snapshot_format, bool(baseline_snapshot))
    for path in snapshot_paths:
        print(f"[validation-gate] snapshot wrote {path}")
    snapshot_json_path = _snapshot_json_path(snapshot_paths)

    if not baseline_snapshot:
        print("[validation-gate] no baseline snapshot provided; comparison skipped")
        _print_summary_if_requested(
            args,
            result=result,
            snapshot=snapshot,
            baseline_snapshot=baseline_snapshot,
            candidate_snapshot_path=snapshot_json_path or (snapshot_paths[0] if snapshot_paths else None),
            comparison=None,
            comparison_paths=[],
        )
        print("[validation-gate] completed status=PASS")
        return 0
    if snapshot_json_path is None:
        print("[validation-gate] failed: JSON snapshot unavailable for comparison")
        return 1

    comparison = SnapshotComparisonEngine().compare_files(baseline_snapshot, snapshot_json_path)
    comparison_report = format_snapshot_comparison_report(comparison)
    print(comparison_report)
    print(f"[validation-gate] regression_status={comparison.regression_status}")
    if args.export_comparison:
        comparison_paths = _export_comparison(comparison, comparison_report, args.comparison_dir)
        for path in comparison_paths:
            print(f"[validation-gate] comparison wrote {path}")
    else:
        comparison_paths = []
    if comparison.regression_status == "WARNING":
        print("[validation-gate] warning: regression guard reported WARNING")
    _print_summary_if_requested(
        args,
        result=result,
        snapshot=snapshot,
        baseline_snapshot=baseline_snapshot,
        candidate_snapshot_path=snapshot_json_path,
        comparison=comparison,
        comparison_paths=comparison_paths,
    )
    if args.fail_on_regression and comparison.regression_status == "FAIL":
        print("[validation-gate] failed due to regression")
        return 1
    print(f"[validation-gate] completed status={comparison.regression_status}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one-command validation gate for research snapshots.")
    parser.add_argument("--baseline-snapshot", default=None)
    parser.add_argument("--baseline-config", default="configs/validation_baseline.json")
    parser.add_argument("--fail-on-regression", action="store_true")
    parser.add_argument("--snapshot-dir", default="reports/validation_snapshots")
    parser.add_argument("--snapshot-format", choices=["json", "md", "both"], default="both")
    parser.add_argument("--export-comparison", action="store_true")
    parser.add_argument("--comparison-dir", default="reports/validation_snapshots")
    parser.add_argument("--strategy-set", choices=["recommended_decision_profiles_with_costs"], default="recommended_decision_profiles_with_costs")
    parser.add_argument("--sort-by", choices=["net_pnl_after_costs"], default="net_pnl_after_costs")
    parser.add_argument("--recommended-profile", default="balanced_smc_decision_065")
    parser.add_argument("--use-cache", action="store_true")
    parser.add_argument("--cache-dir", default=".cache/backtests")
    parser.add_argument("--max-windows", type=int, default=None)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--show-details", action="store_true")
    parser.add_argument("--summary-badge", action="store_true")
    return parser


def _print_summary_if_requested(
    args,
    result,
    snapshot,
    baseline_snapshot: str | None,
    candidate_snapshot_path: str | None,
    comparison,
    comparison_paths: list[str],
) -> None:
    if not args.summary_badge:
        return
    summary = _build_summary(
        result=result,
        snapshot=snapshot,
        baseline_snapshot=baseline_snapshot,
        candidate_snapshot_path=candidate_snapshot_path,
        comparison=comparison,
        comparison_paths=comparison_paths,
        fail_on_regression=args.fail_on_regression,
    )
    print(format_validation_gate_summary(summary))


def _build_summary(
    result,
    snapshot,
    baseline_snapshot: str | None,
    candidate_snapshot_path: str | None,
    comparison,
    comparison_paths: list[str],
    fail_on_regression: bool,
) -> ValidationGateSummary:
    primary = _primary_row(result)
    regression_status = "SKIPPED" if comparison is None else comparison.regression_status
    gate_status = _gate_status(result, comparison)
    return ValidationGateSummary(
        gate_status=gate_status,
        regression_status=regression_status,
        recommended_profile=result.recommended_profile,
        baseline_commit=None if comparison is None else comparison.baseline_git_commit,
        candidate_commit=snapshot.metadata.git_commit if comparison is None else comparison.candidate_git_commit,
        baseline_snapshot_path=baseline_snapshot,
        candidate_snapshot_path=candidate_snapshot_path,
        comparison_paths=comparison_paths,
        total_samples=result.total_samples,
        completed_samples=result.completed_samples,
        passed_samples=result.passed_samples,
        failed_samples=result.failed_samples,
        skipped_samples=result.skipped_samples,
        net_after_costs_delta=None if comparison is None else comparison.aggregate_net_after_costs_delta,
        max_drawdown_delta=None if comparison is None else comparison.aggregate_max_drawdown_delta,
        regression_flag_count=0 if comparison is None else len(comparison.regression_flags),
        warning_sample_count=0 if comparison is None else comparison.warning_samples,
        failed_sample_count=0 if comparison is None else comparison.failed_samples,
        primary_cache_status=None if primary is None else primary.cache_status,
        primary_original_elapsed=None if primary is None else primary.original_elapsed_seconds,
        primary_cache_read_elapsed=None if primary is None else primary.cache_read_elapsed_seconds,
        primary_saved_estimate=None if primary is None else primary.estimated_saved_seconds,
        fail_on_regression=fail_on_regression,
    )


def _gate_status(result, comparison) -> str:
    if comparison is not None:
        return comparison.regression_status
    if any(row.status in ("FAILED", "ERROR") for row in result.rows):
        return "FAIL"
    if any(row.status == "WARNING" for row in result.rows):
        return "WARNING"
    return "PASS"


def _primary_row(result):
    if not result.rows:
        return None
    return next((row for row in result.rows if row.sample_name == "btcusdt_15m_1000"), result.rows[0])


def _resolve_baseline_snapshot(args) -> str | None:
    if args.baseline_snapshot:
        if not Path(args.baseline_snapshot).exists():
            print(f"Error: baseline snapshot not found: {args.baseline_snapshot}")
            return "__ERROR__"
        return args.baseline_snapshot
    config_path = Path(args.baseline_config)
    if not config_path.exists():
        print(f"[validation-gate] baseline config not found; comparison skipped")
        return None
    engine = ValidationBaselineEngine(repo_root=ROOT_DIR)
    config = engine.load(str(config_path))
    if not config.baseline_snapshot_path:
        return None
    try:
        resolved = engine.validate_baseline_path(config)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return "__ERROR__"
    print(f"[validation-gate] using baseline config {args.baseline_config}")
    print(f"[validation-gate] baseline snapshot {resolved}")
    return resolved


def _export_snapshot(
    snapshot_engine: ValidationSnapshotEngine,
    snapshot,
    snapshot_dir: str,
    snapshot_format: str,
    baseline_requested: bool,
) -> list[str]:
    paths = snapshot_engine.export(snapshot, snapshot_dir, snapshot_format)
    if baseline_requested and not any(Path(path).suffix == ".json" for path in paths):
        paths.append(snapshot_engine.export_json(snapshot, snapshot_dir))
    return paths


def _snapshot_json_path(paths: list[str]) -> str | None:
    return next((path for path in paths if Path(path).suffix == ".json"), None)


def _export_comparison(comparison, comparison_report: str, comparison_dir: str) -> list[str]:
    output_dir = Path(comparison_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = _comparison_filename_stem(comparison)
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(comparison.to_dict(), indent=2), encoding="utf-8")
    md_path.write_text(comparison_report, encoding="utf-8")
    return [str(json_path), str(md_path)]


def _comparison_filename_stem(comparison) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    baseline = _safe_token(comparison.baseline_git_commit or "unknown")
    candidate = _safe_token(comparison.candidate_git_commit or "unknown")
    return f"validation_comparison_{timestamp}_{baseline}_to_{candidate}"


def _safe_token(value: str) -> str:
    return "".join(char if char.isalnum() or char in ("_", "-", ".") else "_" for char in value).strip("._-") or "unknown"


def _command_text(argv: list[str] | None) -> str:
    if argv is None:
        return " ".join(sys.argv)
    return "run_validation_gate.py " + " ".join(argv)


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
        print(f"[multi-sample] skipping {payload['sample']} missing file {payload['fixture']}", flush=True)
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


if __name__ == "__main__":
    raise SystemExit(main())
