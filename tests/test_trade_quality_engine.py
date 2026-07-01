from __future__ import annotations

from types import SimpleNamespace

from engine.trade_quality.trade_quality_engine import TradeQualityEngine
from models.market_context import MarketContext
from models.trade_quality_event import TradeQualityEvent


def _planned_context() -> MarketContext:
    context = MarketContext()
    context.trade_plan_status = "PLANNED"
    context.trade_direction = "BULLISH"
    context.trade_plan = SimpleNamespace(status="PLANNED")
    context.planned_entry_price = 100
    context.planned_stop_loss = 98
    context.planned_take_profit = 106
    context.planned_risk = 2
    context.planned_reward = 6
    context.planned_risk_reward = 3
    return context


def test_no_planned_trade_rejected() -> None:
    context = MarketContext()
    context.trade_plan_status = "NO_TRADE"

    context = TradeQualityEngine().detect(context)

    assert context.trade_quality_status == "REJECTED"
    assert context.trade_quality_score == 0
    assert context.trade_quality is None
    assert "NO_PLANNED_TRADE" in context.trade_quality_blockers


def test_approved_high_quality_trade() -> None:
    context = TradeQualityEngine().detect(_planned_context())

    assert context.trade_quality_status == "APPROVED"
    assert context.trade_quality_score == 100
    assert context.trade_quality_blockers == []
    assert context.trade_quality is not None


def test_rr_too_low_rejected() -> None:
    context = _planned_context()
    context.planned_risk_reward = 1.5

    context = TradeQualityEngine().detect(context)

    assert context.trade_quality_status == "REJECTED"
    assert "RR_TOO_LOW" in context.trade_quality_blockers


def test_lower_minimum_rr_approves_1_5r_trade() -> None:
    context = _planned_context()
    context.planned_take_profit = 103
    context.planned_reward = 3
    context.planned_risk_reward = 1.5

    context = TradeQualityEngine(minimum_rr=1.5).detect(context)

    assert context.trade_quality_status == "APPROVED"
    assert context.trade_quality_score == 100
    assert context.trade_quality_blockers == []


def test_risk_too_tight_rejected() -> None:
    context = _planned_context()
    context.planned_risk = 0.01

    context = TradeQualityEngine().detect(context)

    assert context.trade_quality_status == "REJECTED"
    assert "RISK_TOO_TIGHT" in context.trade_quality_blockers


def test_risk_too_wide_rejected() -> None:
    context = _planned_context()
    context.planned_risk = 3

    context = TradeQualityEngine().detect(context)

    assert context.trade_quality_status == "REJECTED"
    assert "RISK_TOO_WIDE" in context.trade_quality_blockers


def test_invalid_reward_distance_rejected() -> None:
    context = _planned_context()
    context.planned_reward = 0

    context = TradeQualityEngine().detect(context)

    assert context.trade_quality_status == "REJECTED"
    assert "INVALID_REWARD_DISTANCE" in context.trade_quality_blockers


def test_invalid_trade_direction_rejected() -> None:
    context = _planned_context()
    context.trade_direction = "NONE"

    context = TradeQualityEngine().detect(context)

    assert context.trade_quality_status == "REJECTED"
    assert "INVALID_TRADE_DIRECTION" in context.trade_quality_blockers


def test_incomplete_trade_plan_rejected() -> None:
    context = _planned_context()
    context.planned_take_profit = None

    context = TradeQualityEngine().detect(context)

    assert context.trade_quality_status == "REJECTED"
    assert "INCOMPLETE_TRADE_PLAN" in context.trade_quality_blockers


def test_invalid_entry_price_rejected_without_crashing() -> None:
    context = _planned_context()
    context.planned_entry_price = 0

    context = TradeQualityEngine().detect(context)

    assert context.trade_quality_status == "REJECTED"
    assert "INVALID_ENTRY_PRICE" in context.trade_quality_blockers
    assert context.trade_quality is not None
    assert context.trade_quality.risk_percent is None
    assert context.trade_quality.reward_percent is None


def test_quality_score_too_low_rejected() -> None:
    context = TradeQualityEngine(minimum_quality_score=101).detect(_planned_context())

    assert context.trade_quality_status == "REJECTED"
    assert "QUALITY_SCORE_TOO_LOW" in context.trade_quality_blockers


def test_trade_quality_event_string_for_approved_trade() -> None:
    event = TradeQualityEvent(status="APPROVED", score=100, risk_reward=2.4)

    output = str(event)

    assert "APPROVED" in output
    assert "SCORE=100" in output


def test_trade_quality_event_string_for_rejected_trade() -> None:
    event = TradeQualityEvent(status="REJECTED", score=60, blockers=["RR_TOO_LOW", "RISK_TOO_WIDE"])

    output = str(event)

    assert "REJECTED" in output
    assert "BLOCKERS=RR_TOO_LOW,RISK_TOO_WIDE" in output


def test_existing_context_objects_are_preserved() -> None:
    context = _planned_context()
    context.bos = ["bos"]
    context.choch = ["choch"]
    context.liquidity_sweeps = ["sweep"]
    context.fvgs = ["fvg"]
    context.order_blocks = ["order_block"]
    context.breaker_blocks = ["breaker"]
    context.ote = "ote"
    context.setups = ["setup"]
    context.active_setup = "active_setup"
    context.entry_trigger = "entry_trigger"
    trade_plan = context.trade_plan

    context = TradeQualityEngine().detect(context)

    assert context.bos == ["bos"]
    assert context.choch == ["choch"]
    assert context.liquidity_sweeps == ["sweep"]
    assert context.fvgs == ["fvg"]
    assert context.order_blocks == ["order_block"]
    assert context.breaker_blocks == ["breaker"]
    assert context.ote == "ote"
    assert context.setups == ["setup"]
    assert context.active_setup == "active_setup"
    assert context.entry_trigger == "entry_trigger"
    assert context.trade_plan is trade_plan


def test_debug_values_are_populated() -> None:
    context = TradeQualityEngine().detect(_planned_context())

    assert context.debug["trade_quality_status"] == "APPROVED"
    assert context.debug["trade_quality_score"] == 100
    assert context.debug["trade_quality_blockers"] == []
    assert context.debug["trade_quality_reasons"] == [
        "TRADE_PLAN_COMPLETE",
        "RR_OK",
        "RISK_DISTANCE_OK",
        "REWARD_DISTANCE_OK",
        "DIRECTION_OK",
    ]
