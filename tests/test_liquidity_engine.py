import pandas as pd

from engine.liquidity.liquidity_engine import LiquidityEngine
from engine.structure.structure_engine_v2 import StructureEngineV2
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


def make_event(index: int, price: float, swing_type: str, broken: bool = False) -> StructureEvent:
    return StructureEvent(index=index, price=price, swing_type=swing_type, broken=broken)


def make_context(structure: list[StructureEvent], candles: pd.DataFrame) -> MarketContext:
    return MarketContext(candles=candles, structure=structure)


def test_buy_side_liquidity_sweep_creates_one_event() -> None:
    context = make_context(
        structure=[
            make_event(1, 10.0, "HIGH"),
            make_event(2, 5.0, "LOW"),
        ],
        candles=make_candles(
            closes=[8.0, 9.0, 9.8, 9.7],
            highs=[8.0, 10.0, 10.6, 9.9],
            lows=[7.0, 8.0, 8.5, 8.7],
        ),
    )

    LiquidityEngine().detect(context)

    assert len(context.liquidity_sweeps) == 1
    assert context.liquidity_sweeps[0].direction == "BUY_SIDE"
    assert context.structure[0].swept is True
    assert context.structure[0].liquidity is True
    assert context.structure[0].liquidity_type == "BUY_SIDE"
    assert context.structure[0].bos is False


def test_sell_side_liquidity_sweep_creates_one_event() -> None:
    context = make_context(
        structure=[
            make_event(1, 10.0, "LOW"),
            make_event(2, 20.0, "HIGH"),
        ],
        candles=make_candles(
            closes=[15.0, 12.0, 10.2, 10.4],
            highs=[16.0, 13.0, 10.8, 10.9],
            lows=[14.0, 11.0, 9.4, 9.6],
        ),
    )

    LiquidityEngine().detect(context)

    assert len(context.liquidity_sweeps) == 1
    assert context.liquidity_sweeps[0].direction == "SELL_SIDE"
    assert context.structure[0].swept is True
    assert context.structure[0].liquidity_type == "SELL_SIDE"


def test_close_break_is_not_liquidity() -> None:
    context = make_context(
        structure=[
            make_event(1, 10.0, "HIGH"),
            make_event(2, 5.0, "LOW"),
        ],
        candles=make_candles(
            closes=[8.0, 9.0, 10.4, 4.6],
            highs=[8.0, 10.0, 10.5, 4.7],
            lows=[7.0, 8.0, 9.8, 4.5],
        ),
    )

    LiquidityEngine().detect(context)

    assert context.liquidity_sweeps == []
    assert all(not item.swept for item in context.structure)


def test_broken_bos_level_is_ignored() -> None:
    context = make_context(
        structure=[
            make_event(1, 10.0, "HIGH", broken=True),
            make_event(2, 5.0, "LOW"),
        ],
        candles=make_candles(
            closes=[8.0, 9.0, 9.7],
            highs=[8.0, 10.8, 9.8],
            lows=[7.0, 8.0, 8.8],
        ),
    )

    LiquidityEngine().detect(context)

    assert context.liquidity_sweeps == []
    assert context.structure[0].swept is False


def test_no_duplicate_sweeps_for_same_level() -> None:
    context = make_context(
        structure=[
            make_event(1, 10.0, "HIGH"),
            make_event(2, 5.0, "LOW"),
        ],
        candles=make_candles(
            closes=[8.0, 9.0, 9.8, 9.7, 9.6],
            highs=[8.0, 10.0, 10.4, 10.5, 10.7],
            lows=[7.0, 8.0, 8.5, 8.6, 8.7],
        ),
    )

    LiquidityEngine().detect(context)

    assert len(context.liquidity_sweeps) == 1
    assert context.structure[0].swept is True


def test_structure_engine_and_liquidity_engine_work_together() -> None:
    context = MarketContext(
        structure=[
            make_event(1, 10.0, "HIGH"),
            make_event(2, 5.0, "LOW"),
            make_event(3, 12.0, "HIGH"),
            make_event(4, 8.0, "LOW"),
        ],
        candles=make_candles(
            closes=[8.0, 9.0, 6.0, 10.5, 8.5, 4.5, 11.8],
            highs=[8.0, 10.0, 7.0, 12.0, 9.0, 5.0, 12.6],
            lows=[7.0, 8.0, 5.0, 9.0, 8.0, 4.0, 11.0],
        ),
    )

    context = StructureEngineV2().build(context)
    context = LiquidityEngine().detect(context)

    assert context.bos
    assert context.choch
    assert all(event.event_type == "BOS" for event in context.bos)
    assert all(event.event_type == "CHOCH" for event in context.choch)
    assert len(context.liquidity_sweeps) == 1
    assert context.liquidity_sweeps[0].direction == "BUY_SIDE"
