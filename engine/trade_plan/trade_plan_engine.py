from __future__ import annotations

from models.market_context import MarketContext
from models.trade_plan_event import TradePlanEvent


class TradePlanEngine:
    def __init__(self, minimum_rr: float = 2.0, stop_lookback: int = 5):
        self.minimum_rr = minimum_rr
        self.stop_lookback = stop_lookback

    def detect(self, context: MarketContext) -> MarketContext:
        self._reset_context(context)

        if not self._has_confirmed_entry(context):
            self._mark_no_trade(context, ["NO_CONFIRMED_ENTRY"])
            return context

        entry_price = self._entry_price(context)
        if entry_price is None:
            self._mark_no_trade(context, ["NO_ENTRY_PRICE"])
            return context

        candles = context.candles
        if candles is None or len(candles) == 0:
            self._mark_no_trade(context, ["NO_CANDLES"])
            return context

        direction = context.entry_direction
        stop_loss = self._stop_loss(candles, direction)
        take_profit = self._take_profit(context, direction)
        if take_profit is None:
            self._mark_no_trade(context, ["NO_TAKE_PROFIT_TARGET"])
            return context

        risk = self._risk(direction, entry_price, stop_loss)
        reward = self._reward(direction, entry_price, take_profit)
        blockers: list[str] = []
        risk_reward = None

        if risk <= 0:
            blockers.append("INVALID_RISK")

        if reward <= 0:
            blockers.append("INVALID_REWARD")

        if not blockers:
            risk_reward = reward / risk
            if risk_reward < self.minimum_rr:
                blockers.append("RR_TOO_LOW")

        status = "REJECTED" if blockers else "PLANNED"
        self._set_trade_plan(
            context=context,
            status=status,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk=risk,
            reward=reward,
            risk_reward=risk_reward,
            blockers=blockers,
        )
        return context

    def _reset_context(self, context: MarketContext) -> None:
        context.trade_plan = None
        context.trade_plan_status = "NO_TRADE"
        context.trade_direction = "NONE"
        context.planned_entry_price = None
        context.planned_stop_loss = None
        context.planned_take_profit = None
        context.planned_risk = None
        context.planned_reward = None
        context.planned_risk_reward = None
        context.trade_plan_blockers = []

    def _has_confirmed_entry(self, context: MarketContext) -> bool:
        return (
            context.entry_confirmed is True
            and context.entry_direction in ("BULLISH", "BEARISH")
            and context.entry_trigger is not None
        )

    def _entry_price(self, context: MarketContext) -> float | None:
        if context.current_price is not None:
            return float(context.current_price)

        candles = context.candles
        if candles is None or len(candles) == 0:
            return None

        return float(candles.iloc[-1]["close"])

    def _stop_loss(self, candles, direction: str) -> float:
        recent = candles.iloc[-self.stop_lookback:]
        if direction == "BULLISH":
            return float(recent["low"].astype(float).min())

        return float(recent["high"].astype(float).max())

    def _take_profit(self, context: MarketContext, direction: str) -> float | None:
        if direction == "BULLISH":
            return None if context.dealing_range_high is None else float(context.dealing_range_high)

        return None if context.dealing_range_low is None else float(context.dealing_range_low)

    def _risk(self, direction: str, entry_price: float, stop_loss: float) -> float:
        if direction == "BULLISH":
            return entry_price - stop_loss

        return stop_loss - entry_price

    def _reward(self, direction: str, entry_price: float, take_profit: float) -> float:
        if direction == "BULLISH":
            return take_profit - entry_price

        return entry_price - take_profit

    def _mark_no_trade(self, context: MarketContext, blockers: list[str]) -> None:
        context.trade_plan = None
        context.trade_plan_status = "NO_TRADE"
        context.trade_direction = "NONE"
        context.trade_plan_blockers = blockers
        self._update_debug(context)

    def _set_trade_plan(
        self,
        context: MarketContext,
        status: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        risk: float,
        reward: float,
        risk_reward: float | None,
        blockers: list[str],
    ) -> None:
        event = TradePlanEvent(
            direction=direction,
            status=status,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk=risk,
            reward=reward,
            risk_reward=risk_reward,
            entry_trigger_type=context.entry_trigger_type,
            blockers=blockers,
        )

        context.trade_plan = event
        context.trade_plan_status = status
        context.trade_direction = direction
        context.planned_entry_price = entry_price
        context.planned_stop_loss = stop_loss
        context.planned_take_profit = take_profit
        context.planned_risk = risk
        context.planned_reward = reward
        context.planned_risk_reward = risk_reward
        context.trade_plan_blockers = blockers
        self._update_debug(context)

    def _update_debug(self, context: MarketContext) -> None:
        if not hasattr(context, "debug") or context.debug is None:
            return

        context.debug["trade_plan_status"] = context.trade_plan_status
        context.debug["trade_direction"] = context.trade_direction
        context.debug["planned_entry_price"] = context.planned_entry_price
        context.debug["planned_stop_loss"] = context.planned_stop_loss
        context.debug["planned_take_profit"] = context.planned_take_profit
        context.debug["planned_risk"] = context.planned_risk
        context.debug["planned_reward"] = context.planned_reward
        context.debug["planned_risk_reward"] = context.planned_risk_reward
        context.debug["trade_plan_blockers"] = context.trade_plan_blockers
