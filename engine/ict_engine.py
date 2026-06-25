from models.market_context import MarketContext
from core.swing import SwingDetector
from core.market_structure import MarketStructure
from detectors.real_bos import RealBOSDetector
from engine.trend_engine import TrendEngine
from engine.structure_engine import StructureEngine


class ICTEngine:

    def __init__(self):

        self.swing = SwingDetector()
        self.structure = MarketStructure()
        self.trend = TrendEngine()
        self.real_bos = RealBOSDetector()
        self.structure_engine = StructureEngine()

    def analyze(self, df):

        context = MarketContext()

        context.candles = df

        context.swings = self.swing.detect(df)

        context.swings = self.structure.label_swings(
            context.swings
        )

        context.trend = self.trend.detect(
            context.swings
        )

        context = self.structure_engine.classify(
            context
        )

        context = self.real_bos.detect(
    context
)

        return context