class TrendEngine:

    def __init__(self):
        self.last_high = None
        self.last_low = None
        self.trend = "UNKNOWN"

    def update(self, swing_type, price):

        # پردازش Swing High
        if swing_type == "HIGH":

            if self.last_high is None:
                self.last_high = price
                return self.trend

            if price > self.last_high:
                self.last_high = price

                if self.trend != "UPTREND":
                    self.trend = "UPTREND"

                return self.trend

            self.last_high = price
            return self.trend

        # پردازش Swing Low
        if swing_type == "LOW":

            if self.last_low is None:
                self.last_low = price
                return self.trend

            if price < self.last_low:
                self.last_low = price

                if self.trend != "DOWNTREND":
                    self.trend = "DOWNTREND"

                return self.trend

            self.last_low = price
            return self.trend

        return self.trend