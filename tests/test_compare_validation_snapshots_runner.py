from __future__ import annotations

import json

from scripts.compare_validation_snapshots import main


def _row(**overrides):
    values = {
        "sample_name": "btcusdt_15m_1000",
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "status": "PASSED",
        "recommended_profile": "balanced_smc_decision_065",
        "total_trades": 5,
        "wins": 5,
        "losses": 0,
        "win_rate": 100.0,
        "net_pnl_after_costs": 1404.24,
        "max_drawdown": 0.0,
        "validation_status": "PASS",
        "profitable_segments": 4,
        "losing_segments": 0,
        "empty_segments": 0,
        "worst_segment_net_pnl_after_costs": 157.54,
    }
    values.update(overrides)
    return values


def _snapshot(rows=None):
    return {
        "metadata": {
            "snapshot_schema_version": "2.50.0",
            "created_at": "2026-07-07T12:00:00+00:00",
            "git_commit": "abc123",
            "recommended_profile": "balanced_smc_decision_065",
        },
        "multi_sample_result": {"rows": [_row()] if rows is None else rows},
    }


def _write(path, snapshot) -> None:
    path.write_text(json.dumps(snapshot), encoding="utf-8")


def test_cli_prints_report(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    _write(baseline, _snapshot())
    _write(candidate, _snapshot())

    return_code = main(["--baseline", str(baseline), "--candidate", str(candidate)])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "===== SNAPSHOT COMPARISON / REGRESSION GUARD =====" in captured.out
    assert "Regression Status : PASS" in captured.out


def test_cli_fail_on_regression_exits_nonzero_on_fail(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    _write(baseline, _snapshot())
    _write(candidate, _snapshot([_row(status="FAILED")]))

    return_code = main(["--baseline", str(baseline), "--candidate", str(candidate), "--fail-on-regression"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "Regression Status : FAIL" in captured.out


def test_cli_export_json_writes_file(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    output = tmp_path / "comparison.json"
    _write(baseline, _snapshot())
    _write(candidate, _snapshot())

    return_code = main(["--baseline", str(baseline), "--candidate", str(candidate), "--export-json", str(output)])

    captured = capsys.readouterr()
    assert return_code == 0
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["regression_status"] == "PASS"
    assert "[snapshot-comparison] wrote" in captured.out


def test_cli_export_md_writes_file(tmp_path, capsys) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    output = tmp_path / "comparison.md"
    _write(baseline, _snapshot())
    _write(candidate, _snapshot())

    return_code = main(["--baseline", str(baseline), "--candidate", str(candidate), "--export-md", str(output)])

    captured = capsys.readouterr()
    assert return_code == 0
    assert output.exists()
    assert "SNAPSHOT COMPARISON" in output.read_text(encoding="utf-8")
    assert "[snapshot-comparison] wrote" in captured.out


def test_cli_missing_file_returns_nonzero(capsys) -> None:
    return_code = main(["--baseline", "missing-a.json", "--candidate", "missing-b.json"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "snapshot not found" in captured.out
