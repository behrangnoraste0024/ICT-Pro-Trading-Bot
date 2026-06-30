from __future__ import annotations

from models.market_context import MarketContext
from models.order_block_event import OrderBlockEvent


class OrderBlockEngine:
    def detect(self, context: MarketContext) -> MarketContext:
        context.order_blocks = []

        candles = context.candles
        if candles is None:
            self._update_debug(context)
            return context

        seen_triggers: set[tuple[int, str]] = set()

        for trigger in list(context.bos) + list(context.choch):
            trigger_index = getattr(trigger, "candle_index", None)
            direction = getattr(trigger, "direction", "")
            source_event_type = getattr(trigger, "event_type", "")

            if trigger_index is None or direction not in ("BULLISH", "BEARISH"):
                continue

            dedupe_key = (int(trigger_index), direction)
            if dedupe_key in seen_triggers:
                continue

            block_index = self._find_order_block_index(candles, int(trigger_index), direction)
            if block_index is None:
                continue

            candle = candles.iloc[block_index]

            context.order_blocks.append(
                OrderBlockEvent(
                    index=int(block_index),
                    trigger_index=int(trigger_index),
                    direction=direction,
                    lower_bound=float(candle["low"]),
                    upper_bound=float(candle["high"]),
                    open=float(candle["open"]),
                    high=float(candle["high"]),
                    low=float(candle["low"]),
                    close=float(candle["close"]),
                    source_event_type=source_event_type,
                )
            )

            seen_triggers.add(dedupe_key)

        self._update_debug(context)
        return context

    def _find_order_block_index(self, candles, trigger_index: int, direction: str) -> int | None:
        for candle_index in range(trigger_index - 1, -1, -1):
            candle = candles.iloc[candle_index]
            open_price = float(candle["open"])
            close_price = float(candle["close"])

            if direction == "BULLISH" and close_price < open_price:
                return candle_index

            if direction == "BEARISH" and close_price > open_price:
                return candle_index

        return None

    def _update_debug(self, context: MarketContext) -> None:
        if not hasattr(context, "debug") or context.debug is None:
            return

        context.debug["order_blocks_total"] = len(context.order_blocks)
        context.debug["bullish_order_blocks"] = sum(
            1 for block in context.order_blocks if block.direction == "BULLISH"
        )
        context.debug["bearish_order_blocks"] = sum(
            1 for block in context.order_blocks if block.direction == "BEARISH"
        )
