from __future__ import annotations

import builtins
import json

from scripts.download_missing_historical_samples import main


def _registry(path, samples) -> None:
    path.write_text(json.dumps({"schema_version": "1.0", "samples": samples}), encoding="utf-8")


def _sample(name: str, fixture_path: str, *, minimum: int = 2) -> dict:
    return {
        "sample_name": name,
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "fixture_path": fixture_path,
        "expected_min_candles": minimum,
        "required_for_full_gate": False,
        "required_for_ci_gate": False,
    }


def test_cli_dry_run_prints_plan(tmp_path, capsys) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(tmp_path / "sample.json"))])

    return_code = main(["--registry", str(registry), "--dry-run"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "HISTORICAL SAMPLE DOWNLOAD PLAN" in captured.out
    assert "DRY_RUN" in captured.out


def test_cli_dry_run_json_prints_serializable_json(tmp_path, capsys) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(tmp_path / "sample.json"))])

    return_code = main(["--registry", str(registry), "--dry-run", "--json"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert return_code == 0
    assert data["planned_downloads"] == 1


def test_cli_sample_filters_one_sample(tmp_path, capsys) -> None:
    registry = tmp_path / "registry.json"
    _registry(
        registry,
        [
            _sample("one", str(tmp_path / "one.json")),
            _sample("two", str(tmp_path / "two.json")),
        ],
    )

    return_code = main(["--registry", str(registry), "--sample", "two", "--dry-run"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "two | BTC/USDT" in captured.out
    assert "one | BTC/USDT" not in captured.out


def test_cli_unknown_sample_exits_nonzero(tmp_path, capsys) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("known", str(tmp_path / "known.json"))])

    return_code = main(["--registry", str(registry), "--sample", "unknown", "--dry-run"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "historical sample not found" in captured.out


def test_cli_real_download_without_ccxt_reports_clear_error(tmp_path, capsys, monkeypatch) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(tmp_path / "sample.json"))])
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "ccxt":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    return_code = main(["--registry", str(registry)])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "ccxt is required for historical downloads" in captured.out
