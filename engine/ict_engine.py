from models.market_context import MarketContext
from core.swing import SwingDetector
from engine.fvg.fvg_engine import FVGEngine
from engine.liquidity.liquidity_engine import LiquidityEngine
from engine.structure.structure_engine_v2 import StructureEngineV2


class ICTEngine:

    def __init__(self):

        self.swing = SwingDetector()
        self.structure_engine = StructureEngineV2()
        self.liquidity_engine = LiquidityEngine()
        self.fvg_engine = FVGEngine()

    def analyze(self, df):

        context = MarketContext()

        context.candles = df

        context.swings = self.swing.detect(df)

        context = self.structure_engine.build(context)
        context = self.liquidity_engine.detect(context)
        context = self.fvg_engine.detect(context)

        return context
