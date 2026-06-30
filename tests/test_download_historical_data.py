from __future__ import annotations

import importlib

from scripts import download_historical_data


def _fake_rows() -> list[list]:
    return [
        [1, 100, 110, 90, 105, 10],
        [2, 105, 115, 95, 108, 12],
    ]


def test_main_success_with_mocked_fetch(monkeypatch, tmp_path) -> None:
    output_path = tmp_path / "candles.json"
    monkeypatch.setattr(download_historical_data, "fetch_ohlcv_from_exchange", lambda *args: _fake_rows())

    return_code = download_historical_data.main(
        ["--symbol", "BTC/USDT", "--timeframe", "15m", "--limit", "2", "--output", str(output_path)]
    )

    assert return_code == 0
    assert output_path.exists()


def test_main_invalid_limit() -> None:
    return_code = download_historical_data.main(["--limit", "0"])

    assert return_code == 1


def test_main_handles_fetch_failure(monkeypatch, tmp_path) -> None:
    def fail_fetch(*args):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(download_historical_data, "fetch_ohlcv_from_exchange", fail_fetch)

    return_code = download_historical_data.main(["--limit", "2", "--output", str(tmp_path / "candles.json")])

    assert return_code == 1


def test_default_output_path_is_generated() -> None:
    output_path = download_historical_data._default_output_path("BTC/USDT", "15m", 1000)

    assert output_path == "data/historical/btcusdt_15m_1000.json"


def test_import_safety() -> None:
    module = importlib.import_module("scripts.download_historical_data")

    assert hasattr(module, "main")


def test_no_live_network(monkeypatch, tmp_path) -> None:
    called = {"fetch": False}

    def fake_fetch(*args):
        called["fetch"] = True
        return _fake_rows()

    monkeypatch.setattr(download_historical_data, "fetch_ohlcv_from_exchange", fake_fetch)

    return_code = download_historical_data.main(["--limit", "2", "--output", str(tmp_path / "candles.json")])

    assert return_code == 0
    assert called["fetch"] is True
