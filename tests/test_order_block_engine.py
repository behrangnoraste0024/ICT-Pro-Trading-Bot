from __future__ import annotations

import pandas as pd

from engine.order_block.order_block_engine import OrderBlockEngine
from models.bos_event import BOSEvent
from models.market_context import MarketContext


def _make_context(candles: list[dict]) -> MarketContext:
    df = pd.DataFrame(candles)
    return MarketContext(candles=df)


def test_bullish_order_block_from_bos() -> None:
    context = _make_context(
        [
            {"open": 10, "high": 11, "low": 9, "close": 10.5},
            {"open": 10.5, "high": 11.2, "low": 10.1, "close": 10.2},
            {"open": 10.2, "high": 10.8, "low": 9.9, "close": 10.6},
            {"open": 10.6, "high": 12.5, "low": 10.5, "close": 12.2},
        ]
    )
    context.bos = [BOSEvent(candle_index=3, level=11.5, direction="BULLISH", event_type="BOS")]

    context = OrderBlockEngine().detect(context)

    assert len(context.order_blocks) == 1
    block = context.order_blocks[0]
    assert block.direction == "BULLISH"
    assert block.source_event_type == "BOS"
    assert block.index == 1
    assert block.lower_bound == 10.1
    assert block.upper_bound == 11.2


def test_bearish_order_block_from_bos() -> None:
    context = _make_context(
        [
            {"open": 20, "high": 20.5, "low": 19.7, "close": 20.2},
            {"open": 20.2, "high": 20.8, "low": 20.0, "close": 20.6},
            {"open": 20.6, "high": 20.9, "low": 20.1, "close": 20.8},
            {"open": 20.8, "high": 21.0, "low": 19.0, "close": 19.2},
        ]
    )
    context.bos = [BOSEvent(candle_index=3, level=19.8, direction="BEARISH", event_type="BOS")]

    context = OrderBlockEngine().detect(context)

    assert len(context.order_blocks) == 1
    block = context.order_blocks[0]
    assert block.direction == "BEARISH"
    assert block.source_event_type == "BOS"
    assert block.index == 2
    assert block.lower_bound == 20.1
    assert block.upper_bound == 20.9


def test_bullish_order_block_from_choch() -> None:
    context = _make_context(
        [
            {"open": 10, "high": 11, "low": 9, "close": 10.5},
            {"open": 10.5, "high": 11.2, "low": 10.1, "close": 10.2},
            {"open": 10.2, "high": 10.8, "low": 9.9, "close": 10.6},
            {"open": 10.6, "high": 12.5, "low": 10.5, "close": 12.2},
        ]
    )
    context.choch = [BOSEvent(candle_index=3, level=11.5, direction="BULLISH", event_type="CHOCH")]

    context = OrderBlockEngine().detect(context)

    assert len(context.order_blocks) == 1
    assert context.order_blocks[0].source_event_type == "CHOCH"
    assert context.order_blocks[0].direction == "BULLISH"


def test_bearish_order_block_from_choch() -> None:
    context = _make_context(
        [
            {"open": 20, "high": 20.5, "low": 19.7, "close": 20.2},
            {"open": 20.2, "high": 20.8, "low": 20.0, "close": 20.6},
            {"open": 20.6, "high": 20.9, "low": 20.1, "close": 20.8},
            {"open": 20.8, "high": 21.0, "low": 19.0, "close": 19.2},
        ]
    )
    context.choch = [BOSEvent(candle_index=3, level=19.8, direction="BEARISH", event_type="CHOCH")]

    context = OrderBlockEngine().detect(context)

    assert len(context.order_blocks) == 1
    assert context.order_blocks[0].direction == "BEARISH"
    assert context.order_blocks[0].source_event_type == "CHOCH"


def test_no_valid_opposite_candle_means_no_order_block() -> None:
    context = _make_context(
        [
            {"open": 10, "high": 11, "low": 9, "close": 10.5},
            {"open": 10.5, "high": 11.2, "low": 10.1, "close": 10.7},
            {"open": 10.7, "high": 11.5, "low": 10.4, "close": 10.9},
        ]
    )
    context.bos = [BOSEvent(candle_index=2, level=11.0, direction="BULLISH", event_type="BOS")]

    context = OrderBlockEngine().detect(context)

    assert context.order_blocks == []


def test_duplicate_triggers_do_not_duplicate_order_blocks() -> None:
    context = _make_context(
        [
            {"open": 10, "high": 11, "low": 9, "close": 10.5},
            {"open": 10.5, "high": 11.2, "low": 10.1, "close": 10.2},
            {"open": 10.2, "high": 10.8, "low": 9.9, "close": 10.6},
            {"open": 10.6, "high": 12.5, "low": 10.5, "close": 12.2},
        ]
    )
    trigger = BOSEvent(candle_index=3, level=11.5, direction="BULLISH", event_type="BOS")
    context.bos = [trigger, trigger]

    context = OrderBlockEngine().detect(context)

    assert len(context.order_blocks) == 1


def test_order_block_detection_preserves_other_context_lists() -> None:
    context = _make_context(
        [
            {"open": 10, "high": 11, "low": 9, "close": 10.5},
            {"open": 10.5, "high": 11.2, "low": 10.1, "close": 10.2},
            {"open": 10.2, "high": 10.8, "low": 9.9, "close": 10.6},
            {"open": 10.6, "high": 12.5, "low": 10.5, "close": 12.2},
        ]
    )
    context.bos = [BOSEvent(candle_index=3, level=11.5, direction="BULLISH", event_type="BOS")]
    context.choch = [BOSEvent(candle_index=3, level=11.4, direction="BEARISH", event_type="CHOCH")]
    context.liquidity_sweeps = ["liquidity"]
    context.fvgs = ["fvg"]

    original_choch = list(context.choch)
    original_liquidity = list(context.liquidity_sweeps)
    original_fvgs = list(context.fvgs)

    context = OrderBlockEngine().detect(context)

    assert context.bos
    assert context.choch == original_choch
    assert context.liquidity_sweeps == original_liquidity
    assert context.fvgs == original_fvgs
