from models.market_context import MarketContext
from core.swing import SwingDetector
from core.market_structure import MarketStructure
from engine.trend_engine import TrendEngine
from engine.structure_engine import StructureEngine
from detectors.real_bos import RealBOSDetector
from detectors.choch import CHOCHDetector


class ICTEngine:

    def __init__(self):

        self.swing = SwingDetector()
        self.market_structure = MarketStructure()
        self.structure_engine = StructureEngine()
        self.trend_engine = TrendEngine()

        # فعلاً نگه می‌داریم تا در مراحل بعد جایگزین شوند
        self.real_bos = RealBOSDetector()
        self.choch = CHOCHDetector()

    def analyze(self, df):

        context = MarketContext()

        context.candles = df

        # 1. Detect Swings
        context.swings = self.swing.detect(df)

        # 2. Build Structure
        context = self.structure_engine.build(context)

        # 3. Trend
        context.trend = self.trend_engine.detect(
            context.swings
        )

        # 4. BOS (نسخه فعلی)
        context = self.real_bos.detect(context)

        # 5. CHOCH (نسخه فعلی)
        context = self.choch.detect(context)

        return context