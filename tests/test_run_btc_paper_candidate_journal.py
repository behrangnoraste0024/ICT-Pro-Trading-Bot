from __future__ import annotations

import json

from scripts import run_btc_paper_candidate_journal
from tests.test_btc_paper_candidate_journal_engine import _write_journal_configs


def test_default_runner_prints_validation(capsys, monkeypatch, tmp_path) -> None:
    _write_journal_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_candidate_journal, "ROOT_DIR", tmp_path)

    code = run_btc_paper_candidate_journal.main([])

    captured = capsys.readouterr()
    assert code == 0
    assert "BTC PAPER CANDIDATE JOURNAL CONFIG VALIDATION" in captured.out


def test_json_prints_serializable_validation(capsys, monkeypatch, tmp_path) -> None:
    _write_journal_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_candidate_journal, "ROOT_DIR", tmp_path)

    code = run_btc_paper_candidate_journal.main(["--json"])

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["status"] == "PASS"


def test_strict_exits_zero_for_pass(capsys, monkeypatch, tmp_path) -> None:
    _write_journal_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_candidate_journal, "ROOT_DIR", tmp_path)

    code = run_btc_paper_candidate_journal.main(["--strict"])

    capsys.readouterr()
    assert code == 0


def test_strict_exits_one_for_fail(capsys, monkeypatch, tmp_path) -> None:
    _write_journal_configs(tmp_path, journal={"allow_order_submission": True})
    monkeypatch.setattr(run_btc_paper_candidate_journal, "ROOT_DIR", tmp_path)

    code = run_btc_paper_candidate_journal.main(["--strict"])

    capsys.readouterr()
    assert code == 1


def test_summary_json_handles_missing_journal(capsys, monkeypatch, tmp_path) -> None:
    _write_journal_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_candidate_journal, "ROOT_DIR", tmp_path)

    code = run_btc_paper_candidate_journal.main(["--summary", "--json", "--journal-path", str(tmp_path / "missing.jsonl")])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert payload["total_entries_read"] == 0
    assert payload["status"] == "WARNING"


def test_simulate_and_record_json_never_executes(capsys, monkeypatch, tmp_path) -> None:
    _write_journal_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_candidate_journal, "ROOT_DIR", tmp_path)
    journal_path = tmp_path / "reports" / "paper_candidate_journal" / "test.jsonl"

    code = run_btc_paper_candidate_journal.main(["--simulate-and-record", "--json", "--journal-path", str(journal_path)])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert payload["entry_written"] is True
    assert payload["executable_trade_created"] is False
    assert payload["paper_trade_persisted"] is False
    assert payload["position_created"] is False
    assert payload["order_submitted"] is False
    assert payload["exchange_connected"] is False
    assert payload["state_mutated"] is False
    assert journal_path.exists()


def test_exports_json_and_md(capsys, monkeypatch, tmp_path) -> None:
    _write_journal_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_candidate_journal, "ROOT_DIR", tmp_path)
    json_path = tmp_path / "journal.json"
    md_path = tmp_path / "journal.md"

    code = run_btc_paper_candidate_journal.main(["--summary", "--export-json", str(json_path), "--export-md", str(md_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert "[btc-paper-candidate-journal] wrote" in captured.out
    assert json_path.exists()
    assert md_path.exists()
