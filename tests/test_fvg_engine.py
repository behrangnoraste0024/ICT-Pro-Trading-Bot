import pandas as pd

from engine.fvg_engine import FVGEngine
from engine.ict_engine import ICTEngine
from engine.liquidity_engine import LiquidityEngine
from engine.structure_engine_v2 import StructureEngineV2
from models.market_context import MarketContext
from models.structure_event import StructureEvent


def make_candles(
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> pd.DataFrame:
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


def make_context(candles: pd.DataFrame) -> MarketContext:
    return MarketContext(candles=candles)


def test_bullish_fvg_detection() -> None:
    context = make_context(
        make_candles(
            closes=[10.0, 11.0, 13.0],
            highs=[10.0, 11.0, 11.5],
            lows=[9.0, 10.0, 12.2],
        )
    )

    FVGEngine().detect(context)

    assert len(context.fvgs) == 1
    fvg = context.fvgs[0]
    assert fvg.direction == "BULLISH"
    assert fvg.lower_bound == 10.0
    assert fvg.upper_bound == 12.2


def test_bearish_fvg_detection() -> None:
    context = make_context(
        make_candles(
            closes=[13.0, 12.0, 9.0],
            highs=[13.5, 12.5, 10.0],
            lows=[12.0, 11.0, 8.5],
        )
    )

    FVGEngine().detect(context)

    assert len(context.fvgs) == 1
    fvg = context.fvgs[0]
    assert fvg.direction == "BEARISH"
    assert fvg.lower_bound == 10.0
    assert fvg.upper_bound == 12.0


def test_no_fvg_when_conditions_do_not_hold() -> None:
    context = make_context(
        make_candles(
            closes=[10.0, 10.5, 10.2, 10.1],
            highs=[10.2, 10.6, 10.3, 10.2],
            lows=[9.8, 10.0, 9.9, 9.7],
        )
    )

    FVGEngine().detect(context)

    assert context.fvgs == []


def test_multiple_fvgs_are_detected() -> None:
    context = make_context(
        make_candles(
            closes=[10.0, 11.0, 13.0, 12.0, 9.0, 8.0],
            highs=[10.0, 11.0, 11.5, 12.5, 10.0, 9.0],
            lows=[9.0, 10.0, 12.2, 11.8, 8.4, 7.5],
        )
    )

    FVGEngine().detect(context)

    assert len(context.fvgs) > 1
    assert "BULLISH" in [fvg.direction for fvg in context.fvgs]
    assert "BEARISH" in [fvg.direction for fvg in context.fvgs]


def test_fvg_detection_does_not_overwrite_other_event_lists() -> None:
    context = make_context(
        make_candles(
            closes=[10.0, 11.0, 13.0],
            highs=[10.0, 11.0, 11.5],
            lows=[9.0, 10.0, 12.2],
        )
    )
    context.bos = ["bos"]
    context.choch = ["choch"]
    context.liquidity_sweeps = ["liq"]

    FVGEngine().detect(context)

    assert context.bos == ["bos"]
    assert context.choch == ["choch"]
    assert context.liquidity_sweeps == ["liq"]
    assert len(context.fvgs) == 1


def test_integration_safety_with_existing_engines() -> None:
    context = MarketContext(
        structure=[
            StructureEvent(index=1, price=10.0, swing_type="HIGH"),
            StructureEvent(index=2, price=5.0, swing_type="LOW"),
            StructureEvent(index=3, price=12.0, swing_type="HIGH"),
            StructureEvent(index=4, price=8.0, swing_type="LOW"),
        ],
        candles=make_candles(
            closes=[8.0, 9.0, 6.0, 10.5, 8.5, 4.5, 11.8],
            highs=[8.0, 10.0, 7.0, 12.0, 9.0, 5.0, 12.6],
            lows=[7.0, 8.0, 5.0, 9.0, 8.0, 4.0, 11.0],
        ),
    )

    context = StructureEngineV2().build(context)
    context = LiquidityEngine().detect(context)
    context = FVGEngine().detect(context)

    assert context.fvgs
    assert context.bos
    assert context.choch
    assert context.liquidity_sweeps is not None


def test_full_ict_engine_produces_fvgs() -> None:
    candles = make_candles(
        closes=[10.0, 11.0, 13.0, 12.0, 9.0],
        highs=[10.0, 11.0, 11.5, 12.5, 10.0],
        lows=[9.0, 10.0, 12.2, 11.8, 8.5],
    )

    context = ICTEngine().analyze(candles)

    assert hasattr(context, "fvgs")
    assert context.fvgs
