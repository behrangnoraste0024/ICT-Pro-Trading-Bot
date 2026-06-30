from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from engine.backtest.trade_outcome_diagnostics_engine import TradeOutcomeDiagnosticsEngine
from models.market_context import MarketContext


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
