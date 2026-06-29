from models.bos_event import BOSEvent


class BOSDetector:

    def detect(self, context):

        df = context.candles
        swings = context.swings

        if len(swings) < 2:
            return context

        context.bos = []

        for swing in swings:

            # -----------------------------
            # Bullish BOS
            # -----------------------------

            if swing.swing_type == "HIGH":

                for i in range(swing.index + 1, len(df)):

                    close = df["close"].iloc[i]

                    if close > swing.price:

                        context.bos.append(

                            BOSEvent(
                                candle_index=i,
                                level=swing.price,
                                direction="BULLISH",
                                event_type="BOS"
                            )

                        )

                        swing.bos = True

                        break

            # -----------------------------
            # Bearish BOS
            # -----------------------------

            else:

                for i in range(swing.index + 1, len(df)):

                    close = df["close"].iloc[i]

                    if close < swing.price:

                        context.bos.append(

                            BOSEvent(
                                candle_index=i,
                                level=swing.price,
                                direction="BEARISH",
                                event_type="BOS"
                            )

                        )

                        swing.bos = True

                        break

        return context