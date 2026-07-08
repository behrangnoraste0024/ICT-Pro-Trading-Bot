from __future__ import annotations

from scripts.run_validation_gate import _parser, apply_validation_gate_preset


def _args(argv: list[str]):
    parser = _parser()
    args = parser.parse_args(argv)
    provided = {token[2:].split("=", 1)[0] for token in argv if token.startswith("--")}
    apply_validation_gate_preset(args, provided)
    return args


def test_full_preset_applies_required_full_scope() -> None:
    args = _args(["--preset", "full"])

    assert args.sample_scope == "required_full"


def test_ci_preset_applies_required_ci_scope() -> None:
    args = _args(["--preset", "ci"])

    assert args.sample_scope == "required_ci"


def test_quick_preset_applies_required_ci_scope() -> None:
    args = _args(["--preset", "quick"])

    assert args.sample_scope == "required_ci"


def test_snapshot_only_preset_applies_required_full_scope() -> None:
    args = _args(["--preset", "snapshot-only"])

    assert args.sample_scope == "required_full"


def test_explicit_sample_scope_overrides_preset() -> None:
    args = _args(["--preset", "full", "--sample-scope", "all_available"])

    assert args.sample_scope == "all_available"
