from __future__ import annotations

from copy import copy
from copy import deepcopy

from engine.backtest.trade_metadata_extractor import apply_trade_metadata_to_context
from engine.backtest.trade_metadata_extractor import extract_trade_metadata_from_context
from models.market_context import MarketContext
from models.rolling_trade_state import RollingTradeState


class TradeStateManager:
    def open_from_context(self, context: MarketContext, entry_index: int | None = None) -> RollingTradeState | None:
        can_open_from_paper = context.paper_trade_status in ("PAPER_OPEN", "PAPER_CLOSED_TP", "PAPER_CLOSED_SL")
        can_open_from_plan = context.trade_quality_status == "APPROVED" and context.trade_plan_status == "PLANNED"

        if not can_open_from_paper and not can_open_from_plan:
            return None

        direction = context.trade_direction
        entry_price = context.planned_entry_price
        stop_loss = context.planned_stop_loss
        take_profit = context.planned_take_profit

        if direction not in ("BULLISH", "BEARISH"):
            return None
        if entry_price is None or stop_loss is None or take_profit is None:
            return None

        resolved_entry_index = self._resolve_entry_index(context, entry_index)

        return RollingTradeState(
            is_open=True,
            direction=direction,
            status="OPEN",
            entry_price=float(entry_price),
            stop_loss=float(stop_loss),
            take_profit=float(take_profit),
            entry_index=resolved_entry_index,
            entry_context_metadata=self._entry_context_metadata(context),
            entry_context_snapshot=self._entry_context_snapshot(context),
        )

    def update_with_candle(self, state: RollingTradeState, candle, candle_index: int) -> RollingTradeState:
        if not state.is_open:
            return state

        high = float(candle["high"])
        low = float(candle["low"])

        if state.direction == "BULLISH":
            tp_hit = high >= state.take_profit
            sl_hit = low <= state.stop_loss
        else:
            tp_hit = low <= state.take_profit
            sl_hit = high >= state.stop_loss

        if tp_hit and sl_hit:
            return self._close_state(state, "CLOSED_SL", state.stop_loss, candle_index, ["CONSERVATIVE_SL_FIRST"])
        if tp_hit:
            return self._close_state(state, "CLOSED_TP", state.take_profit, candle_index, [])
        if sl_hit:
            return self._close_state(state, "CLOSED_SL", state.stop_loss, candle_index, [])

        return state

    def to_paper_trade_context(self, state: RollingTradeState) -> MarketContext:
        context = self._paper_context_base(state)
        status_map = {
            "OPEN": "PAPER_OPEN",
            "CLOSED_TP": "PAPER_CLOSED_TP",
            "CLOSED_SL": "PAPER_CLOSED_SL",
        }

        context.paper_trade_status = status_map.get(state.status, "NO_PAPER_TRADE")
        context.paper_trade_direction = state.direction
        context.paper_entry_price = state.entry_price
        context.paper_stop_loss = state.stop_loss
        context.paper_take_profit = state.take_profit
        context.paper_entry_index = state.entry_index
        context.paper_exit_price = state.exit_price
        context.paper_exit_index = state.exit_index
        context.paper_pnl = state.pnl
        context.paper_trade_reasons = list(state.reasons)
        return context

    def _resolve_entry_index(self, context: MarketContext, entry_index: int | None) -> int | None:
        if entry_index is not None:
            return entry_index
        if context.paper_entry_index is not None:
            return context.paper_entry_index

        entry_trigger = getattr(context, "entry_trigger", None)
        if entry_trigger is not None:
            trigger_index = getattr(entry_trigger, "candle_index", None)
            if trigger_index is not None:
                return int(trigger_index)

        return None

    def _close_state(
        self,
        state: RollingTradeState,
        status: str,
        exit_price: float,
        candle_index: int,
        reasons: list[str],
    ) -> RollingTradeState:
        state.is_open = False
        state.status = status
        state.exit_price = float(exit_price)
        state.exit_index = candle_index
        state.pnl = self._pnl(state)
        state.reasons.extend(reasons)
        return state

    def _pnl(self, state: RollingTradeState) -> float:
        if state.direction == "BULLISH":
            return state.exit_price - state.entry_price

        return state.entry_price - state.exit_price

    def _entry_context_metadata(self, context: MarketContext) -> dict:
        return extract_trade_metadata_from_context(context)

    def _entry_context_snapshot(self, context: MarketContext):
        try:
            return deepcopy(context)
        except Exception:
            try:
                return copy(context)
            except Exception:
                return None

    def _paper_context_base(self, state: RollingTradeState) -> MarketContext:
        if state.entry_context_snapshot is not None:
            try:
                return deepcopy(state.entry_context_snapshot)
            except Exception:
                try:
                    return copy(state.entry_context_snapshot)
                except Exception:
                    pass

        context = MarketContext()
        apply_trade_metadata_to_context(context, state.entry_context_metadata)
        return context
