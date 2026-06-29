from models.market_context import MarketContext
from core.swing import SwingDetector
from core.market_structure import MarketStructure
from engine.trend_engine import TrendEngine
from detectors.real_bos import RealBOSDetector
from detectors.bos import BOSDetector
from detectors.choch import CHOCHDetector
from core.structure_builder import StructureBuilder
from engine.external_structure import ExternalStructure
from core.structure_converter import StructureConverter


class ICTEngine:

    def __init__(self):

        self.swing = SwingDetector()
        self.market_structure = MarketStructure()
        self.converter = StructureConverter()
        
        self.trend_engine = TrendEngine()
        self.structure_builder = StructureBuilder()
        self.external = ExternalStructure()

        # فعلاً نگه می‌داریم تا در مراحل بعد جایگزین شوند
        self.bos_detector = BOSDetector()
        self.choch = CHOCHDetector()

    def analyze(self, df):

        context = MarketContext()

        context.candles = df

        # 1. Detect Swings
        context.swings = self.swing.detect(df)
        context.structure = self.converter.convert(
    context.swings
)

        # 2. Build Structure
        context = self.structure_builder.build(context)
        context = self.external.build(context)

        # 3. Trend
        context.trend = self.trend_engine.detect(
            context.swings
        )

        # 4. BOS (نسخه فعلی)
        context = self.bos_detector.detect(context)

        # 5. CHOCH (نسخه فعلی)
        context = self.choch.detect(context)

        return context