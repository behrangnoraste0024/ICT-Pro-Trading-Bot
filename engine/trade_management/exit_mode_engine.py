from __future__ import annotations

from models.market_context import MarketContext


class ExitModeEngine:
    TARGET_R_BY_MODE = {
        "fixed_1r": 1.0,
        "fixed_1_5r": 1.5,
        "fixed_2r": 2.0,
        "fixed_3r": 3.0,
    }
    VALID_MODES = {"original", *TARGET_R_BY_MODE.keys()}

    def apply(self, context: MarketContext, exit_mode: str = "original") -> MarketContext:
        if exit_mode not in self.VALID_MODES:
            raise ValueError(f"Unsupported exit mode: {exit_mode}")

        self._reset_metadata(context, exit_mode)

        if exit_mode == "original":
            return self._fallback(context, "ORIGINAL_MODE", applied="original")

        if context.trade_plan_status != "PLANNED" or context.trade_plan is None:
            return self._fallback(context, "NO_PLANNED_TRADE")

        direction = context.trade_direction
        if direction not in ("BULLISH", "BEARISH"):
            return self._fallback(context, "INVALID_DIRECTION")

        entry_price = context.planned_entry_price
        stop_loss = context.planned_stop_loss
        original_take_profit = context.planned_take_profit
        if entry_price is None or stop_loss is None or original_take_profit is None:
            return self._fallback(context, "MISSING_PRICES")

        entry_price = float(entry_price)
        stop_loss = float(stop_loss)
        target_r = self.TARGET_R_BY_MODE[exit_mode]
        risk = self._risk(direction, entry_price, stop_loss)
        if risk <= 0:
            return self._fallback(context, "INVALID_RISK")

        new_take_profit = self._fixed_take_profit(direction, entry_price, risk, target_r)
        reward = self._reward(direction, entry_price, new_take_profit)
        risk_reward = reward / risk

        context.planned_risk = risk
        context.planned_reward = reward
        context.planned_risk_reward = risk_reward
        context.planned_take_profit = new_take_profit
        context.exit_mode_applied = exit_mode
        context.exit_mode_target_r = target_r
        context.exit_mode_original_take_profit = float(original_take_profit)
        context.exit_mode_new_take_profit = new_take_profit
        context.exit_mode_fallback_reason = "NONE"

        trade_plan = context.trade_plan
        trade_plan.take_profit = new_take_profit
        trade_plan.risk = risk
        trade_plan.reward = reward
        trade_plan.risk_reward = risk_reward

        self._update_debug(context)
        return context

    def _reset_metadata(self, context: MarketContext, exit_mode: str) -> None:
        context.exit_mode_requested = exit_mode
        context.exit_mode_applied = "original"
        context.exit_mode_target_r = None
        context.exit_mode_original_take_profit = context.planned_take_profit
        context.exit_mode_new_take_profit = context.planned_take_profit
        context.exit_mode_fallback_reason = "NONE"
        self._update_debug(context)

    def _fallback(self, context: MarketContext, reason: str, applied: str | None = None) -> MarketContext:
        context.exit_mode_applied = applied if applied is not None else "original"
        context.exit_mode_fallback_reason = reason
        self._update_debug(context)
        return context

    def _risk(self, direction: str, entry_price: float, stop_loss: float) -> float:
        if direction == "BULLISH":
            return entry_price - stop_loss
        return stop_loss - entry_price

    def _fixed_take_profit(self, direction: str, entry_price: float, risk: float, target_r: float) -> float:
        if direction == "BULLISH":
            return entry_price + (risk * target_r)
        return entry_price - (risk * target_r)

    def _reward(self, direction: str, entry_price: float, take_profit: float) -> float:
        if direction == "BULLISH":
            return take_profit - entry_price
        return entry_price - take_profit

    def _update_debug(self, context: MarketContext) -> None:
        if not hasattr(context, "debug") or context.debug is None:
            return
        context.debug["exit_mode_requested"] = context.exit_mode_requested
        context.debug["exit_mode_applied"] = context.exit_mode_applied
        context.debug["exit_mode_target_r"] = context.exit_mode_target_r
        context.debug["exit_mode_original_take_profit"] = context.exit_mode_original_take_profit
        context.debug["exit_mode_new_take_profit"] = context.exit_mode_new_take_profit
        context.debug["exit_mode_fallback_reason"] = context.exit_mode_fallback_reason
