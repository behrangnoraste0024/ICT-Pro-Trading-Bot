from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from engine.backtest.trade_outcome_diagnostics_engine import TradeOutcomeDiagnosticsEngine
from models.entry_trigger_event import EntryTriggerEvent
from models.market_context import MarketContext
from models.ote_zone import OTEZone
from models.setup_event import SetupEvent
from models.trade_quality_event import TradeQualityEvent


def _trade_context(status: str = "PAPER_CLOSED_TP", direction: str = "BULLISH", pnl: float | None = 20) -> MarketContext:
    context = MarketContext()
    context.paper_trade_status = status
    context.paper_trade_direction = direction
    context.paper_entry_price = 100
    context.paper_stop_loss = 90 if direction in ("BULLISH", "LONG", "BUY") else 110
    context.paper_take_profit = 120 if direction in ("BULLISH", "LONG", "BUY") else 80
    context.paper_exit_price = 120 if status == "PAPER_CLOSED_TP" else 90
    context.paper_pnl = pnl
    context.paper_entry_index = 1
    context.paper_exit_index = 2 if status != "PAPER_OPEN" else None
    return context


def test_no_paper_trades_returns_empty_diagnostics() -> None:
    diagnostics = TradeOutcomeDiagnosticsEngine().summarize_contexts([MarketContext()])

    assert diagnostics.total_trades == 0
    assert diagnostics.trades == []


def test_paper_closed_tp_maps_to_win() -> None:
    record = TradeOutcomeDiagnosticsEngine().collect_from_context(_trade_context("PAPER_CLOSED_TP"), 1)

    assert record.result == "WIN"


def test_paper_closed_sl_maps_to_loss() -> None:
    record = TradeOutcomeDiagnosticsEngine().collect_from_context(_trade_context("PAPER_CLOSED_SL", pnl=-10), 1)

    assert record.result == "LOSS"


def test_paper_open_maps_to_open() -> None:
    record = TradeOutcomeDiagnosticsEngine().collect_from_context(_trade_context("PAPER_OPEN", pnl=None), 1)

    assert record.result == "OPEN"


def test_long_risk_reward_calculation() -> None:
    record = TradeOutcomeDiagnosticsEngine().collect_from_context(_trade_context(direction="BULLISH"), 1)

    assert record.risk == 10
    assert record.reward == 20
    assert record.risk_reward == 2


def test_short_risk_reward_calculation() -> None:
    record = TradeOutcomeDiagnosticsEngine().collect_from_context(_trade_context(direction="BEARISH"), 1)

    assert record.risk == 10
    assert record.reward == 20
    assert record.risk_reward == 2


def test_direction_normalization_bullish_to_long() -> None:
    record = TradeOutcomeDiagnosticsEngine().collect_from_context(_trade_context(direction="BULLISH"), 1)

    assert record.direction == "LONG"


def test_direction_normalization_bearish_to_short() -> None:
    record = TradeOutcomeDiagnosticsEngine().collect_from_context(_trade_context(direction="BEARISH"), 1)

    assert record.direction == "SHORT"


def test_aggregates_trade_metrics() -> None:
    diagnostics = TradeOutcomeDiagnosticsEngine().summarize_contexts(
        [
            _trade_context("PAPER_CLOSED_TP", pnl=20),
            _trade_context("PAPER_CLOSED_SL", pnl=-10),
            _trade_context("PAPER_OPEN", pnl=None),
        ]
    )

    assert diagnostics.total_trades == 3
    assert diagnostics.closed_trades == 2
    assert diagnostics.open_trades == 1
    assert diagnostics.wins == 1
    assert diagnostics.losses == 1
    assert diagnostics.net_pnl == 10
    assert diagnostics.average_pnl == 5
    assert diagnostics.win_rate == 50


def test_average_win_and_largest_win_calculated() -> None:
    diagnostics = TradeOutcomeDiagnosticsEngine().summarize_contexts(
        [_trade_context("PAPER_CLOSED_TP", pnl=10), _trade_context("PAPER_CLOSED_TP", pnl=30)]
    )

    assert diagnostics.average_win == 20
    assert diagnostics.largest_win == 30


