from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from engine.setup.setup_engine import SetupEngine
from models.market_context import MarketContext
from models.setup_event import SetupEvent


def _sweep(candle_index: int, direction: str) -> SimpleNamespace:
    return SimpleNamespace(candle_index=candle_index, direction=direction)


def _poi(direction: str, lower_bound: float = 95, upper_bound: float = 105, active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        index=10,
        direction=direction,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        active=active,
        event_type="FVG",
    )


def _order_block(
    direction: str,
    lower_bound: float = 95,
    upper_bound: float = 105,
    active: bool = True,
    invalidated: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        index=11,
        direction=direction,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        active=active,
        invalidated=invalidated,
        event_type="ORDER_BLOCK",
    )


def _breaker(direction: str, lower_bound: float = 95, upper_bound: float = 105) -> SimpleNamespace:
    return SimpleNamespace(
        index=12,
        direction=direction,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        active=True,
        event_type="BREAKER_BLOCK",
    )


def _base_context(direction: str = "BULLISH") -> MarketContext:
    context = MarketContext(candles=pd.DataFrame([{"close": 100}] * 100))
    context.current_price = 100
    context.bos = ["bos"]
    context.choch = ["choch"]
    context.liquidity_sweeps = []
    context.fvgs = []
    context.order_blocks = []
    context.breaker_blocks = []
    context.ote = "ote"

    if direction == "BULLISH":
        context.trend = "UPTREND"
        context.current_price_zone = "DISCOUNT"
        context.ote_direction = "BULLISH"
        context.liquidity_sweeps = [_sweep(99, "SELL_SIDE")]
        context.fvgs = [_poi("BULLISH")]
    else:
        context.trend = "DOWNTREND"
        context.current_price_zone = "PREMIUM"
        context.ote_direction = "BEARISH"
        context.liquidity_sweeps = [_sweep(99, "BUY_SIDE")]
        context.fvgs = [_poi("BEARISH")]

    context.in_ote_zone = True
    return context


def test_valid_bullish_setup() -> None:
    context = SetupEngine().detect(_base_context("BULLISH"))

    assert context.setup_status == "VALID"
    assert context.setup_bias == "BULLISH"
    assert context.setup_score == 100
    assert context.active_setup is not None


def test_valid_bearish_setup() -> None:
    context = SetupEngine().detect(_base_context("BEARISH"))

    assert context.setup_status == "VALID"
    assert context.setup_bias == "BEARISH"
    assert context.setup_score == 100


def test_bullish_wrong_trend_invalid() -> None:
    context = _base_context("BULLISH")
    context.trend = "DOWNTREND"

    context = SetupEngine().detect(context)

    assert context.setup_status == "INVALID"
    assert "WRONG_TREND" in context.setup_blockers


def test_wrong_price_zone_invalid() -> None:
    context = _base_context("BULLISH")
    context.current_price_zone = "PREMIUM"

    context = SetupEngine().detect(context)

    assert context.setup_status == "INVALID"
    assert "WRONG_PRICE_ZONE" in context.setup_blockers


def test_ote_not_aligned_invalid() -> None:
    context = _base_context("BULLISH")
    context.ote_direction = "BEARISH"

    context = SetupEngine().detect(context)

    assert context.setup_status == "INVALID"
    assert "OTE_NOT_ALIGNED" in context.setup_blockers


def test_price_not_in_ote_invalid() -> None:
    context = _base_context("BULLISH")
    context.in_ote_zone = False

    context = SetupEngine().detect(context)

    assert context.setup_status == "INVALID"
    assert "PRICE_NOT_IN_OTE" in context.setup_blockers


def test_no_recent_liquidity_sweep_invalid() -> None:
    context = _base_context("BULLISH")
    context.liquidity_sweeps = [_sweep(20, "SELL_SIDE")]

    context = SetupEngine().detect(context)

    assert context.setup_status == "INVALID"
    assert "NO_RECENT_LIQUIDITY_SWEEP" in context.setup_blockers


def test_no_active_poi_at_price_invalid() -> None:
    context = _base_context("BULLISH")
    context.fvgs = [_poi("BULLISH", lower_bound=101, upper_bound=105)]

    context = SetupEngine().detect(context)

    assert context.setup_status == "INVALID"
    assert "NO_ACTIVE_POI_AT_PRICE" in context.setup_blockers


def test_inactive_poi_does_not_count() -> None:
    context = _base_context("BULLISH")
    context.fvgs = [_poi("BULLISH", active=False)]

    context = SetupEngine().detect(context)

    assert context.setup_status == "INVALID"
    assert "NO_ACTIVE_POI_AT_PRICE" in context.setup_blockers


def test_invalidated_order_block_does_not_count() -> None:
    context = _base_context("BULLISH")
    context.fvgs = []
    context.order_blocks = [_order_block("BULLISH", invalidated=True)]

    context = SetupEngine().detect(context)

    assert context.setup_status == "INVALID"
    assert "NO_ACTIVE_POI_AT_PRICE" in context.setup_blockers


def test_breaker_block_can_count_as_poi() -> None:
    context = _base_context("BULLISH")
    context.fvgs = []
    context.breaker_blocks = [_breaker("BULLISH")]

    context = SetupEngine().detect(context)

    assert context.setup_status == "VALID"
    assert context.setup_bias == "BULLISH"


def test_existing_context_lists_and_ote_are_preserved() -> None:
    context = _base_context("BULLISH")
    original_bos = list(context.bos)
    original_choch = list(context.choch)
    original_liquidity = list(context.liquidity_sweeps)
    original_fvgs = list(context.fvgs)
    original_order_blocks = list(context.order_blocks)
    original_breaker_blocks = list(context.breaker_blocks)
    original_ote = context.ote

    context = SetupEngine().detect(context)

    assert context.bos == original_bos
    assert context.choch == original_choch
    assert context.liquidity_sweeps == original_liquidity
    assert context.fvgs == original_fvgs
    assert context.order_blocks == original_order_blocks
    assert context.breaker_blocks == original_breaker_blocks
    assert context.ote == original_ote


def test_both_valid_setups_conflict_safety() -> None:
    class ConflictSetupEngine(SetupEngine):
        def _evaluate_direction(self, context: MarketContext, direction: str) -> SetupEvent:
            return SetupEvent(
                direction=direction,
                status="VALID",
                score=100,
                matched_pois=["POI"],
            )

    context = ConflictSetupEngine().detect(_base_context("BULLISH"))

    assert context.setup_bias == "CONFLICT"
    assert context.setup_status == "INVALID"
    assert "CONFLICTING_SETUPS" in context.setup_blockers


def test_debug_values_are_populated() -> None:
    context = SetupEngine().detect(_base_context("BULLISH"))

    assert context.debug["setup_bias"] == "BULLISH"
    assert context.debug["setup_score"] == 100
    assert context.debug["setup_status"] == "VALID"
    assert context.debug["setup_blockers"] == []
