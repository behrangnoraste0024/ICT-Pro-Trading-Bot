from pathlib import Path

import pandas as pd

from core.swing import SwingDetector
from engine.breaker.breaker_block_engine import BreakerBlockEngine
from engine.fvg.fvg_engine import FVGEngine
from engine.premium_discount.premium_discount_engine import PremiumDiscountEngine
from engine.order_block.order_block_engine import OrderBlockEngine
from engine.liquidity.liquidity_engine import LiquidityEngine
from engine.structure.structure_engine_v2 import StructureEngineV2
from models.market_context import MarketContext


FIXTURE_PATH = Path("tests/fixtures/btcusdt_100_candles.json")


def load_fixture_dataframe() -> pd.DataFrame:
    return pd.read_json(FIXTURE_PATH)


def run_pipeline(df: pd.DataFrame) -> MarketContext:
    context = MarketContext(candles=df)
    context.swings = SwingDetector().detect(df)
    context = StructureEngineV2().build(context)
    context = LiquidityEngine().detect(context)
    context = FVGEngine().detect(context)
    context = OrderBlockEngine().detect(context)
    context = BreakerBlockEngine().detect(context)
    context = PremiumDiscountEngine().detect(context)
    return context


def test_fixture_has_expected_schema_and_numeric_columns() -> None:
    df = load_fixture_dataframe()

    assert len(df) == 100

    required_columns = {"timestamp", "open", "high", "low", "close", "volume"}
    assert required_columns.issubset(df.columns)

    for column in ["open", "high", "low", "close", "volume", "timestamp"]:
        numeric = pd.to_numeric(df[column], errors="raise")
        assert len(numeric) == 100


def test_full_pipeline_regression_baseline() -> None:
    df = load_fixture_dataframe()
    context = run_pipeline(df)

    assert len(context.swings) == 12
    assert len(context.structure) == 12
    assert len(context.bos) == 2
    assert len(context.choch) == 1
    assert len(context.liquidity_sweeps) == 3
    assert len(context.fvgs) == 24
    assert sum(1 for fvg in context.fvgs if fvg.active) == 12
    assert sum(1 for fvg in context.fvgs if fvg.mitigation_type == "PARTIAL") == 8
    assert sum(1 for fvg in context.fvgs if fvg.mitigation_type == "FULL") == 12
    assert len(context.order_blocks) == 3
    assert sum(1 for block in context.order_blocks if block.direction == "BULLISH") == 2
    assert sum(1 for block in context.order_blocks if block.direction == "BEARISH") == 1
    assert len(context.breaker_blocks) == 2
    assert sum(1 for block in context.breaker_blocks if block.direction == "BULLISH") == 1
    assert sum(1 for block in context.breaker_blocks if block.direction == "BEARISH") == 1
    assert sum(1 for block in context.order_blocks if block.invalidated) == 2
    assert context.dealing_range_high == 60780.57
    assert context.dealing_range_low == 59745.46
    assert context.equilibrium == 60263.015
    assert context.current_price == 59796.0
    assert context.current_price_zone == "DISCOUNT"
    assert context.premium_zone == {"lower_bound": 60263.015, "upper_bound": 60780.57}
    assert context.discount_zone == {"lower_bound": 59745.46, "upper_bound": 60263.015}
    assert context.trend == "DOWNTREND"
    assert context.external_high == 60780.57
    assert context.external_low == 59745.46
