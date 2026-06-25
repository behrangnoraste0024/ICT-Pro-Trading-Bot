class BOSDetector:

    def detect(self, swings):

        previous_high = None
        previous_low = None

        for swing in swings:

            if swing.swing_type == "HIGH":

                if previous_high is not None:

                    if swing.price > previous_high.price:

                        previous_high.broken = True
                        previous_high.bos = True

                previous_high = swing

            else:

                if previous_low is not None:

                    if swing.price < previous_low.price:

                        previous_low.broken = True
                        previous_low.bos = True

                previous_low = swing

        return swings