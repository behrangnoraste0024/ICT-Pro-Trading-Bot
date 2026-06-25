import ccxt
import pandas as pd


class DataLoader:

    def __init__(self):
        self.exchange = ccxt.binance()

    def load_data(self, symbol="BTC/USDT", timeframe="15m", limit=100):

        ohlcv = self.exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            limit=limit
        )

        df = pd.DataFrame(
            ohlcv,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume"
            ]
        )

        return df