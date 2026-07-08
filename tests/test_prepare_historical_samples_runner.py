from __future__ import annotations

import json

from scripts.prepare_historical_samples import main


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


def test_cli_default_prints_plan_and_exits_zero(tmp_path, capsys) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(tmp_path / "missing.json"))])

    return_code = main(["--registry", str(registry)])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "HISTORICAL SAMPLE PREPARATION PLAN" in captured.out


def test_cli_json_prints_json_plan(tmp_path, capsys) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(tmp_path / "missing.json"))])

    return_code = main(["--registry", str(registry), "--json"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert return_code == 0
    assert data["action_required_samples"] == 1


def test_cli_fail_if_action_required_exits_one_when_sample_missing(tmp_path, capsys) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("sample", str(tmp_path / "missing.json"))])

    return_code = main(["--registry", str(registry), "--fail-if-action-required"])

    capsys.readouterr()
    assert return_code == 1


def test_cli_sample_filters_to_one_sample(tmp_path, capsys) -> None:
    registry = tmp_path / "registry.json"
    _registry(
        registry,
        [
            _sample("one", str(tmp_path / "one.json")),
            _sample("two", str(tmp_path / "two.json")),
        ],
    )

    return_code = main(["--registry", str(registry), "--sample", "two"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "two | BTC/USDT" in captured.out
    assert "one | BTC/USDT" not in captured.out


def test_cli_unknown_sample_exits_nonzero(tmp_path, capsys) -> None:
    registry = tmp_path / "registry.json"
    _registry(registry, [_sample("known", str(tmp_path / "known.json"))])

    return_code = main(["--registry", str(registry), "--sample", "unknown"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "historical sample not found" in captured.out


def test_cli_import_source_dry_run_does_not_write_destination(tmp_path, capsys) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "dest.json"
    registry = tmp_path / "registry.json"
    source.write_text(json.dumps([{}, {}]), encoding="utf-8")
    _registry(registry, [_sample("sample", str(destination))])

    return_code = main(
        [
            "--registry",
            str(registry),
            "--sample",
            "sample",
            "--source",
            str(source),
            "--import-source",
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "dry-run import accepted" in captured.out
    assert not destination.exists()


def test_cli_import_source_writes_destination(tmp_path, capsys) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "dest.json"
    registry = tmp_path / "registry.json"
    source.write_text(json.dumps([{}, {}]), encoding="utf-8")
    _registry(registry, [_sample("sample", str(destination))])

    return_code = main(
        [
            "--registry",
            str(registry),
            "--sample",
            "sample",
            "--source",
            str(source),
            "--import-source",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "imported" in captured.out
    assert destination.exists()


def test_cli_import_source_refuses_overwrite(tmp_path, capsys) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "dest.json"
    registry = tmp_path / "registry.json"
    source.write_text(json.dumps([{}, {}]), encoding="utf-8")
    destination.write_text(json.dumps([{"old": True}]), encoding="utf-8")
    _registry(registry, [_sample("sample", str(destination))])

    return_code = main(
        [
            "--registry",
            str(registry),
            "--sample",
            "sample",
            "--source",
            str(source),
            "--import-source",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 1
    assert "destination already exists" in captured.out


def test_cli_import_source_refuses_too_few_candles(tmp_path, capsys) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "dest.json"
    registry = tmp_path / "registry.json"
    source.write_text(json.dumps([{}]), encoding="utf-8")
    _registry(registry, [_sample("sample", str(destination), minimum=2)])

    return_code = main(
        [
            "--registry",
            str(registry),
            "--sample",
            "sample",
            "--source",
            str(source),
            "--import-source",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 1
    assert "too few candles" in captured.out


def test_cli_import_source_allows_too_few_when_flagged(tmp_path, capsys) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "dest.json"
    registry = tmp_path / "registry.json"
    source.write_text(json.dumps([{}]), encoding="utf-8")
    _registry(registry, [_sample("sample", str(destination), minimum=2)])

    return_code = main(
        [
            "--registry",
            str(registry),
            "--sample",
            "sample",
            "--source",
            str(source),
            "--import-source",
            "--allow-too-few",
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "warning: imported source has fewer candles" in captured.out


def test_cli_import_source_invalid_json_exits_nonzero(tmp_path, capsys) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "dest.json"
    registry = tmp_path / "registry.json"
    source.write_text("{", encoding="utf-8")
    _registry(registry, [_sample("sample", str(destination))])

    return_code = main(
        [
            "--registry",
            str(registry),
            "--sample",
            "sample",
            "--source",
            str(source),
            "--import-source",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 1
    assert "source file invalid JSON" in captured.out


def test_cli_validate_after_import_prints_availability(tmp_path, capsys) -> None:
    source = tmp_path / "source.json"
    destination = tmp_path / "dest.json"
    registry = tmp_path / "registry.json"
    source.write_text(json.dumps({"candles": [{}, {}]}), encoding="utf-8")
    _registry(registry, [_sample("sample", str(destination))])

    return_code = main(
        [
            "--registry",
            str(registry),
            "--sample",
            "sample",
            "--source",
            str(source),
            "--import-source",
            "--validate-after-import",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "HISTORICAL SAMPLE REGISTRY" in captured.out
    assert "AVAILABLE" in captured.out


def test_cli_source_without_sample_exits_nonzero(tmp_path, capsys) -> None:
    return_code = main(["--registry", str(tmp_path / "registry.json"), "--source", str(tmp_path / "source.json")])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "--source requires --sample" in captured.out
