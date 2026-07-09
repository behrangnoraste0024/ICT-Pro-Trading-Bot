from __future__ import annotations

import json

from scripts import run_btc_paper_trade_candidate
from tests.test_btc_paper_trade_candidate_engine import _write_trade_candidate_configs


def test_default_runner_prints_validation(capsys, monkeypatch, tmp_path) -> None:
    _write_trade_candidate_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_trade_candidate, "ROOT_DIR", tmp_path)

    code = run_btc_paper_trade_candidate.main([])

    captured = capsys.readouterr()
    assert code == 0
    assert "BTC PAPER TRADE CANDIDATE CONFIG VALIDATION" in captured.out


def test_json_prints_serializable_validation(capsys, monkeypatch, tmp_path) -> None:
    _write_trade_candidate_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_trade_candidate, "ROOT_DIR", tmp_path)

    code = run_btc_paper_trade_candidate.main(["--json"])

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["status"] == "PASS"


def test_strict_exits_zero_for_pass(capsys, monkeypatch, tmp_path) -> None:
    _write_trade_candidate_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_trade_candidate, "ROOT_DIR", tmp_path)

    code = run_btc_paper_trade_candidate.main(["--strict"])

    capsys.readouterr()
    assert code == 0


def test_strict_exits_one_for_fail(capsys, monkeypatch, tmp_path) -> None:
    _write_trade_candidate_configs(tmp_path, candidate={"allow_order_submission": True})
    monkeypatch.setattr(run_btc_paper_trade_candidate, "ROOT_DIR", tmp_path)

    code = run_btc_paper_trade_candidate.main(["--strict"])

    capsys.readouterr()
    assert code == 1


def test_simulate_and_json_never_execute(capsys, monkeypatch, tmp_path) -> None:
    _write_trade_candidate_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_trade_candidate, "ROOT_DIR", tmp_path)

    code = run_btc_paper_trade_candidate.main(["--simulate", "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert payload["executable_trade_created"] is False
    assert payload["paper_trade_persisted"] is False
    assert payload["position_created"] is False
    assert payload["order_submitted"] is False
    assert payload["exchange_connected"] is False
    assert payload["state_mutated"] is False


def test_exports_json_and_md(capsys, monkeypatch, tmp_path) -> None:
    _write_trade_candidate_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_trade_candidate, "ROOT_DIR", tmp_path)
    json_path = tmp_path / "candidate.json"
    md_path = tmp_path / "candidate.md"

    code = run_btc_paper_trade_candidate.main(["--simulate", "--export-json", str(json_path), "--export-md", str(md_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert "[btc-paper-trade-candidate] wrote" in captured.out
    assert json_path.exists()
    assert md_path.exists()
