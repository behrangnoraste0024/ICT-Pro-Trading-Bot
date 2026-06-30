from __future__ import annotations

from models.market_context import MarketContext


class DealingRangeModeEngine:
    VALID_MODES = {"current_external", "recent_50"}

    def apply(self, context: MarketContext, mode: str = "current_external") -> MarketContext:
        if mode not in self.VALID_MODES:
            raise ValueError(f"Unsupported dealing range mode: {mode}")

        context.dealing_range_mode_requested = mode
        if mode == "current_external":
            context.dealing_range_mode_applied = "current_external"
            context.dealing_range_mode_fallback_reason = None
            return context

        return self._apply_recent_50(context)

    def _apply_recent_50(self, context: MarketContext) -> MarketContext:
        candles = context.candles
        if candles is None or len(candles) < 50:
            return self._fallback(context, "INSUFFICIENT_CANDLES")

        recent = candles.iloc[-50:]
        try:
            recent_high = float(recent["high"].max())
            recent_low = float(recent["low"].min())
        except (KeyError, TypeError, ValueError):
            return self._fallback(context, "INVALID_RECENT_50_RANGE")

        if recent_high <= recent_low:
            return self._fallback(context, "INVALID_RECENT_50_RANGE")

        current_price = context.current_price
        if current_price is None:
            try:
                current_price = float(candles["close"].iloc[-1])
            except (KeyError, TypeError, ValueError):
                current_price = None

        context.dealing_range_high = recent_high
        context.dealing_range_low = recent_low
        context.external_high = recent_high
        context.external_low = recent_low
        context.equilibrium = (recent_high + recent_low) / 2
        context.current_price = current_price
        context.premium_zone = {"lower_bound": context.equilibrium, "upper_bound": recent_high}
        context.discount_zone = {"lower_bound": recent_low, "upper_bound": context.equilibrium}
        context.current_price_zone = self._price_zone(current_price, context.equilibrium)
        context.dealing_range_mode_requested = "recent_50"
        context.dealing_range_mode_applied = "recent_50"
        context.dealing_range_mode_fallback_reason = None
        self._update_debug(context)
        return context

    def _fallback(self, context: MarketContext, reason: str) -> MarketContext:
        context.dealing_range_mode_requested = "recent_50"
        context.dealing_range_mode_applied = "current_external"
        context.dealing_range_mode_fallback_reason = reason
        self._update_debug(context)
        return context

    def _price_zone(self, current_price: float | None, equilibrium: float) -> str:
        if current_price is None:
            return "UNKNOWN"
        if current_price > equilibrium:
            return "PREMIUM"
        if current_price < equilibrium:
            return "DISCOUNT"
        return "EQUILIBRIUM"

    def _update_debug(self, context: MarketContext) -> None:
        if not hasattr(context, "debug") or context.debug is None:
            return
        context.debug["dealing_range_mode_requested"] = getattr(context, "dealing_range_mode_requested", None)
        context.debug["dealing_range_mode_applied"] = getattr(context, "dealing_range_mode_applied", None)
        context.debug["dealing_range_mode_fallback_reason"] = getattr(
            context, "dealing_range_mode_fallback_reason", None
        )
