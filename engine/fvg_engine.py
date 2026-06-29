from __future__ import annotations

from models.fvg_event import FVGEvent
from models.market_context import MarketContext


class FVGEngine:
    def detect(self, context: MarketContext) -> MarketContext:
        context.fvgs = []

        candles = context.candles
        if candles is None or len(candles) < 3:
            return context

        for index in range(2, len(candles)):
            start_index = index - 2
            middle_index = index - 1

            start_high = float(candles["high"].iloc[start_index])
            start_low = float(candles["low"].iloc[start_index])
            end_high = float(candles["high"].iloc[index])
            end_low = float(candles["low"].iloc[index])

            if start_high < end_low:
                context.fvgs.append(
                    FVGEvent(
                        index=index,
                        start_index=start_index,
                        middle_index=middle_index,
                        end_index=index,
                        direction="BULLISH",
                        lower_bound=float(start_high),
                        upper_bound=float(end_low),
                    )
                )
                continue

            if start_low > end_high:
                context.fvgs.append(
                    FVGEvent(
                        index=index,
                        start_index=start_index,
                        middle_index=middle_index,
                        end_index=index,
                        direction="BEARISH",
                        lower_bound=float(end_high),
                        upper_bound=float(start_low),
                    )
                )

        return context
