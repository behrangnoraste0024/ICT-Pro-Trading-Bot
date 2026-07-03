from __future__ import annotations

from models.execution_quality import ExecutionQualityResult
from models.market_context import MarketContext


class ExecutionQualityEngine:
    def evaluate(self, context: MarketContext) -> ExecutionQualityResult:
        candle = self._entry_candle(context)
        volatility_component = self._volatility_component(candle)
        spread_component = self._spread_component(context, candle)
        structure_component = self._structure_component(context, candle)
        liquidity_component = self._liquidity_component(context)
        timing_component = self._timing_component(context, candle)
        score = self._clamp(
            (
                volatility_component * 0.25
                + spread_component * 0.15
                + structure_component * 0.25
                + liquidity_component * 0.15
                + timing_component * 0.20
            )
        )
        return ExecutionQualityResult(
            score=score,
            volatility_component=volatility_component,
            spread_component=spread_component,
            structure_component=structure_component,
            liquidity_component=liquidity_component,
            timing_component=timing_component,
            reasoning={
                "entry_index": getattr(context, "paper_entry_index", None),
                "direction": getattr(context, "paper_trade_direction", "NONE"),
                "uses_entry_candle_only": True,
            },
        )

    def attach(self, context: MarketContext) -> MarketContext:
        result = self.evaluate(context)
        context.execution_quality_result = result
        context.execution_quality_score = result.score
        return context

    def _entry_candle(self, context: MarketContext):
        candles = getattr(context, "candles", None)
        if candles is None or len(candles) == 0:
            return None
        entry_index = getattr(context, "paper_entry_index", None)
        if entry_index is None:
            return candles.iloc[-1]
        safe_index = max(0, min(int(entry_index), len(candles) - 1))
        return candles.iloc[safe_index]

    def _volatility_component(self, candle) -> float:
        if candle is None:
            return 0.5
        high = float(candle["high"])
        low = float(candle["low"])
        close = abs(float(candle["close"])) or 1.0
        range_pct = (high - low) / close
        if range_pct <= 0.002:
            return 0.9
        if range_pct <= 0.006:
            return 0.75
        if range_pct <= 0.012:
            return 0.55
        return 0.3

    def _spread_component(self, context: MarketContext, candle) -> float:
        explicit_spread = getattr(context, "spread_pct", None)
        if explicit_spread is not None:
            return self._inverse_threshold(float(explicit_spread), 0.0002, 0.001)
        if candle is None:
            return 0.5
        high = float(candle["high"])
        low = float(candle["low"])
        close = abs(float(candle["close"])) or 1.0
        wick_proxy = max((high - low) / close, 0.0)
        return self._inverse_threshold(wick_proxy, 0.002, 0.012)

    def _structure_component(self, context: MarketContext, candle) -> float:
        risk_reward = getattr(context, "planned_risk_reward", None)
        setup_score = float(getattr(context, "setup_score", 0) or 0)
        rr_component = 0.7 if risk_reward is None else min(float(risk_reward) / 2.0, 1.0)
        setup_component = min(setup_score / 100.0, 1.0)
        return self._clamp((rr_component * 0.4) + (setup_component * 0.6))

    def _liquidity_component(self, context: MarketContext) -> float:
        if getattr(context, "liquidity_sweeps", None):
            return 0.85
        if getattr(context, "matched_pois", None):
            return 0.75
        if getattr(context, "order_blocks", None):
            return 0.65
        return 0.5

    def _timing_component(self, context: MarketContext, candle) -> float:
        if candle is None:
            return 0.5
        entry = getattr(context, "paper_entry_price", None)
        if entry is None:
            return 0.5
        high = float(candle["high"])
        low = float(candle["low"])
        if high <= low:
            return 0.5
        position = (float(entry) - low) / (high - low)
        direction = getattr(context, "paper_trade_direction", "NONE")
        if direction in ("BULLISH", "LONG"):
            return self._clamp(1.0 - position)
        if direction in ("BEARISH", "SHORT"):
            return self._clamp(position)
        return 0.5

    def _inverse_threshold(self, value: float, good: float, poor: float) -> float:
        if value <= good:
            return 1.0
        if value >= poor:
            return 0.2
        return self._clamp(1.0 - ((value - good) / (poor - good)) * 0.8)

    def _clamp(self, value: float) -> float:
        return max(0.0, min(float(value), 1.0))
