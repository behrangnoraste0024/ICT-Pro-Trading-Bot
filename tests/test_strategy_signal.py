from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict

from models.market_context import MarketContext
from strategy import ICTStrategy, evaluate_strategy_signal


_DEFAULT_ENTRY_TRIGGER = object()


def _context(
    *,
    trend: str,
    setup_bias: str,
    entry_direction: str,
    ote_direction: str,
    setup_status: str = "VALID",
    entry_confirmed: bool = True,
    entry_trigger: object | None = _DEFAULT_ENTRY_TRIGGER,
    entry_trigger_type: str = "DISPLACEMENT_BREAK",
    entry_status: str | None = None,
    entry_blockers: list | None = None,
    entry: object | None = None,
    displacement_state: str = "CONFIRMED",
    session_filter_state: str = "ALLOWED",
    current_price_zone: str | None = None,
    trend_bias_state: str | None = None,
    swings: list | None = None,
    structure: list | None = None,
    bos: list | None = None,
    choch: list | None = None,
    liquidity: list | None = None,
    liquidity_sweeps: list | None = None,
    fvgs: list | None = None,
    order_blocks: list | None = None,
    breaker_blocks: list | None = None,
) -> MarketContext:
    resolved_price_zone = current_price_zone or ("DISCOUNT" if setup_bias == "LONG" else "PREMIUM")
    context = MarketContext(
        candles=[{"close": 100.0}],
        swings=[{"type": "low"}, {"type": "high"}] if swings is None else swings,
        structure=[{"type": "structure"}] if structure is None else structure,
        trend=trend,
        bos=[{"direction": trend}] if bos is None else bos,
        choch=[] if choch is None else choch,
        external_high=110.0,
        external_low=90.0,
        internal_highs=[{"price": 105.0}],
        internal_lows=[{"price": 95.0}],
        liquidity=[{"level": 100.0}] if liquidity is None else liquidity,
        liquidity_sweeps=[{"side": setup_bias}] if liquidity_sweeps is None else liquidity_sweeps,
        fvgs=[{"active": True}] if fvgs is None else fvgs,
        order_blocks=[{"side": setup_bias}] if order_blocks is None else order_blocks,
        breaker_blocks=[{"side": setup_bias}] if breaker_blocks is None else breaker_blocks,
        dealing_range_high=110.0,
        dealing_range_low=90.0,
        current_price=96.0,
        current_price_zone=resolved_price_zone,
        ote_direction=ote_direction,
        in_ote_zone=True,
        setup_bias=setup_bias,
        setup_score=85,
        setup_status=setup_status,
        entry_trigger={"type": entry_trigger_type} if entry_trigger is _DEFAULT_ENTRY_TRIGGER else entry_trigger,
        entry_direction=entry_direction,
        entry_status=entry_status or ("CONFIRMED" if entry_confirmed else "NOT_CONFIRMED"),
        entry_trigger_type=entry_trigger_type,
        entry_confirmed=entry_confirmed,
        entry_blockers=[] if entry_blockers is None else entry_blockers,
    )
    if entry is not None:
        context.entry = entry
    context.discount_zone = {"low": 90.0, "high": 100.0}
    context.premium_zone = {"low": 100.0, "high": 110.0}
    context.displacement_state = displacement_state
    context.session_filter_state = session_filter_state
    if trend_bias_state is not None:
        context.trend_bias_state = trend_bias_state
    return context


def test_strategy_signal_is_deterministic_for_same_context() -> None:
    context = _context(trend="BULLISH", setup_bias="LONG", entry_direction="LONG", ote_direction="LONG")

    first = evaluate_strategy_signal(context)
    second = evaluate_strategy_signal(context)

    assert first == second


def test_strategy_signal_reports_long_condition() -> None:
    context = _context(trend="BULLISH", setup_bias="LONG", entry_direction="LONG", ote_direction="LONG")

    result = ICTStrategy().evaluate(context)

    assert result.signal_status == "SIGNAL"
    assert result.direction == "LONG"
    assert result.confidence_score > 0
    assert "LONG directional context is aligned" in result.reasons
    assert "entry trigger evidence is present" in result.reasons
    assert "displacement evidence is confirmed" in result.reasons
    assert "session filter allows strategy evaluation" in result.reasons
    assert "liquidity evidence is present" in result.reasons
    assert "liquidity sweep evidence is present" in result.reasons
    assert "fair value gap evidence is present" in result.reasons
    assert "order block evidence is present" in result.reasons
    assert "breaker block evidence is present" in result.reasons
    assert "premium/discount evidence supports LONG" in result.reasons
    assert "trend bias supports LONG" in result.reasons
    assert "market structure evidence is present" in result.reasons
    assert "swing context evidence is present" in result.reasons
    assert result.blockers == []
    assert result.event_type == "STRATEGY_SIGNAL"


