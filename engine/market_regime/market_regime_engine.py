from __future__ import annotations

from typing import Any

from models.market_context import MarketContext


class MarketRegimeEngine:
    VALID_MODES = {"rolling_return"}

    def detect(
        self,
        context: MarketContext,
        regime_mode: str = "rolling_return",
        regime_lookback: int = 200,
        regime_threshold_pct: float = 0.0,
        regime_fallback: str = "all",
    ) -> MarketContext:
        self._reset_metadata(context, regime_mode, regime_lookback, regime_threshold_pct, regime_fallback)

        if regime_mode not in self.VALID_MODES:
            context.market_regime = "UNKNOWN"
            context.market_regime_reason = "UNSUPPORTED_REGIME_MODE"
            self._update_debug(context)
            return context

        candles = getattr(context, "candles", None)
        if candles is None or not hasattr(candles, "iloc") or "close" not in getattr(candles, "columns", []):
            context.market_regime = "UNKNOWN"
            context.market_regime_reason = "INSUFFICIENT_CANDLES"
            self._update_debug(context)
            return context

        if len(candles) <= regime_lookback:
            context.market_regime = "UNKNOWN"
            context.market_regime_reason = "INSUFFICIENT_CANDLES"
            self._update_debug(context)
            return context

        try:
            old_close = float(candles["close"].iloc[-regime_lookback - 1])
            current_close = float(candles["close"].iloc[-1])
        except (TypeError, ValueError, IndexError):
            context.market_regime = "UNKNOWN"
            context.market_regime_reason = "INSUFFICIENT_CANDLES"
            self._update_debug(context)
            return context

        if old_close == 0:
            context.market_regime = "UNKNOWN"
            context.market_regime_reason = "INVALID_OLD_CLOSE"
            self._update_debug(context)
            return context

        return_pct = (current_close - old_close) / old_close
        context.market_regime_return_pct = return_pct

        if return_pct > regime_threshold_pct:
            context.market_regime = "BULLISH"
            context.market_regime_reason = "BULLISH_ROLLING_RETURN"
        elif return_pct < -regime_threshold_pct:
            context.market_regime = "BEARISH"
            context.market_regime_reason = "BEARISH_ROLLING_RETURN"
        else:
            context.market_regime = "RANGE"
            context.market_regime_reason = "RANGE_ROLLING_RETURN"

        self._update_debug(context)
        return context

    def _reset_metadata(
        self,
        context: MarketContext,
        regime_mode: str,
        regime_lookback: int,
        regime_threshold_pct: float,
        regime_fallback: str,
    ) -> None:
        context.market_regime = "UNKNOWN"
        context.market_regime_mode = regime_mode
        context.market_regime_lookback = regime_lookback
        context.market_regime_threshold_pct = regime_threshold_pct
        context.market_regime_return_pct = None
        context.market_regime_fallback = regime_fallback
        context.market_regime_reason = None

    def _update_debug(self, context: MarketContext) -> None:
        debug: Any = getattr(context, "debug", None)
        if debug is None:
            return

        debug["market_regime"] = context.market_regime
        debug["market_regime_mode"] = context.market_regime_mode
        debug["market_regime_lookback"] = context.market_regime_lookback
        debug["market_regime_threshold_pct"] = context.market_regime_threshold_pct
        debug["market_regime_return_pct"] = context.market_regime_return_pct
        debug["market_regime_fallback"] = context.market_regime_fallback
        debug["market_regime_reason"] = context.market_regime_reason
