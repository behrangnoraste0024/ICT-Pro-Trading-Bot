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
