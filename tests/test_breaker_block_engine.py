from __future__ import annotations

import pandas as pd

from engine.breaker.breaker_block_engine import BreakerBlockEngine
from models.market_context import MarketContext
from models.order_block_event import OrderBlockEvent


def _make_context(candles: list[dict]) -> MarketContext:
    return MarketContext(candles=pd.DataFrame(candles))


def _bullish_order_block() -> OrderBlockEvent:
    return OrderBlockEvent(
        index=2,
        trigger_index=3,
        direction="BULLISH",
        lower_bound=10.0,
        upper_bound=11.0,
        open=10.5,
        high=11.0,
        low=10.0,
        close=10.2,
        source_event_type="BOS",
    )


def _bearish_order_block() -> OrderBlockEvent:
    return OrderBlockEvent(
        index=2,
        trigger_index=3,
        direction="BEARISH",
        lower_bound=20.0,
        upper_bound=21.0,
        open=20.2,
        high=21.0,
        low=20.0,
        close=20.8,
        source_event_type="CHOCH",
    )


def test_bullish_ob_becomes_bearish_breaker() -> None:
    context = _make_context(
        [
            {"open": 10.5, "high": 10.8, "low": 10.1, "close": 10.4},
            {"open": 10.4, "high": 10.7, "low": 10.0, "close": 10.2},
            {"open": 10.2, "high": 10.6, "low": 10.1, "close": 10.5},
            {"open": 10.5, "high": 11.4, "low": 10.2, "close": 11.2},
            {"open": 11.2, "high": 11.3, "low": 9.4, "close": 9.6},
        ]
    )
    context.order_blocks = [_bullish_order_block()]

    context = BreakerBlockEngine().detect(context)

    assert len(context.breaker_blocks) == 1
    breaker = context.breaker_blocks[0]
    assert breaker.direction == "BEARISH"
    assert breaker.original_order_block_direction == "BULLISH"
    assert breaker.source_order_block_index == 2
    assert breaker.invalidation_index == 4
    assert context.order_blocks[0].invalidated is True
    assert context.order_blocks[0].active is False
    assert context.order_blocks[0].invalidation_index == 4


def test_wick_only_below_bullish_ob_does_not_create_breaker() -> None:
    context = _make_context(
        [
            {"open": 10.5, "high": 10.8, "low": 10.1, "close": 10.4},
            {"open": 10.4, "high": 10.7, "low": 10.0, "close": 10.2},
            {"open": 10.2, "high": 10.6, "low": 10.1, "close": 10.5},
            {"open": 10.5, "high": 11.4, "low": 10.2, "close": 11.2},
            {"open": 11.2, "high": 11.3, "low": 9.4, "close": 10.1},
        ]
    )
    context.order_blocks = [_bullish_order_block()]

    context = BreakerBlockEngine().detect(context)

    assert context.breaker_blocks == []
    assert context.order_blocks[0].invalidated is False
    assert context.order_blocks[0].active is True


def test_bearish_ob_becomes_bullish_breaker() -> None:
    context = _make_context(
        [
            {"open": 20.5, "high": 20.8, "low": 20.1, "close": 20.4},
            {"open": 20.4, "high": 20.7, "low": 20.0, "close": 20.2},
            {"open": 20.2, "high": 20.6, "low": 20.1, "close": 20.3},
            {"open": 20.3, "high": 19.8, "low": 19.2, "close": 19.4},
            {"open": 19.4, "high": 21.4, "low": 19.3, "close": 21.2},
        ]
    )
    context.order_blocks = [_bearish_order_block()]

    context = BreakerBlockEngine().detect(context)

    assert len(context.breaker_blocks) == 1
    breaker = context.breaker_blocks[0]
    assert breaker.direction == "BULLISH"
    assert breaker.original_order_block_direction == "BEARISH"
    assert breaker.source_order_block_index == 2
    assert breaker.invalidation_index == 4
    assert context.order_blocks[0].invalidated is True
    assert context.order_blocks[0].active is False


def test_wick_only_above_bearish_ob_does_not_create_breaker() -> None:
    context = _make_context(
        [
            {"open": 20.5, "high": 20.8, "low": 20.1, "close": 20.4},
            {"open": 20.4, "high": 20.7, "low": 20.0, "close": 20.2},
            {"open": 20.2, "high": 20.6, "low": 20.1, "close": 20.3},
            {"open": 20.3, "high": 19.8, "low": 19.2, "close": 19.4},
            {"open": 19.4, "high": 21.4, "low": 19.3, "close": 20.9},
        ]
    )
    context.order_blocks = [_bearish_order_block()]

    context = BreakerBlockEngine().detect(context)

    assert context.breaker_blocks == []
    assert context.order_blocks[0].invalidated is False
    assert context.order_blocks[0].active is True


def test_breaker_scan_starts_only_after_trigger_index() -> None:
    context = _make_context(
        [
            {"open": 10.5, "high": 10.8, "low": 10.1, "close": 9.6},
            {"open": 10.4, "high": 10.7, "low": 10.0, "close": 10.2},
            {"open": 10.2, "high": 10.6, "low": 10.1, "close": 10.5},
            {"open": 10.5, "high": 11.4, "low": 10.2, "close": 11.2},
            {"open": 11.2, "high": 11.3, "low": 9.4, "close": 9.6},
        ]
    )
    context.order_blocks = [_bullish_order_block()]

    context = BreakerBlockEngine().detect(context)

    assert len(context.breaker_blocks) == 1
    assert context.breaker_blocks[0].invalidation_index == 4


def test_duplicate_breakers_are_not_created() -> None:
    context = _make_context(
        [
            {"open": 10.5, "high": 10.8, "low": 10.1, "close": 10.4},
            {"open": 10.4, "high": 10.7, "low": 10.0, "close": 10.2},
            {"open": 10.2, "high": 10.6, "low": 10.1, "close": 10.5},
            {"open": 10.5, "high": 11.4, "low": 10.2, "close": 11.2},
            {"open": 11.2, "high": 11.3, "low": 9.4, "close": 9.6},
        ]
    )
    order_block = _bullish_order_block()
    context.order_blocks = [order_block, OrderBlockEvent(**order_block.__dict__)]

    context = BreakerBlockEngine().detect(context)

    assert len(context.breaker_blocks) == 1


def test_context_lists_are_preserved_and_debug_values_exist() -> None:
    context = _make_context(
        [
            {"open": 10.5, "high": 10.8, "low": 10.1, "close": 10.4},
            {"open": 10.4, "high": 10.7, "low": 10.0, "close": 10.2},
            {"open": 10.2, "high": 10.6, "low": 10.1, "close": 10.5},
            {"open": 10.5, "high": 11.4, "low": 10.2, "close": 11.2},
            {"open": 11.2, "high": 11.3, "low": 9.4, "close": 9.6},
        ]
    )
    context.bos = ["bos"]
    context.choch = ["choch"]
    context.liquidity_sweeps = ["liquidity"]
    context.fvgs = ["fvg"]
    context.order_blocks = [_bullish_order_block()]

    context = BreakerBlockEngine().detect(context)

    assert context.bos == ["bos"]
    assert context.choch == ["choch"]
    assert context.liquidity_sweeps == ["liquidity"]
    assert context.fvgs == ["fvg"]
    assert context.order_blocks
    assert context.debug["breaker_blocks_total"] == 1
    assert context.debug["bullish_breaker_blocks"] == 0
    assert context.debug["bearish_breaker_blocks"] == 1
    assert context.debug["invalidated_order_blocks"] == 1
