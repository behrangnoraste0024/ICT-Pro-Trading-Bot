from __future__ import annotations

import pandas as pd

from engine.market_regime.market_regime_engine import MarketRegimeEngine
from models.market_context import MarketContext


def _context(closes: list[float]) -> MarketContext:
    return MarketContext(candles=pd.DataFrame({"close": closes}))


def test_bullish_rolling_return() -> None:
    context = MarketRegimeEngine().detect(_context([100, 105]), regime_lookback=1)

    assert context.market_regime == "BULLISH"
    assert context.market_regime_reason == "BULLISH_ROLLING_RETURN"


def test_bearish_rolling_return() -> None:
    context = MarketRegimeEngine().detect(_context([100, 95]), regime_lookback=1)

    assert context.market_regime == "BEARISH"
    assert context.market_regime_reason == "BEARISH_ROLLING_RETURN"


def test_range_rolling_return() -> None:
    context = MarketRegimeEngine().detect(_context([100, 100]), regime_lookback=1)

    assert context.market_regime == "RANGE"
    assert context.market_regime_reason == "RANGE_ROLLING_RETURN"


def test_threshold_creates_range() -> None:
    context = MarketRegimeEngine().detect(_context([100, 100.5]), regime_lookback=1, regime_threshold_pct=0.01)

    assert context.market_regime == "RANGE"


def test_insufficient_candles() -> None:
    context = MarketRegimeEngine().detect(_context([100]), regime_lookback=1)

    assert context.market_regime == "UNKNOWN"
    assert context.market_regime_reason == "INSUFFICIENT_CANDLES"


def test_old_close_zero() -> None:
    context = MarketRegimeEngine().detect(_context([0, 100]), regime_lookback=1)

    assert context.market_regime == "UNKNOWN"
    assert context.market_regime_reason == "INVALID_OLD_CLOSE"


def test_missing_candles() -> None:
    context = MarketRegimeEngine().detect(MarketContext(), regime_lookback=1)

    assert context.market_regime == "UNKNOWN"
    assert context.market_regime_reason == "INSUFFICIENT_CANDLES"


def test_unsupported_regime_mode() -> None:
    context = MarketRegimeEngine().detect(_context([100, 105]), regime_mode="bad_mode", regime_lookback=1)

    assert context.market_regime == "UNKNOWN"
    assert context.market_regime_reason == "UNSUPPORTED_REGIME_MODE"


def test_no_lookahead_uses_context_candles_only() -> None:
    context = _context([100, 90])
    full_future_data = pd.DataFrame({"close": [100, 90, 200]})

    context = MarketRegimeEngine().detect(context, regime_lookback=1)

    assert len(full_future_data) == 3
    assert context.market_regime == "BEARISH"


def test_context_fields_and_debug_are_populated() -> None:
    context = MarketRegimeEngine().detect(
        _context([100, 105]),
        regime_lookback=1,
        regime_threshold_pct=0.01,
        regime_fallback="block",
    )

    assert context.market_regime_mode == "rolling_return"
    assert context.market_regime_lookback == 1
    assert context.market_regime_threshold_pct == 0.01
    assert context.market_regime_return_pct == 0.05
    assert context.market_regime_fallback == "block"
    assert context.debug["market_regime"] == "BULLISH"
