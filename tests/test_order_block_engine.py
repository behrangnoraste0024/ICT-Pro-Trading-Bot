from __future__ import annotations

import pandas as pd

from engine.order_block.order_block_engine import OrderBlockEngine
from models.bos_event import BOSEvent
from models.market_context import MarketContext


def _make_context(candles: list[dict]) -> MarketContext:
    return MarketContext(candles=pd.DataFrame(candles))


def _run_engine(context: MarketContext) -> MarketContext:
    return OrderBlockEngine().detect(context)


def test_bullish_order_block_no_mitigation() -> None:
    context = _make_context(
        [
            {"open": 10.0, "high": 10.4, "low": 9.8, "close": 10.2},
            {"open": 10.2, "high": 10.3, "low": 9.7, "close": 9.9},
            {"open": 9.9, "high": 10.2, "low": 9.8, "close": 10.0},
            {"open": 10.0, "high": 11.6, "low": 10.7, "close": 11.4},
            {"open": 11.4, "high": 11.7, "low": 11.3, "close": 11.5},
            {"open": 11.5, "high": 11.8, "low": 11.4, "close": 11.6},
        ]
    )
    context.bos = [BOSEvent(candle_index=3, level=11.0, direction="BULLISH", event_type="BOS")]

    context = _run_engine(context)

    assert len(context.order_blocks) == 1
    order_block = context.order_blocks[0]
    assert order_block.mitigation_type == "NONE"
    assert order_block.mitigation_index is None
    assert order_block.mitigated is False
    assert order_block.active is True


def test_bullish_order_block_partial_mitigation() -> None:
    context = _make_context(
        [
            {"open": 10.0, "high": 10.4, "low": 9.8, "close": 10.2},
            {"open": 10.2, "high": 10.3, "low": 9.7, "close": 9.9},
            {"open": 9.9, "high": 10.2, "low": 9.8, "close": 10.0},
            {"open": 10.0, "high": 11.6, "low": 10.7, "close": 11.4},
            {"open": 11.4, "high": 11.7, "low": 10.0, "close": 11.0},
            {"open": 11.0, "high": 11.8, "low": 11.4, "close": 11.6},
        ]
    )
    context.bos = [BOSEvent(candle_index=3, level=11.0, direction="BULLISH", event_type="BOS")]

    context = _run_engine(context)

    order_block = context.order_blocks[0]
    assert order_block.mitigation_type == "PARTIAL"
    assert order_block.mitigation_index == 4
    assert order_block.mitigated is True
    assert order_block.active is True


def test_bullish_order_block_full_mitigation() -> None:
    context = _make_context(
        [
            {"open": 10.0, "high": 10.4, "low": 9.8, "close": 10.2},
            {"open": 10.2, "high": 10.3, "low": 9.7, "close": 9.9},
            {"open": 9.9, "high": 10.2, "low": 9.8, "close": 10.0},
            {"open": 10.0, "high": 11.6, "low": 10.7, "close": 11.4},
            {"open": 11.4, "high": 11.7, "low": 9.6, "close": 10.2},
            {"open": 10.2, "high": 11.8, "low": 11.4, "close": 11.6},
        ]
    )
    context.bos = [BOSEvent(candle_index=3, level=11.0, direction="BULLISH", event_type="BOS")]

    context = _run_engine(context)

    order_block = context.order_blocks[0]
    assert order_block.mitigation_type == "FULL"
    assert order_block.mitigation_index == 4
    assert order_block.mitigated is True
    assert order_block.active is False


def test_bearish_order_block_no_mitigation() -> None:
    context = _make_context(
        [
            {"open": 12.0, "high": 12.5, "low": 11.8, "close": 12.3},
            {"open": 12.3, "high": 12.6, "low": 12.0, "close": 12.4},
            {"open": 12.4, "high": 12.7, "low": 12.1, "close": 12.5},
            {"open": 12.5, "high": 11.5, "low": 10.9, "close": 11.1},
            {"open": 11.1, "high": 11.2, "low": 10.8, "close": 11.0},
        ]
    )
    context.bos = [BOSEvent(candle_index=3, level=11.0, direction="BEARISH", event_type="BOS")]

    context = _run_engine(context)

    order_block = context.order_blocks[0]
    assert order_block.mitigation_type == "NONE"
    assert order_block.mitigation_index is None
    assert order_block.mitigated is False
    assert order_block.active is True


def test_bearish_order_block_partial_mitigation() -> None:
    context = _make_context(
        [
            {"open": 12.0, "high": 12.5, "low": 11.8, "close": 12.3},
            {"open": 12.3, "high": 12.6, "low": 12.0, "close": 12.4},
            {"open": 12.4, "high": 12.7, "low": 12.1, "close": 12.5},
            {"open": 12.5, "high": 11.5, "low": 10.9, "close": 11.1},
            {"open": 11.1, "high": 12.3, "low": 10.8, "close": 11.0},
        ]
    )
    context.bos = [BOSEvent(candle_index=3, level=11.0, direction="BEARISH", event_type="BOS")]

    context = _run_engine(context)

    order_block = context.order_blocks[0]
    assert order_block.mitigation_type == "PARTIAL"
    assert order_block.mitigation_index == 4
    assert order_block.mitigated is True
    assert order_block.active is True


