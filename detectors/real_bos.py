from models.bos_event import BOSEvent


class RealBOSDetector:

    def detect(self, context):

        df = context.candles

        highs = [
            s for s in context.swings
            if s.swing_type == "HIGH"
        ]

        lows = [
            s for s in context.swings
            if s.swing_type == "LOW"
        ]

        # -------------------------
        # Bullish BOS
        # -------------------------

        if highs:

            last_high = highs[-1]

            for i in range(last_high.index + 1, len(df)):

                if df["close"].iloc[i] > last_high.price:

                    context.bos.append(

                        BOSEvent(
                            candle_index=i,
                            level=last_high.price,
                            direction="BULLISH",
                            event_type="BOS"
                        )

                    )

                    break

        # -------------------------
        # Bearish BOS
        # -------------------------

        if lows:

            last_low = lows[-1]

            for i in range(last_low.index + 1, len(df)):

                if df["close"].iloc[i] < last_low.price:

                    context.bos.append(

                        BOSEvent(
                            candle_index=i,
                            level=last_low.price,
                            direction="BEARISH",
                            event_type="BOS"
                        )

                    )

                    break

        return context