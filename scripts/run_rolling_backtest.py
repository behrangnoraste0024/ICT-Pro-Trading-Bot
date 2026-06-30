from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.rolling_backtest.rolling_backtest_engine import RollingBacktestEngine
from reporting.rolling_backtest_report import format_rolling_backtest_report


DEFAULT_FIXTURE = "tests/fixtures/btcusdt_100_candles.json"
REQUIRED_COLUMNS = {"open", "high", "low", "close"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic rolling backtest from a candle fixture.")
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--min-candles", type=int, default=50)
    args = parser.parse_args(argv)

    if args.min_candles <= 0:
        print("Error: --min-candles must be greater than 0.")
        return 1

    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        print(f"Error: fixture not found: {fixture_path}")
        return 1

    try:
        candles = pd.read_json(fixture_path)
    except Exception as exc:
        print(f"Error: failed to load fixture: {exc}")
        return 1

    missing_columns = REQUIRED_COLUMNS.difference(candles.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        print(f"Error: fixture missing required columns: {missing}")
        return 1

    result = RollingBacktestEngine(min_candles=args.min_candles).run(candles)
    report = format_rolling_backtest_report(result, str(fixture_path), args.min_candles)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
