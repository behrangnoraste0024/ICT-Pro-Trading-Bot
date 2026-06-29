from models.market_context import MarketContext
from core.swing import SwingDetector
from engine.structure_engine_v2 import StructureEngineV2


class ICTEngine:

    def __init__(self):

        self.swing = SwingDetector()
        self.structure_engine = StructureEngineV2()

    def analyze(self, df):

        context = MarketContext()

        context.candles = df

        context.swings = self.swing.detect(df)

        context = self.structure_engine.build(context)

        return context
