from __future__ import annotations

from models.market_context import MarketContext


class PremiumDiscountEngine:
    def detect(self, context: MarketContext) -> MarketContext:
        candles = context.candles
        current_price = None
        if candles is not None and len(candles) > 0 and "close" in candles:
            current_price = float(candles["close"].iloc[-1])

        context.dealing_range_high = context.external_high
        context.dealing_range_low = context.external_low
        context.current_price = current_price
        context.current_price_zone = "UNKNOWN"
        context.equilibrium = None
        context.premium_zone = None
        context.discount_zone = None

        if (
            context.dealing_range_high is None
            or context.dealing_range_low is None
            or context.dealing_range_high <= context.dealing_range_low
        ):
            self._update_debug(context)
            return context

        context.equilibrium = (context.dealing_range_high + context.dealing_range_low) / 2
        context.premium_zone = {
            "lower_bound": context.equilibrium,
            "upper_bound": context.dealing_range_high,
        }
        context.discount_zone = {
            "lower_bound": context.dealing_range_low,
            "upper_bound": context.equilibrium,
        }

        if current_price is not None:
            if current_price > context.equilibrium:
                context.current_price_zone = "PREMIUM"
            elif current_price < context.equilibrium:
                context.current_price_zone = "DISCOUNT"
            else:
                context.current_price_zone = "EQUILIBRIUM"

        self._update_debug(context)
        return context

    def _update_debug(self, context: MarketContext) -> None:
        if not hasattr(context, "debug") or context.debug is None:
            return

        context.debug["dealing_range_high"] = context.dealing_range_high
        context.debug["dealing_range_low"] = context.dealing_range_low
        context.debug["equilibrium"] = context.equilibrium
        context.debug["current_price"] = context.current_price
        context.debug["current_price_zone"] = context.current_price_zone
