from pathlib import Path

import pandas as pd

from core.swing import SwingDetector
from engine.breaker.breaker_block_engine import BreakerBlockEngine
from engine.fvg.fvg_engine import FVGEngine
from engine.premium_discount.premium_discount_engine import PremiumDiscountEngine
from engine.ote.ote_engine import OTEEngine
from engine.setup.setup_engine import SetupEngine
from engine.entry.entry_trigger_engine import EntryTriggerEngine
from engine.trade_plan.trade_plan_engine import TradePlanEngine
from engine.trade_quality.trade_quality_engine import TradeQualityEngine
from engine.paper_trade.paper_trade_engine import PaperTradeEngine
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
    context = OTEEngine().detect(context)
    context = SetupEngine().detect(context)
    context = EntryTriggerEngine().detect(context)
    context = TradePlanEngine().detect(context)
    context = TradeQualityEngine().detect(context)
    context = PaperTradeEngine().detect(context)
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
    assert context.ote_direction == "BEARISH"
    assert context.ote_lower_bound == 60387.2282
    assert context.ote_upper_bound == 60563.1969
    assert context.ote_level_62 == 60387.2282
    assert context.ote_level_705 == 60475.21255
    assert context.ote_level_79 == 60563.1969
    assert context.in_ote_zone is False
    assert context.setup_status == "INVALID"
    assert context.setup_bias == "NONE"
    assert context.setup_score == 65
    assert context.setup_blockers == ["WRONG_PRICE_ZONE", "PRICE_NOT_IN_OTE"]
    assert len(context.setups) == 2
    assert context.entry_status == "NOT_CONFIRMED"
    assert context.entry_direction == "NONE"
    assert context.entry_trigger_type == "NONE"
    assert context.entry_confirmed is False
    assert context.entry_blockers == ["NO_VALID_SETUP"]
    assert context.trade_plan_status == "NO_TRADE"
    assert context.trade_direction == "NONE"
    assert context.planned_entry_price is None
    assert context.planned_stop_loss is None
    assert context.planned_take_profit is None
    assert context.planned_risk is None
    assert context.planned_reward is None
    assert context.planned_risk_reward is None
    assert context.trade_plan_blockers == ["NO_CONFIRMED_ENTRY"]
    assert context.trade_quality_status == "REJECTED"
    assert context.trade_quality_score == 0
    assert context.trade_quality_blockers == ["NO_PLANNED_TRADE"]
    assert context.trade_quality_reasons == []
    assert context.paper_trade_status == "NO_PAPER_TRADE"
    assert context.paper_trade_direction == "NONE"
    assert context.paper_entry_price is None
    assert context.paper_stop_loss is None
    assert context.paper_take_profit is None
    assert context.paper_entry_index is None
    assert context.paper_exit_price is None
    assert context.paper_exit_index is None
    assert context.paper_pnl is None
    assert context.paper_trade_blockers == ["TRADE_QUALITY_NOT_APPROVED"]
    assert context.paper_trade_reasons == []
    assert context.trend == "DOWNTREND"
    assert context.external_high == 60780.57
    assert context.external_low == 59745.46
