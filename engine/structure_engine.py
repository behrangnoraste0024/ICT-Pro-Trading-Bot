class StructureEngine:

    def classify(self, context):

        swings = context.swings

        if len(swings) < 4:
            return context

        external_high = max(
            [s.price for s in swings if s.swing_type == "HIGH"]
        )

        external_low = min(
            [s.price for s in swings if s.swing_type == "LOW"]
        )

        context.external_high = external_high
        context.external_low = external_low

        return context