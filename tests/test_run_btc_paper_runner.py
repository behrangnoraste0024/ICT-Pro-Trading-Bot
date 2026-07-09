from __future__ import annotations

import json
from pathlib import Path

from scripts import run_btc_paper_runner

from tests.test_btc_paper_runner_engine import _write_configs
from tests.test_btc_paper_signal_evaluation_engine import _write_configs as _write_signal_configs
from tests.test_btc_paper_trade_candidate_engine import _write_trade_candidate_configs


def test_status_works_without_state_file(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)

    code = run_btc_paper_runner.main(["--status"])

    captured = capsys.readouterr()
    assert code == 0
    assert "BTC PAPER RUNNER DRY-RUN STATUS" in captured.out
    assert not (tmp_path / "reports" / "paper_runner" / "btc_paper_runner_state.json").exists()


def test_start_prints_no_execution_message_and_writes_state(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)

    code = run_btc_paper_runner.main(["--start", "--state-file", "reports/paper_runner/state.json"])

    captured = capsys.readouterr()
    assert code == 0
    assert "No signals, trades, orders, or exchange connections were executed" in captured.out
    assert json.loads((tmp_path / "reports" / "paper_runner" / "state.json").read_text(encoding="utf-8"))["state"] == "RUNNING"


def test_json_prints_serializable_result(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)

    code = run_btc_paper_runner.main(["--start", "--json"])

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["current_state"] == "RUNNING"


def test_exports_json_and_markdown(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)
    json_path = tmp_path / "runner.json"
    md_path = tmp_path / "runner.md"

    code = run_btc_paper_runner.main(["--status", "--export-json", str(json_path), "--export-md", str(md_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert "[btc-paper-runner] wrote" in captured.out
    assert json_path.exists()
    assert md_path.exists()


def test_pause_from_ready_exits_one(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)

    code = run_btc_paper_runner.main(["--pause"])

    capsys.readouterr()
    assert code == 1


def test_evaluate_signal_dry_run_does_not_mutate_state(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    _write_signal_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)
    state_path = tmp_path / "reports" / "paper_runner" / "state.json"
    run_btc_paper_runner.main(["--initialize", "--state-file", "reports/paper_runner/state.json"])
    before = json.loads(state_path.read_text(encoding="utf-8"))

    code = run_btc_paper_runner.main(["--evaluate-signal-dry-run", "--state-file", "reports/paper_runner/state.json"])

    captured = capsys.readouterr()
    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert code == 0
    assert before == after
    assert "BTC PAPER SIGNAL EVALUATION DRY-RUN" in captured.out
    assert "No signals, trades, orders, or exchange connections were executed" in captured.out


def test_simulate_trade_candidate_dry_run_does_not_mutate_state(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    _write_signal_configs(tmp_path)
    _write_trade_candidate_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)
    state_path = tmp_path / "reports" / "paper_runner" / "state.json"
    run_btc_paper_runner.main(["--initialize", "--state-file", "reports/paper_runner/state.json"])
    before = json.loads(state_path.read_text(encoding="utf-8"))

    code = run_btc_paper_runner.main(["--simulate-trade-candidate-dry-run", "--state-file", "reports/paper_runner/state.json"])

    captured = capsys.readouterr()
    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert code == 0
    assert before == after
    assert "BTC PAPER TRADE CANDIDATE DRY-RUN" in captured.out
    assert "Order Submitted     : false" in captured.out
