from __future__ import annotations

from engine.trade_management.direction_mode_engine import DirectionModeEngine
from models.market_context import MarketContext


def _planned_context(direction: str) -> MarketContext:
    context = MarketContext()
    context.trade_plan_status = "PLANNED"
    context.trade_direction = direction
    context.planned_entry_price = 100
    context.planned_stop_loss = 95
    context.planned_take_profit = 110
    context.bos = ["preserved"]
    return context


def _planned_context_with_trend(direction: str, trend: str | None) -> MarketContext:
    context = _planned_context(direction)
    if trend is not None:
        context.trend = trend
    return context


def test_all_mode_allows_long() -> None:
    context = DirectionModeEngine().apply(_planned_context("BULLISH"), "all")

    assert context.direction_mode_allowed is True
    assert context.direction_mode_fallback_reason == "ALL_MODE"


def test_all_mode_allows_short() -> None:
    context = DirectionModeEngine().apply(_planned_context("BEARISH"), "all")

    assert context.direction_mode_allowed is True
    assert context.direction_mode_fallback_reason == "ALL_MODE"


def test_long_only_allows_long() -> None:
    context = DirectionModeEngine().apply(_planned_context("BULLISH"), "long_only")

    assert context.direction_mode_allowed is True
    assert context.direction_mode_fallback_reason == "NONE"


def test_long_only_blocks_short() -> None:
    context = DirectionModeEngine().apply(_planned_context("BEARISH"), "long_only")

    assert context.direction_mode_allowed is False
    assert context.direction_mode_blocked_direction == "BEARISH"
    assert context.direction_mode_fallback_reason == "DIRECTION_MODE_BLOCKED"


def test_short_only_allows_short() -> None:
    context = DirectionModeEngine().apply(_planned_context("BEARISH"), "short_only")

    assert context.direction_mode_allowed is True
    assert context.direction_mode_fallback_reason == "NONE"


def test_short_only_blocks_long() -> None:
    context = DirectionModeEngine().apply(_planned_context("BULLISH"), "short_only")

    assert context.direction_mode_allowed is False
    assert context.direction_mode_blocked_direction == "BULLISH"
    assert context.direction_mode_fallback_reason == "DIRECTION_MODE_BLOCKED"


def test_no_planned_trade_does_not_crash() -> None:
    context = MarketContext()

    context = DirectionModeEngine().apply(context, "short_only")

    assert context.direction_mode_allowed is None
    assert context.direction_mode_fallback_reason == "NO_PLANNED_TRADE"


def test_invalid_trade_direction_marks_invalid_direction() -> None:
    context = _planned_context("SIDEWAYS")

    context = DirectionModeEngine().apply(context, "short_only")

    assert context.direction_mode_allowed is None
    assert context.direction_mode_fallback_reason == "INVALID_DIRECTION"


def test_invalid_mode_marks_invalid_direction_without_crashing() -> None:
    context = DirectionModeEngine().apply(_planned_context("BULLISH"), "bad_mode")

    assert context.direction_mode_allowed is None
    assert context.direction_mode_fallback_reason == "INVALID_DIRECTION"


def test_allowed_trade_sets_allowed_true() -> None:
    context = DirectionModeEngine().apply(_planned_context("BULLISH"), "long_only")

    assert context.direction_mode_allowed is True


def test_engine_does_not_mutate_unrelated_fields() -> None:
    context = _planned_context("BULLISH")
    original_bos = context.bos

    context = DirectionModeEngine().apply(context, "long_only")

    assert context.bos is original_bos
    assert context.bos == ["preserved"]


def test_debug_values_are_populated() -> None:
    context = DirectionModeEngine().apply(_planned_context("BEARISH"), "long_only")

    assert context.debug["direction_mode_requested"] == "long_only"
    assert context.debug["direction_mode_applied"] == "long_only"
    assert context.debug["direction_mode_allowed"] is False
    assert context.debug["direction_mode_blocked_direction"] == "BEARISH"
    assert context.debug["direction_mode_fallback_reason"] == "DIRECTION_MODE_BLOCKED"


