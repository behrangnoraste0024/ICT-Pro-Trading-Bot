class ICTStrategy:

    def __init__(self):
        self.trend = None

    def check_trend(self, close, ema200):
        if close > ema200:
            self.trend = "Bullish"
        else:
            self.trend = "Bearish"

        return self.trend