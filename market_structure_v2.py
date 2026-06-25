class MarketStructure:

    def __init__(self):
        self.last_high = None
        self.last_low = None

    def analyze(self, swing_type, price):

        if swing_type == "HIGH":

            if self.last_high is None:
                self.last_high = price
                return "FIRST HIGH"

            if price > self.last_high:
                self.last_high = price
                return "HH"     # Higher High

            else:
                self.last_high = price
                return "LH"     # Lower High


        if swing_type == "LOW":

            if self.last_low is None:
                self.last_low = price
                return "FIRST LOW"

            if price > self.last_low:
                self.last_low = price
                return "HL"     # Higher Low

            else:
                self.last_low = price
                return "LL"     # Lower Low