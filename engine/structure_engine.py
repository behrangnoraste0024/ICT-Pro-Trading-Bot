class StructureEngine:

    def build(self, context):

        swings = context.swings

        if len(swings) < 2:
            return context

        # -----------------------------
        # Label HH HL LH LL
        # -----------------------------

        last_high = None
        last_low = None

        for swing in swings:

            if swing.swing_type == "HIGH":

                if last_high is None:
                    swing.label = "HH"

                elif swing.price > last_high:
                    swing.label = "HH"

                else:
                    swing.label = "LH"

                last_high = swing.price

            else:

                if last_low is None:
                    swing.label = "HL"

                elif swing.price > last_low:
                    swing.label = "HL"

                else:
                    swing.label = "LL"

                last_low = swing.price

        # -----------------------------
        # External Structure
        # -----------------------------

        highs = [s.price for s in swings if s.swing_type == "HIGH"]
        lows = [s.price for s in swings if s.swing_type == "LOW"]

        if highs:
            context.external_high = max(highs)

        if lows:
            context.external_low = min(lows)

        # -----------------------------
        # Trend
        # -----------------------------

        hh = 0
        lh = 0
        hl = 0
        ll = 0

        for s in swings:

            if s.label == "HH":
                hh += 1

            elif s.label == "LH":
                lh += 1

            elif s.label == "HL":
                hl += 1

            elif s.label == "LL":
                ll += 1

        if hh + hl > lh + ll:
            context.trend = "UPTREND"

        elif ll + lh > hh + hl:
            context.trend = "DOWNTREND"

        else:
            context.trend = "RANGE"

        return context