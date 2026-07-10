from __future__ import annotations

import json

from scripts import run_btc_forward_test_loop
from tests.test_btc_forward_test_loop_engine import _write_forward_configs


def test_default_runner_prints_validation(capsys, monkeypatch, tmp_path) -> None:
    _write_forward_configs(tmp_path)
    monkeypatch.setattr(run_btc_forward_test_loop, "ROOT_DIR", tmp_path)

    code = run_btc_forward_test_loop.main([])

    captured = capsys.readouterr()
    assert code == 0
    assert "BTC FORWARD TEST LOOP CONFIG VALIDATION" in captured.out


def test_json_prints_serializable_validation(capsys, monkeypatch, tmp_path) -> None:
    _write_forward_configs(tmp_path)
    monkeypatch.setattr(run_btc_forward_test_loop, "ROOT_DIR", tmp_path)

    code = run_btc_forward_test_loop.main(["--json"])

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["status"] == "PASS"


def test_strict_exits_zero_for_pass(capsys, monkeypatch, tmp_path) -> None:
    _write_forward_configs(tmp_path)
    monkeypatch.setattr(run_btc_forward_test_loop, "ROOT_DIR", tmp_path)

    code = run_btc_forward_test_loop.main(["--strict"])

    capsys.readouterr()
    assert code == 0


def test_strict_exits_one_for_fail(capsys, monkeypatch, tmp_path) -> None:
    _write_forward_configs(tmp_path, forward={"allow_order_submission": True})
    monkeypatch.setattr(run_btc_forward_test_loop, "ROOT_DIR", tmp_path)

    code = run_btc_forward_test_loop.main(["--strict"])

    capsys.readouterr()
    assert code == 1


def test_run_json_never_executes(capsys, monkeypatch, tmp_path) -> None:
    _write_forward_configs(tmp_path)
    monkeypatch.setattr(run_btc_forward_test_loop, "ROOT_DIR", tmp_path)

    code = run_btc_forward_test_loop.main(["--run", "--cycles", "2", "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert payload["cycles_requested"] == 2
    assert payload["live_market_data_used"] is False
    assert payload["executable_trade_created"] is False
    assert payload["paper_trade_persisted"] is False
    assert payload["position_created"] is False
    assert payload["order_submitted"] is False
    assert payload["exchange_connected"] is False
    assert payload["state_mutated"] is False


def test_state_summary_reset_and_exports(capsys, monkeypatch, tmp_path) -> None:
    _write_forward_configs(tmp_path)
    monkeypatch.setattr(run_btc_forward_test_loop, "ROOT_DIR", tmp_path)
    state_path = tmp_path / "reports" / "forward_test" / "state.json"
    json_path = tmp_path / "forward.json"
    md_path = tmp_path / "forward.md"

    run_code = run_btc_forward_test_loop.main(["--run", "--cycles", "1", "--state-file", str(state_path)])
    summary_code = run_btc_forward_test_loop.main(["--summary", "--state-file", str(state_path), "--export-json", str(json_path), "--export-md", str(md_path)])
    reset_code = run_btc_forward_test_loop.main(["--reset-state", "--state-file", str(state_path)])

    captured = capsys.readouterr()
    assert run_code == 0
    assert summary_code == 0
    assert reset_code == 0
    assert "[btc-forward-test] wrote" in captured.out
    assert json_path.exists()
    assert md_path.exists()
    assert not state_path.exists()
