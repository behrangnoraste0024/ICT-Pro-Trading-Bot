from __future__ import annotations

import pandas as pd

from engine.premium_discount.premium_discount_engine import PremiumDiscountEngine
from models.market_context import MarketContext


def _make_context(candles: list[dict], external_high=None, external_low=None) -> MarketContext:
    context = MarketContext(candles=pd.DataFrame(candles))
    context.external_high = external_high
    context.external_low = external_low
    context.bos = ["bos"]
    context.choch = ["choch"]
    context.liquidity_sweeps = ["liquidity"]
    context.fvgs = ["fvg"]
    context.order_blocks = ["order_block"]
    context.breaker_blocks = ["breaker_block"]
    return context


def test_valid_dealing_range_calculates_equilibrium() -> None:
    context = _make_context(
        [{"close": 95}, {"close": 105}],
        external_high=110,
        external_low=90,
    )

    context = PremiumDiscountEngine().detect(context)

    assert context.equilibrium == 100
    assert context.premium_zone == {"lower_bound": 100, "upper_bound": 110}
    assert context.discount_zone == {"lower_bound": 90, "upper_bound": 100}


def test_current_price_above_equilibrium_is_premium() -> None:
    context = _make_context(
        [{"close": 95}, {"close": 105}],
        external_high=110,
        external_low=90,
    )

    context = PremiumDiscountEngine().detect(context)

    assert context.current_price_zone == "PREMIUM"


def test_current_price_below_equilibrium_is_discount() -> None:
    context = _make_context(
        [{"close": 95}, {"close": 95}],
        external_high=110,
        external_low=90,
    )

    context = PremiumDiscountEngine().detect(context)

    assert context.current_price_zone == "DISCOUNT"


def test_current_price_equal_equilibrium_is_equilibrium() -> None:
    context = _make_context(
        [{"close": 95}, {"close": 100}],
        external_high=110,
        external_low=90,
    )

    context = PremiumDiscountEngine().detect(context)

    assert context.current_price_zone == "EQUILIBRIUM"


def test_invalid_missing_external_values_returns_unknown() -> None:
    context = _make_context(
        [{"close": 95}, {"close": 100}],
        external_high=None,
        external_low=None,
    )

    context = PremiumDiscountEngine().detect(context)

    assert context.current_price_zone == "UNKNOWN"
    assert context.equilibrium is None
    assert context.premium_zone is None
    assert context.discount_zone is None


def test_invalid_range_high_less_than_or_equal_low_returns_unknown() -> None:
    context = _make_context(
        [{"close": 95}, {"close": 100}],
        external_high=90,
        external_low=100,
    )

    context = PremiumDiscountEngine().detect(context)

    assert context.current_price_zone == "UNKNOWN"
    assert context.equilibrium is None


def test_empty_candles_do_not_crash() -> None:
    context = MarketContext(candles=pd.DataFrame())
    context.external_high = 110
    context.external_low = 90

    context = PremiumDiscountEngine().detect(context)

    assert context.current_price is None
    assert context.current_price_zone == "UNKNOWN"


def test_existing_context_lists_are_preserved() -> None:
    context = _make_context(
        [{"close": 95}, {"close": 100}],
        external_high=110,
        external_low=90,
    )

    original_bos = list(context.bos)
    original_choch = list(context.choch)
    original_liquidity_sweeps = list(context.liquidity_sweeps)
    original_fvgs = list(context.fvgs)
    original_order_blocks = list(context.order_blocks)
    original_breaker_blocks = list(context.breaker_blocks)

    context = PremiumDiscountEngine().detect(context)

    assert context.bos == original_bos
    assert context.choch == original_choch
    assert context.liquidity_sweeps == original_liquidity_sweeps
    assert context.fvgs == original_fvgs
    assert context.order_blocks == original_order_blocks
    assert context.breaker_blocks == original_breaker_blocks


def test_debug_values_are_populated() -> None:
    context = _make_context(
        [{"close": 95}, {"close": 105}],
        external_high=110,
        external_low=90,
    )

    context = PremiumDiscountEngine().detect(context)

    assert context.debug["dealing_range_high"] == 110
    assert context.debug["dealing_range_low"] == 90
    assert context.debug["equilibrium"] == 100
    assert context.debug["current_price"] == 105
    assert context.debug["current_price_zone"] == "PREMIUM"
