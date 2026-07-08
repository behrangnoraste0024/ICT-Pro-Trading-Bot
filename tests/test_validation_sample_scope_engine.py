from __future__ import annotations

import json

import pytest

from engine.diagnostics.validation_sample_scope_engine import ValidationSampleScopeEngine


def _registry(path, *, available: set[str] | None = None) -> None:
    available = available or set()
    samples = [
        _sample("btcusdt_15m_1000", "BTC/USDT", "15m", full=True, ci=True, available="btcusdt_15m_1000" in available),
        _sample("btcusdt_1h_1000", "BTC/USDT", "1h", full=True, ci=False, available="btcusdt_1h_1000" in available),
        _sample("ethusdt_15m_1000", "ETH/USDT", "15m", full=False, ci=False, available="ethusdt_15m_1000" in available),
        _sample("ethusdt_1h_1000", "ETH/USDT", "1h", full=False, ci=False, available="ethusdt_1h_1000" in available),
    ]
    path.write_text(json.dumps({"schema_version": "1.0", "samples": samples}), encoding="utf-8")


def _sample(name: str, symbol: str, timeframe: str, *, full: bool, ci: bool, available: bool) -> dict:
    fixture_path = f"data/historical/{name}.json"
    if available:
        fixture_path = f"{name}.json"
    return {
        "sample_name": name,
        "symbol": symbol,
        "timeframe": timeframe,
        "fixture_path": fixture_path,
        "expected_min_candles": 1,
        "required_for_full_gate": full,
        "required_for_ci_gate": ci,
    }


def _write_fixture(path) -> None:
    path.write_text(json.dumps([{"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]), encoding="utf-8")


def _names(result) -> list[str]:
    return [sample.name for sample in result.selected_samples]


def test_required_full_selects_btc_full_gate_samples(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    registry = tmp_path / "registry.json"
    _registry(registry)

    result = ValidationSampleScopeEngine(repo_root=tmp_path).select(str(registry), "required_full")

    assert _names(result) == ["btcusdt_15m_1000", "btcusdt_1h_1000"]
    assert {sample.name for sample in result.excluded_samples} == {"ethusdt_15m_1000", "ethusdt_1h_1000"}


def test_required_ci_selects_only_ci_required_samples(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    registry = tmp_path / "registry.json"
    _registry(registry)

    result = ValidationSampleScopeEngine(repo_root=tmp_path).select(str(registry), "required_ci")

    assert _names(result) == ["btcusdt_15m_1000"]


def test_btc_only_selects_all_btc_samples(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    registry = tmp_path / "registry.json"
    _registry(registry)

    result = ValidationSampleScopeEngine(repo_root=tmp_path).select(str(registry), "btc_only")

    assert _names(result) == ["btcusdt_15m_1000", "btcusdt_1h_1000"]


def test_all_registry_selects_all_samples(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    registry = tmp_path / "registry.json"
    _registry(registry)

    result = ValidationSampleScopeEngine(repo_root=tmp_path).select(str(registry), "all_registry")

    assert _names(result) == ["btcusdt_15m_1000", "btcusdt_1h_1000", "ethusdt_15m_1000", "ethusdt_1h_1000"]


def test_all_available_selects_available_samples(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("btcusdt_15m_1000", "ethusdt_15m_1000"):
        _write_fixture(tmp_path / f"{name}.json")
    registry = tmp_path / "registry.json"
    _registry(registry, available={"btcusdt_15m_1000", "ethusdt_15m_1000"})

    result = ValidationSampleScopeEngine(repo_root=tmp_path).select(str(registry), "all_available")

    assert _names(result) == ["btcusdt_15m_1000", "ethusdt_15m_1000"]


def test_explicit_sample_names_select_requested_samples(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    registry = tmp_path / "registry.json"
    _registry(registry)

    result = ValidationSampleScopeEngine(repo_root=tmp_path).select(str(registry), "all_registry", ["ethusdt_1h_1000"])

    assert result.sample_scope == "explicit"
    assert _names(result) == ["ethusdt_1h_1000"]


def test_unknown_explicit_sample_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    registry = tmp_path / "registry.json"
    _registry(registry)

    with pytest.raises(ValueError, match="historical sample not found"):
        ValidationSampleScopeEngine(repo_root=tmp_path).select(str(registry), "all_registry", ["missing"])
