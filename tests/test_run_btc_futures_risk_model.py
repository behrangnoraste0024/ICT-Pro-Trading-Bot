from __future__ import annotations

import json
from pathlib import Path

from scripts import run_btc_futures_risk_model
from tests.test_btc_futures_risk_model_engine import _write_risk_configs


def test_default_validation_and_json(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_risk_configs(tmp_path)
    monkeypatch.setattr(run_btc_futures_risk_model, "ROOT_DIR", tmp_path)

    text_code = run_btc_futures_risk_model.main([])
    text = capsys.readouterr().out
    json_code = run_btc_futures_risk_model.main(["--json"])
    payload = json.loads(capsys.readouterr().out)

    assert text_code == 0
    assert "BTC FUTURES RISK MODEL CONFIG VALIDATION" in text
    assert json_code == 0
    assert payload["status"] == "PASS"


def test_strict_pass_and_fail(tmp_path: Path, monkeypatch) -> None:
    path = _write_risk_configs(tmp_path)
    monkeypatch.setattr(run_btc_futures_risk_model, "ROOT_DIR", tmp_path)

    assert run_btc_futures_risk_model.main(["--strict"]) == 0
    path.write_text(path.read_text(encoding="utf-8").replace('"simulation_only": true', '"simulation_only": false'), encoding="utf-8")
    assert run_btc_futures_risk_model.main(["--strict"]) == 1


def test_analyze_scenario_compare_and_exports(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_risk_configs(tmp_path)
    monkeypatch.setattr(run_btc_futures_risk_model, "ROOT_DIR", tmp_path)
    json_path = tmp_path / "risk.json"
    md_path = tmp_path / "risk.md"

    scenario_code = run_btc_futures_risk_model.main(["--analyze-scenario", "--side", "LONG", "--entry-price", "64000", "--mark-price", "63800", "--stop-loss", "62000", "--take-profit", "67000", "--notional", "1000", "--account-equity", "10000", "--leverage", "3", "--funding-rate", "0.0001", "--export-json", str(json_path), "--export-md", str(md_path)])
    scenario_text = capsys.readouterr().out
    compare_code = run_btc_futures_risk_model.main(["--compare-leverage", "--side", "LONG", "--entry-price", "64000", "--mark-price", "63800", "--stop-loss", "62000", "--take-profit", "67000", "--notional", "1000", "--account-equity", "10000"])
    compare_text = capsys.readouterr().out

    assert scenario_code == 0
    assert "Estimated Liquidation:" in scenario_text
    assert json_path.exists()
    assert md_path.exists()
    assert compare_code == 0
    assert "BTC FUTURES LEVERAGE COMPARISON" in compare_text


def test_analyze_scenario_json_serializable(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_risk_configs(tmp_path)
    monkeypatch.setattr(run_btc_futures_risk_model, "ROOT_DIR", tmp_path)

    code = run_btc_futures_risk_model.main(["--analyze-scenario", "--side", "SHORT", "--entry-price", "64000", "--mark-price", "64200", "--stop-loss", "66000", "--take-profit", "61000", "--notional", "1000", "--account-equity", "10000", "--leverage", "3", "--funding-rate", "0.0001", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["scenario"]["side"] == "SHORT"
    assert payload["exchange_leverage_changed"] is False


def test_missing_scenario_args_returns_fail_report(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_risk_configs(tmp_path)
    monkeypatch.setattr(run_btc_futures_risk_model, "ROOT_DIR", tmp_path)

    code = run_btc_futures_risk_model.main(["--analyze-scenario", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "FAIL"
    assert payload["decision"] == "INVALID_SCENARIO"
    assert payload["trading_api_used"] is False
    assert payload["order_submitted"] is False
    assert payload["issues"][0]["name"] == "invalid_cli_request"
