from __future__ import annotations

from models.market_context import MarketContext
from models.setup_event import SetupEvent


class SetupEngine:
    def __init__(self, lookback: int = 30):
        self.lookback = lookback

    def detect(self, context: MarketContext) -> MarketContext:
        bullish = self._evaluate_direction(context, "BULLISH")
        bearish = self._evaluate_direction(context, "BEARISH")

        context.setups = [bullish, bearish]

        valid_setups = [setup for setup in context.setups if setup.status == "VALID"]

        if len(valid_setups) == 1:
            setup = valid_setups[0]
            context.active_setup = setup
            context.setup_bias = setup.direction
            context.setup_score = setup.score
            context.setup_status = "VALID"
            context.setup_blockers = []
        elif len(valid_setups) > 1:
            context.active_setup = None
            context.setup_bias = "CONFLICT"
            context.setup_score = max(setup.score for setup in context.setups)
            context.setup_status = "INVALID"
            context.setup_blockers = ["CONFLICTING_SETUPS"]
        else:
            best_setup = max(context.setups, key=lambda setup: setup.score, default=None)
            context.active_setup = None
            context.setup_bias = "NONE"
            context.setup_score = best_setup.score if best_setup else 0
            context.setup_status = "INVALID"
            context.setup_blockers = list(best_setup.blockers) if best_setup else []

        self._update_debug(context)
        return context

    def _evaluate_direction(self, context: MarketContext, direction: str) -> SetupEvent:
        expected_trend = "UPTREND" if direction == "BULLISH" else "DOWNTREND"
        expected_zone = "DISCOUNT" if direction == "BULLISH" else "PREMIUM"
        required_sweep = "SELL_SIDE" if direction == "BULLISH" else "BUY_SIDE"

        score = 0
        reasons: list[str] = []
        blockers: list[str] = []

        if context.trend == expected_trend:
            score += 20
            reasons.append("TREND_ALIGNED")
        else:
            blockers.append("WRONG_TREND")

        if context.current_price_zone == expected_zone:
            score += 15
            reasons.append("CORRECT_PRICE_ZONE")
        else:
            blockers.append("WRONG_PRICE_ZONE")

        if context.ote_direction == direction:
            score += 15
            reasons.append("OTE_ALIGNED")
        else:
            blockers.append("OTE_NOT_ALIGNED")

        if context.in_ote_zone is True:
            score += 20
            reasons.append("PRICE_IN_OTE")
        else:
            blockers.append("PRICE_NOT_IN_OTE")

        if self._has_recent_liquidity_sweep(context, required_sweep):
            score += 15
            reasons.append("RECENT_LIQUIDITY_SWEEP")
        else:
            blockers.append("NO_RECENT_LIQUIDITY_SWEEP")

        matched_pois = self._matched_pois(context, direction)
        if matched_pois:
            score += 15
            reasons.append("ACTIVE_POI_AT_PRICE")
        else:
            blockers.append("NO_ACTIVE_POI_AT_PRICE")

        status = "VALID" if not blockers else "INVALID"

        return SetupEvent(
            direction=direction,
            status=status,
            score=score,
            reasons=reasons,
            blockers=blockers,
            current_price=context.current_price,
            price_zone=context.current_price_zone,
            trend=context.trend,
            ote_direction=context.ote_direction,
            in_ote_zone=context.in_ote_zone,
            matched_pois=matched_pois,
        )

    def _has_recent_liquidity_sweep(self, context: MarketContext, direction: str) -> bool:
        candles = context.candles
        if candles is None or len(candles) == 0:
            return False

        current_index = len(candles) - 1
        first_valid_index = current_index - self.lookback

        for sweep in context.liquidity_sweeps:
            if getattr(sweep, "direction", None) != direction:
                continue

            sweep_index = self._event_index(sweep)
            if sweep_index is None:
                continue

            if first_valid_index <= sweep_index <= current_index:
                return True

        return False

    def _event_index(self, event) -> int | None:
        for field_name in ("candle_index", "index", "sweep_index"):
            value = getattr(event, field_name, None)
            if value is not None:
                return int(value)

        return None

    def _matched_pois(self, context: MarketContext, direction: str) -> list[str]:
        current_price = context.current_price
        if current_price is None:
            return []

        matches: list[str] = []

        for poi in list(context.fvgs) + list(context.order_blocks) + list(context.breaker_blocks):
            if not self._is_valid_poi(poi, direction, current_price):
                continue

            event_type = getattr(poi, "event_type", poi.__class__.__name__)
            poi_index = getattr(poi, "index", getattr(poi, "trigger_index", "UNKNOWN"))
            matches.append(f"{event_type}:{direction}:{poi_index}")

        return matches

    def _is_valid_poi(self, poi, direction: str, current_price: float) -> bool:
        if getattr(poi, "direction", None) != direction:
            return False

        if getattr(poi, "active", False) is not True:
            return False

        if getattr(poi, "event_type", "") == "ORDER_BLOCK" and getattr(poi, "invalidated", False):
            return False

        lower_bound = getattr(poi, "lower_bound", None)
        upper_bound = getattr(poi, "upper_bound", None)
        if lower_bound is None or upper_bound is None:
            return False

        return float(lower_bound) <= current_price <= float(upper_bound)

    def _update_debug(self, context: MarketContext) -> None:
        if not hasattr(context, "debug") or context.debug is None:
            return

        context.debug["setup_bias"] = context.setup_bias
        context.debug["setup_score"] = context.setup_score
        context.debug["setup_status"] = context.setup_status
        context.debug["setup_blockers"] = context.setup_blockers
