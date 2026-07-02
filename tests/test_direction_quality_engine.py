from __future__ import annotations

from copy import deepcopy

from engine.trade_management.direction_quality_engine import DirectionQualityEngine
from models.market_context import MarketContext


def _planned(direction: str = "BULLISH") -> MarketContext:
    context = MarketContext()
    context.trade_plan_status = "PLANNED"
    context.trade_direction = direction
    context.entry_trigger_type = "CONFIRMATION_CANDLE"
    context.setup_score = 100
    context.market_regime = "BULLISH" if direction == "BULLISH" else "BEARISH"
    context.bos = ["preserved"]
    return context


def test_off_mode_allows_long() -> None:
    context = DirectionQualityEngine().apply(_planned("BULLISH"), "off")

    assert context.direction_quality_allowed is True
    assert context.direction_quality_reasons == ["QUALITY_MODE_OFF"]


def test_off_mode_allows_short() -> None:
    context = DirectionQualityEngine().apply(_planned("BEARISH"), "off")

    assert context.direction_quality_allowed is True


def test_long_strict_does_not_affect_short() -> None:
    context = DirectionQualityEngine().apply(_planned("BEARISH"), "long_strict", strict_long_require_displacement=True)

    assert context.direction_quality_allowed is True
    assert context.direction_quality_reasons == ["STRICT_MODE_NOT_APPLICABLE"]


def test_short_strict_does_not_affect_long() -> None:
    context = DirectionQualityEngine().apply(_planned("BULLISH"), "short_strict", strict_short_require_displacement=True)

    assert context.direction_quality_allowed is True
    assert context.direction_quality_reasons == ["STRICT_MODE_NOT_APPLICABLE"]


def test_both_strict_applies_to_both() -> None:
    context = _planned("BEARISH")

    context = DirectionQualityEngine().apply(context, "both_strict", strict_short_require_displacement=True)

    assert context.direction_quality_allowed is False
    assert context.direction_quality_blocker == "STRICT_SHORT_NO_DISPLACEMENT"


def test_long_strict_require_regime_known_blocks_unknown_regime() -> None:
    context = _planned("BULLISH")
    context.market_regime = "UNKNOWN"

    context = DirectionQualityEngine().apply(context, "long_strict", strict_long_require_regime_known=True)

    assert context.direction_quality_allowed is False
    assert context.direction_quality_blocker == "STRICT_LONG_UNKNOWN_REGIME"


def test_long_strict_require_regime_bullish_blocks_bearish() -> None:
    context = _planned("BULLISH")
    context.market_regime = "BEARISH"

    context = DirectionQualityEngine().apply(context, "long_strict", strict_long_require_regime_bullish=True)

    assert context.direction_quality_allowed is False
    assert context.direction_quality_blocker == "STRICT_LONG_NOT_BULLISH_REGIME"


def test_long_strict_require_regime_bullish_allows_bullish() -> None:
    context = DirectionQualityEngine().apply(_planned("BULLISH"), "long_strict", strict_long_require_regime_bullish=True)

    assert context.direction_quality_allowed is True
    assert context.direction_quality_reasons == ["STRICT_RULES_PASSED"]


def test_long_strict_require_displacement_blocks_confirmation_candle() -> None:
    context = DirectionQualityEngine().apply(_planned("BULLISH"), "long_strict", strict_long_require_displacement=True)

    assert context.direction_quality_allowed is False
    assert context.direction_quality_blocker == "STRICT_LONG_NO_DISPLACEMENT"


def test_long_strict_require_displacement_allows_displacement() -> None:
    context = _planned("BULLISH")
    context.entry_trigger_type = "DISPLACEMENT"

    context = DirectionQualityEngine().apply(context, "long_strict", strict_long_require_displacement=True)

    assert context.direction_quality_allowed is True


def test_long_strict_min_setup_score_blocks_low_score() -> None:
    context = _planned("BULLISH")
    context.setup_score = 99

    context = DirectionQualityEngine().apply(context, "long_strict", strict_long_min_setup_score=100)

    assert context.direction_quality_allowed is False
    assert context.direction_quality_blocker == "STRICT_LONG_SETUP_SCORE_TOO_LOW"


def test_long_strict_min_setup_score_allows_equal_score() -> None:
    context = DirectionQualityEngine().apply(_planned("BULLISH"), "long_strict", strict_long_min_setup_score=100)

    assert context.direction_quality_allowed is True


def test_multiple_failed_requirements_all_captured() -> None:
    context = _planned("BULLISH")
    context.market_regime = "UNKNOWN"
    context.setup_score = 50

    context = DirectionQualityEngine().apply(
        context,
        "long_strict",
        strict_long_require_regime_known=True,
        strict_long_require_regime_bullish=True,
        strict_long_require_displacement=True,
        strict_long_min_setup_score=100,
    )

    assert context.direction_quality_reasons == [
        "STRICT_LONG_UNKNOWN_REGIME",
        "STRICT_LONG_NOT_BULLISH_REGIME",
        "STRICT_LONG_NO_DISPLACEMENT",
        "STRICT_LONG_SETUP_SCORE_TOO_LOW",
    ]


def test_no_planned_trade_does_not_crash() -> None:
    context = DirectionQualityEngine().apply(MarketContext(), "long_strict")

    assert context.direction_quality_allowed is None
    assert context.direction_quality_blocker == "NO_PLANNED_TRADE"


def test_does_not_mutate_unrelated_fields() -> None:
    context = _planned("BULLISH")
    before_bos = deepcopy(context.bos)

    DirectionQualityEngine().apply(context, "long_strict", strict_long_require_regime_bullish=True)

    assert context.bos == before_bos
