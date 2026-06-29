from __future__ import annotations

from models.liquidity_event import LiquidityEvent
from models.market_context import MarketContext
from models.structure_event import StructureEvent


class LiquidityEngine:
    def detect(self, context: MarketContext) -> MarketContext:
        context.liquidity_sweeps = []
        context.liquidity = []

        candles = context.candles
        structure = context.structure

        if candles is None or not structure:
            return context

        for level in structure:
            if level.swing_type not in ("HIGH", "LOW"):
                continue

            if level.broken or level.swept:
                continue

            for candle_index in range(level.index + 1, len(candles)):
                high = float(candles["high"].iloc[candle_index])
                low = float(candles["low"].iloc[candle_index])
                close = float(candles["close"].iloc[candle_index])

                if level.swing_type == "HIGH" and high > level.price and close <= level.price:
                    self._mark_sweep(context, level, candle_index, "BUY_SIDE")
                    break

                if level.swing_type == "LOW" and low < level.price and close >= level.price:
                    self._mark_sweep(context, level, candle_index, "SELL_SIDE")
                    break

        return context

    def _mark_sweep(
        self,
        context: MarketContext,
        level: StructureEvent,
        candle_index: int,
        direction: str,
    ) -> None:
        level.swept = True
        level.liquidity = True
        level.liquidity_type = direction

        sweep = LiquidityEvent(
            candle_index=candle_index,
            level_index=level.index,
            level=level.price,
            direction=direction,
        )

        context.liquidity_sweeps.append(sweep)
        context.liquidity.append(sweep)
