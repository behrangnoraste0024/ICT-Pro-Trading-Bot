from __future__ import annotations

import pytest

from data.historical_data_utils import describe_candles
from data.historical_data_utils import load_candles_json
from data.historical_data_utils import normalize_ohlcv_rows
from data.historical_data_utils import save_candles_json
from data.historical_data_utils import validate_candle_records


def _records() -> list[dict]:
    return [
        {"timestamp": 1, "open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0, "volume": 10.0},
        {"timestamp": 2, "open": 105.0, "high": 115.0, "low": 95.0, "close": 108.0, "volume": 12.0},
    ]


def test_normalize_ccxt_rows() -> None:
    records = normalize_ohlcv_rows([[1, 100, 110, 90, 105, 10]])

    assert records == [
        {"timestamp": 1, "open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0, "volume": 10.0}
    ]


def test_validate_accepts_valid_records() -> None:
    validate_candle_records(_records())


def test_validate_rejects_empty_records() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        validate_candle_records([])


def test_validate_rejects_missing_key() -> None:
    records = _records()
    del records[0]["close"]

    with pytest.raises(ValueError, match="missing required key"):
        validate_candle_records(records)


def test_validate_rejects_high_lower_than_low() -> None:
    records = _records()
    records[0]["high"] = 80

    with pytest.raises(ValueError, match="high lower than low"):
        validate_candle_records(records)


def test_validate_rejects_decreasing_timestamps() -> None:
    records = _records()
    records[1]["timestamp"] = 0

    with pytest.raises(ValueError, match="non-decreasing"):
        validate_candle_records(records)


def test_save_and_load_json_round_trip(tmp_path) -> None:
    output_path = tmp_path / "candles.json"

    save_candles_json(_records(), output_path)
    df = load_candles_json(output_path)

    assert len(df) == 2
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]


def test_describe_candles_returns_expected_values() -> None:
    description = describe_candles(_records())

    assert description["count"] == 2
    assert description["first_timestamp"] == 1
    assert description["last_timestamp"] == 2
    assert description["first_close"] == 105.0
    assert description["last_close"] == 108.0
