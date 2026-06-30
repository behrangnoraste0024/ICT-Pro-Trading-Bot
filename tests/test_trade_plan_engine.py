from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from engine.trade_plan.trade_plan_engine import TradePlanEngine
from models.market_context import MarketContext


def _candles(rows: list[dict[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _five_candles() -> pd.DataFrame:
    return _candles(
        [
            {"open": 100, "high": 104, "low": 99, "close": 101},
            {"open": 101, "high": 103, "low": 98, "close": 102},
            {"open": 102, "high": 106, "low": 97, "close": 103},
            {"open": 103, "high": 105, "low": 96, "close": 104},
            {"open": 104, "high": 102, "low": 95, "close": 100},
        ]
    )


def _confirmed_context(direction: str = "BULLISH") -> MarketContext:
    context = MarketContext(candles=_five_candles())
    context.entry_confirmed = True
    context.entry_direction = direction
    context.entry_trigger = SimpleNamespace(trigger_type="DISPLACEMENT")
    context.entry_trigger_type = "DISPLACEMENT"
    context.current_price = 100
    context.dealing_range_high = 112
    context.dealing_range_low = 88
    return context


def test_no_confirmed_entry_no_trade() -> None:
    context = MarketContext(candles=_five_candles())
    context.entry_confirmed = False

    context = TradePlanEngine().detect(context)

    assert context.trade_plan_status == "NO_TRADE"
    assert context.trade_direction == "NONE"
    assert context.trade_plan is None
    assert "NO_CONFIRMED_ENTRY" in context.trade_plan_blockers


def test_bullish_trade_plan_planned() -> None:
    context = TradePlanEngine().detect(_confirmed_context("BULLISH"))

    assert context.trade_plan_status == "PLANNED"
    assert context.trade_direction == "BULLISH"
    assert context.planned_entry_price == 100
    assert context.planned_stop_loss == 95
    assert context.planned_take_profit == 112
    assert context.planned_risk == 5
    assert context.planned_reward == 12
    assert context.planned_risk_reward == 2.4
    assert context.trade_plan is not None


def test_bearish_trade_plan_planned() -> None:
    context = TradePlanEngine().detect(_confirmed_context("BEARISH"))

    assert context.trade_plan_status == "PLANNED"
    assert context.trade_direction == "BEARISH"
    assert context.planned_entry_price == 100
    assert context.planned_stop_loss == 106
    assert context.planned_take_profit == 88
    assert context.planned_risk == 6
    assert context.planned_reward == 12
    assert context.planned_risk_reward == 2.0


def test_bullish_invalid_risk_rejected() -> None:
    context = _confirmed_context("BULLISH")
    context.candles = _candles(
        [
            {"open": 100, "high": 103, "low": 101, "close": 102},
            {"open": 102, "high": 104, "low": 100, "close": 103},
        ]
    )

    context = TradePlanEngine().detect(context)

    assert context.trade_plan_status == "REJECTED"
    assert "INVALID_RISK" in context.trade_plan_blockers


def test_bullish_invalid_reward_rejected() -> None:
    context = _confirmed_context("BULLISH")
    context.dealing_range_high = 99

    context = TradePlanEngine().detect(context)

    assert context.trade_plan_status == "REJECTED"
    assert "INVALID_REWARD" in context.trade_plan_blockers


def test_bearish_invalid_risk_rejected() -> None:
    context = _confirmed_context("BEARISH")
    context.candles = _candles(
        [
            {"open": 100, "high": 99, "low": 95, "close": 98},
            {"open": 98, "high": 100, "low": 96, "close": 99},
        ]
    )

    context = TradePlanEngine().detect(context)

    assert context.trade_plan_status == "REJECTED"
    assert "INVALID_RISK" in context.trade_plan_blockers


def test_bearish_invalid_reward_rejected() -> None:
    context = _confirmed_context("BEARISH")
    context.dealing_range_low = 101

    context = TradePlanEngine().detect(context)

    assert context.trade_plan_status == "REJECTED"
    assert "INVALID_REWARD" in context.trade_plan_blockers


def test_rr_too_low_rejected() -> None:
    context = _confirmed_context("BULLISH")
    context.dealing_range_high = 106

    context = TradePlanEngine().detect(context)

    assert context.trade_plan_status == "REJECTED"
    assert "RR_TOO_LOW" in context.trade_plan_blockers


def test_missing_take_profit_target_no_trade() -> None:
    context = _confirmed_context("BULLISH")
    context.dealing_range_high = None

    context = TradePlanEngine().detect(context)

    assert context.trade_plan_status == "NO_TRADE"
    assert context.trade_plan is None
    assert "NO_TAKE_PROFIT_TARGET" in context.trade_plan_blockers


def test_missing_candles_no_trade() -> None:
    context = _confirmed_context("BULLISH")
    context.candles = pd.DataFrame()
    context.current_price = 100

    context = TradePlanEngine().detect(context)

    assert context.trade_plan_status == "NO_TRADE"
    assert "NO_CANDLES" in context.trade_plan_blockers


def test_uses_last_candle_close_when_current_price_is_none() -> None:
    context = _confirmed_context("BULLISH")
    context.current_price = None
    context.dealing_range_high = 115

    context = TradePlanEngine().detect(context)

    assert context.trade_plan_status == "PLANNED"
    assert context.planned_entry_price == 100


def test_fewer_than_five_candles_uses_available_candles() -> None:
    context = _confirmed_context("BULLISH")
    context.candles = _candles(
        [
            {"open": 100, "high": 104, "low": 98, "close": 101},
            {"open": 101, "high": 103, "low": 94, "close": 100},
            {"open": 100, "high": 105, "low": 96, "close": 100},
        ]
    )

    context = TradePlanEngine().detect(context)

    assert context.planned_stop_loss == 94


def test_rejected_trade_still_creates_trade_plan_object() -> None:
    context = _confirmed_context("BULLISH")
    context.dealing_range_high = 106

    context = TradePlanEngine().detect(context)

    assert context.trade_plan_status == "REJECTED"
    assert context.trade_plan is not None


def test_existing_context_lists_are_preserved() -> None:
    context = _confirmed_context("BULLISH")
    context.bos = ["bos"]
    context.choch = ["choch"]
    context.liquidity_sweeps = ["sweep"]
    context.fvgs = ["fvg"]
    context.order_blocks = ["order_block"]
    context.breaker_blocks = ["breaker"]
    context.ote = "ote"
    context.setups = ["setup"]
    context.active_setup = "active_setup"
    entry_trigger = context.entry_trigger

    context = TradePlanEngine().detect(context)

    assert context.bos == ["bos"]
    assert context.choch == ["choch"]
    assert context.liquidity_sweeps == ["sweep"]
    assert context.fvgs == ["fvg"]
    assert context.order_blocks == ["order_block"]
    assert context.breaker_blocks == ["breaker"]
    assert context.ote == "ote"
    assert context.setups == ["setup"]
    assert context.active_setup == "active_setup"
    assert context.entry_trigger is entry_trigger


def test_debug_values_are_populated() -> None:
    context = TradePlanEngine().detect(_confirmed_context("BULLISH"))

    assert context.debug["trade_plan_status"] == "PLANNED"
    assert context.debug["trade_direction"] == "BULLISH"
    assert context.debug["planned_entry_price"] == 100
    assert context.debug["planned_stop_loss"] == 95
    assert context.debug["planned_take_profit"] == 112
    assert context.debug["planned_risk"] == 5
    assert context.debug["planned_reward"] == 12
    assert context.debug["planned_risk_reward"] == 2.4
    assert context.debug["trade_plan_blockers"] == []