def test_average_loss_and_largest_loss_calculated() -> None:
    diagnostics = TradeOutcomeDiagnosticsEngine().summarize_contexts(
        [_trade_context("PAPER_CLOSED_SL", pnl=-10), _trade_context("PAPER_CLOSED_SL", pnl=-30)]
    )

    assert diagnostics.average_loss == -20
    assert diagnostics.largest_loss == -30


def test_matched_poi_count_and_types_extracted_safely() -> None:
    context = _trade_context()
    context.active_setup = SimpleNamespace(
        matched_pois=[SimpleNamespace(poi_type="ORDER_BLOCK"), SimpleNamespace(event_type="FVG")]
    )

    record = TradeOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record.matched_poi_count == 2
    assert record.matched_poi_types == ["ORDER_BLOCK", "FVG"]


def test_collect_from_context_extracts_metadata_from_real_nested_events() -> None:
    context = _trade_context()
    context.active_setup = SetupEvent(
        direction="BULLISH",
        status="VALID",
        score=85,
        price_zone="DISCOUNT",
        ote_direction="BULLISH",
        in_ote_zone=True,
        matched_pois=["ORDER_BLOCK:BULLISH:10"],
    )
    context.entry_trigger = EntryTriggerEvent(
        direction="BULLISH",
        status="CONFIRMED",
        trigger_type="DISPLACEMENT",
        confirmed=True,
        candle_index=1,
        current_price=105,
    )
    context.trade_quality = TradeQualityEvent(status="APPROVED", score=90, risk_reward=2.5)
    context.ote = OTEZone(
        direction="BULLISH",
        dealing_range_high=110,
        dealing_range_low=90,
        level_62=97.6,
        level_705=95.9,
        level_79=94.2,
        lower_bound=94.2,
        upper_bound=97.6,
        current_price=95,
        in_zone=True,
    )

    record = TradeOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record.setup_status == "VALID"
    assert record.setup_bias == "BULLISH"
    assert record.setup_score == 85
    assert record.entry_status == "CONFIRMED"
    assert record.entry_trigger_type == "DISPLACEMENT"
    assert record.current_price_zone == "DISCOUNT"
    assert record.in_ote_zone is True
    assert record.ote_direction == "BULLISH"
    assert record.matched_poi_count == 1
    assert record.matched_poi_types == ["str"]
    assert record.trade_quality_status == "APPROVED"
    assert record.trade_quality_score == 90


def test_collect_from_context_extracts_metadata_from_event_lists_and_nested_zone_objects() -> None:
    context = _trade_context()
    context.setups = [
        SetupEvent(direction="BULLISH", status="INVALID", score=25),
        SetupEvent(
            direction="BEARISH",
            status="VALID",
            score=100,
            price_zone="PREMIUM",
            ote_direction="BEARISH",
            in_ote_zone=True,
            matched_pois=["ORDER_BLOCK:BEARISH:9"],
        ),
    ]
    context.entry_triggers = [
        EntryTriggerEvent(
            direction="BEARISH",
            status="CONFIRMED",
            trigger_type="CONFIRMATION_CANDLE",
            confirmed=True,
            candle_index=1,
            current_price=99,
        )
    ]
    context.trade_quality_events = [TradeQualityEvent(status="APPROVED", score=90, risk_reward=3)]
    context.premium_discount = SimpleNamespace(zone="PREMIUM")
    context.ote = SimpleNamespace(in_zone=True, direction="BEARISH")

    record = TradeOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record.setup_score == 100
    assert record.setup_bias == "BEARISH"
    assert record.entry_trigger_type == "CONFIRMATION_CANDLE"
    assert record.current_price_zone == "PREMIUM"
    assert record.in_ote_zone is True
    assert record.ote_direction == "BEARISH"
    assert record.matched_poi_count == 1
    assert record.trade_quality_score == 90


def test_missing_trade_metadata_stays_none_instead_of_context_defaults() -> None:
    record = TradeOutcomeDiagnosticsEngine().collect_from_context(_trade_context(), 1)

    assert record.setup_score is None
    assert record.entry_trigger_type is None
    assert record.current_price_zone is None
    assert record.in_ote_zone is None


