from __future__ import annotations

import json

from scripts.check_historical_samples import main


def _registry(path, samples) -> None:
    path.write_text(json.dumps({"schema_version": "1.0", "samples": samples}), encoding="utf-8")


def _sample(fixture_path: str, *, full: bool = False, ci: bool = False) -> dict:
    return {
        "sample_name": "sample",
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "fixture_path": fixture_path,
        "expected_min_candles": 2,
        "required_for_full_gate": full,
        "required_for_ci_gate": ci,
    }


def test_cli_default_exits_zero_when_optional_samples_missing(tmp_path, capsys) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample(str(tmp_path / "missing.json"))])

    return_code = main(["--registry", str(registry)])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "MISSING" in captured.out


def test_cli_fail_missing_required_full_exits_one(tmp_path, capsys) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample(str(tmp_path / "missing.json"), full=True)])

    return_code = main(["--registry", str(registry), "--fail-missing-required-full"])

    capsys.readouterr()
    assert return_code == 1


def test_cli_fail_missing_required_ci_exits_one(tmp_path, capsys) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample(str(tmp_path / "missing.json"), ci=True)])

    return_code = main(["--registry", str(registry), "--fail-missing-required-ci"])

    capsys.readouterr()
    assert return_code == 1


def test_cli_json_prints_json_report(tmp_path, capsys) -> None:
    fixture = tmp_path / "candles.json"
    fixture.write_text(json.dumps([{}, {}]), encoding="utf-8")
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample(str(fixture), full=True)])

    return_code = main(["--registry", str(registry), "--json"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert return_code == 0
    assert data["available_samples"] == 1
    assert data["samples"][0]["status"] == "AVAILABLE"


def test_cli_missing_registry_exits_nonzero(tmp_path, capsys) -> None:
    return_code = main(["--registry", str(tmp_path / "missing.json")])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "historical sample registry not found" in captured.out
