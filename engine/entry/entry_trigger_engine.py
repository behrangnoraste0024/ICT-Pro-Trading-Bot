from __future__ import annotations

from models.entry_trigger_event import EntryTriggerEvent
from models.market_context import MarketContext


class EntryTriggerEngine:
    def __init__(
        self,
        displacement_lookback: int = 10,
        displacement_multiplier: float = 1.5,
        wick_ratio_limit: float = 0.25,
    ):
        self.displacement_lookback = displacement_lookback
        self.displacement_multiplier = displacement_multiplier
        self.wick_ratio_limit = wick_ratio_limit

    def detect(self, context: MarketContext) -> MarketContext:
        self._reset_context(context)

        blockers: list[str] = []

        if not self._has_valid_setup(context):
            blockers.append("NO_VALID_SETUP")
            self._mark_not_confirmed(context, blockers)
            return context

        if not self._has_matched_poi(context):
            blockers.append("NO_MATCHED_POI")
            self._mark_not_confirmed(context, blockers)
            return context

        candles = context.candles
        if candles is None or len(candles) < 2:
            blockers.append("NOT_ENOUGH_CANDLES")
            self._mark_not_confirmed(context, blockers)
            return context

        direction = context.setup_bias
        confirmation = self._has_confirmation_candle(candles, direction)
        displacement = self._has_displacement_candle(candles, direction)

        if displacement:
            self._mark_confirmed(context, direction, "DISPLACEMENT", ["DISPLACEMENT"])
            return context

        if confirmation:
            self._mark_confirmed(context, direction, "CONFIRMATION_CANDLE", ["CONFIRMATION_CANDLE"])
            return context

        blockers.append("NO_CONFIRMATION_CANDLE_OR_DISPLACEMENT")
        self._mark_not_confirmed(context, blockers)
        return context

    def _reset_context(self, context: MarketContext) -> None:
        context.entry_trigger = None
        context.entry_status = "NOT_CONFIRMED"
        context.entry_direction = "NONE"
        context.entry_trigger_type = "NONE"
        context.entry_confirmed = False
        context.entry_blockers = []

    def _has_valid_setup(self, context: MarketContext) -> bool:
        return (
            context.setup_status == "VALID"
            and context.active_setup is not None
            and context.setup_bias in ("BULLISH", "BEARISH")
        )

    def _has_matched_poi(self, context: MarketContext) -> bool:
        matched_pois = getattr(context.active_setup, "matched_pois", None)
        return bool(matched_pois)

    def _has_confirmation_candle(self, candles, direction: str) -> bool:
        current = candles.iloc[-1]
        previous = candles.iloc[-2]

        current_open = float(current["open"])
        current_close = float(current["close"])

        if direction == "BULLISH":
            return current_close > current_open and current_close > float(previous["high"])

        return current_close < current_open and current_close < float(previous["low"])

    def _has_displacement_candle(self, candles, direction: str) -> bool:
        if len(candles) < self.displacement_lookback + 1:
            return False

        current = candles.iloc[-1]
        previous_candles = candles.iloc[-self.displacement_lookback - 1:-1]

        current_open = float(current["open"])
        current_high = float(current["high"])
        current_low = float(current["low"])
        current_close = float(current["close"])
        candle_range = current_high - current_low

        if candle_range <= 0:
            return False

        body_size = abs(current_close - current_open)
        avg_body_size = (
            previous_candles["close"].astype(float) - previous_candles["open"].astype(float)
        ).abs().mean()

        if body_size < avg_body_size * self.displacement_multiplier:
            return False

        if direction == "BULLISH":
            upper_wick = current_high - current_close
            return current_close > current_open and upper_wick <= candle_range * self.wick_ratio_limit

        lower_wick = current_close - current_low
        return current_close < current_open and lower_wick <= candle_range * self.wick_ratio_limit

    def _mark_confirmed(
        self,
        context: MarketContext,
        direction: str,
        trigger_type: str,
        reasons: list[str],
    ) -> None:
        current = context.candles.iloc[-1]
        event = EntryTriggerEvent(
            direction=direction,
            status="CONFIRMED",
            trigger_type=trigger_type,
            confirmed=True,
            candle_index=len(context.candles) - 1,
            current_price=float(current["close"]),
            reasons=reasons,
            blockers=[],
        )

        context.entry_trigger = event
        context.entry_status = "CONFIRMED"
        context.entry_direction = direction
        context.entry_trigger_type = trigger_type
        context.entry_confirmed = True
        context.entry_blockers = []
        self._update_debug(context)

    def _mark_not_confirmed(self, context: MarketContext, blockers: list[str]) -> None:
        context.entry_trigger = None
        context.entry_status = "NOT_CONFIRMED"
        context.entry_direction = "NONE"
        context.entry_trigger_type = "NONE"
        context.entry_confirmed = False
        context.entry_blockers = blockers
        self._update_debug(context)

    def _update_debug(self, context: MarketContext) -> None:
        if not hasattr(context, "debug") or context.debug is None:
            return

        context.debug["entry_status"] = context.entry_status
        context.debug["entry_direction"] = context.entry_direction
        context.debug["entry_trigger_type"] = context.entry_trigger_type
        context.debug["entry_confirmed"] = context.entry_confirmed
        context.debug["entry_blockers"] = context.entry_blockers
