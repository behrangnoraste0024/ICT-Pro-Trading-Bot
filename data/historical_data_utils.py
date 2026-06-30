from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def normalize_ohlcv_rows(rows: list) -> list[dict]:
    records: list[dict] = []

    for row in rows:
        if len(row) < 6:
            raise ValueError("OHLCV row must contain timestamp, open, high, low, close, volume")

        records.append(
            {
                "timestamp": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
        )

    return records


def validate_candle_records(records: list[dict]) -> None:
    if not records:
        raise ValueError("Candle records must not be empty")

    previous_timestamp = None

    for index, record in enumerate(records):
        for key in REQUIRED_COLUMNS:
            if key not in record:
                raise ValueError(f"Candle record {index} missing required key: {key}")

        timestamp = record["timestamp"]
        if previous_timestamp is not None and timestamp < previous_timestamp:
            raise ValueError("Candle timestamps must be non-decreasing")
        previous_timestamp = timestamp

        open_price = _numeric(record["open"], "open", index)
        high_price = _numeric(record["high"], "high", index)
        low_price = _numeric(record["low"], "low", index)
        _numeric(record["close"], "close", index)
        _numeric(record["volume"], "volume", index)

        if high_price < low_price:
            raise ValueError(f"Candle record {index} has high lower than low")


def save_candles_json(records: list[dict], output_path: str | Path) -> None:
    validate_candle_records(records)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2), encoding="utf-8")


def load_candles_json(path: str | Path) -> pd.DataFrame:
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_candle_records(records)
    return pd.DataFrame(records, columns=REQUIRED_COLUMNS)


def describe_candles(records_or_dataframe: Any) -> dict:
    if isinstance(records_or_dataframe, pd.DataFrame):
        records = records_or_dataframe.to_dict("records")
    else:
        records = records_or_dataframe

    validate_candle_records(records)

    return {
        "count": len(records),
        "first_timestamp": records[0]["timestamp"],
        "last_timestamp": records[-1]["timestamp"],
        "first_close": float(records[0]["close"]),
        "last_close": float(records[-1]["close"]),
    }


def _numeric(value, field_name: str, index: int) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Candle record {index} has non-numeric {field_name}") from exc
