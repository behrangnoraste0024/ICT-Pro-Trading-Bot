from models.market_context import MarketContext
from core.swing import SwingDetector
from engine.fvg.fvg_engine import FVGEngine
from engine.breaker.breaker_block_engine import BreakerBlockEngine
from engine.premium_discount.premium_discount_engine import PremiumDiscountEngine
from engine.ote.ote_engine import OTEEngine
from engine.setup.setup_engine import SetupEngine
from engine.entry.entry_trigger_engine import EntryTriggerEngine
from engine.order_block.order_block_engine import OrderBlockEngine
from engine.liquidity.liquidity_engine import LiquidityEngine
from engine.structure.structure_engine_v2 import StructureEngineV2


class ICTEngine:

    def __init__(self):

        self.swing = SwingDetector()
        self.structure_engine = StructureEngineV2()
        self.liquidity_engine = LiquidityEngine()
        self.fvg_engine = FVGEngine()
        self.order_block_engine = OrderBlockEngine()
        self.breaker_block_engine = BreakerBlockEngine()
        self.premium_discount_engine = PremiumDiscountEngine()
        self.ote_engine = OTEEngine()
        self.setup_engine = SetupEngine()
        self.entry_trigger_engine = EntryTriggerEngine()

    def analyze(self, df):

        context = MarketContext()

        context.candles = df

        context.swings = self.swing.detect(df)

        context = self.structure_engine.build(context)
        context = self.liquidity_engine.detect(context)
        context = self.fvg_engine.detect(context)
        context = self.order_block_engine.detect(context)
        context = self.breaker_block_engine.detect(context)
        context = self.premium_discount_engine.detect(context)
        context = self.ote_engine.detect(context)
        context = self.setup_engine.detect(context)
        context = self.entry_trigger_engine.detect(context)

        return context
