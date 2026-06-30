from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data.historical_data_utils import describe_candles
from data.historical_data_utils import normalize_ohlcv_rows
from data.historical_data_utils import save_candles_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download historical OHLCV data to a JSON fixture.")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    if args.limit <= 0:
        print("Error: --limit must be greater than 0.")
        return 1

    output_path = args.output or _default_output_path(args.symbol, args.timeframe, args.limit)

    try:
        rows = fetch_ohlcv_from_exchange(args.exchange, args.symbol, args.timeframe, args.limit)
        records = normalize_ohlcv_rows(rows)
        save_candles_json(records, output_path)
        description = describe_candles(records)
    except Exception as exc:
        print(f"Error: historical data download failed: {exc}")
        return 1

    print("===== HISTORICAL DATA DOWNLOAD =====")
    print(f"Exchange  : {args.exchange}")
    print(f"Symbol    : {args.symbol}")
    print(f"Timeframe : {args.timeframe}")
    print(f"Limit     : {args.limit}")
    print(f"Saved To  : {output_path}")
    print(f"Candles   : {description['count']}")
    print(f"First TS  : {description['first_timestamp']}")
    print(f"Last TS   : {description['last_timestamp']}")
    return 0


def fetch_ohlcv_from_exchange(exchange_name: str, symbol: str, timeframe: str, limit: int) -> list:
    import ccxt

    exchange_class = getattr(ccxt, exchange_name)
    exchange = exchange_class({"enableRateLimit": True, "timeout": 30000})
    return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)


def _default_output_path(symbol: str, timeframe: str, limit: int) -> str:
    symbol_normalized = "".join(character.lower() for character in symbol if character.isalnum())
    return f"data/historical/{symbol_normalized}_{timeframe}_{limit}.json"


if __name__ == "__main__":
    raise SystemExit(main())
