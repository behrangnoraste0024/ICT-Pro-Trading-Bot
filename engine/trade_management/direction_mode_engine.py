from __future__ import annotations

from models.market_context import MarketContext


class DirectionModeEngine:
    VALID_MODES = {"all", "long_only", "short_only"}

    def apply(self, context: MarketContext, direction_mode: str = "all") -> MarketContext:
        self._reset_metadata(context, direction_mode)

        if direction_mode not in self.VALID_MODES:
            context.direction_mode_fallback_reason = "INVALID_DIRECTION"
            self._update_debug(context)
            return context

        context.direction_mode_applied = direction_mode

        if direction_mode == "all":
            context.direction_mode_allowed = True if context.trade_plan_status == "PLANNED" else None
            context.direction_mode_fallback_reason = "ALL_MODE"
            self._update_debug(context)
            return context

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
            context.direction_mode_fallback_reason = "NONE"
        else:
            context.direction_mode_blocked_direction = direction
            context.direction_mode_fallback_reason = "DIRECTION_MODE_BLOCKED"

        self._update_debug(context)
        return context

    def _reset_metadata(self, context: MarketContext, direction_mode: str) -> None:
        context.direction_mode_requested = direction_mode
        context.direction_mode_applied = None
        context.direction_mode_allowed = None
        context.direction_mode_blocked_direction = None
        context.direction_mode_fallback_reason = None

    def _is_allowed(self, direction: str, direction_mode: str) -> bool:
        if direction_mode == "long_only":
            return direction == "BULLISH"
        if direction_mode == "short_only":
            return direction == "BEARISH"
        return True

    def _update_debug(self, context: MarketContext) -> None:
        if not hasattr(context, "debug") or context.debug is None:
            return

        context.debug["direction_mode_requested"] = context.direction_mode_requested
        context.debug["direction_mode_applied"] = context.direction_mode_applied
        context.debug["direction_mode_allowed"] = context.direction_mode_allowed
        context.debug["direction_mode_blocked_direction"] = context.direction_mode_blocked_direction
        context.debug["direction_mode_fallback_reason"] = context.direction_mode_fallback_reason
