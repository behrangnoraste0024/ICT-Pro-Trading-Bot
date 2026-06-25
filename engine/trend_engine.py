class TrendEngine:

    def detect(self, swings):

        highs = []
        lows = []

        for swing in swings:

            if swing.swing_type == "HIGH":
                highs.append(swing)

            else:
                lows.append(swing)

        if len(highs) < 2 or len(lows) < 2:
            return "UNKNOWN"

        last_high = highs[-1]
        prev_high = highs[-2]

        last_low = lows[-1]
        prev_low = lows[-2]

        if last_high.price > prev_high.price and last_low.price > prev_low.price:
            return "UPTREND"

        if last_high.price < prev_high.price and last_low.price < prev_low.price:
            return "DOWNTREND"

        return "RANGE"