def test_bearish_order_block_full_mitigation() -> None:
    context = _make_context(
        [
            {"open": 12.0, "high": 12.5, "low": 11.8, "close": 12.3},
            {"open": 12.3, "high": 12.6, "low": 12.0, "close": 12.4},
            {"open": 12.4, "high": 12.7, "low": 12.1, "close": 12.5},
            {"open": 12.5, "high": 11.5, "low": 10.9, "close": 11.1},
            {"open": 11.1, "high": 12.9, "low": 10.8, "close": 12.2},
        ]
    )
    context.bos = [BOSEvent(candle_index=3, level=11.0, direction="BEARISH", event_type="BOS")]

    context = _run_engine(context)

    order_block = context.order_blocks[0]
    assert order_block.mitigation_type == "FULL"
    assert order_block.mitigation_index == 4
    assert order_block.mitigated is True
    assert order_block.active is False


def test_full_priority_over_partial_for_bullish_and_bearish() -> None:
    bullish_context = _make_context(
        [
            {"open": 10.0, "high": 10.4, "low": 9.8, "close": 10.2},
            {"open": 10.2, "high": 10.3, "low": 9.7, "close": 9.9},
            {"open": 9.9, "high": 10.2, "low": 9.8, "close": 10.0},
            {"open": 10.0, "high": 11.6, "low": 10.7, "close": 11.4},
            {"open": 11.4, "high": 11.7, "low": 9.6, "close": 10.2},
        ]
    )
    bullish_context.bos = [BOSEvent(candle_index=3, level=11.0, direction="BULLISH", event_type="BOS")]

    bullish_context = _run_engine(bullish_context)

    bullish_block = bullish_context.order_blocks[0]
    assert bullish_block.mitigation_type == "FULL"
    assert bullish_block.active is False

    bearish_context = _make_context(
        [
            {"open": 12.0, "high": 12.5, "low": 11.8, "close": 12.3},
            {"open": 12.3, "high": 12.6, "low": 12.0, "close": 12.4},
            {"open": 12.4, "high": 12.7, "low": 12.1, "close": 12.5},
            {"open": 12.5, "high": 11.5, "low": 10.9, "close": 11.1},
            {"open": 11.1, "high": 12.9, "low": 10.8, "close": 12.2},
        ]
    )
    bearish_context.bos = [BOSEvent(candle_index=3, level=11.0, direction="BEARISH", event_type="BOS")]

    bearish_context = _run_engine(bearish_context)

    bearish_block = bearish_context.order_blocks[0]
    assert bearish_block.mitigation_type == "FULL"
    assert bearish_block.active is False


def test_mitigation_starts_only_after_trigger_index() -> None:
    context = _make_context(
        [
            {"open": 10.0, "high": 10.4, "low": 9.8, "close": 10.2},
            {"open": 10.2, "high": 10.3, "low": 9.7, "close": 9.9},
            {"open": 9.9, "high": 10.2, "low": 9.8, "close": 10.0},
            {"open": 10.0, "high": 11.6, "low": 9.6, "close": 11.4},
            {"open": 11.4, "high": 11.7, "low": 11.3, "close": 11.5},
        ]
    )
    context.bos = [BOSEvent(candle_index=3, level=11.0, direction="BULLISH", event_type="BOS")]

    context = _run_engine(context)

    order_block = context.order_blocks[0]
    assert order_block.mitigation_type == "NONE"
    assert order_block.mitigation_index is None


def test_duplicate_triggers_do_not_duplicate_order_blocks() -> None:
    context = _make_context(
        [
            {"open": 10.0, "high": 10.4, "low": 9.8, "close": 10.2},
            {"open": 10.2, "high": 10.3, "low": 9.7, "close": 9.9},
            {"open": 9.9, "high": 10.2, "low": 9.8, "close": 10.0},
            {"open": 10.0, "high": 11.6, "low": 10.7, "close": 11.4},
            {"open": 11.4, "high": 11.7, "low": 10.6, "close": 11.0},
        ]
    )
    trigger = BOSEvent(candle_index=3, level=11.0, direction="BULLISH", event_type="BOS")
    context.bos = [trigger, trigger]

    context = _run_engine(context)

    assert len(context.order_blocks) == 1


def test_order_block_detection_preserves_other_context_lists() -> None:
    context = _make_context(
        [
            {"open": 10.0, "high": 10.4, "low": 9.8, "close": 10.2},
            {"open": 10.2, "high": 10.3, "low": 9.7, "close": 9.9},
            {"open": 9.9, "high": 10.2, "low": 9.8, "close": 10.0},
            {"open": 10.0, "high": 11.6, "low": 10.7, "close": 11.4},
            {"open": 11.4, "high": 11.7, "low": 10.6, "close": 11.0},
        ]
    )
    context.bos = [BOSEvent(candle_index=3, level=11.0, direction="BULLISH", event_type="BOS")]
    context.choch = [BOSEvent(candle_index=3, level=11.0, direction="BEARISH", event_type="CHOCH")]
    context.liquidity_sweeps = ["liquidity"]
    context.fvgs = ["fvg"]

    original_bos = list(context.bos)
    original_choch = list(context.choch)
    original_liquidity = list(context.liquidity_sweeps)
    original_fvgs = list(context.fvgs)

    context = _run_engine(context)

    assert context.bos == original_bos
    assert context.choch == original_choch
    assert context.liquidity_sweeps == original_liquidity
    assert context.fvgs == original_fvgs
