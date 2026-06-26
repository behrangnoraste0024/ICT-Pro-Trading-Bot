from models.bos_event import BOSEvent


class CHOCHDetector:

    def detect(self, context):

        if len(context.swings) < 4:
            return context

        trend = context.trend

        swings = context.swings

        for i in range(1, len(swings)):

            current = swings[i]
            previous = swings[i - 1]

            # -------- Bearish CHOCH --------

            if trend == "UPTREND":

                if (
                    previous.swing_type == "LOW"
                    and current.swing_type == "LOW"
                    and current.price < previous.price
                ):

                    current.choch = True

                    context.bos.append(
                        BOSEvent(
                            candle_index=current.index,
                            level=current.price,
                            direction="Bearish",
                            event_type="CHOCH"
                        )
                    )

            # -------- Bullish CHOCH --------

            elif trend == "DOWNTREND":

                if (
                    previous.swing_type == "HIGH"
                    and current.swing_type == "HIGH"
                    and current.price > previous.price
                ):

                    current.choch = True

                    context.bos.append(
                        BOSEvent(
                            candle_index=current.index,
                            level=current.price,
                            direction="Bullish",
                            event_type="CHOCH"
                        )
                    )

        return context