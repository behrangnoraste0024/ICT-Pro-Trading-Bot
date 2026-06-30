from __future__ import annotations

from models.market_context import MarketContext
from models.ote_zone import OTEZone


class OTEEngine:
    def detect(self, context: MarketContext) -> MarketContext:
        context.ote = None
        context.ote_direction = "NONE"
        context.ote_lower_bound = None
        context.ote_upper_bound = None
        context.ote_level_62 = None
        context.ote_level_705 = None
        context.ote_level_79 = None
        context.in_ote_zone = False

        if not self._has_valid_range(context) or context.trend not in ("UPTREND", "DOWNTREND"):
            self._update_debug(context)
            return context

        range_size = context.dealing_range_high - context.dealing_range_low
        current_price = context.current_price

        if context.trend == "UPTREND":
            level_62 = context.dealing_range_high - range_size * 0.62
            level_705 = context.dealing_range_high - range_size * 0.705
            level_79 = context.dealing_range_high - range_size * 0.79
            lower_bound = level_79
            upper_bound = level_62
            direction = "BULLISH"
        else:
            level_62 = context.dealing_range_low + range_size * 0.62
            level_705 = context.dealing_range_low + range_size * 0.705
            level_79 = context.dealing_range_low + range_size * 0.79
            lower_bound = level_62
            upper_bound = level_79
            direction = "BEARISH"

        in_zone = False
        if current_price is not None:
            in_zone = lower_bound <= current_price <= upper_bound

        context.ote = OTEZone(
            direction=direction,
            dealing_range_high=context.dealing_range_high,
            dealing_range_low=context.dealing_range_low,
            level_62=level_62,
            level_705=level_705,
            level_79=level_79,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            current_price=current_price,
            in_zone=in_zone,
        )
        context.ote_direction = direction
        context.ote_lower_bound = lower_bound
        context.ote_upper_bound = upper_bound
        context.ote_level_62 = level_62
        context.ote_level_705 = level_705
        context.ote_level_79 = level_79
        context.in_ote_zone = in_zone

        self._update_debug(context)
        return context

    def _has_valid_range(self, context: MarketContext) -> bool:
        return (
            context.dealing_range_high is not None
            and context.dealing_range_low is not None
            and context.dealing_range_high > context.dealing_range_low
        )

    def _update_debug(self, context: MarketContext) -> None:
        if not hasattr(context, "debug") or context.debug is None:
            return

        context.debug["ote_direction"] = context.ote_direction
        context.debug["ote_lower_bound"] = context.ote_lower_bound
        context.debug["ote_upper_bound"] = context.ote_upper_bound
        context.debug["ote_level_62"] = context.ote_level_62
        context.debug["ote_level_705"] = context.ote_level_705
        context.debug["ote_level_79"] = context.ote_level_79
        context.debug["in_ote_zone"] = context.in_ote_zone