def test_collect_from_context_extracts_regime_and_direction_metadata() -> None:
    context = _trade_context()
    context.market_regime = "BEARISH"
    context.market_regime_mode = "rolling_return"
    context.market_regime_lookback = 200
    context.market_regime_threshold_pct = 0.01
    context.market_regime_return_pct = -0.0234
    context.market_regime_fallback = "all"
    context.market_regime_reason = "BEARISH_ROLLING_RETURN"
    context.direction_mode_requested = "regime_trend"
    context.direction_mode_applied = "regime_trend"
    context.direction_mode_allowed = True
    context.direction_mode_fallback_reason = "REGIME_TREND_BEARISH_SHORT_ONLY"
    context.direction_mode_resolved_direction = "SHORT"
    context.regime_source_regime = "BEARISH"
    context.regime_fallback = "all"

    record = TradeOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record.market_regime == "BEARISH"
    assert record.market_regime_return_pct == -0.0234
    assert record.market_regime_reason == "BEARISH_ROLLING_RETURN"
    assert record.direction_mode_applied == "regime_trend"
    assert record.direction_mode_allowed is True
    assert record.direction_mode_resolved_direction == "SHORT"
    assert record.regime_source_regime == "BEARISH"


def test_collect_from_context_preserves_unknown_market_regime() -> None:
    context = _trade_context()
    context.market_regime = "UNKNOWN"
    context.market_regime_reason = "INSUFFICIENT_CANDLES"

    record = TradeOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record.market_regime == "UNKNOWN"
    assert record.market_regime_reason == "INSUFFICIENT_CANDLES"


def test_collect_from_context_extracts_direction_quality_metadata() -> None:
    context = _trade_context()
    context.direction_quality_mode_requested = "long_strict"
    context.direction_quality_applied = "long_strict"
    context.direction_quality_allowed = False
    context.direction_quality_blocked_direction = "LONG"
    context.direction_quality_blocker = "STRICT_LONG_NO_DISPLACEMENT"
    context.direction_quality_reasons = ["STRICT_LONG_NO_DISPLACEMENT", "STRICT_LONG_SETUP_SCORE_TOO_LOW"]

    record = TradeOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record.direction_quality_mode_requested == "long_strict"
    assert record.direction_quality_applied == "long_strict"
    assert record.direction_quality_allowed is False
    assert record.direction_quality_blocked_direction == "LONG"
    assert record.direction_quality_blocker == "STRICT_LONG_NO_DISPLACEMENT"
    assert record.direction_quality_reasons == ["STRICT_LONG_NO_DISPLACEMENT", "STRICT_LONG_SETUP_SCORE_TOO_LOW"]


def test_blockers_and_reasons_copied_safely() -> None:
    context = _trade_context()
    context.setup_blockers = ["A"]
    context.entry_blockers = ["B"]
    context.trade_plan_blockers = ["C"]
    context.trade_quality_blockers = ["D"]
    context.paper_trade_blockers = ["E"]
    context.paper_trade_reasons = ["R"]

    record = TradeOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record.setup_blockers == ["A"]
    assert record.entry_blockers == ["B"]
    assert record.trade_plan_blockers == ["C"]
    assert record.trade_quality_blockers == ["D"]
    assert record.paper_trade_blockers == ["E"]
    assert record.reasons == ["R"]


def test_missing_fields_do_not_crash() -> None:
    context = MarketContext()
    context.paper_trade_status = "PAPER_OPEN"

    record = TradeOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record is not None
    assert record.result == "OPEN"


def test_summarize_contexts_does_not_mutate_input_contexts() -> None:
    context = _trade_context()
    before = deepcopy(context.__dict__)

    TradeOutcomeDiagnosticsEngine().summarize_contexts([context])

    assert context.__dict__ == before


def test_str_includes_event_type_and_net_pnl() -> None:
    diagnostics = TradeOutcomeDiagnosticsEngine().summarize_contexts([_trade_context()])
    output = str(diagnostics)

    assert "TRADE_OUTCOME_DIAGNOSTICS" in output
    assert "NET_PNL=20.0" in output
