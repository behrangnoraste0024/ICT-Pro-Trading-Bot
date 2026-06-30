from __future__ import annotations

from models.market_context import MarketContext
from models.paper_trade_event import PaperTradeEvent


class PaperTradeEngine:
    def detect(self, context: MarketContext) -> MarketContext:
        self._reset_context(context)

        if context.trade_quality_status != "APPROVED":
            self._mark_no_paper_trade(context, ["TRADE_QUALITY_NOT_APPROVED"])
            return context

        if not self._has_valid_plan(context):
            self._mark_no_paper_trade(context, ["INCOMPLETE_TRADE_PLAN"])
            return context

        candles = context.candles
        if candles is None or len(candles) == 0:
            self._mark_no_paper_trade(context, ["NO_CANDLES"])
            return context

        entry_index = self._resolve_entry_index(context)
        entry_price = self._resolve_entry_price(context)
        if entry_price is None:
            self._mark_no_paper_trade(context, ["INCOMPLETE_TRADE_PLAN"])
            return context

        stop_loss = float(context.planned_stop_loss)
        take_profit = float(context.planned_take_profit)
        direction = context.trade_direction

        exit_price = None
        exit_index = None
        pnl = None
        reasons: list[str] = []

        future_candles = candles.iloc[entry_index + 1 :]
        for candle_index, candle in future_candles.iterrows():
            high = float(candle["high"])
            low = float(candle["low"])

            tp_hit = self._tp_hit(direction, high, low, take_profit)
            sl_hit = self._sl_hit(direction, high, low, stop_loss)

            if tp_hit and sl_hit:
                exit_price = stop_loss
                exit_index = int(candle_index)
                pnl = self._pnl(direction, entry_price, stop_loss)
                reasons.append("CONSERVATIVE_SL_FIRST")
                status = "PAPER_CLOSED_SL"
                break

            if sl_hit:
                exit_price = stop_loss
                exit_index = int(candle_index)
                pnl = self._pnl(direction, entry_price, stop_loss)
                status = "PAPER_CLOSED_SL"
                break

            if tp_hit:
                exit_price = take_profit
                exit_index = int(candle_index)
                pnl = self._pnl(direction, entry_price, take_profit)
                status = "PAPER_CLOSED_TP"
                break
        else:
            status = "PAPER_OPEN"
            event = PaperTradeEvent(
                direction=direction,
                status=status,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                entry_index=entry_index,
                exit_price=None,
                exit_index=None,
                pnl=None,
                reasons=reasons,
                blockers=[],
            )
            self._set_context(context, event)
            return context

        event = PaperTradeEvent(
            direction=direction,
            status=status,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_index=entry_index,
            exit_price=exit_price,
            exit_index=exit_index,
            pnl=pnl,
            reasons=reasons,
            blockers=[],
        )
        self._set_context(context, event)
        return context

    def _reset_context(self, context: MarketContext) -> None:
        context.paper_trade = None
        context.paper_trade_status = "NO_PAPER_TRADE"
        context.paper_trade_direction = "NONE"
        context.paper_entry_price = None
        context.paper_stop_loss = None
        context.paper_take_profit = None
        context.paper_entry_index = None
        context.paper_exit_price = None
        context.paper_exit_index = None
        context.paper_pnl = None
        context.paper_trade_blockers = []
        context.paper_trade_reasons = []

    def _has_valid_plan(self, context: MarketContext) -> bool:
        required = [
            context.trade_plan_status == "PLANNED",
            context.trade_direction in ("BULLISH", "BEARISH"),
            context.planned_entry_price is not None,
            context.planned_stop_loss is not None,
            context.planned_take_profit is not None,
        ]
        return all(required) and context.trade_plan is not None

    def _resolve_entry_index(self, context: MarketContext) -> int:
        entry_trigger = getattr(context, "entry_trigger", None)
        if entry_trigger is not None:
            entry_index = getattr(entry_trigger, "candle_index", None)
            if entry_index is not None:
                return int(entry_index)

        return len(context.candles) - 1

    def _resolve_entry_price(self, context: MarketContext) -> float | None:
        if context.planned_entry_price is not None:
            return float(context.planned_entry_price)
        return None

    def _tp_hit(self, direction: str, high: float, low: float, take_profit: float) -> bool:
        if direction == "BULLISH":
            return high >= take_profit
        return low <= take_profit

    def _sl_hit(self, direction: str, high: float, low: float, stop_loss: float) -> bool:
        if direction == "BULLISH":
            return low <= stop_loss
        return high >= stop_loss

    def _pnl(self, direction: str, entry_price: float, exit_price: float) -> float:
        if direction == "BULLISH":
            return exit_price - entry_price
        return entry_price - exit_price

    def _mark_no_paper_trade(self, context: MarketContext, blockers: list[str]) -> None:
        context.paper_trade = None
        context.paper_trade_status = "NO_PAPER_TRADE"
        context.paper_trade_direction = "NONE"
        context.paper_trade_blockers = blockers
        context.paper_trade_reasons = []
        self._update_debug(context)

    def _set_context(self, context: MarketContext, event: PaperTradeEvent) -> None:
        context.paper_trade = event
        context.paper_trade_status = event.status
        context.paper_trade_direction = event.direction
        context.paper_entry_price = event.entry_price
        context.paper_stop_loss = event.stop_loss
        context.paper_take_profit = event.take_profit
        context.paper_entry_index = event.entry_index
        context.paper_exit_price = event.exit_price
        context.paper_exit_index = event.exit_index
        context.paper_pnl = event.pnl
        context.paper_trade_blockers = event.blockers
        context.paper_trade_reasons = event.reasons
        self._update_debug(context)

    def _update_debug(self, context: MarketContext) -> None:
        if not hasattr(context, "debug") or context.debug is None:
            return

        context.debug["paper_trade_status"] = context.paper_trade_status
        context.debug["paper_trade_direction"] = context.paper_trade_direction
        context.debug["paper_entry_price"] = context.paper_entry_price
        context.debug["paper_stop_loss"] = context.paper_stop_loss
        context.debug["paper_take_profit"] = context.paper_take_profit
        context.debug["paper_entry_index"] = context.paper_entry_index
        context.debug["paper_exit_price"] = context.paper_exit_price
        context.debug["paper_exit_index"] = context.paper_exit_index
        context.debug["paper_pnl"] = context.paper_pnl
        context.debug["paper_trade_blockers"] = context.paper_trade_blockers
        context.debug["paper_trade_reasons"] = context.paper_trade_reasons
