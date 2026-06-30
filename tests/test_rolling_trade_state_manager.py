from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from engine.rolling_backtest.trade_state_manager import TradeStateManager
from models.market_context import MarketContext
from models.rolling_trade_state import RollingTradeState


def _approved_context(direction: str = "BULLISH") -> MarketContext:
    context = MarketContext()
    context.trade_quality_status = "APPROVED"
    context.trade_plan_status = "PLANNED"
    context.trade_direction = direction
    context.trade_plan = SimpleNamespace(status="PLANNED")
    context.planned_entry_price = 100
    context.planned_stop_loss = 95 if direction == "BULLISH" else 105
    context.planned_take_profit = 112 if direction == "BULLISH" else 88
    return context


def _candle(high: float, low: float):
    return pd.Series({"high": high, "low": low})


def test_opens_state_from_approved_context() -> None:
    state = TradeStateManager().open_from_context(_approved_context("BULLISH"), entry_index=10)

    assert state is not None
    assert state.is_open is True
    assert state.status == "OPEN"
    assert state.direction == "BULLISH"
    assert state.entry_index == 10


def test_missing_planned_values_returns_none() -> None:
    context = _approved_context("BULLISH")
    context.planned_entry_price = None

    state = TradeStateManager().open_from_context(context)

    assert state is None


def test_bullish_tp_closes() -> None:
    state = TradeStateManager().open_from_context(_approved_context("BULLISH"))

    state = TradeStateManager().update_with_candle(state, _candle(high=113, low=100), candle_index=11)

    assert state.status == "CLOSED_TP"
    assert state.pnl == 12


def test_final_context_preserves_entry_snapshot_metadata_after_close() -> None:
    manager = TradeStateManager()
    context = _approved_context("BULLISH")
    context.setup_score = 100
    context.entry_trigger_type = "CONFIRMATION_CANDLE"
    context.current_price_zone = "PREMIUM"
    context.in_ote_zone = True
    context.ote_direction = "BEARISH"
    context.active_setup = SimpleNamespace(matched_pois=["ORDER_BLOCK:BULLISH:10"])
    context.trade_quality_score = 90
    context.custom_diagnostic_field = "ENTRY_CONTEXT"
    context.candles = pd.DataFrame([{"open": 100, "high": 101, "low": 99, "close": 100}])

    state = manager.open_from_context(context)
    state = manager.update_with_candle(state, _candle(high=113, low=100), candle_index=11)
    final_context = manager.to_paper_trade_context(state)

    assert final_context.setup_score == 100
    assert final_context.entry_trigger_type == "CONFIRMATION_CANDLE"
    assert final_context.current_price_zone == "PREMIUM"
    assert final_context.in_ote_zone is True
    assert final_context.ote_direction == "BEARISH"
    assert final_context.active_setup.matched_pois == ["ORDER_BLOCK:BULLISH:10"]
    assert final_context.trade_quality_score == 90
    assert final_context.custom_diagnostic_field == "ENTRY_CONTEXT"
    assert final_context.paper_trade_status == "PAPER_CLOSED_TP"
    assert final_context.paper_exit_price == 112.0
    assert final_context.paper_pnl == 12.0
    assert len(final_context.candles) == 2


def test_bullish_sl_closes() -> None:
    state = TradeStateManager().open_from_context(_approved_context("BULLISH"))

    state = TradeStateManager().update_with_candle(state, _candle(high=100, low=94), candle_index=11)

    assert state.status == "CLOSED_SL"
    assert state.pnl == -5


def test_bearish_tp_closes() -> None:
    state = TradeStateManager().open_from_context(_approved_context("BEARISH"))

    state = TradeStateManager().update_with_candle(state, _candle(high=100, low=87), candle_index=11)

    assert state.status == "CLOSED_TP"
    assert state.pnl == 12


def test_bearish_sl_closes() -> None:
    state = TradeStateManager().open_from_context(_approved_context("BEARISH"))

    state = TradeStateManager().update_with_candle(state, _candle(high=106, low=90), candle_index=11)

    assert state.status == "CLOSED_SL"
    assert state.pnl == -5


def test_same_candle_bullish_tp_and_sl_closes_sl_first() -> None:
    state = TradeStateManager().open_from_context(_approved_context("BULLISH"))

    state = TradeStateManager().update_with_candle(state, _candle(high=113, low=94), candle_index=11)

    assert state.status == "CLOSED_SL"
    assert "CONSERVATIVE_SL_FIRST" in state.reasons


def test_same_candle_bearish_tp_and_sl_closes_sl_first() -> None:
    state = TradeStateManager().open_from_context(_approved_context("BEARISH"))

    state = TradeStateManager().update_with_candle(state, _candle(high=106, low=87), candle_index=11)

    assert state.status == "CLOSED_SL"
    assert "CONSERVATIVE_SL_FIRST" in state.reasons


def test_no_hit_remains_open() -> None:
    state = TradeStateManager().open_from_context(_approved_context("BULLISH"))

    state = TradeStateManager().update_with_candle(state, _candle(high=105, low=99), candle_index=11)

    assert state.is_open is True
    assert state.status == "OPEN"


def test_str_includes_key_fields() -> None:
    open_state = RollingTradeState(
        is_open=True,
        direction="BULLISH",
        status="OPEN",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=112.0,
    )
    closed_state = RollingTradeState(
        direction="BEARISH",
        status="CLOSED_TP",
        entry_price=100.0,
        exit_price=88.0,
        pnl=12.0,
    )

    assert "OPEN" in str(open_state)
    assert "ENTRY=100.0" in str(open_state)
    assert "CLOSED_TP" in str(closed_state)
    assert "PNL=12.0" in str(closed_state)
