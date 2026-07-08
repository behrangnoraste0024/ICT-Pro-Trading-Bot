from __future__ import annotations

import json

from scripts import run_btc_paper_signal_evaluation
from tests.test_btc_paper_signal_evaluation_engine import _write_configs


def test_default_runner_prints_validation(capsys, monkeypatch, tmp_path) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_signal_evaluation, "ROOT_DIR", tmp_path)

    code = run_btc_paper_signal_evaluation.main([])

    captured = capsys.readouterr()
    assert code == 0
    assert "BTC PAPER SIGNAL EVALUATION CONFIG VALIDATION" in captured.out


def test_json_prints_serializable_validation(capsys, monkeypatch, tmp_path) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_signal_evaluation, "ROOT_DIR", tmp_path)

    code = run_btc_paper_signal_evaluation.main(["--json"])

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["status"] == "PASS"


def test_strict_exits_zero_for_pass(capsys, monkeypatch, tmp_path) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_signal_evaluation, "ROOT_DIR", tmp_path)

    code = run_btc_paper_signal_evaluation.main(["--strict"])

    capsys.readouterr()
    assert code == 0


def test_strict_exits_one_for_fail(capsys, monkeypatch, tmp_path) -> None:
    _write_configs(tmp_path, runtime={"live_trading_enabled": True})
    monkeypatch.setattr(run_btc_paper_signal_evaluation, "ROOT_DIR", tmp_path)

    code = run_btc_paper_signal_evaluation.main(["--strict"])

    capsys.readouterr()
    assert code == 1


def test_evaluate_and_json_never_execute(capsys, monkeypatch, tmp_path) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_signal_evaluation, "ROOT_DIR", tmp_path)

    code = run_btc_paper_signal_evaluation.main(["--evaluate", "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert payload["trade_created"] is False
    assert payload["order_submitted"] is False
    assert payload["exchange_connected"] is False
    assert payload["state_mutated"] is False


def test_exports_json_and_md(capsys, monkeypatch, tmp_path) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_signal_evaluation, "ROOT_DIR", tmp_path)
    json_path = tmp_path / "signal.json"
    md_path = tmp_path / "signal.md"

    code = run_btc_paper_signal_evaluation.main(["--evaluate", "--export-json", str(json_path), "--export-md", str(md_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert "[btc-paper-signal-evaluation] wrote" in captured.out
    assert json_path.exists()
    assert md_path.exists()
