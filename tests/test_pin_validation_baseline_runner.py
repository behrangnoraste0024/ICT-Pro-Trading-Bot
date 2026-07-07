from __future__ import annotations

import json
from pathlib import Path

import scripts.pin_validation_baseline as pin_runner
from scripts.pin_validation_baseline import main


def _snapshot(
    path: Path,
    *,
    commit: str = "abc123",
    profile: str = "balanced_smc_decision_065",
    status: str = "PASSED",
    net_after_costs: float = 1000.0,
) -> None:
    path.write_text(
        json.dumps(
            {
                "metadata": {
                    "git_commit": commit,
                    "created_at": "2026-07-07T12:00:00+00:00",
                    "recommended_profile": profile,
                },
                "multi_sample_result": {
                    "rows": [
                        {
                            "sample_name": "btcusdt_15m_1000",
                            "symbol": "BTC/USDT",
                            "timeframe": "15m",
                            "status": status,
                            "recommended_profile": profile,
                            "total_trades": 5,
                            "win_rate": 100.0,
                            "net_pnl_after_costs": net_after_costs,
                            "max_drawdown": 0.0,
                            "validation_status": "PASS",
                            "profitable_segments": 4,
                            "losing_segments": 0,
                            "empty_segments": 0,
                            "worst_segment_net_pnl_after_costs": 100.0,
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )


def _config_with_baseline(config: Path, baseline: Path) -> None:
    config.write_text(
        json.dumps(
            {
                "baseline_snapshot_path": str(baseline),
                "baseline_git_commit": "base123",
                "baseline_created_at": "2026-07-07T11:00:00+00:00",
                "recommended_profile": "balanced_smc_decision_065",
                "notes": "keep me",
            }
        ),
        encoding="utf-8",
    )


def test_print_works_when_config_missing(tmp_path, capsys) -> None:
    return_code = main(["--print", "--config", str(tmp_path / "missing.json")])

    captured = capsys.readouterr()
    assert return_code == 0
    assert '"baseline_snapshot_path": null' in captured.out


def test_snapshot_writes_config_from_snapshot_metadata(tmp_path, capsys) -> None:
    snapshot = tmp_path / "snapshot.json"
    config = tmp_path / "config.json"
    _snapshot(snapshot)

    return_code = main(["--snapshot", str(snapshot), "--config", str(config)])

    captured = capsys.readouterr()
    data = json.loads(config.read_text(encoding="utf-8"))
    assert return_code == 0
    assert data["baseline_git_commit"] == "abc123"
    assert data["baseline_created_at"] == "2026-07-07T12:00:00+00:00"
    assert "[baseline] pinned" in captured.out


def test_snapshot_dry_run_does_not_write(tmp_path, capsys) -> None:
    snapshot = tmp_path / "snapshot.json"
    config = tmp_path / "config.json"
    _snapshot(snapshot)

    return_code = main(["--snapshot", str(snapshot), "--config", str(config), "--dry-run"])

    capsys.readouterr()
    assert return_code == 0
    assert not config.exists()


def test_validate_exits_zero_for_valid_config(tmp_path, capsys) -> None:
    snapshot = tmp_path / "snapshot.json"
    config = tmp_path / "config.json"
    _snapshot(snapshot)
    main(["--snapshot", str(snapshot), "--config", str(config)])
    capsys.readouterr()

    return_code = main(["--validate", "--config", str(config)])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[baseline] valid" in captured.out


def test_validate_exits_nonzero_for_missing_configured_file(tmp_path, capsys) -> None:
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"baseline_snapshot_path": "missing.json"}), encoding="utf-8")

    return_code = main(["--validate", "--config", str(config)])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "baseline snapshot not found" in captured.out


def test_clear_clears_baseline_fields(tmp_path, capsys) -> None:
    snapshot = tmp_path / "snapshot.json"
    config = tmp_path / "config.json"
    _snapshot(snapshot)
    main(["--snapshot", str(snapshot), "--config", str(config)])
    capsys.readouterr()

    return_code = main(["--clear", "--config", str(config)])

    captured = capsys.readouterr()
    data = json.loads(config.read_text(encoding="utf-8"))
    assert return_code == 0
    assert data["baseline_snapshot_path"] is None
    assert "[baseline] cleared" in captured.out


def test_snapshot_and_clear_cannot_both_be_used(tmp_path, capsys) -> None:
    return_code = main(["--snapshot", str(tmp_path / "snapshot.json"), "--clear"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "mutually exclusive" in captured.out


def test_promotes_candidate_snapshot_and_writes_config(tmp_path, capsys) -> None:
    candidate = tmp_path / "candidate.json"
    config = tmp_path / "config.json"
    _snapshot(candidate, commit="cand456")

    return_code = main(["--promote-candidate", str(candidate), "--config", str(config)])

    captured = capsys.readouterr()
    data = json.loads(config.read_text(encoding="utf-8"))
    assert return_code == 0
    assert data["baseline_snapshot_path"].endswith("candidate.json")
    assert data["baseline_git_commit"] == "cand456"
    assert data["baseline_created_at"] == "2026-07-07T12:00:00+00:00"
    assert data["recommended_profile"] == "balanced_smc_decision_065"
    assert "[baseline] promoted" in captured.out


def test_promotion_dry_run_does_not_write_config(tmp_path, capsys) -> None:
    candidate = tmp_path / "candidate.json"
    config = tmp_path / "config.json"
    _snapshot(candidate)

    return_code = main(["--promote-candidate", str(candidate), "--config", str(config), "--dry-run"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert not config.exists()
    assert '"baseline_git_commit": "abc123"' in captured.out
    assert "[baseline] promotion dry-run accepted" in captured.out


def test_promotion_stores_relative_path_when_candidate_is_inside_repo(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(pin_runner, "ROOT_DIR", tmp_path)
    reports = tmp_path / "reports" / "validation_snapshots"
    reports.mkdir(parents=True)
    candidate = reports / "candidate.json"
    config = tmp_path / "configs" / "validation_baseline.json"
    _snapshot(candidate)

    return_code = main(["--promote-candidate", str(candidate), "--config", str(config)])

    capsys.readouterr()
    data = json.loads(config.read_text(encoding="utf-8"))
    assert return_code == 0
    assert data["baseline_snapshot_path"] == str(Path("reports") / "validation_snapshots" / "candidate.json")


def test_promotion_rejects_missing_candidate_snapshot(tmp_path, capsys) -> None:
    return_code = main(["--promote-candidate", str(tmp_path / "missing.json"), "--config", str(tmp_path / "config.json")])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "candidate snapshot not found" in captured.out


def test_promotion_rejects_invalid_json_candidate_snapshot(tmp_path, capsys) -> None:
    candidate = tmp_path / "candidate.json"
    candidate.write_text("{", encoding="utf-8")

    return_code = main(["--promote-candidate", str(candidate), "--config", str(tmp_path / "config.json")])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "Error:" in captured.out


def test_promotion_rejects_profile_mismatch_by_default(tmp_path, capsys) -> None:
    candidate = tmp_path / "candidate.json"
    config = tmp_path / "config.json"
    _snapshot(candidate, profile="research_baseline")

    return_code = main(["--promote-candidate", str(candidate), "--config", str(config)])

    captured = capsys.readouterr()
    assert return_code == 1
    assert not config.exists()
    assert "promotion rejected profile mismatch" in captured.out


def test_promotion_allows_profile_mismatch_with_force(tmp_path, capsys) -> None:
    candidate = tmp_path / "candidate.json"
    config = tmp_path / "config.json"
    _snapshot(candidate, profile="research_baseline")

    return_code = main(["--promote-candidate", str(candidate), "--config", str(config), "--force"])

    captured = capsys.readouterr()
    data = json.loads(config.read_text(encoding="utf-8"))
    assert return_code == 0
    assert data["recommended_profile"] == "research_baseline"
    assert "force=true" in captured.out


def test_require_pass_accepts_pass_comparison(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    config = tmp_path / "config.json"
    _snapshot(baseline, commit="base123")
    _snapshot(candidate, commit="cand456")
    _config_with_baseline(config, baseline)

    return_code = main(["--promote-candidate", str(candidate), "--config", str(config), "--require-pass"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "promotion comparison status=PASS" in captured.out


def test_require_pass_rejects_fail_comparison(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    config = tmp_path / "config.json"
    _snapshot(baseline, commit="base123", net_after_costs=1000.0)
    _snapshot(candidate, commit="cand456", net_after_costs=800.0)
    _config_with_baseline(config, baseline)

    return_code = main(["--promote-candidate", str(candidate), "--config", str(config), "--require-pass"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "promotion comparison status=FAIL" in captured.out
    assert "promotion rejected status=FAIL" in captured.out


def test_require_pass_rejects_warning_by_default(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    config = tmp_path / "config.json"
    _snapshot(baseline, commit="base123", net_after_costs=1000.0)
    _snapshot(candidate, commit="cand456", net_after_costs=950.0)
    _config_with_baseline(config, baseline)

    return_code = main(["--promote-candidate", str(candidate), "--config", str(config), "--require-pass"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "promotion comparison status=WARNING" in captured.out
    assert "promotion rejected status=WARNING" in captured.out


def test_require_pass_allows_warning_with_allow_warning(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    config = tmp_path / "config.json"
    _snapshot(baseline, commit="base123", net_after_costs=1000.0)
    _snapshot(candidate, commit="cand456", net_after_costs=950.0)
    _config_with_baseline(config, baseline)

    return_code = main(
        [
            "--promote-candidate",
            str(candidate),
            "--config",
            str(config),
            "--require-pass",
            "--allow-warning",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "promotion comparison status=WARNING" in captured.out


def test_force_allows_fail_promotion(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    config = tmp_path / "config.json"
    _snapshot(baseline, commit="base123", net_after_costs=1000.0)
    _snapshot(candidate, commit="cand456", net_after_costs=800.0)
    _config_with_baseline(config, baseline)

    return_code = main(["--promote-candidate", str(candidate), "--config", str(config), "--require-pass", "--force"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "promotion comparison status=FAIL" in captured.out


def test_force_allows_missing_current_baseline(tmp_path, capsys) -> None:
    candidate = tmp_path / "candidate.json"
    config = tmp_path / "config.json"
    _snapshot(candidate)
    config.write_text(json.dumps({"baseline_snapshot_path": str(tmp_path / "missing.json")}), encoding="utf-8")

    return_code = main(["--promote-candidate", str(candidate), "--config", str(config), "--require-pass", "--force"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "promotion continuing without comparison force=true" in captured.out


def test_promotion_exports_comparison_files_when_requested(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    config = tmp_path / "config.json"
    export_dir = tmp_path / "exports"
    _snapshot(baseline, commit="base123")
    _snapshot(candidate, commit="cand456")
    _config_with_baseline(config, baseline)

    return_code = main(
        [
            "--promote-candidate",
            str(candidate),
            "--config",
            str(config),
            "--require-pass",
            "--comparison-export-dir",
            str(export_dir),
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert list(export_dir.glob("baseline_promotion_comparison_*_base123_to_cand456.json"))
    assert list(export_dir.glob("baseline_promotion_comparison_*_base123_to_cand456.md"))
    assert "promotion comparison wrote" in captured.out


def test_snapshot_and_promote_candidate_are_mutually_exclusive(tmp_path, capsys) -> None:
    return_code = main(
        [
            "--snapshot",
            str(tmp_path / "snapshot.json"),
            "--promote-candidate",
            str(tmp_path / "candidate.json"),
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 1
    assert "mutually exclusive" in captured.out
