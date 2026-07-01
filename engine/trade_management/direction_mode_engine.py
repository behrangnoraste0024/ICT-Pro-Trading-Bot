from __future__ import annotations

from models.market_context import MarketContext


class DirectionModeEngine:
    VALID_MODES = {"all", "long_only", "short_only", "auto_trend", "regime_trend"}
    VALID_AUTO_TREND_FALLBACKS = {"all", "block"}
    VALID_REGIME_FALLBACKS = {"all", "block"}

    def apply(
        self,
        context: MarketContext,
        direction_mode: str = "all",
        auto_trend_fallback: str = "all",
        regime_fallback: str = "all",
    ) -> MarketContext:
        self._reset_metadata(context, direction_mode, auto_trend_fallback, regime_fallback)

        if (
            direction_mode not in self.VALID_MODES
            or auto_trend_fallback not in self.VALID_AUTO_TREND_FALLBACKS
            or regime_fallback not in self.VALID_REGIME_FALLBACKS
        ):
            context.direction_mode_fallback_reason = "INVALID_DIRECTION"
            self._update_debug(context)
            return context

        context.direction_mode_applied = direction_mode

        if direction_mode == "all":
            context.direction_mode_allowed = True if context.trade_plan_status == "PLANNED" else None
            context.direction_mode_resolved_direction = "ALL"
            context.direction_mode_fallback_reason = "ALL_MODE"
            self._update_debug(context)
            return context

        if direction_mode == "auto_trend":
            return self._apply_auto_trend(context, auto_trend_fallback)

        if direction_mode == "regime_trend":
            return self._apply_regime_trend(context, regime_fallback)

        if context.trade_plan_status != "PLANNED":
            context.direction_mode_fallback_reason = "NO_PLANNED_TRADE"
            self._update_debug(context)
            return context

        direction = context.trade_direction
        if direction not in ("BULLISH", "BEARISH"):
            context.direction_mode_fallback_reason = "INVALID_DIRECTION"
            self._update_debug(context)
            return context

        allowed = self._is_allowed(direction, direction_mode)
        context.direction_mode_allowed = allowed
        if allowed:
            context.direction_mode_resolved_direction = "LONG" if direction_mode == "long_only" else "SHORT"
            context.direction_mode_fallback_reason = "NONE"
        else:
            context.direction_mode_blocked_direction = direction
            context.direction_mode_resolved_direction = "LONG" if direction_mode == "long_only" else "SHORT"
            context.direction_mode_fallback_reason = "DIRECTION_MODE_BLOCKED"

        self._update_debug(context)
        return context

    def _reset_metadata(
        self,
        context: MarketContext,
        direction_mode: str,
        auto_trend_fallback: str,
        regime_fallback: str,
    ) -> None:
        context.direction_mode_requested = direction_mode
        context.direction_mode_applied = None
        context.direction_mode_allowed = None
        context.direction_mode_blocked_direction = None
        context.direction_mode_fallback_reason = None
        context.direction_mode_resolved_direction = None
        context.auto_trend_source_trend = None
        context.auto_trend_fallback = auto_trend_fallback
        context.regime_source_regime = None
        context.regime_fallback = regime_fallback

    def _is_allowed(self, direction: str, direction_mode: str) -> bool:
        if direction_mode == "long_only":
            return direction == "BULLISH"
        if direction_mode == "short_only":
            return direction == "BEARISH"
        return True

    def _apply_auto_trend(self, context: MarketContext, auto_trend_fallback: str) -> MarketContext:
        trend = self._normalize_trend(getattr(context, "trend", None))
        context.auto_trend_source_trend = trend

        if trend == "UPTREND":
            context.direction_mode_resolved_direction = "LONG"
            context.direction_mode_fallback_reason = "AUTO_TREND_UPTREND_LONG_ONLY"
            return self._apply_resolved_direction(context, allowed_direction="BULLISH")

        if trend == "DOWNTREND":
            context.direction_mode_resolved_direction = "SHORT"
            context.direction_mode_fallback_reason = "AUTO_TREND_DOWNTREND_SHORT_ONLY"
            return self._apply_resolved_direction(context, allowed_direction="BEARISH")

        if auto_trend_fallback == "all":
            context.direction_mode_resolved_direction = "ALL"
            context.direction_mode_allowed = True if context.trade_plan_status == "PLANNED" else None
            context.direction_mode_fallback_reason = "AUTO_TREND_FALLBACK_ALL"
            self._update_debug(context)
            return context

        context.direction_mode_resolved_direction = "NONE"
        if context.trade_plan_status == "PLANNED":
            context.direction_mode_allowed = False
            context.direction_mode_blocked_direction = self._blocked_direction(context.trade_direction)
        context.direction_mode_fallback_reason = "AUTO_TREND_FALLBACK_BLOCK"
        self._update_debug(context)
        return context

    def _apply_regime_trend(self, context: MarketContext, regime_fallback: str) -> MarketContext:
        regime = self._normalize_regime(getattr(context, "market_regime", None))
        context.regime_source_regime = regime

        if regime == "BULLISH":
            context.direction_mode_resolved_direction = "LONG"
            context.direction_mode_fallback_reason = "REGIME_TREND_BULLISH_LONG_ONLY"
            return self._apply_resolved_direction(context, allowed_direction="BULLISH")

        if regime == "BEARISH":
            context.direction_mode_resolved_direction = "SHORT"
            context.direction_mode_fallback_reason = "REGIME_TREND_BEARISH_SHORT_ONLY"
            return self._apply_resolved_direction(context, allowed_direction="BEARISH")

        if regime not in ("RANGE", "UNKNOWN"):
            context.direction_mode_fallback_reason = "REGIME_TREND_UNKNOWN_REGIME"

        if regime_fallback == "all":
            context.direction_mode_resolved_direction = "ALL"
            context.direction_mode_allowed = True if context.trade_plan_status == "PLANNED" else None
            if context.direction_mode_fallback_reason is None:
                context.direction_mode_fallback_reason = "REGIME_TREND_FALLBACK_ALL"
            self._update_debug(context)
            return context

        context.direction_mode_resolved_direction = "NONE"
        if context.trade_plan_status == "PLANNED":
            context.direction_mode_allowed = False
            context.direction_mode_blocked_direction = self._blocked_direction(context.trade_direction)
        if context.direction_mode_fallback_reason is None:
            context.direction_mode_fallback_reason = "REGIME_TREND_FALLBACK_BLOCK"
        self._update_debug(context)
        return context

    def _apply_resolved_direction(self, context: MarketContext, allowed_direction: str) -> MarketContext:
        if context.trade_plan_status != "PLANNED":
            self._update_debug(context)
            return context

        direction = context.trade_direction
        if direction not in ("BULLISH", "BEARISH"):
            context.direction_mode_allowed = None
            context.direction_mode_fallback_reason = "INVALID_DIRECTION"
            self._update_debug(context)
            return context

        context.direction_mode_allowed = direction == allowed_direction
        if not context.direction_mode_allowed:
            context.direction_mode_blocked_direction = direction
        self._update_debug(context)
        return context

    def _normalize_trend(self, trend) -> str:
        value = str(trend or "UNKNOWN").upper()
        if value in ("UPTREND", "DOWNTREND", "RANGE"):
            return value
        return "UNKNOWN"

    def _normalize_regime(self, regime) -> str:
        value = str(regime or "UNKNOWN").upper()
        if value in ("BULLISH", "BEARISH", "RANGE", "UNKNOWN"):
            return value
        return "UNKNOWN"

    def _blocked_direction(self, direction: str) -> str | None:
        return direction if direction in ("BULLISH", "BEARISH") else None

    def _update_debug(self, context: MarketContext) -> None:
        if not hasattr(context, "debug") or context.debug is None:
            return

        context.debug["direction_mode_requested"] = context.direction_mode_requested
        context.debug["direction_mode_applied"] = context.direction_mode_applied
        context.debug["direction_mode_allowed"] = context.direction_mode_allowed
        context.debug["direction_mode_blocked_direction"] = context.direction_mode_blocked_direction
        context.debug["direction_mode_fallback_reason"] = context.direction_mode_fallback_reason
        context.debug["direction_mode_resolved_direction"] = context.direction_mode_resolved_direction
        context.debug["auto_trend_source_trend"] = context.auto_trend_source_trend
        context.debug["auto_trend_fallback"] = context.auto_trend_fallback
        context.debug["regime_source_regime"] = context.regime_source_regime
        context.debug["regime_fallback"] = context.regime_fallback
