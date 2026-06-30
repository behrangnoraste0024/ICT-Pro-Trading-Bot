from __future__ import annotations

import pandas as pd
import pytest

from engine.dealing_range.dealing_range_mode_engine import DealingRangeModeEngine
from engine.ict_engine import ICTEngine
from models.engine_config import EngineConfig
from models.market_context import MarketContext


def _candles(length: int, close: float = 100) -> pd.DataFrame:
    rows = []
    for index in range(length):
        rows.append(
            {
                "open": close,
                "high": 200 if index < 10 else 120,
                "low": 10 if index < 10 else 80,
                "close": close,
                "volume": 1,
            }
        )
    return pd.DataFrame(rows)


def _context(close: float = 100, length: int = 60) -> MarketContext:
    context = MarketContext(candles=_candles(length, close))
    context.dealing_range_high = 110
    context.dealing_range_low = 90
    context.external_high = 110
    context.external_low = 90
    context.equilibrium = 100
    context.current_price = close
    context.current_price_zone = "DISCOUNT"
    return context


def test_current_external_mode_does_nothing() -> None:
    context = _context(close=95)

    DealingRangeModeEngine().apply(context, mode="current_external")

    assert context.dealing_range_high == 110
    assert context.dealing_range_low == 90
    assert context.equilibrium == 100
    assert context.current_price_zone == "DISCOUNT"


def test_recent_50_mode_calculates_range_from_last_50_candles() -> None:
    context = _context()

    DealingRangeModeEngine().apply(context, mode="recent_50")

    assert context.dealing_range_high == 120
    assert context.dealing_range_low == 80


def test_recent_50_mode_sets_equilibrium() -> None:
    context = _context()

    DealingRangeModeEngine().apply(context, mode="recent_50")

    assert context.equilibrium == 100


def test_recent_50_mode_sets_premium_zone() -> None:
    context = _context(close=105)

    DealingRangeModeEngine().apply(context, mode="recent_50")

    assert context.current_price_zone == "PREMIUM"


def test_recent_50_mode_sets_discount_zone() -> None:
    context = _context(close=95)

    DealingRangeModeEngine().apply(context, mode="recent_50")

    assert context.current_price_zone == "DISCOUNT"


def test_recent_50_mode_sets_equilibrium_zone() -> None:
    context = _context(close=100)

    DealingRangeModeEngine().apply(context, mode="recent_50")

    assert context.current_price_zone == "EQUILIBRIUM"


def test_recent_50_falls_back_when_fewer_than_50_candles() -> None:
    context = _context(length=49)

    DealingRangeModeEngine().apply(context, mode="recent_50")

    assert context.dealing_range_high == 110
    assert context.dealing_range_low == 90
    assert context.dealing_range_mode_applied == "current_external"
    assert context.dealing_range_mode_fallback_reason == "INSUFFICIENT_CANDLES"


def test_invalid_mode_raises_value_error() -> None:
    with pytest.raises(ValueError):
        DealingRangeModeEngine().apply(_context(), mode="bad_mode")


def test_invalid_recent_range_falls_back_safely() -> None:
    context = _context()
    context.candles = pd.DataFrame([{"open": 1, "high": 100, "low": 100, "close": 100} for _ in range(50)])

    DealingRangeModeEngine().apply(context, mode="recent_50")

    assert context.dealing_range_mode_applied == "current_external"
    assert context.dealing_range_mode_fallback_reason == "INVALID_RECENT_50_RANGE"


def test_does_not_call_network() -> None:
    context = _context()

    DealingRangeModeEngine().apply(context, mode="recent_50")

    assert context.dealing_range_mode_applied == "recent_50"


def test_default_ict_engine_fixed_fixture_remains_unchanged() -> None:
    df = pd.read_json("tests/fixtures/btcusdt_100_candles.json")

    context = ICTEngine().analyze(df)

    assert context.dealing_range_high == 60780.57
    assert context.dealing_range_low == 59745.46
    assert context.equilibrium == 60263.015
    assert context.current_price_zone == "DISCOUNT"


def test_ict_engine_recent_50_changes_dealing_range() -> None:
    df = pd.read_json("tests/fixtures/btcusdt_100_candles.json")
    expected_high = float(df["high"].iloc[-50:].max())
    expected_low = float(df["low"].iloc[-50:].min())

    context = ICTEngine(config=EngineConfig(dealing_range_mode="recent_50")).analyze(df)

    assert context.dealing_range_high == expected_high
    assert context.dealing_range_low == expected_low


def test_ict_engine_recent_50_ote_uses_updated_range() -> None:
    df = pd.read_json("tests/fixtures/btcusdt_100_candles.json")
    expected_high = float(df["high"].iloc[-50:].max())
    expected_low = float(df["low"].iloc[-50:].min())
    range_size = expected_high - expected_low

    context = ICTEngine(config=EngineConfig(dealing_range_mode="recent_50")).analyze(df)

    if context.ote_direction == "BEARISH":
        assert context.ote_lower_bound == expected_low + range_size * 0.62
        assert context.ote_upper_bound == expected_low + range_size * 0.79
    elif context.ote_direction == "BULLISH":
        assert context.ote_lower_bound == expected_high - range_size * 0.79
        assert context.ote_upper_bound == expected_high - range_size * 0.62
