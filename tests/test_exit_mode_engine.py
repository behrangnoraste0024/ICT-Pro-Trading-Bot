from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from engine.trade_management.exit_mode_engine import ExitModeEngine
from models.market_context import MarketContext
from models.trade_plan_event import TradePlanEvent


def _planned_context(
    direction: str = "BULLISH",
    entry: float | None = 100,
    stop: float | None = 90,
    take_profit: float | None = 150,
    status: str = "PLANNED",
) -> MarketContext:
    context = MarketContext()
    context.trade_plan_status = status
    context.trade_direction = direction
    risk = None
    reward = None
    risk_reward = None
    if entry is not None and stop is not None and take_profit is not None and direction in ("BULLISH", "BEARISH"):
        risk = entry - stop if direction == "BULLISH" else stop - entry
        reward = take_profit - entry if direction == "BULLISH" else entry - take_profit
        risk_reward = reward / risk if risk > 0 else None
    context.planned_entry_price = entry
    context.planned_stop_loss = stop
    context.planned_take_profit = take_profit
    context.planned_risk = risk
    context.planned_reward = reward
    context.planned_risk_reward = risk_reward
    context.trade_plan = TradePlanEvent(
        direction=direction,
        status=status,
        entry_price=entry,
        stop_loss=stop,
        take_profit=take_profit,
        risk=risk,
        reward=reward,
        risk_reward=risk_reward,
        entry_trigger_type="CONFIRMATION_CANDLE",
    )
    return context


def test_original_mode_does_not_change_tp_or_rr() -> None:
    context = _planned_context()

    ExitModeEngine().apply(context, "original")

    assert context.planned_take_profit == 150
    assert context.planned_risk_reward == 5
    assert context.exit_mode_applied == "original"
    assert context.exit_mode_fallback_reason == "ORIGINAL_MODE"


def test_fixed_1r_long() -> None:
    context = _planned_context()

    ExitModeEngine().apply(context, "fixed_1r")

    assert context.planned_take_profit == 110
    assert context.planned_risk_reward == 1
    assert context.trade_plan.take_profit == 110


def test_fixed_1_5r_long() -> None:
    context = _planned_context()

    ExitModeEngine().apply(context, "fixed_1_5r")

    assert context.planned_take_profit == 115
    assert context.planned_risk_reward == 1.5


def test_fixed_2r_long() -> None:
    context = _planned_context()

    ExitModeEngine().apply(context, "fixed_2r")

    assert context.planned_take_profit == 120
    assert context.planned_risk_reward == 2


def test_fixed_3r_long() -> None:
    context = _planned_context()

    ExitModeEngine().apply(context, "fixed_3r")

    assert context.planned_take_profit == 130
    assert context.planned_risk_reward == 3


def test_fixed_1r_short() -> None:
    context = _planned_context(direction="BEARISH", stop=110, take_profit=50)

    ExitModeEngine().apply(context, "fixed_1r")

    assert context.planned_take_profit == 90
    assert context.planned_risk_reward == 1


def test_fixed_1_5r_short() -> None:
    context = _planned_context(direction="BEARISH", stop=110, take_profit=50)

    ExitModeEngine().apply(context, "fixed_1_5r")

    assert context.planned_take_profit == 85
    assert context.planned_risk_reward == 1.5


def test_fixed_2r_short() -> None:
    context = _planned_context(direction="BEARISH", stop=110, take_profit=50)

    ExitModeEngine().apply(context, "fixed_2r")

    assert context.planned_take_profit == 80
    assert context.planned_risk_reward == 2


def test_fixed_3r_short() -> None:
    context = _planned_context(direction="BEARISH", stop=110, take_profit=50)

    ExitModeEngine().apply(context, "fixed_3r")

    assert context.planned_take_profit == 70
    assert context.planned_risk_reward == 3


def test_invalid_risk_long_does_not_change_tp() -> None:
    context = _planned_context(stop=101)

    ExitModeEngine().apply(context, "fixed_1r")

    assert context.planned_take_profit == 150
    assert context.exit_mode_fallback_reason == "INVALID_RISK"


def test_invalid_risk_short_does_not_change_tp() -> None:
    context = _planned_context(direction="BEARISH", stop=99, take_profit=50)

    ExitModeEngine().apply(context, "fixed_1r")

    assert context.planned_take_profit == 50
    assert context.exit_mode_fallback_reason == "INVALID_RISK"


def test_no_planned_trade_does_not_crash() -> None:
    context = MarketContext()

    ExitModeEngine().apply(context, "fixed_1r")

    assert context.exit_mode_fallback_reason == "NO_PLANNED_TRADE"


def test_rejected_trade_plan_is_not_modified_or_promoted() -> None:
    context = _planned_context(status="REJECTED")

    ExitModeEngine().apply(context, "fixed_1r")

    assert context.trade_plan_status == "REJECTED"
    assert context.planned_take_profit == 150
    assert context.exit_mode_fallback_reason == "NO_PLANNED_TRADE"


def test_invalid_direction_does_not_change_tp() -> None:
    context = _planned_context(direction="SIDEWAYS")

    ExitModeEngine().apply(context, "fixed_1r")

    assert context.planned_take_profit == 150
    assert context.exit_mode_fallback_reason == "INVALID_DIRECTION"


def test_missing_prices_does_not_crash() -> None:
    context = _planned_context(entry=None)

    ExitModeEngine().apply(context, "fixed_1r")

    assert context.exit_mode_fallback_reason == "MISSING_PRICES"


def test_engine_does_not_mutate_unrelated_context_fields() -> None:
    context = _planned_context()
    context.setup_score = 100
    context.active_setup = SimpleNamespace(name="setup")
    before = deepcopy(context.active_setup)

    ExitModeEngine().apply(context, "fixed_1r")

    assert context.setup_score == 100
    assert context.active_setup == before


def test_debug_fields_are_populated() -> None:
    context = _planned_context()

    ExitModeEngine().apply(context, "fixed_1_5r")

    assert context.debug["exit_mode_requested"] == "fixed_1_5r"
    assert context.debug["exit_mode_applied"] == "fixed_1_5r"
    assert context.debug["exit_mode_target_r"] == 1.5
    assert context.debug["exit_mode_original_take_profit"] == 150
    assert context.debug["exit_mode_new_take_profit"] == 115
    assert context.debug["exit_mode_fallback_reason"] == "NONE"
