from models.swing_point import SwingPoint


class SwingDetector:

    def __init__(self, left=3, right=3):
        self.left = left
        self.right = right

    def detect(self, df):

        swings = []

        highs = df["high"].tolist()
        lows = df["low"].tolist()

        for i in range(self.left, len(df) - self.right):

            # -------------------------
            # Swing High
            # -------------------------

            current_high = highs[i]

            is_high = True

            for j in range(i - self.left, i + self.right + 1):

                if j == i:
                    continue

                if highs[j] >= current_high:
                    is_high = False
                    break

            if is_high:

                swings.append(
                    SwingPoint(
                        index=i,
                        price=float(current_high),
                        swing_type="HIGH"
                    )
                )

            # -------------------------
            # Swing Low
            # -------------------------

            current_low = lows[i]

            is_low = True

            for j in range(i - self.left, i + self.right + 1):

                if j == i:
                    continue

                if lows[j] <= current_low:
                    is_low = False
                    break

            if is_low:

                swings.append(
                    SwingPoint(
                        index=i,
                        price=float(current_low),
                        swing_type="LOW"
                    )
                )

        # --------------------------------
        # Sort by candle index
        # --------------------------------

        swings.sort(key=lambda s: s.index)

        # --------------------------------
        # Remove consecutive duplicate highs/lows
        # Keep only the strongest one
        # --------------------------------

        filtered = []

        for swing in swings:

            if not filtered:

                filtered.append(swing)
                continue

            last = filtered[-1]

            if last.swing_type != swing.swing_type:

                filtered.append(swing)
                continue

            if swing.swing_type == "HIGH":

                if swing.price > last.price:
                    filtered[-1] = swing

            else:

                if swing.price < last.price:
                    filtered[-1] = swing

        return filtered