def test_strategy_signal_reports_short_condition() -> None:
    context = _context(trend="BEARISH", setup_bias="SHORT", entry_direction="SHORT", ote_direction="SHORT")

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "SIGNAL"
    assert result.direction == "SHORT"
    assert result.confidence_score > 0
    assert "SHORT directional context is aligned" in result.reasons
    assert "entry trigger evidence is present" in result.reasons
    assert "displacement evidence is confirmed" in result.reasons
    assert "session filter allows strategy evaluation" in result.reasons
    assert "liquidity evidence is present" in result.reasons
    assert "liquidity sweep evidence is present" in result.reasons
    assert "fair value gap evidence is present" in result.reasons
    assert "order block evidence is present" in result.reasons
    assert "breaker block evidence is present" in result.reasons
    assert "premium/discount evidence supports SHORT" in result.reasons
    assert "trend bias supports SHORT" in result.reasons
    assert "market structure evidence is present" in result.reasons
    assert "swing context evidence is present" in result.reasons
    assert result.blockers == []


def test_strategy_signal_reports_no_signal_when_direction_is_not_aligned() -> None:
    context = _context(trend="UNKNOWN", setup_bias="NONE", entry_direction="NONE", ote_direction="NONE")

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "NO_SIGNAL"
    assert result.direction == "NONE"
    assert result.confidence_score == 0.0
    assert "directional context is not aligned" in result.blockers


def test_strategy_signal_reports_existing_and_derived_blockers() -> None:
    context = _context(
        trend="BULLISH",
        setup_bias="LONG",
        entry_direction="LONG",
        ote_direction="LONG",
        setup_status="INVALID",
        entry_confirmed=False,
    )
    context.setup_blockers = ["setup quality below threshold"]
    context.entry_blockers = ["entry trigger missing"]

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "NO_SIGNAL"
    assert result.direction == "NONE"
    assert result.blockers == [
        "setup quality below threshold",
        "entry trigger missing",
        "setup status is not valid",
        "entry is not confirmed",
        "entry status is not confirmed",
    ]


def test_strategy_signal_reports_displacement_advisory_blocker() -> None:
    context = _context(
        trend="BULLISH",
        setup_bias="LONG",
        entry_direction="LONG",
        ote_direction="LONG",
        displacement_state="WEAK",
    )

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "NO_SIGNAL"
    assert result.direction == "NONE"
    assert "displacement evidence is not confirmed" in result.blockers
    assert result.source_evidence["displacement_state"] == "WEAK"


def test_strategy_signal_reports_session_filter_advisory_blocker() -> None:
    context = _context(
        trend="BULLISH",
        setup_bias="LONG",
        entry_direction="LONG",
        ote_direction="LONG",
        session_filter_state="BLOCKED",
    )

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "NO_SIGNAL"
    assert result.direction == "NONE"
    assert "session filter does not allow strategy evaluation" in result.blockers
    assert result.source_evidence["session_filter_state"] == "BLOCKED"


def test_strategy_signal_reports_premium_discount_advisory_blocker() -> None:
    context = _context(
        trend="BULLISH",
        setup_bias="LONG",
        entry_direction="LONG",
        ote_direction="LONG",
        current_price_zone="PREMIUM",
    )

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "NO_SIGNAL"
    assert result.direction == "NONE"
    assert "premium/discount evidence is not aligned" in result.blockers
    assert result.source_evidence["premium_discount_state"] == "PREMIUM"


def test_strategy_signal_reports_trend_bias_advisory_blocker() -> None:
    context = _context(
        trend="BULLISH",
        setup_bias="LONG",
        entry_direction="LONG",
        ote_direction="LONG",
        trend_bias_state="BEARISH",
    )

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "NO_SIGNAL"
    assert result.direction == "NONE"
    assert "trend bias is not aligned" in result.blockers
    assert result.source_evidence["trend_bias_state"] == "BEARISH"


def test_strategy_signal_reports_market_structure_advisory_blocker() -> None:
    context = _context(
        trend="BULLISH",
        setup_bias="LONG",
        entry_direction="LONG",
        ote_direction="LONG",
        structure=[],
        bos=[],
        choch=[],
    )
    context.external_high = None
    context.external_low = None
    context.internal_highs = []
    context.internal_lows = []

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "NO_SIGNAL"
    assert result.direction == "NONE"
    assert "market structure evidence is missing" in result.blockers
    assert result.source_evidence["market_structure_present"] is False


def test_strategy_signal_reports_swing_context_advisory_blocker() -> None:
    context = _context(
        trend="BULLISH",
        setup_bias="LONG",
        entry_direction="LONG",
        ote_direction="LONG",
        swings=[{"type": "low"}],
    )

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "NO_SIGNAL"
    assert result.direction == "NONE"
    assert "swing context evidence is insufficient" in result.blockers
    assert result.source_evidence["swing_context_present"] is False


