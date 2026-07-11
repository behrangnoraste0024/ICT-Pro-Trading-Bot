from __future__ import annotations

import json
from pathlib import Path

from scripts import run_btc_futures_paper_position
from tests.test_btc_futures_paper_position_engine import _write_configs


def test_default_json_and_strict(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_futures_paper_position, "ROOT_DIR", tmp_path)

    text_code = run_btc_futures_paper_position.main([])
    text = capsys.readouterr().out
    json_code = run_btc_futures_paper_position.main(["--json"])
    payload = json.loads(capsys.readouterr().out)
    strict_code = run_btc_futures_paper_position.main(["--strict"])

    assert text_code == 0
    assert "BTC FUTURES PAPER POSITION CONFIG VALIDATION" in text
    assert json_code == 0
    assert payload["status"] == "PASS"
    assert strict_code == 0


def test_cli_lifecycle_json_and_exports(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_futures_paper_position, "ROOT_DIR", tmp_path)
    json_path = tmp_path / "exports" / "paper.json"
    md_path = tmp_path / "exports" / "paper.md"

    init_code = run_btc_futures_paper_position.main(["--initialize", "--json", "--export-json", str(json_path), "--export-md", str(md_path)])
    init_payload = json.loads(capsys.readouterr().out)
    open_code = run_btc_futures_paper_position.main(["--open-position", "--side", "LONG", "--entry-price", "64000", "--mark-price", "64000", "--stop-loss", "62000", "--take-profit", "67000", "--notional", "1000", "--leverage", "3", "--action-id", "open-1", "--json"])
    open_payload = json.loads(capsys.readouterr().out)
    mark_code = run_btc_futures_paper_position.main(["--mark-to-market", "--mark-price", "65000", "--action-id", "mark-1", "--json"])
    mark_payload = json.loads(capsys.readouterr().out)
    funding_code = run_btc_futures_paper_position.main(["--apply-funding", "--funding-rate", "0.0001", "--funding-periods", "1", "--action-id", "funding-1", "--json"])
    funding_payload = json.loads(capsys.readouterr().out)
    close_code = run_btc_futures_paper_position.main(["--close-position", "--close-price", "66000", "--close-reason", "MANUAL", "--action-id", "close-1", "--json"])
    close_payload = json.loads(capsys.readouterr().out)
    summary_code = run_btc_futures_paper_position.main(["--ledger-summary", "--json"])
    summary_payload = json.loads(capsys.readouterr().out)

    assert init_code == open_code == mark_code == funding_code == close_code == summary_code == 0
    assert init_payload["state_written"] is True
    assert open_payload["local_paper_futures_position_created"] is True
    assert mark_payload["decision"] == "MARK_UPDATED"
    assert funding_payload["local_funding_applied"] is True
    assert close_payload["local_position_closed"] is True
    assert summary_payload["position_opened_events"] == 1
    assert json_path.exists()
    assert md_path.exists()


def test_missing_args_reset_and_simulate_lifecycle(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_futures_paper_position, "ROOT_DIR", tmp_path)

    missing_code = run_btc_futures_paper_position.main(["--open-position", "--json"])
    missing_payload = json.loads(capsys.readouterr().out)
    reset_code = run_btc_futures_paper_position.main(["--reset", "--json"])
    reset_payload = json.loads(capsys.readouterr().out)
    lifecycle_code = run_btc_futures_paper_position.main(["--simulate-lifecycle", "--json"])
    lifecycle_payload = json.loads(capsys.readouterr().out)

    assert missing_code == 1
    assert missing_payload["status"] == "FAIL"
    assert reset_code == 0
    assert reset_payload["status"] == "WARNING"
    assert lifecycle_code == 0
    assert lifecycle_payload["metadata"]["persistent_state_used"] is False
    assert lifecycle_payload["state_written"] is False
    assert lifecycle_payload["ledger_written"] is False
