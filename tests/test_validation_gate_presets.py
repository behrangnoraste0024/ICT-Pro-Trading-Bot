from __future__ import annotations

from scripts.run_validation_gate import _parser, apply_validation_gate_preset


def _args(argv: list[str]):
    parser = _parser()
    args = parser.parse_args(argv)
    provided = {token[2:].split("=", 1)[0] for token in argv if token.startswith("--")}
    apply_validation_gate_preset(args, provided)
    return args


def test_quick_preset_applies_max_windows_100() -> None:
    args = _args(["--preset", "quick"])

    assert args.max_windows == 100


def test_quick_preset_uses_cache_and_summary_badge() -> None:
    args = _args(["--preset", "quick"])

    assert args.use_cache is True
    assert args.cache_dir == ".cache/backtests"
    assert args.summary_badge is True


def test_quick_preset_does_not_automatically_fail_on_regression() -> None:
    args = _args(["--preset", "quick"])

    assert args.fail_on_regression is False


def test_quick_preset_skips_baseline_config_unless_explicit() -> None:
    args = _args(["--preset", "quick"])

    assert args.baseline_config is None


def test_full_preset_applies_daily_gate_defaults() -> None:
    args = _args(["--preset", "full"])

    assert args.baseline_config == "configs/validation_baseline.json"
    assert args.fail_on_regression is True
    assert args.export_comparison is True
    assert args.summary_badge is True
    assert args.show_details is True
    assert args.use_cache is True


def test_ci_preset_applies_regression_gate_without_details_by_default() -> None:
    args = _args(["--preset", "ci"])

    assert args.fail_on_regression is True
    assert args.export_comparison is True
    assert args.summary_badge is True
    assert args.show_details is False
    assert args.use_cache is True


def test_snapshot_only_preset_skips_comparison() -> None:
    args = _args(["--preset", "snapshot-only"])

    assert args.baseline_config is None
    assert args.baseline_snapshot is None
    assert args.fail_on_regression is False
    assert args.summary_badge is True


def test_explicit_max_windows_overrides_quick_default() -> None:
    args = _args(["--preset", "quick", "--max-windows", "200"])

    assert args.max_windows == 200


def test_explicit_snapshot_format_overrides_preset_default() -> None:
    args = _args(["--preset", "full", "--snapshot-format", "json"])

    assert args.snapshot_format == "json"


def test_explicit_baseline_config_with_quick_enables_comparison_path() -> None:
    args = _args(["--preset", "quick", "--baseline-config", "configs/validation_baseline.json"])

    assert args.baseline_config == "configs/validation_baseline.json"


def test_non_preset_behavior_remains_unchanged() -> None:
    args = _args([])

    assert args.baseline_config == "configs/validation_baseline.json"
    assert args.snapshot_format == "both"
    assert args.use_cache is False
    assert args.summary_badge is False
