from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.snapshot_comparison_engine import SnapshotComparisonEngine
from engine.diagnostics.validation_baseline_engine import ValidationBaselineEngine
from engine.diagnostics.validation_baseline_history_engine import ValidationBaselineHistoryEngine
from models.validation_baseline_history import ValidationBaselineHistoryEntry
from reporting.snapshot_comparison_report import format_snapshot_comparison_report


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    selected_actions = [bool(args.snapshot), bool(args.promote_candidate), bool(args.clear)]
    if sum(selected_actions) > 1:
        print("Error: --snapshot, --promote-candidate, and --clear are mutually exclusive.")
        return 1
    engine = ValidationBaselineEngine(repo_root=ROOT_DIR)
    history_engine = ValidationBaselineHistoryEngine()
    try:
        if args.history_print or args.history_json:
            _print_history(history_engine, args)
            return 0
        if args.promote_candidate:
            return _promote_candidate(engine, history_engine, args)
        if args.snapshot:
            previous_config = engine.load(args.config)
            config = engine.pin_snapshot(args.snapshot, args.config, dry_run=args.dry_run)
            _print_config(config)
            print(f"[baseline] pinned {config.baseline_snapshot_path}")
            if not _record_history(history_engine, args, "PIN", previous_config, config):
                return 1
        if args.clear:
            previous_config = engine.load(args.config)
            config = engine.clear(args.config, dry_run=args.dry_run)
            _print_config(config)
            print("[baseline] cleared")
            if not _record_history(history_engine, args, "CLEAR", previous_config, config):
                return 1
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
    parser.add_argument("--promote-candidate", default=None)
    parser.add_argument("--require-pass", action="store_true")
    parser.add_argument("--allow-warning", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--expected-profile", default="balanced_smc_decision_065")
    parser.add_argument("--comparison-export-dir", default=None)
    parser.add_argument("--config", default="configs/validation_baseline.json")
    parser.add_argument("--print", dest="print_config", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--history-config", default="configs/validation_baseline_history.json")
    parser.add_argument("--record-history", action="store_true")
    parser.add_argument("--history-print", action="store_true")
    parser.add_argument("--history-limit", type=int, default=None)
    parser.add_argument("--history-json", action="store_true")
    parser.add_argument("--history-notes", default=None)
    parser.add_argument("--no-history", action="store_true")
    return parser


def _print_config(config) -> None:
    print(json.dumps(config.to_dict(), indent=2))


def _promote_candidate(
    engine: ValidationBaselineEngine,
    history_engine: ValidationBaselineHistoryEngine,
    args: argparse.Namespace,
) -> int:
    candidate_path = Path(args.promote_candidate)
    print(f"[baseline] promotion candidate {candidate_path}")
    candidate = _load_candidate_snapshot(candidate_path)
    metadata = candidate["metadata"]
    candidate_profile = metadata.get("recommended_profile")
    if args.expected_profile and candidate_profile != args.expected_profile:
        message = (
            "[baseline] promotion rejected profile mismatch "
            f"expected={args.expected_profile} candidate={candidate_profile}"
        )
        if not args.force:
            print(message)
            return 1
        print(f"{message} force=true")

    comparison = None
    if args.require_pass:
        comparison = _compare_current_baseline(engine, args, candidate_path)
        if comparison is None:
            if not args.force:
                print("[baseline] promotion rejected missing current baseline")
                return 1
            print("[baseline] promotion continuing without comparison force=true")
        else:
            print(format_snapshot_comparison_report(comparison))
            print(f"[baseline] promotion comparison status={comparison.regression_status}")
            if args.comparison_export_dir:
                _export_comparison(comparison, args.comparison_export_dir)
            if comparison.regression_status == "FAIL" and not args.force:
                print("[baseline] promotion rejected status=FAIL")
                return 1
            if comparison.regression_status == "WARNING" and not (args.allow_warning or args.force):
                print("[baseline] promotion rejected status=WARNING")
                return 1

    previous_config = engine.load(args.config)
    config = engine.pin_snapshot(str(candidate_path), args.config, dry_run=args.dry_run)
    _print_config(config)
    if args.dry_run:
        print(f"[baseline] promotion dry-run accepted {candidate_path}")
    else:
        print(f"[baseline] promoted {candidate_path}")
    if not _record_history(history_engine, args, "PROMOTE", previous_config, config, comparison):
        return 1
    return 0


def _load_candidate_snapshot(candidate_path: Path) -> dict[str, Any]:
    if not candidate_path.exists():
        raise FileNotFoundError(f"candidate snapshot not found: {candidate_path}")
    with candidate_path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"candidate snapshot must be a JSON object: {candidate_path}")
    metadata = loaded.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError(f"candidate snapshot missing metadata: {candidate_path}")
    result = loaded.get("multi_sample_result")
    if not isinstance(result, dict):
        raise ValueError(f"candidate snapshot missing multi_sample_result: {candidate_path}")
    return loaded


def _compare_current_baseline(engine: ValidationBaselineEngine, args: argparse.Namespace, candidate_path: Path):
    try:
        config = engine.load(args.config)
        baseline_path = engine.validate_baseline_path(config)
    except FileNotFoundError as exc:
        print(f"[baseline] current baseline unavailable {exc}")
        return None
    print(f"[baseline] current baseline {baseline_path}")
    return SnapshotComparisonEngine().compare_files(baseline_path, str(candidate_path))


def _export_comparison(comparison, export_dir: str) -> None:
    output_dir = Path(export_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = _comparison_stem(comparison)
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(comparison.to_dict(), indent=2), encoding="utf-8")
    md_path.write_text(format_snapshot_comparison_report(comparison), encoding="utf-8")
    print(f"[baseline] promotion comparison wrote {json_path}")
    print(f"[baseline] promotion comparison wrote {md_path}")


def _comparison_stem(comparison) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    baseline = _safe_token(comparison.baseline_git_commit or "unknown")
    candidate = _safe_token(comparison.candidate_git_commit or "unknown")
    return f"baseline_promotion_comparison_{timestamp}_{baseline}_to_{candidate}"


def _safe_token(value: str) -> str:
    return "".join(character if character.isalnum() or character in ("-", "_") else "_" for character in value)


def _record_history(
    history_engine: ValidationBaselineHistoryEngine,
    args: argparse.Namespace,
    action: str,
    previous_config,
    config,
    comparison=None,
) -> bool:
    if args.no_history or not args.record_history:
        return True
    entry = _history_entry(args, action, previous_config, config, comparison)
    if args.dry_run:
        _print_history_entry(entry)
        print("[baseline-history] dry-run entry prepared")
        return True
    try:
        history_engine.append_entry(args.history_config, entry)
    except Exception as exc:
        print(f"Error: baseline history append failed: {exc}")
        if args.force:
            print("[baseline-history] continuing after history failure force=true")
            return True
        return False
    print(f"[baseline-history] recorded {action}")
    return True


def _history_entry(args: argparse.Namespace, action: str, previous_config, config, comparison=None) -> ValidationBaselineHistoryEntry:
    return ValidationBaselineHistoryEntry(
        promoted_at=datetime.now(UTC).isoformat(),
        action=action,
        baseline_snapshot_path=config.baseline_snapshot_path,
        baseline_git_commit=config.baseline_git_commit,
        baseline_created_at=config.baseline_created_at,
        recommended_profile=config.recommended_profile,
        previous_baseline_snapshot_path=previous_config.baseline_snapshot_path,
        previous_baseline_git_commit=previous_config.baseline_git_commit,
        comparison_status=None if comparison is None else comparison.regression_status,
        comparison_net_after_costs_delta=None if comparison is None else comparison.aggregate_net_after_costs_delta,
        comparison_max_drawdown_delta=None if comparison is None else comparison.aggregate_max_drawdown_delta,
        comparison_regression_flags=[] if comparison is None else list(comparison.regression_flags),
        promoted_by_command=" ".join(sys.argv),
        notes=args.history_notes,
    )


def _print_history(history_engine: ValidationBaselineHistoryEngine, args: argparse.Namespace) -> None:
    history = history_engine.load(args.history_config)
    if args.history_json:
        print(json.dumps(history.to_dict(), indent=2))
        return
    print("===== VALIDATION BASELINE HISTORY =====")
    print(f"Total Entries: {len(history.entries)}")
    entries = list(reversed(history.entries))
    if args.history_limit is not None:
        entries = entries[: max(args.history_limit, 0)]
    for index, entry in enumerate(entries, start=1):
        print(
            f"{index}. {entry.promoted_at} {entry.action} "
            f"commit={entry.baseline_git_commit} profile={entry.recommended_profile} "
            f"path={entry.baseline_snapshot_path}"
        )
        print(f"   previous={entry.previous_baseline_git_commit}")
        print(
            f"   comparison={entry.comparison_status} "
            f"net_delta={entry.comparison_net_after_costs_delta} "
            f"maxdd_delta={entry.comparison_max_drawdown_delta}"
        )
        if entry.comparison_regression_flags:
            print(f"   flags={','.join(entry.comparison_regression_flags)}")
        print(f"   notes={entry.notes}")


def _print_history_entry(entry: ValidationBaselineHistoryEntry) -> None:
    print(json.dumps(entry.to_dict(), indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
