from __future__ import annotations

from models.breaker_block_event import BreakerBlockEvent
from models.market_context import MarketContext
from models.order_block_event import OrderBlockEvent


class BreakerBlockEngine:
    def detect(self, context: MarketContext) -> MarketContext:
        context.breaker_blocks = []

        candles = context.candles
        if candles is None:
            self._update_debug(context)
            return context

        seen_breakers: set[tuple[int, int]] = set()

        for order_block in context.order_blocks:
            if getattr(order_block, "invalidated", False):
                continue

            breaker = self._detect_breaker_for_order_block(context, order_block, candles, seen_breakers)
            if breaker is not None:
                context.breaker_blocks.append(breaker)

        self._update_debug(context)
        return context

    def _detect_breaker_for_order_block(
        self,
        context: MarketContext,
        order_block: OrderBlockEvent,
        candles,
        seen_breakers: set[tuple[int, int]],
    ) -> BreakerBlockEvent | None:
        for candle_index in range(order_block.trigger_index + 1, len(candles)):
            close = float(candles["close"].iloc[candle_index])

            if order_block.direction == "BULLISH" and close < order_block.lower_bound:
                key = (order_block.index, candle_index)
                if key in seen_breakers:
                    return None

                seen_breakers.add(key)
                self._invalidate_order_block(order_block, candle_index)
                return BreakerBlockEvent(
                    index=candle_index,
                    source_order_block_index=order_block.index,
                    source_trigger_index=order_block.trigger_index,
                    invalidation_index=candle_index,
                    direction="BEARISH",
                    original_order_block_direction="BULLISH",
                    lower_bound=order_block.lower_bound,
                    upper_bound=order_block.upper_bound,
                    source_event_type=order_block.source_event_type,
                )

            if order_block.direction == "BEARISH" and close > order_block.upper_bound:
                key = (order_block.index, candle_index)
                if key in seen_breakers:
                    return None

                seen_breakers.add(key)
                self._invalidate_order_block(order_block, candle_index)
                return BreakerBlockEvent(
                    index=candle_index,
                    source_order_block_index=order_block.index,
                    source_trigger_index=order_block.trigger_index,
                    invalidation_index=candle_index,
                    direction="BULLISH",
                    original_order_block_direction="BEARISH",
                    lower_bound=order_block.lower_bound,
                    upper_bound=order_block.upper_bound,
                    source_event_type=order_block.source_event_type,
                )

        return None

    def _invalidate_order_block(self, order_block: OrderBlockEvent, invalidation_index: int) -> None:
        order_block.invalidated = True
        order_block.invalidation_index = invalidation_index
        order_block.active = False

    def _update_debug(self, context: MarketContext) -> None:
        if not hasattr(context, "debug") or context.debug is None:
            return

        context.debug["breaker_blocks_total"] = len(context.breaker_blocks)
        context.debug["bullish_breaker_blocks"] = sum(
            1 for block in context.breaker_blocks if block.direction == "BULLISH"
        )
        context.debug["bearish_breaker_blocks"] = sum(
            1 for block in context.breaker_blocks if block.direction == "BEARISH"
        )
        context.debug["invalidated_order_blocks"] = sum(
            1 for block in context.order_blocks if getattr(block, "invalidated", False)
        )
