from __future__ import annotations

import json
from pathlib import Path

from models.multi_sample_validation import MultiSampleValidationResult, MultiSampleValidationRow
from models.snapshot_comparison import SnapshotComparisonResult
from scripts.run_validation_gate import main


class _FakeMultiSampleValidationEngine:
    last_kwargs = None

    def validate(self, **kwargs) -> MultiSampleValidationResult:
        type(self).last_kwargs = kwargs
        progress = kwargs.get("progress_callback")
        if progress is not None:
            progress(
                {
                    "event": "start",
                    "samples": 1,
                    "strategy_set": "recommended_decision_profiles_with_costs",
                    "sort_by": "net_pnl_after_costs",
                }
            )
            progress(
                {
                    "event": "sample_finish",
                    "sample": "mock_sample",
                    "status": "PASSED",
                    "elapsed_seconds": 0.1,
                    "trades": 5,
                    "net_pnl_after_costs": 1404.24,
                }
            )
            progress({"event": "complete", "completed": 1, "skipped": 0, "errors": 0})
        return MultiSampleValidationResult(
            rows=[
                MultiSampleValidationRow(
                    sample_name="mock_sample",
                    fixture_path="mock.json",
                    symbol="BTC/USDT",
                    timeframe="15m",
                    status="PASSED",
                    recommended_profile=kwargs["recommended_profile"],
                    score_threshold=0.65,
                    total_trades=5,
                    wins=5,
                    losses=0,
                    win_rate=100.0,
                    net_pnl_after_costs=1404.24,
                    validation_status="PASS",
                    profitable_segments=4,
                    losing_segments=0,
                    empty_segments=0,
                    worst_segment_net_pnl_after_costs=157.54,
                    improvement_vs_baseline=1215.74,
                )
            ],
            total_samples=1,
            completed_samples=1,
            passed_samples=1,
            recommended_profile=kwargs["recommended_profile"],
        )


class _FakeSnapshotComparisonEngine:
    status = "PASS"
    compared = False
    last_baseline_path = None

    def compare_files(self, baseline_path: str, candidate_path: str) -> SnapshotComparisonResult:
        type(self).compared = True
        type(self).last_baseline_path = baseline_path
        return SnapshotComparisonResult(
            baseline_path=baseline_path,
            candidate_path=candidate_path,
            baseline_git_commit="base123",
            candidate_git_commit="cand123",
            baseline_recommended_profile="balanced_smc_decision_065",
            candidate_recommended_profile="balanced_smc_decision_065",
            total_samples_compared=1,
            passed_samples=1 if self.status == "PASS" else 0,
            warning_samples=1 if self.status == "WARNING" else 0,
            failed_samples=1 if self.status == "FAIL" else 0,
            regression_status=self.status,
            regression_flags=["mock:FAIL"] if self.status == "FAIL" else [],
        )


def _patch_validation(monkeypatch) -> None:
    monkeypatch.setattr("scripts.run_validation_gate.MultiSampleValidationEngine", _FakeMultiSampleValidationEngine)


def _patch_comparison(monkeypatch, status: str) -> None:
    _FakeSnapshotComparisonEngine.status = status
    _FakeSnapshotComparisonEngine.compared = False
    _FakeSnapshotComparisonEngine.last_baseline_path = None
    monkeypatch.setattr("scripts.run_validation_gate.SnapshotComparisonEngine", _FakeSnapshotComparisonEngine)


def _baseline(tmp_path: Path) -> str:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"metadata": {}, "multi_sample_result": {"rows": []}}), encoding="utf-8")
    return str(path)


