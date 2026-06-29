from models.market_context import MarketContext


class StructureBuilder:

    """
    Builds market structure from detected swings.

    Responsible for:

    - HH
    - HL
    - LH
    - LL
    - External High
    - External Low
    """

    def build(self, context: MarketContext):

        swings = context.swings

        if len(swings) < 2:
            return context

        previous_high = None
        previous_low = None

        external_high = None
        external_low = None

        # ------------------------------------
        # Classify every swing
        # ------------------------------------

        for swing in swings:

            # ===============================
            # HIGH
            # ===============================

            if swing.swing_type == "HIGH":

                if previous_high is None:

                    swing.label = "HH"

                else:

                    if swing.price > previous_high.price:
                        swing.label = "HH"
                    else:
                        swing.label = "LH"

                previous_high = swing

            # ===============================
            # LOW
            # ===============================

            else:

                if previous_low is None:

                    swing.label = "HL"

                else:

                    if swing.price > previous_low.price:
                        swing.label = "HL"
                    else:
                        swing.label = "LL"

                previous_low = swing

        # ------------------------------------
        # External Structure
        # ------------------------------------

        highs = [s for s in swings if s.swing_type == "HIGH"]
        lows = [s for s in swings if s.swing_type == "LOW"]

        if highs:
            external_high = max(highs, key=lambda x: x.price).price

        if lows:
            external_low = min(lows, key=lambda x: x.price).price

        context.external_high = external_high
        context.external_low = external_low

        return context