def test_auto_trend_downtrend_allows_short() -> None:
    context = DirectionModeEngine().apply(_planned_context_with_trend("BEARISH", "DOWNTREND"), "auto_trend")

    assert context.direction_mode_allowed is True
    assert context.direction_mode_resolved_direction == "SHORT"
    assert context.auto_trend_source_trend == "DOWNTREND"
    assert context.direction_mode_fallback_reason == "AUTO_TREND_DOWNTREND_SHORT_ONLY"


def test_auto_trend_downtrend_blocks_long() -> None:
    context = DirectionModeEngine().apply(_planned_context_with_trend("BULLISH", "DOWNTREND"), "auto_trend")

    assert context.direction_mode_allowed is False
    assert context.direction_mode_blocked_direction == "BULLISH"
    assert context.direction_mode_resolved_direction == "SHORT"
    assert context.direction_mode_fallback_reason == "AUTO_TREND_DOWNTREND_SHORT_ONLY"


def test_auto_trend_uptrend_allows_long() -> None:
    context = DirectionModeEngine().apply(_planned_context_with_trend("BULLISH", "UPTREND"), "auto_trend")

    assert context.direction_mode_allowed is True
    assert context.direction_mode_resolved_direction == "LONG"
    assert context.auto_trend_source_trend == "UPTREND"
    assert context.direction_mode_fallback_reason == "AUTO_TREND_UPTREND_LONG_ONLY"


def test_auto_trend_uptrend_blocks_short() -> None:
    context = DirectionModeEngine().apply(_planned_context_with_trend("BEARISH", "UPTREND"), "auto_trend")

    assert context.direction_mode_allowed is False
    assert context.direction_mode_blocked_direction == "BEARISH"
    assert context.direction_mode_resolved_direction == "LONG"
    assert context.direction_mode_fallback_reason == "AUTO_TREND_UPTREND_LONG_ONLY"


def test_auto_trend_unknown_fallback_all_allows_long() -> None:
    context = DirectionModeEngine().apply(_planned_context_with_trend("BULLISH", "UNKNOWN"), "auto_trend", "all")

    assert context.direction_mode_allowed is True
    assert context.direction_mode_resolved_direction == "ALL"
    assert context.direction_mode_fallback_reason == "AUTO_TREND_FALLBACK_ALL"


def test_auto_trend_unknown_fallback_all_allows_short() -> None:
    context = DirectionModeEngine().apply(_planned_context_with_trend("BEARISH", "UNKNOWN"), "auto_trend", "all")

    assert context.direction_mode_allowed is True
    assert context.direction_mode_resolved_direction == "ALL"
    assert context.direction_mode_fallback_reason == "AUTO_TREND_FALLBACK_ALL"


def test_auto_trend_unknown_fallback_block_blocks_long() -> None:
    context = DirectionModeEngine().apply(_planned_context_with_trend("BULLISH", "UNKNOWN"), "auto_trend", "block")

    assert context.direction_mode_allowed is False
    assert context.direction_mode_blocked_direction == "BULLISH"
    assert context.direction_mode_resolved_direction == "NONE"
    assert context.direction_mode_fallback_reason == "AUTO_TREND_FALLBACK_BLOCK"


def test_auto_trend_unknown_fallback_block_blocks_short() -> None:
    context = DirectionModeEngine().apply(_planned_context_with_trend("BEARISH", "UNKNOWN"), "auto_trend", "block")

    assert context.direction_mode_allowed is False
    assert context.direction_mode_blocked_direction == "BEARISH"
    assert context.direction_mode_resolved_direction == "NONE"
    assert context.direction_mode_fallback_reason == "AUTO_TREND_FALLBACK_BLOCK"


