from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from engine.entry.entry_trigger_engine import EntryTriggerEngine
from models.market_context import MarketContext


def _candles(rows: list[dict[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _valid_context(direction: str, candles: pd.DataFrame) -> MarketContext:
    context = MarketContext(candles=candles)
    context.setup_status = "VALID"
    context.setup_bias = direction
    context.active_setup = SimpleNamespace(direction=direction, matched_pois=["FVG:BULLISH:1"])
    return context


def _body_average_candles(current: dict[str, float]) -> pd.DataFrame:
    rows = [
        {"open": 100, "high": 103, "low": 99, "close": 102},
        {"open": 102, "high": 103, "low": 99, "close": 100},
        {"open": 100, "high": 103, "low": 99, "close": 102},
        {"open": 102, "high": 103, "low": 99, "close": 100},
        {"open": 100, "high": 103, "low": 99, "close": 102},
        {"open": 102, "high": 103, "low": 99, "close": 100},
        {"open": 100, "high": 103, "low": 99, "close": 102},
        {"open": 102, "high": 103, "low": 99, "close": 100},
        {"open": 100, "high": 103, "low": 99, "close": 102},
        {"open": 102, "high": 103, "low": 99, "close": 100},
    ]
    rows.append(current)
    return _candles(rows)


def test_no_valid_setup_not_confirmed() -> None:
    context = MarketContext(candles=_candles([{"open": 1, "high": 2, "low": 1, "close": 2}] * 2))
    context.setup_status = "INVALID"
    context.active_setup = None

    context = EntryTriggerEngine().detect(context)

    assert context.entry_status == "NOT_CONFIRMED"
    assert context.entry_direction == "NONE"
    assert context.entry_trigger is None
    assert "NO_VALID_SETUP" in context.entry_blockers


def test_bullish_confirmation_candle_confirms_entry() -> None:
    candles = _candles(
        [
            {"open": 98, "high": 100, "low": 97, "close": 99},
            {"open": 99, "high": 102, "low": 98, "close": 101},
        ]
    )

    context = EntryTriggerEngine().detect(_valid_context("BULLISH", candles))

    assert context.entry_status == "CONFIRMED"
    assert context.entry_direction == "BULLISH"
    assert context.entry_trigger_type == "CONFIRMATION_CANDLE"
    assert context.entry_confirmed is True
    assert context.entry_trigger is not None


def test_bearish_confirmation_candle_confirms_entry() -> None:
    candles = _candles(
        [
            {"open": 102, "high": 103, "low": 100, "close": 101},
            {"open": 101, "high": 102, "low": 98, "close": 99},
        ]
    )

    context = EntryTriggerEngine().detect(_valid_context("BEARISH", candles))

    assert context.entry_status == "CONFIRMED"
    assert context.entry_direction == "BEARISH"
    assert context.entry_trigger_type == "CONFIRMATION_CANDLE"
    assert context.entry_confirmed is True


def test_bullish_displacement_confirms_entry() -> None:
    candles = _body_average_candles({"open": 100, "high": 104, "low": 99, "close": 103.5})

    context = EntryTriggerEngine().detect(_valid_context("BULLISH", candles))

    assert context.entry_status == "CONFIRMED"
    assert context.entry_trigger_type == "DISPLACEMENT"


def test_bearish_displacement_confirms_entry() -> None:
    candles = _body_average_candles({"open": 100, "high": 101, "low": 96, "close": 96.5})

    context = EntryTriggerEngine().detect(_valid_context("BEARISH", candles))

    assert context.entry_status == "CONFIRMED"
    assert context.entry_trigger_type == "DISPLACEMENT"


def test_displacement_has_priority_over_confirmation() -> None:
    candles = _body_average_candles({"open": 100, "high": 105, "low": 99, "close": 104})

    context = EntryTriggerEngine().detect(_valid_context("BULLISH", candles))

    assert context.entry_trigger_type == "DISPLACEMENT"


def test_no_confirmation_and_no_displacement_not_confirmed() -> None:
    candles = _candles(
        [
            {"open": 100, "high": 105, "low": 95, "close": 102},
            {"open": 101, "high": 104, "low": 99, "close": 100},
        ]
    )

    context = EntryTriggerEngine().detect(_valid_context("BULLISH", candles))

    assert context.entry_status == "NOT_CONFIRMED"
    assert context.entry_confirmed is False
    assert "NO_CONFIRMATION_CANDLE_OR_DISPLACEMENT" in context.entry_blockers


def test_missing_matched_poi_not_confirmed() -> None:
    context = _valid_context(
        "BULLISH",
        _candles(
            [
                {"open": 98, "high": 100, "low": 97, "close": 99},
                {"open": 99, "high": 102, "low": 98, "close": 101},
            ]
        ),
    )
    context.active_setup.matched_pois = []

    context = EntryTriggerEngine().detect(context)

    assert context.entry_status == "NOT_CONFIRMED"
    assert "NO_MATCHED_POI" in context.entry_blockers


def test_not_enough_candles_not_confirmed() -> None:
    context = EntryTriggerEngine().detect(
        _valid_context("BULLISH", _candles([{"open": 1, "high": 1, "low": 1, "close": 1}]))
    )

    assert context.entry_status == "NOT_CONFIRMED"
    assert "NOT_ENOUGH_CANDLES" in context.entry_blockers


def test_not_enough_displacement_candles_still_allows_confirmation() -> None:
    candles = _candles(
        [
            {"open": 98, "high": 100, "low": 97, "close": 99},
            {"open": 99, "high": 102, "low": 98, "close": 101},
        ]
    )

    context = EntryTriggerEngine().detect(_valid_context("BULLISH", candles))

    assert context.entry_status == "CONFIRMED"
    assert context.entry_trigger_type == "CONFIRMATION_CANDLE"


def test_zero_candle_range_does_not_crash() -> None:
    candles = _body_average_candles({"open": 100, "high": 100, "low": 100, "close": 100})

    context = EntryTriggerEngine().detect(_valid_context("BULLISH", candles))

    assert context.entry_status == "NOT_CONFIRMED"
    assert "NO_CONFIRMATION_CANDLE_OR_DISPLACEMENT" in context.entry_blockers


def test_existing_context_lists_are_preserved() -> None:
    context = _valid_context(
        "BULLISH",
        _candles(
            [
                {"open": 98, "high": 100, "low": 97, "close": 99},
                {"open": 99, "high": 102, "low": 98, "close": 101},
            ]
        ),
    )
    context.bos = ["bos"]
    context.choch = ["choch"]
    context.liquidity_sweeps = ["sweep"]
    context.fvgs = ["fvg"]
    context.order_blocks = ["order_block"]
    context.breaker_blocks = ["breaker"]
    context.ote = "ote"
    context.setups = ["setup"]
    active_setup = context.active_setup

    context = EntryTriggerEngine().detect(context)

    assert context.bos == ["bos"]
    assert context.choch == ["choch"]
    assert context.liquidity_sweeps == ["sweep"]
    assert context.fvgs == ["fvg"]
    assert context.order_blocks == ["order_block"]
    assert context.breaker_blocks == ["breaker"]
    assert context.ote == "ote"
    assert context.setups == ["setup"]
    assert context.active_setup is active_setup


def test_debug_values_are_populated() -> None:
    candles = _candles(
        [
            {"open": 98, "high": 100, "low": 97, "close": 99},
            {"open": 99, "high": 102, "low": 98, "close": 101},
        ]
    )

    context = EntryTriggerEngine().detect(_valid_context("BULLISH", candles))

    assert context.debug["entry_status"] == "CONFIRMED"
    assert context.debug["entry_direction"] == "BULLISH"
    assert context.debug["entry_trigger_type"] == "CONFIRMATION_CANDLE"
    assert context.debug["entry_confirmed"] is True
    assert context.debug["entry_blockers"] == []
