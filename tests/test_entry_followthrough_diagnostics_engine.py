from __future__ import annotations

from copy import deepcopy

import pandas as pd

from engine.backtest.entry_followthrough_diagnostics_engine import EntryFollowthroughDiagnosticsEngine
from models.entry_followthrough_diagnostics import EntryFollowthroughDiagnostics
from models.market_context import MarketContext


def _candles(rows: list[dict[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _context(
    direction: str = "BULLISH",
    status: str = "PAPER_CLOSED_SL",
    result_exit: float = 90,
    trigger: str = "CONFIRMATION_CANDLE",
    candles: pd.DataFrame | None = None,
) -> MarketContext:
    context = MarketContext(candles=candles)
    context.paper_trade_status = status
    context.paper_trade_direction = direction
    context.paper_entry_price = 100
    context.paper_stop_loss = 90 if direction == "BULLISH" else 110
    context.paper_take_profit = 120 if direction == "BULLISH" else 80
    context.paper_exit_price = result_exit
    context.paper_entry_index = 0
    context.paper_exit_index = None if status == "PAPER_OPEN" else max((len(candles) if candles is not None else 1) - 1, 0)
    context.paper_pnl = result_exit - 100 if direction == "BULLISH" else 100 - result_exit
    context.entry_trigger_type = trigger
    context.setup_score = 100
    context.current_price_zone = "DISCOUNT"
    context.in_ote_zone = True
    context.matched_pois = ["FVG"]
    return context


def test_no_trades_returns_empty_diagnostics() -> None:
    diagnostics = EntryFollowthroughDiagnosticsEngine().summarize_trade_contexts([MarketContext()])

    assert diagnostics.total_trades == 0
    assert diagnostics.records == []


def test_long_favorable_h1() -> None:
    context = _context(candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 101, "high": 105, "low": 100, "close": 104}]))

    record = EntryFollowthroughDiagnosticsEngine().collect_from_context(context, 1)

    assert record.horizons[1].favorable_r == 0.5


def test_long_adverse_h1() -> None:
    context = _context(candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 99, "high": 101, "low": 95, "close": 96}]))

    record = EntryFollowthroughDiagnosticsEngine().collect_from_context(context, 1)

    assert record.horizons[1].adverse_r == 0.5


def test_short_favorable_h1() -> None:
    context = _context(direction="BEARISH", candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 99, "high": 100, "low": 95, "close": 96}]))

    record = EntryFollowthroughDiagnosticsEngine().collect_from_context(context, 1)

    assert record.horizons[1].favorable_r == 0.5


def test_short_adverse_h1() -> None:
    context = _context(direction="BEARISH", candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 101, "high": 105, "low": 99, "close": 104}]))

    record = EntryFollowthroughDiagnosticsEngine().collect_from_context(context, 1)

    assert record.horizons[1].adverse_r == 0.5


def test_next_candle_continuation_long() -> None:
    context = _context(candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 101, "high": 105, "low": 100, "close": 104}]))

    record = EntryFollowthroughDiagnosticsEngine().collect_from_context(context, 1)

    assert record.next_candle_continuation is True


def test_next_candle_rejection_long() -> None:
    context = _context(candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 101, "high": 102, "low": 95, "close": 99}]))

    record = EntryFollowthroughDiagnosticsEngine().collect_from_context(context, 1)

    assert record.next_candle_rejection is True


def test_next_candle_continuation_short() -> None:
    context = _context(direction="BEARISH", candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 99, "high": 100, "low": 95, "close": 96}]))

    record = EntryFollowthroughDiagnosticsEngine().collect_from_context(context, 1)

    assert record.next_candle_continuation is True


def test_next_candle_rejection_short() -> None:
    context = _context(direction="BEARISH", candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 99, "high": 105, "low": 98, "close": 101}]))

    record = EntryFollowthroughDiagnosticsEngine().collect_from_context(context, 1)

    assert record.next_candle_rejection is True


def test_no_followthrough_3_flag() -> None:
    context = _context(candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 100, "high": 102, "low": 99, "close": 101}, {"open": 101, "high": 102, "low": 98, "close": 99}, {"open": 99, "high": 102, "low": 97, "close": 98}]))

    record = EntryFollowthroughDiagnosticsEngine().collect_from_context(context, 1)

    assert record.no_followthrough_3 is True


def test_strong_followthrough_3_flag() -> None:
    context = _context(candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 100, "high": 111, "low": 99, "close": 110}, {"open": 110, "high": 112, "low": 109, "close": 111}, {"open": 111, "high": 113, "low": 110, "close": 112}]))

    record = EntryFollowthroughDiagnosticsEngine().collect_from_context(context, 1)

    assert record.strong_followthrough_3 is True