def test_auto_trend_missing_trend_fallback_all_does_not_crash() -> None:
    context = DirectionModeEngine().apply(_planned_context_with_trend("BULLISH", None), "auto_trend", "all")

    assert context.direction_mode_allowed is True
    assert context.auto_trend_source_trend == "UNKNOWN"
    assert context.direction_mode_fallback_reason == "AUTO_TREND_FALLBACK_ALL"


def test_auto_trend_missing_trend_fallback_block_blocks_planned_trade() -> None:
    context = DirectionModeEngine().apply(_planned_context_with_trend("BULLISH", None), "auto_trend", "block")

    assert context.direction_mode_allowed is False
    assert context.auto_trend_source_trend == "UNKNOWN"
    assert context.direction_mode_fallback_reason == "AUTO_TREND_FALLBACK_BLOCK"


def test_auto_trend_sets_source_trend_and_fallback() -> None:
    context = DirectionModeEngine().apply(_planned_context_with_trend("BULLISH", "RANGE"), "auto_trend", "block")

    assert context.auto_trend_source_trend == "RANGE"
    assert context.auto_trend_fallback == "block"


def test_auto_trend_sets_debug_values() -> None:
    context = DirectionModeEngine().apply(_planned_context_with_trend("BULLISH", "UPTREND"), "auto_trend")

    assert context.debug["direction_mode_requested"] == "auto_trend"
    assert context.debug["direction_mode_resolved_direction"] == "LONG"
    assert context.debug["auto_trend_source_trend"] == "UPTREND"
    assert context.debug["auto_trend_fallback"] == "all"


def test_regime_trend_bullish_allows_long() -> None:
    context = _planned_context("BULLISH")
    context.market_regime = "BULLISH"

    context = DirectionModeEngine().apply(context, "regime_trend")

    assert context.direction_mode_allowed is True
    assert context.direction_mode_resolved_direction == "LONG"
    assert context.regime_source_regime == "BULLISH"
    assert context.direction_mode_fallback_reason == "REGIME_TREND_BULLISH_LONG_ONLY"


def test_regime_trend_bullish_blocks_short() -> None:
    context = _planned_context("BEARISH")
    context.market_regime = "BULLISH"

    context = DirectionModeEngine().apply(context, "regime_trend")

    assert context.direction_mode_allowed is False
    assert context.direction_mode_blocked_direction == "BEARISH"
    assert context.direction_mode_resolved_direction == "LONG"


def test_regime_trend_bearish_allows_short() -> None:
    context = _planned_context("BEARISH")
    context.market_regime = "BEARISH"

    context = DirectionModeEngine().apply(context, "regime_trend")

    assert context.direction_mode_allowed is True
    assert context.direction_mode_resolved_direction == "SHORT"
    assert context.direction_mode_fallback_reason == "REGIME_TREND_BEARISH_SHORT_ONLY"


def test_regime_trend_range_fallback_all_allows_planned_trade() -> None:
    context = _planned_context("BULLISH")
    context.market_regime = "RANGE"

    context = DirectionModeEngine().apply(context, "regime_trend", regime_fallback="all")

    assert context.direction_mode_allowed is True
    assert context.direction_mode_resolved_direction == "ALL"
    assert context.direction_mode_fallback_reason == "REGIME_TREND_FALLBACK_ALL"


def test_regime_trend_range_fallback_block_blocks_planned_trade() -> None:
    context = _planned_context("BULLISH")
    context.market_regime = "RANGE"

    context = DirectionModeEngine().apply(context, "regime_trend", regime_fallback="block")

    assert context.direction_mode_allowed is False
    assert context.direction_mode_resolved_direction == "NONE"
    assert context.direction_mode_fallback_reason == "REGIME_TREND_FALLBACK_BLOCK"


def test_regime_trend_sets_debug_values() -> None:
    context = _planned_context("BEARISH")
    context.market_regime = "BEARISH"

    context = DirectionModeEngine().apply(context, "regime_trend", regime_fallback="block")

    assert context.debug["direction_mode_requested"] == "regime_trend"
    assert context.debug["regime_source_regime"] == "BEARISH"
    assert context.debug["regime_fallback"] == "block"
