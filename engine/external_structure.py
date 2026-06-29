class ExternalStructure:

    def build(self, context):

        highs = [
            s for s in context.swings
            if s.swing_type == "HIGH"
        ]

        lows = [
            s for s in context.swings
            if s.swing_type == "LOW"
        ]

        if highs:
            context.external_high = max(
                highs,
                key=lambda x: x.price
            ).price

        if lows:
            context.external_low = min(
                lows,
                key=lambda x: x.price
            ).price

        return context