def test_early_reversal_3_flag() -> None:
    context = _context(candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 100, "high": 104, "low": 98, "close": 99}, {"open": 99, "high": 104, "low": 90, "close": 98}, {"open": 98, "high": 103, "low": 96, "close": 97}]))

    record = EntryFollowthroughDiagnosticsEngine().collect_from_context(context, 1)

    assert record.early_reversal_3 is True


def test_immediate_favorable_flag() -> None:
    context = _context(candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 100, "high": 103, "low": 99, "close": 102}]))

    record = EntryFollowthroughDiagnosticsEngine().collect_from_context(context, 1)

    assert record.immediate_favorable is True


def test_immediate_adverse_flag() -> None:
    context = _context(candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 100, "high": 101, "low": 95, "close": 96}]))

    record = EntryFollowthroughDiagnosticsEngine().collect_from_context(context, 1)

    assert record.immediate_adverse is True


def test_aggregates_averages_for_h1_h3_h5() -> None:
    rows = [
        {"open": 100, "high": 100, "low": 100, "close": 100},
        {"open": 100, "high": 105, "low": 95, "close": 101},
        {"open": 101, "high": 106, "low": 96, "close": 102},
        {"open": 102, "high": 107, "low": 97, "close": 103},
        {"open": 103, "high": 108, "low": 98, "close": 104},
        {"open": 104, "high": 109, "low": 99, "close": 105},
    ]

    diagnostics = EntryFollowthroughDiagnosticsEngine().summarize_trade_contexts([_context(candles=_candles(rows))])

    assert diagnostics.average_h1_favorable_r == 0.5
    assert diagnostics.average_h3_favorable_r == 0.7
    assert diagnostics.average_h5_favorable_r == 0.9


def test_by_trigger_counts_and_averages() -> None:
    winner = _context(status="PAPER_CLOSED_TP", result_exit=120, trigger="DISPLACEMENT", candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 100, "high": 110, "low": 99, "close": 109}]))
    loser = _context(trigger="DISPLACEMENT", candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 100, "high": 102, "low": 95, "close": 96}]))

    diagnostics = EntryFollowthroughDiagnosticsEngine().summarize_trade_contexts([winner, loser])

    assert diagnostics.trigger_counts["DISPLACEMENT"] == 2
    assert diagnostics.trigger_win_counts["DISPLACEMENT"] == 1
    assert diagnostics.trigger_loss_counts["DISPLACEMENT"] == 1
    assert diagnostics.trigger_average_h3_favorable_r["DISPLACEMENT"] == 0.6


def test_by_direction_no_followthrough_counts() -> None:
    long_record = _context(candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 100, "high": 102, "low": 99, "close": 101}]))
    short_record = _context(direction="BEARISH", candles=_candles([{"open": 100, "high": 100, "low": 100, "close": 100}, {"open": 100, "high": 101, "low": 98, "close": 99}]))

    diagnostics = EntryFollowthroughDiagnosticsEngine().summarize_trade_contexts([long_record, short_record])

    assert diagnostics.long_no_followthrough_3_count == 1
    assert diagnostics.short_no_followthrough_3_count == 1


def test_missing_indices_do_not_crash() -> None:
    context = _context(candles=_candles([{"open": 100, "high": 101, "low": 99, "close": 100}]))
    context.paper_entry_index = None

    record = EntryFollowthroughDiagnosticsEngine().collect_from_context(context, 1)

    assert record is not None
    assert record.horizons == {}


def test_missing_candles_do_not_crash() -> None:
    record = EntryFollowthroughDiagnosticsEngine().collect_from_context(_context(candles=None), 1)

    assert record is not None
    assert record.horizons == {}


def test_summarize_trade_contexts_does_not_mutate_contexts() -> None:
    context = _context(candles=_candles([{"open": 100, "high": 101, "low": 99, "close": 100}]))
    before = deepcopy(context.__dict__)

    EntryFollowthroughDiagnosticsEngine().summarize_trade_contexts([context])

    pd.testing.assert_frame_equal(context.candles, before.pop("candles"))
    current = dict(context.__dict__)
    current.pop("candles")
    assert current == before


def test_str_includes_event_type() -> None:
    output = str(EntryFollowthroughDiagnostics(total_trades=1, no_followthrough_3_count=1))

    assert "ENTRY_FOLLOWTHROUGH_DIAGNOSTICS" in output
