from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from engine.paper_trade.paper_trade_engine import PaperTradeEngine
from models.market_context import MarketContext
from models.paper_trade_event import PaperTradeEvent


def _candles(rows: list[dict[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _approved_context(direction: str = "BULLISH") -> MarketContext:
    context = MarketContext(
        candles=_candles(
            [
                {"open": 99, "high": 101, "low": 98, "close": 100},
                {"open": 100, "high": 102, "low": 99, "close": 101},
            ]
        )
    )
    context.trade_quality_status = "APPROVED"
    context.trade_plan_status = "PLANNED"
    context.trade_direction = direction
    context.trade_plan = SimpleNamespace(status="PLANNED")
    context.trade_quality = SimpleNamespace(status="APPROVED")
    context.planned_entry_price = 100
    context.planned_stop_loss = 95 if direction == "BULLISH" else 105
    context.planned_take_profit = 112 if direction == "BULLISH" else 88
    context.planned_risk = 5
    context.planned_reward = 12
    context.planned_risk_reward = 2.4
    context.entry_trigger = SimpleNamespace(candle_index=len(context.candles) - 1)
    return context


def test_no_approved_trade_quality() -> None:
    context = MarketContext()
    context.trade_quality_status = "REJECTED"

    context = PaperTradeEngine().detect(context)

    assert context.paper_trade_status == "NO_PAPER_TRADE"
    assert context.paper_trade_direction == "NONE"
    assert context.paper_trade is None
    assert "TRADE_QUALITY_NOT_APPROVED" in context.paper_trade_blockers


def test_approved_bullish_trade_opens_when_no_future_candles() -> None:
    context = MarketContext(
        candles=_candles([{"open": 99, "high": 101, "low": 98, "close": 100}])
    )
    context.trade_quality_status = "APPROVED"
    context.trade_plan_status = "PLANNED"
    context.trade_direction = "BULLISH"
    context.trade_plan = SimpleNamespace(status="PLANNED")
    context.trade_quality = SimpleNamespace(status="APPROVED")
    context.planned_entry_price = 100
    context.planned_stop_loss = 95
    context.planned_take_profit = 112
    context.planned_risk = 5
    context.planned_reward = 12
    context.planned_risk_reward = 2.4
    context.entry_trigger = SimpleNamespace(candle_index=0)

    context = PaperTradeEngine().detect(context)

    assert context.paper_trade_status == "PAPER_OPEN"
    assert context.paper_trade is not None
    assert context.paper_pnl is None


def test_approved_bearish_trade_opens_when_no_future_candles() -> None:
    context = _approved_context("BEARISH")
    context.candles = _candles([{"open": 101, "high": 103, "low": 100, "close": 102}])
    context.entry_trigger = SimpleNamespace(candle_index=0)

    context = PaperTradeEngine().detect(context)

    assert context.paper_trade_status == "PAPER_OPEN"
    assert context.paper_trade is not None


def test_bullish_trade_closes_tp() -> None:
    context = _approved_context("BULLISH")
    context.candles = _candles(
        [
            {"open": 99, "high": 101, "low": 98, "close": 100},
            {"open": 100, "high": 113, "low": 99, "close": 111},
        ]
    )
    context.entry_trigger = SimpleNamespace(candle_index=0)

    context = PaperTradeEngine().detect(context)

    assert context.paper_trade_status == "PAPER_CLOSED_TP"
    assert context.paper_exit_price == 112
    assert context.paper_pnl == 12


def test_bullish_trade_closes_sl() -> None:
    context = _approved_context("BULLISH")
    context.candles = _candles(
        [
            {"open": 99, "high": 101, "low": 98, "close": 100},
            {"open": 100, "high": 104, "low": 94, "close": 96},
        ]
    )
    context.entry_trigger = SimpleNamespace(candle_index=0)

    context = PaperTradeEngine().detect(context)

    assert context.paper_trade_status == "PAPER_CLOSED_SL"
    assert context.paper_exit_price == 95
    assert context.paper_pnl == -5


def test_bearish_trade_closes_tp() -> None:
    context = _approved_context("BEARISH")
    context.candles = _candles(
        [
            {"open": 101, "high": 103, "low": 100, "close": 102},
            {"open": 102, "high": 103, "low": 87, "close": 89},
        ]
    )
    context.entry_trigger = SimpleNamespace(candle_index=0)

    context = PaperTradeEngine().detect(context)

    assert context.paper_trade_status == "PAPER_CLOSED_TP"
    assert context.paper_pnl == 12


def test_bearish_trade_closes_sl() -> None:
    context = _approved_context("BEARISH")
    context.candles = _candles(
        [
            {"open": 101, "high": 103, "low": 100, "close": 102},
            {"open": 102, "high": 106, "low": 95, "close": 97},
        ]
    )
    context.entry_trigger = SimpleNamespace(candle_index=0)

    context = PaperTradeEngine().detect(context)

    assert context.paper_trade_status == "PAPER_CLOSED_SL"
    assert context.paper_pnl == -5


def test_same_candle_tp_and_sl_uses_conservative_sl_first_bullish() -> None:
    context = _approved_context("BULLISH")
    context.candles = _candles(
        [
            {"open": 99, "high": 101, "low": 98, "close": 100},
            {"open": 100, "high": 113, "low": 94, "close": 111},
        ]
    )
    context.entry_trigger = SimpleNamespace(candle_index=0)

    context = PaperTradeEngine().detect(context)

    assert context.paper_trade_status == "PAPER_CLOSED_SL"
    assert "CONSERVATIVE_SL_FIRST" in context.paper_trade_reasons


def test_same_candle_tp_and_sl_uses_conservative_sl_first_bearish() -> None:
    context = _approved_context("BEARISH")
    context.candles = _candles(
        [
            {"open": 101, "high": 103, "low": 100, "close": 102},
            {"open": 102, "high": 106, "low": 87, "close": 89},
        ]
    )
    context.entry_trigger = SimpleNamespace(candle_index=0)

    context = PaperTradeEngine().detect(context)

    assert context.paper_trade_status == "PAPER_CLOSED_SL"
    assert "CONSERVATIVE_SL_FIRST" in context.paper_trade_reasons


def test_missing_planned_values_no_paper_trade() -> None:
    context = _approved_context("BULLISH")
    context.planned_entry_price = None

    context = PaperTradeEngine().detect(context)

    assert context.paper_trade_status == "NO_PAPER_TRADE"
    assert "INCOMPLETE_TRADE_PLAN" in context.paper_trade_blockers


def test_missing_candles_no_paper_trade() -> None:
    context = _approved_context("BULLISH")
    context.candles = pd.DataFrame()

    context = PaperTradeEngine().detect(context)

    assert context.paper_trade_status == "NO_PAPER_TRADE"
    assert "NO_CANDLES" in context.paper_trade_blockers


def test_uses_fallback_entry_index_when_entry_trigger_missing() -> None:
    context = _approved_context("BULLISH")
    context.entry_trigger = None
    context.candles = _candles(
        [
            {"open": 99, "high": 101, "low": 98, "close": 100},
            {"open": 100, "high": 102, "low": 99, "close": 101},
        ]
    )

    context = PaperTradeEngine().detect(context)

    assert context.paper_entry_index == len(context.candles) - 1


def test_paper_trade_event_string_for_open_trade() -> None:
    event = PaperTradeEvent(
        direction="BULLISH",
        status="PAPER_OPEN",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=112.0,
        entry_index=1,
        exit_price=None,
        exit_index=None,
        pnl=None,
    )

    output = str(event)

    assert "PAPER_OPEN" in output
    assert "ENTRY=100.0" in output


def test_paper_trade_event_string_for_closed_trade() -> None:
    event = PaperTradeEvent(
        direction="BULLISH",
        status="PAPER_CLOSED_TP",
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=112.0,
        entry_index=1,
        exit_price=112.0,
        exit_index=2,
        pnl=12.0,
    )

    output = str(event)

    assert "PAPER_CLOSED_TP" in output
    assert "PNL=12.0" in output


def test_existing_context_objects_are_preserved() -> None:
    context = _approved_context("BULLISH")
    context.bos = ["bos"]
    context.choch = ["choch"]
    context.liquidity_sweeps = ["sweep"]
    context.fvgs = ["fvg"]
    context.order_blocks = ["order_block"]
    context.breaker_blocks = ["breaker"]
    context.ote = "ote"
    context.setups = ["setup"]
    context.active_setup = "active_setup"
    context.entry_trigger = "entry_trigger"
    context.trade_plan = "trade_plan"
    context.trade_quality = "trade_quality"

    context = PaperTradeEngine().detect(context)

    assert context.bos == ["bos"]
    assert context.choch == ["choch"]
    assert context.liquidity_sweeps == ["sweep"]
    assert context.fvgs == ["fvg"]
    assert context.order_blocks == ["order_block"]
    assert context.breaker_blocks == ["breaker"]
    assert context.ote == "ote"
    assert context.setups == ["setup"]
    assert context.active_setup == "active_setup"
    assert context.entry_trigger == "entry_trigger"
    assert context.trade_plan == "trade_plan"
    assert context.trade_quality == "trade_quality"


def test_debug_values_are_populated() -> None:
    context = _approved_context("BULLISH")
    context = PaperTradeEngine().detect(context)

    assert context.debug["paper_trade_status"] == "PAPER_OPEN"
    assert context.debug["paper_trade_direction"] == "BULLISH"
    assert context.debug["paper_entry_price"] == 100
    assert context.debug["paper_stop_loss"] == 95
    assert context.debug["paper_take_profit"] == 112
    assert context.debug["paper_entry_index"] == len(context.candles) - 1
    assert context.debug["paper_exit_price"] is None
    assert context.debug["paper_exit_index"] is None
    assert context.debug["paper_pnl"] is None
    assert context.debug["paper_trade_blockers"] == []
    assert context.debug["paper_trade_reasons"] == []
