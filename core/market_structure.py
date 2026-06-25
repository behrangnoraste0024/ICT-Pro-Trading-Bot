class MarketStructure:

    def label_swings(self, swings):

        last_high = None
        last_low = None

        for swing in swings:

            if swing.swing_type == "HIGH":

                if last_high is None:
                    swing.label = "HH"
                else:
                    if swing.price > last_high:
                        swing.label = "HH"
                    else:
                        swing.label = "LH"

                last_high = swing.price

            elif swing.swing_type == "LOW":

                if last_low is None:
                    swing.label = "HL"
                else:
                    if swing.price > last_low:
                        swing.label = "HL"
                    else:
                        swing.label = "LL"

                last_low = swing.price

        return swings