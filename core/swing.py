from models.swing_point import SwingPoint


class SwingDetector:

    def __init__(self, left=2, right=2):
        self.left = left
        self.right = right

    def detect(self, df):

        swings = []

        highs = df["high"]
        lows = df["low"]

        for i in range(self.left, len(df) - self.right):

            # Swing High
            current_high = highs.iloc[i]

            is_high = True

            for j in range(i-self.left, i+self.right+1):

                if j == i:
                    continue

                if highs.iloc[j] >= current_high:
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

            # Swing Low
            current_low = lows.iloc[i]

            is_low = True

            for j in range(i-self.left, i+self.right+1):

                if j == i:
                    continue

                if lows.iloc[j] <= current_low:
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

        return swings