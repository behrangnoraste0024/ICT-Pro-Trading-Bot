from __future__ import annotations

import pandas as pd

from engine.ote.ote_engine import OTEEngine
from models.market_context import MarketContext


def _make_context(
    candles: list[dict],
    trend: str,
    dealing_range_high,
    dealing_range_low,
    current_price=None,
) -> MarketContext:
    context = MarketContext(candles=pd.DataFrame(candles))
    context.trend = trend
    context.dealing_range_high = dealing_range_high
    context.dealing_range_low = dealing_range_low
    context.current_price = current_price
    context.bos = ["bos"]
    context.choch = ["choch"]
    context.liquidity_sweeps = ["liquidity"]
    context.fvgs = ["fvg"]
    context.order_blocks = ["order_block"]
    context.breaker_blocks = ["breaker_block"]
    return context


def test_bullish_ote_calculation() -> None:
    context = _make_context(
        [{"close": 96}],
        trend="UPTREND",
        dealing_range_high=110,
        dealing_range_low=90,
        current_price=96,
    )

    context = OTEEngine().detect(context)

    assert context.ote_direction == "BULLISH"
    assert context.ote_level_62 == 97.6
    assert context.ote_level_705 == 95.9
    assert context.ote_level_79 == 94.2
    assert context.ote_lower_bound == 94.2
    assert context.ote_upper_bound == 97.6


def test_bearish_ote_calculation() -> None:
    context = _make_context(
        [{"close": 104}],
        trend="DOWNTREND",
        dealing_range_high=110,
        dealing_range_low=90,
        current_price=104,
    )

    context = OTEEngine().detect(context)

    assert context.ote_direction == "BEARISH"
    assert context.ote_level_62 == 102.4
    assert context.ote_level_705 == 104.1
    assert context.ote_level_79 == 105.8
    assert context.ote_lower_bound == 102.4
    assert context.ote_upper_bound == 105.8


def test_current_price_inside_bullish_ote() -> None:
    context = _make_context(
        [{"close": 96}],
        trend="UPTREND",
        dealing_range_high=110,
        dealing_range_low=90,
        current_price=96,
    )

    context = OTEEngine().detect(context)

    assert context.in_ote_zone is True


def test_current_price_outside_bullish_ote() -> None:
    context = _make_context(
        [{"close": 100}],
        trend="UPTREND",
        dealing_range_high=110,
        dealing_range_low=90,
        current_price=100,
    )

    context = OTEEngine().detect(context)

    assert context.in_ote_zone is False


def test_current_price_inside_bearish_ote() -> None:
    context = _make_context(
        [{"close": 104}],
        trend="DOWNTREND",
        dealing_range_high=110,
        dealing_range_low=90,
        current_price=104,
    )

    context = OTEEngine().detect(context)

    assert context.in_ote_zone is True


def test_range_trend_creates_no_ote() -> None:
    context = _make_context(
        [{"close": 100}],
        trend="RANGE",
        dealing_range_high=110,
        dealing_range_low=90,
    )

    context = OTEEngine().detect(context)

    assert context.ote is None
    assert context.ote_direction == "NONE"
    assert context.in_ote_zone is False


def test_unknown_trend_creates_no_ote() -> None:
    context = _make_context(
        [{"close": 100}],
        trend="UNKNOWN",
        dealing_range_high=110,
        dealing_range_low=90,
    )

    context = OTEEngine().detect(context)

    assert context.ote is None
    assert context.ote_direction == "NONE"


def test_invalid_dealing_range_creates_no_ote() -> None:
    context = _make_context(
        [{"close": 100}],
        trend="UPTREND",
        dealing_range_high=90,
        dealing_range_low=100,
    )

    context = OTEEngine().detect(context)

    assert context.ote is None
    assert context.ote_direction == "NONE"


def test_missing_range_values_creates_no_ote() -> None:
    context = _make_context(
        [{"close": 100}],
        trend="UPTREND",
        dealing_range_high=None,
        dealing_range_low=None,
    )

    context = OTEEngine().detect(context)

    assert context.ote is None
    assert context.ote_direction == "NONE"


def test_existing_context_lists_are_preserved() -> None:
    context = _make_context(
        [{"close": 100}],
        trend="UPTREND",
        dealing_range_high=110,
        dealing_range_low=90,
    )

    original_bos = list(context.bos)
    original_choch = list(context.choch)
    original_liquidity = list(context.liquidity_sweeps)
    original_fvgs = list(context.fvgs)
    original_order_blocks = list(context.order_blocks)
    original_breaker_blocks = list(context.breaker_blocks)

    context = OTEEngine().detect(context)

    assert context.bos == original_bos
    assert context.choch == original_choch
    assert context.liquidity_sweeps == original_liquidity
    assert context.fvgs == original_fvgs
    assert context.order_blocks == original_order_blocks
    assert context.breaker_blocks == original_breaker_blocks


def test_debug_values_are_populated() -> None:
    context = _make_context(
        [{"close": 105}],
        trend="UPTREND",
        dealing_range_high=110,
        dealing_range_low=90,
        current_price=105,
    )

    context = OTEEngine().detect(context)

    assert context.debug["ote_direction"] == "BULLISH"
    assert context.debug["ote_lower_bound"] == 94.2
    assert context.debug["ote_upper_bound"] == 97.6
    assert context.debug["ote_level_62"] == 97.6
    assert context.debug["ote_level_705"] == 95.9
    assert context.debug["ote_level_79"] == 94.2
    assert context.debug["in_ote_zone"] is False
