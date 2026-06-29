import pandas as pd

from engine.structure_engine_v2 import StructureEngineV2
from models.bos_event import BOSEvent
from models.market_context import MarketContext
from models.structure_event import StructureEvent
from models.swing_point import SwingPoint


def make_candles(closes: list[float], highs: list[float] | None = None, lows: list[float] | None = None) -> pd.DataFrame:
    highs = highs or closes
    lows = lows or closes

    return pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1.0] * len(closes),
        }
    )


def event(index: int, price: float, swing_type: str) -> StructureEvent:
    return StructureEvent(index=index, price=price, swing_type=swing_type)


def build_context(structure: list[StructureEvent], candles: pd.DataFrame, trend: str = "UNKNOWN") -> MarketContext:
    context = MarketContext(candles=candles, structure=structure, trend=trend)
    return StructureEngineV2().build(context)


def test_classify_structure_populates_events_and_labels_swings() -> None:
    context = MarketContext(
        swings=[
            SwingPoint(index=1, price=10.0, swing_type="HIGH"),
            SwingPoint(index=2, price=5.0, swing_type="LOW"),
            SwingPoint(index=3, price=9.0, swing_type="HIGH"),
            SwingPoint(index=4, price=6.0, swing_type="LOW"),
            SwingPoint(index=5, price=11.0, swing_type="HIGH"),
            SwingPoint(index=6, price=4.0, swing_type="LOW"),
        ]
    )

    StructureEngineV2().classify_structure(context)

    assert [item.label for item in context.structure] == ["HH", "HL", "LH", "HL", "HH", "LL"]
    assert [swing.label for swing in context.swings] == ["HH", "HL", "LH", "HL", "HH", "LL"]


def test_bullish_bos_requires_close_break_not_wick() -> None:
    context = build_context(
        structure=[
            event(index=1, price=10.0, swing_type="HIGH"),
            event(index=2, price=5.0, swing_type="LOW"),
            event(index=4, price=12.0, swing_type="HIGH"),
        ],
        candles=make_candles(
            closes=[8.0, 9.0, 8.0, 9.8, 10.1, 11.0],
            highs=[8.0, 10.0, 8.0, 11.0, 10.2, 11.2],
            lows=[7.0, 8.0, 5.0, 8.0, 9.0, 10.0],
        ),
    )

    assert len(context.bos) == 1
    assert context.bos[0].direction == "BULLISH"
    assert context.bos[0].level == 10.0
    assert context.bos[0].candle_index == 4


def test_bullish_wick_only_break_does_not_create_bos() -> None:
    context = build_context(
        structure=[
            event(index=1, price=10.0, swing_type="HIGH"),
            event(index=2, price=5.0, swing_type="LOW"),
            event(index=4, price=12.0, swing_type="HIGH"),
        ],
        candles=make_candles(
            closes=[8.0, 9.0, 8.0, 9.8, 9.9, 9.7],
            highs=[8.0, 10.0, 8.0, 11.0, 10.8, 10.4],
            lows=[7.0, 8.0, 5.0, 8.0, 9.0, 9.0],
        ),
    )

    assert context.bos == []
    assert all(not item.bos for item in context.structure)


def test_bearish_bos_requires_close_break_not_wick() -> None:
    context = build_context(
        structure=[
            event(index=1, price=10.0, swing_type="LOW"),
            event(index=2, price=20.0, swing_type="HIGH"),
            event(index=4, price=8.0, swing_type="LOW"),
        ],
        candles=make_candles(
            closes=[15.0, 11.0, 15.0, 10.2, 9.5, 8.5],
            highs=[16.0, 12.0, 20.0, 12.0, 10.0, 9.0],
            lows=[14.0, 10.0, 14.0, 9.0, 9.2, 8.2],
        ),
    )

    assert len(context.bos) == 1
    assert context.bos[0].direction == "BEARISH"
    assert context.bos[0].level == 10.0
    assert context.bos[0].candle_index == 4


def test_bearish_wick_only_break_does_not_create_bos() -> None:
    context = build_context(
        structure=[
            event(index=1, price=10.0, swing_type="LOW"),
            event(index=2, price=20.0, swing_type="HIGH"),
            event(index=4, price=8.0, swing_type="LOW"),
        ],
        candles=make_candles(
            closes=[15.0, 11.0, 15.0, 10.2, 10.1, 10.3],
            highs=[16.0, 12.0, 20.0, 12.0, 10.5, 10.6],
            lows=[14.0, 10.0, 14.0, 9.0, 9.2, 9.4],
        ),
    )

    assert context.bos == []
    assert all(not item.bos for item in context.structure)


def test_choch_is_separate_from_bos_events() -> None:
    context = build_context(
        structure=[
            event(index=1, price=10.0, swing_type="HIGH"),
            event(index=2, price=5.0, swing_type="LOW"),
            event(index=3, price=12.0, swing_type="HIGH"),
            event(index=4, price=8.0, swing_type="LOW"),
        ],
        candles=make_candles(
            closes=[8.0, 9.0, 6.0, 10.5, 8.5, 4.5],
            highs=[8.0, 10.0, 7.0, 12.0, 9.0, 5.0],
            lows=[7.0, 8.0, 5.0, 9.0, 8.0, 4.0],
        ),
    )

    assert [item.event_type for item in context.bos] == ["BOS"]
    assert [item.event_type for item in context.choch] == ["CHOCH"]
    assert context.choch[0].direction == "BEARISH"


def test_internal_structure_break_is_not_bos() -> None:
    context = build_context(
        structure=[
            event(index=1, price=10.0, swing_type="HIGH"),
            event(index=2, price=5.0, swing_type="LOW"),
            event(index=3, price=9.0, swing_type="HIGH"),
        ],
        candles=make_candles(
            closes=[8.0, 9.0, 6.0, 9.2, 9.5],
            highs=[8.0, 10.0, 7.0, 9.4, 9.8],
            lows=[7.0, 8.0, 5.0, 8.0, 8.2],
        ),
    )

    internal_highs = [item for item in context.structure if item.swing_type == "HIGH" and item.is_internal]

    assert internal_highs
    assert context.bos == []
    assert all(not item.bos for item in internal_highs)


def test_detect_trend_prefers_latest_bos_or_choch_event() -> None:
    engine = StructureEngineV2()

    bullish_bos = MarketContext(bos=[BOSEvent(1, 10.0, "BULLISH", "BOS")])
    bearish_bos = MarketContext(bos=[BOSEvent(1, 10.0, "BEARISH", "BOS")])
    bearish_choch = MarketContext(
        bos=[BOSEvent(1, 10.0, "BULLISH", "BOS")],
        choch=[BOSEvent(2, 5.0, "BEARISH", "CHOCH")],
    )
    bullish_choch = MarketContext(
        bos=[BOSEvent(1, 5.0, "BEARISH", "BOS")],
        choch=[BOSEvent(2, 10.0, "BULLISH", "CHOCH")],
    )

    assert engine.detect_trend(bullish_bos).trend == "UPTREND"
    assert engine.detect_trend(bearish_bos).trend == "DOWNTREND"
    assert engine.detect_trend(bearish_choch).trend == "DOWNTREND"
    assert engine.detect_trend(bullish_choch).trend == "UPTREND"
