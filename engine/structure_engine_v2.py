from models.market_context import MarketContext


class StructureEngineV2:

    """
    Main Smart Money Structure Engine

    Responsible for:

    - HH HL LH LL
    - External Structure
    - Internal Structure
    - BOS
    - CHOCHpython 
    - Trend
    """

    def build(self, context: MarketContext):

        context = self.classify_structure(context)

        context = self.detect_external_structure(context)

        context = self.detect_internal_structure(context)

        context = self.detect_bos(context)

        context = self.detect_choch(context)

        context = self.detect_trend(context)

        return context

    # -----------------------------------

    def classify_structure(self, context):

        return context

    # -----------------------------------

    def detect_external_structure(self, context):

        return context

    # -----------------------------------

    def detect_internal_structure(self, context):

        return context

    # -----------------------------------

    def detect_bos(self, context):

        return context

    # -----------------------------------

    def detect_choch(self, context):

        return context

    # -----------------------------------

    def detect_trend(self, context):

        return context