def test_strategy_signal_reports_liquidity_advisory_blocker() -> None:
    context = _context(
        trend="BULLISH",
        setup_bias="LONG",
        entry_direction="LONG",
        ote_direction="LONG",
        liquidity=[],
    )

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "NO_SIGNAL"
    assert result.direction == "NONE"
    assert "liquidity evidence is missing" in result.blockers
    assert result.source_evidence["liquidity_present"] is False


def test_strategy_signal_reports_liquidity_sweep_advisory_blocker() -> None:
    context = _context(
        trend="BULLISH",
        setup_bias="LONG",
        entry_direction="LONG",
        ote_direction="LONG",
        liquidity_sweeps=[],
    )

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "NO_SIGNAL"
    assert result.direction == "NONE"
    assert "liquidity sweep evidence is missing" in result.blockers
    assert result.source_evidence["liquidity_sweep_present"] is False


def test_strategy_signal_reports_fvg_advisory_blocker() -> None:
    context = _context(
        trend="BULLISH",
        setup_bias="LONG",
        entry_direction="LONG",
        ote_direction="LONG",
        fvgs=[],
    )

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "NO_SIGNAL"
    assert result.direction == "NONE"
    assert "fair value gap evidence is missing" in result.blockers
    assert result.source_evidence["fvg_present"] is False


def test_strategy_signal_reports_order_block_advisory_blocker() -> None:
    context = _context(
        trend="BULLISH",
        setup_bias="LONG",
        entry_direction="LONG",
        ote_direction="LONG",
        order_blocks=[],
    )

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "NO_SIGNAL"
    assert result.direction == "NONE"
    assert "order block evidence is missing" in result.blockers
    assert result.source_evidence["order_block_present"] is False


def test_strategy_signal_reports_breaker_block_advisory_blocker() -> None:
    context = _context(
        trend="BULLISH",
        setup_bias="LONG",
        entry_direction="LONG",
        ote_direction="LONG",
        breaker_blocks=[],
    )

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "NO_SIGNAL"
    assert result.direction == "NONE"
    assert "breaker block evidence is missing" in result.blockers
    assert result.source_evidence["breaker_block_present"] is False


def test_strategy_signal_reports_entry_trigger_advisory_blocker() -> None:
    context = _context(
        trend="BULLISH",
        setup_bias="LONG",
        entry_direction="LONG",
        ote_direction="LONG",
        entry_trigger=None,
        entry_trigger_type="NONE",
    )

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "NO_SIGNAL"
    assert result.direction == "NONE"
    assert "entry trigger evidence is missing" in result.blockers
    assert result.source_evidence["entry_trigger_present"] is False


def test_strategy_signal_reports_entry_status_advisory_blocker() -> None:
    context = _context(
        trend="BULLISH",
        setup_bias="LONG",
        entry_direction="LONG",
        ote_direction="LONG",
        entry_status="PENDING",
    )

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "NO_SIGNAL"
    assert result.direction == "NONE"
    assert "entry status is not confirmed" in result.blockers
    assert result.source_evidence["entry_status"] == "PENDING"


def test_strategy_signal_reports_entry_blocker_evidence() -> None:
    context = _context(
        trend="BULLISH",
        setup_bias="LONG",
        entry_direction="LONG",
        ote_direction="LONG",
        entry_blockers=["entry candle did not close through trigger"],
    )

    result = evaluate_strategy_signal(context)

    assert result.signal_status == "NO_SIGNAL"
    assert result.direction == "NONE"
    assert "entry candle did not close through trigger" in result.blockers
    assert result.source_evidence["entry_blockers_count"] == 1


def test_strategy_signal_has_no_execution_authority_fields() -> None:
    context = _context(trend="BULLISH", setup_bias="LONG", entry_direction="LONG", ote_direction="LONG")

    payload = asdict(evaluate_strategy_signal(context))

    assert set(payload) == {
        "signal_status",
        "direction",
        "confidence_score",
        "reasons",
        "blockers",
        "source_evidence",
        "event_type",
    }
    forbidden = {
        "quantity",
        "position_size",
        "stop_loss",
        "take_profit",
        "order",
        "permit",
        "signature",
        "transport",
        "paper_fill",
        "persistence",
    }
    assert forbidden.isdisjoint(payload)


def test_strategy_signal_does_not_mutate_market_context() -> None:
    context = _context(trend="BULLISH", setup_bias="LONG", entry_direction="LONG", ote_direction="LONG")
    before = deepcopy(context)

    evaluate_strategy_signal(context)

    assert context == before
