class Liquidity:

    def sweep_high(self, high, equal_high):
        return high > equal_high

    def sweep_low(self, low, equal_low):
        return low < equal_low