from __future__ import annotations

import json

from scripts.pin_validation_baseline import main


def _snapshot(path) -> None:
    path.write_text(
        json.dumps(
            {
                "metadata": {
                    "git_commit": "abc123",
                    "created_at": "2026-07-07T12:00:00+00:00",
                    "recommended_profile": "balanced_smc_decision_065",
                },
                "multi_sample_result": {"rows": []},
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
    assert "cannot both be used" in captured.out
