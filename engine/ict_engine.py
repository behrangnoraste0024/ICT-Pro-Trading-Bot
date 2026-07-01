from models.market_context import MarketContext
from core.swing import SwingDetector
from engine.fvg.fvg_engine import FVGEngine
from engine.breaker.breaker_block_engine import BreakerBlockEngine
from engine.premium_discount.premium_discount_engine import PremiumDiscountEngine
from engine.dealing_range.dealing_range_mode_engine import DealingRangeModeEngine
from engine.ote.ote_engine import OTEEngine
from engine.setup.setup_engine import SetupEngine
from engine.entry.entry_trigger_engine import EntryTriggerEngine
from engine.trade_plan.trade_plan_engine import TradePlanEngine
from engine.trade_management.direction_mode_engine import DirectionModeEngine
from engine.trade_management.exit_mode_engine import ExitModeEngine
from engine.trade_quality.trade_quality_engine import TradeQualityEngine
from engine.paper_trade.paper_trade_engine import PaperTradeEngine
from engine.backtest.backtest_engine import BacktestEngine
from engine.order_block.order_block_engine import OrderBlockEngine
from engine.liquidity.liquidity_engine import LiquidityEngine
from engine.structure.structure_engine_v2 import StructureEngineV2
from models.engine_config import EngineConfig


class ICTEngine:

    def __init__(self, config: EngineConfig | None = None):

        self.config = config if config is not None else EngineConfig()
        self.swing = SwingDetector()
        self.structure_engine = StructureEngineV2()
        self.liquidity_engine = LiquidityEngine()
        self.fvg_engine = FVGEngine()
        self.order_block_engine = OrderBlockEngine()
        self.breaker_block_engine = BreakerBlockEngine()
        self.premium_discount_engine = PremiumDiscountEngine()
        self.dealing_range_mode_engine = DealingRangeModeEngine()
        self.ote_engine = OTEEngine()
        self.setup_engine = SetupEngine()
        self.entry_trigger_engine = EntryTriggerEngine()
        self.trade_plan_engine = TradePlanEngine()
        self.exit_mode_engine = ExitModeEngine()
        self.direction_mode_engine = DirectionModeEngine()
        self.trade_quality_engine = TradeQualityEngine(minimum_rr=self.config.min_risk_reward)
        self.paper_trade_engine = PaperTradeEngine()
        self.backtest_engine = BacktestEngine()

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
        context = self.dealing_range_mode_engine.apply(context, self.config.dealing_range_mode)
        context = self.ote_engine.detect(context)
        context = self.setup_engine.detect(context)
        context = self.entry_trigger_engine.detect(context)
        context = self.trade_plan_engine.detect(context)
        context = self.exit_mode_engine.apply(context, self.config.exit_mode)
        context = self.direction_mode_engine.apply(
            context,
            self.config.direction_mode,
            self.config.auto_trend_fallback,
        )
        context = self.trade_quality_engine.detect(context)
        context = self.paper_trade_engine.detect(context)
        context = self.backtest_engine.detect(context)

        return context
