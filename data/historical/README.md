# Historical Data

Historical candle files in this folder are used for offline backtesting.

Download example:

```powershell
py scripts/download_historical_data.py --symbol BTC/USDT --timeframe 15m --limit 1000 --output data/historical/btcusdt_15m_1000.json
```

Rolling backtest example:

```powershell
py scripts/run_rolling_backtest.py --fixture data/historical/btcusdt_15m_1000.json --min-candles 50
```

Files are saved as JSON lists of records with these columns:

```text
timestamp
open
high
low
close
volume
```

Large historical files may be ignored later if repository size becomes an issue.
