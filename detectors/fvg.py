class FairValueGap:

    def bullish_fvg(self, candle1_high, candle2_low):
        if candle2_low > candle1_high:
            return True
        return False

    def bearish_fvg(self, candle1_low, candle2_high):
        if candle2_high < candle1_low:
            return True
        return False