def test_gate_runs_validation_and_exports_snapshot_without_baseline(tmp_path, capsys, monkeypatch) -> None:
    _patch_validation(monkeypatch)

    return_code = main(["--snapshot-dir", str(tmp_path), "--snapshot-format", "json"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[validation-gate] starting" in captured.out
    assert "[validation-gate] no baseline snapshot provided; comparison skipped" in captured.out
    assert "[validation-gate] completed status=PASS" in captured.out
    assert list(tmp_path.glob("*.json"))


def test_gate_with_baseline_compares_generated_snapshot(tmp_path, capsys, monkeypatch) -> None:
    _patch_validation(monkeypatch)
    _patch_comparison(monkeypatch, "PASS")

    return_code = main(
        [
            "--baseline-snapshot",
            _baseline(tmp_path),
            "--snapshot-dir",
            str(tmp_path),
            "--snapshot-format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert _FakeSnapshotComparisonEngine.compared is True
    assert "[validation-gate] regression_status=PASS" in captured.out


def test_gate_warning_exits_zero_even_with_fail_on_regression(tmp_path, capsys, monkeypatch) -> None:
    _patch_validation(monkeypatch)
    _patch_comparison(monkeypatch, "WARNING")

    return_code = main(
        [
            "--baseline-snapshot",
            _baseline(tmp_path),
            "--fail-on-regression",
            "--snapshot-dir",
            str(tmp_path),
            "--snapshot-format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[validation-gate] warning: regression guard reported WARNING" in captured.out


def test_gate_fail_exits_one_with_fail_on_regression(tmp_path, capsys, monkeypatch) -> None:
    _patch_validation(monkeypatch)
    _patch_comparison(monkeypatch, "FAIL")

    return_code = main(
        [
            "--baseline-snapshot",
            _baseline(tmp_path),
            "--fail-on-regression",
            "--snapshot-dir",
            str(tmp_path),
            "--snapshot-format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 1
    assert "[validation-gate] failed due to regression" in captured.out


def test_gate_fail_exits_zero_without_fail_on_regression(tmp_path, capsys, monkeypatch) -> None:
    _patch_validation(monkeypatch)
    _patch_comparison(monkeypatch, "FAIL")

    return_code = main(
        [
            "--baseline-snapshot",
            _baseline(tmp_path),
            "--snapshot-dir",
            str(tmp_path),
            "--snapshot-format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[validation-gate] completed status=FAIL" in captured.out


def test_gate_missing_baseline_path_exits_nonzero(capsys, monkeypatch) -> None:
    _patch_validation(monkeypatch)

    return_code = main(["--baseline-snapshot", "missing.json"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "baseline snapshot not found" in captured.out


def test_gate_uses_baseline_snapshot_over_baseline_config(tmp_path, capsys, monkeypatch) -> None:
    _patch_validation(monkeypatch)
    _patch_comparison(monkeypatch, "PASS")
    explicit = _baseline(tmp_path)
    configured = tmp_path / "configured.json"
    configured.write_text(json.dumps({"metadata": {}, "multi_sample_result": {"rows": []}}), encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"baseline_snapshot_path": str(configured)}), encoding="utf-8")

    return_code = main(
        [
            "--baseline-snapshot",
            explicit,
            "--baseline-config",
            str(config),
            "--snapshot-dir",
            str(tmp_path / "snapshots"),
            "--snapshot-format",
            "json",
        ]
    )

    capsys.readouterr()
    assert return_code == 0
    assert _FakeSnapshotComparisonEngine.last_baseline_path == explicit


def test_gate_uses_baseline_config_when_snapshot_omitted(tmp_path, capsys, monkeypatch) -> None:
    _patch_validation(monkeypatch)
    _patch_comparison(monkeypatch, "PASS")
    baseline = _baseline(tmp_path)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"baseline_snapshot_path": baseline}), encoding="utf-8")

    return_code = main(
        [
            "--baseline-config",
            str(config),
            "--snapshot-dir",
            str(tmp_path / "snapshots"),
            "--snapshot-format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[validation-gate] using baseline config" in captured.out
    assert _FakeSnapshotComparisonEngine.compared is True


def test_gate_skips_comparison_when_baseline_config_missing(tmp_path, capsys, monkeypatch) -> None:
    _patch_validation(monkeypatch)
    _patch_comparison(monkeypatch, "PASS")

    return_code = main(
        [
            "--baseline-config",
            str(tmp_path / "missing_config.json"),
            "--snapshot-dir",
            str(tmp_path / "snapshots"),
            "--snapshot-format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "baseline config not found" in captured.out
    assert _FakeSnapshotComparisonEngine.compared is False


def test_gate_skips_comparison_when_baseline_config_null(tmp_path, capsys, monkeypatch) -> None:
    _patch_validation(monkeypatch)
    _patch_comparison(monkeypatch, "PASS")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"baseline_snapshot_path": None}), encoding="utf-8")

    return_code = main(
        [
            "--baseline-config",
            str(config),
            "--snapshot-dir",
            str(tmp_path / "snapshots"),
            "--snapshot-format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "comparison skipped" in captured.out
    assert _FakeSnapshotComparisonEngine.compared is False


def test_gate_exits_nonzero_when_config_points_to_missing_baseline(tmp_path, capsys, monkeypatch) -> None:
    _patch_validation(monkeypatch)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"baseline_snapshot_path": "missing.json"}), encoding="utf-8")

    return_code = main(["--baseline-config", str(config)])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "baseline snapshot not found" in captured.out


def test_gate_export_comparison_writes_files(tmp_path, capsys, monkeypatch) -> None:
    _patch_validation(monkeypatch)
    _patch_comparison(monkeypatch, "PASS")

    return_code = main(
        [
            "--baseline-snapshot",
            _baseline(tmp_path),
            "--export-comparison",
            "--snapshot-dir",
            str(tmp_path / "snapshots"),
            "--comparison-dir",
            str(tmp_path / "comparisons"),
            "--snapshot-format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[validation-gate] comparison wrote" in captured.out
    assert list((tmp_path / "comparisons").glob("*.json"))
    assert list((tmp_path / "comparisons").glob("*.md"))


def test_gate_snapshot_format_md_with_baseline_still_creates_json_for_comparison(tmp_path, monkeypatch) -> None:
    _patch_validation(monkeypatch)
    _patch_comparison(monkeypatch, "PASS")
    snapshot_dir = tmp_path / "snapshots"

    return_code = main(
        [
            "--baseline-snapshot",
            _baseline(tmp_path),
            "--snapshot-dir",
            str(snapshot_dir),
            "--snapshot-format",
            "md",
        ]
    )

    assert return_code == 0
    assert list(snapshot_dir.glob("*.md"))
    assert list(snapshot_dir.glob("*.json"))


def test_gate_snapshot_format_both_writes_both(tmp_path, capsys, monkeypatch) -> None:
    _patch_validation(monkeypatch)

    return_code = main(["--snapshot-dir", str(tmp_path), "--snapshot-format", "both"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert captured.out.count("[validation-gate] snapshot wrote") == 2
    assert list(tmp_path.glob("*.json"))
    assert list(tmp_path.glob("*.md"))


def test_generated_snapshot_files_are_gitignored() -> None:
    text = Path(".gitignore").read_text(encoding="utf-8")

    assert "reports/validation_snapshots/*.json" in text
    assert "reports/validation_snapshots/*.md" in text
