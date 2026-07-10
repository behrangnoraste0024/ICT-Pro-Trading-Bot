from __future__ import annotations

import json
from pathlib import Path

import pytest

from models.btc_paper_account import (
    BTCPaperAccountAction,
    BTCPaperAccountActionResult,
    BTCPaperAccountDecision,
    BTCPaperAccountStatus,
)
from scripts import run_btc_paper_account
from tests.test_btc_paper_account_engine import _write_account_configs


def test_validate_default_action_prints_report(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_account_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_account, "ROOT_DIR", tmp_path)

    code = run_btc_paper_account.main([])

    captured = capsys.readouterr()
    assert code == 0
    assert "BTC LOCAL PAPER ACCOUNT CONFIG VALIDATION" in captured.out
    assert "Status            : PASS" in captured.out


def test_initialize_writes_local_state_and_json_output(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_account_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_account, "ROOT_DIR", tmp_path)

    code = run_btc_paper_account.main(["--initialize", "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert payload["status"] == "PASS"
    assert (tmp_path / "reports" / "paper_account" / "btc_paper_account_state.json").exists()


def test_action_exclusivity_is_enforced() -> None:
    with pytest.raises(SystemExit):
        run_btc_paper_account.main(["--status", "--initialize"])


def test_export_json_and_markdown(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_account_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_account, "ROOT_DIR", tmp_path)
    json_path = tmp_path / "paper_account.json"
    md_path = tmp_path / "paper_account.md"

    code = run_btc_paper_account.main(["--status", "--export-json", str(json_path), "--export-md", str(md_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert "[btc-paper-account] wrote" in captured.out
    assert json_path.exists()
    assert md_path.exists()


class _FakePaperAccountEngine:
    def __init__(self, repo_root=None) -> None:
        self.repo_root = repo_root

    def simulate_live_observation(self, *args, **kwargs) -> BTCPaperAccountActionResult:
        return BTCPaperAccountActionResult(
            action=BTCPaperAccountAction.SIMULATE_LIVE_OBSERVATION.value,
            status=BTCPaperAccountStatus.WARNING.value,
            decision=BTCPaperAccountDecision.NO_ACTION_NO_CANDIDATE.value,
            safety_summary={"real_order_submitted": False, "trading_api_used": False},
            no_action_recorded=True,
        )


def test_simulate_live_observation_cli_uses_engine_without_real_order(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_account_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_account, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(run_btc_paper_account, "BTCPaperAccountEngine", _FakePaperAccountEngine)

    code = run_btc_paper_account.main(["--simulate-live-observation"])

    captured = capsys.readouterr()
    assert code == 0
    assert "No Action Recorded : true" in captured.out
    assert "Real Order Sent    : false" in captured.out
