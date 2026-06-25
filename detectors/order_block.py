class OrderBlock:

    def bullish_ob(self, open_price, close_price):
        if close_price < open_price:
            return True
        return False

    def bearish_ob(self, open_price, close_price):
        if close_price > open_price:
            return True
        return False