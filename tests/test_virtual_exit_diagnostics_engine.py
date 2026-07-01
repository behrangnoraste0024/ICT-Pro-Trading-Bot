from __future__ import annotations

from copy import deepcopy

import pandas as pd

from engine.backtest.virtual_exit_diagnostics_engine import VirtualExitDiagnosticsEngine
from models.market_context import MarketContext
from models.virtual_exit_diagnostics import VirtualExitDiagnostics


def _candles(rows: list[dict[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _context(
    direction: str = "BULLISH",
    status: str = "PAPER_CLOSED_SL",
    exit_price: float = 90,
    candles: pd.DataFrame | None = None,
) -> MarketContext:
    context = MarketContext(candles=candles)
    context.paper_trade_status = status
    context.paper_trade_direction = direction
    context.paper_entry_price = 100
    context.paper_stop_loss = 90 if direction == "BULLISH" else 110
    context.paper_take_profit = 160 if direction == "BULLISH" else 40
    context.paper_exit_price = exit_price
    context.paper_entry_index = 0
    context.paper_exit_index = None if status == "PAPER_OPEN" else max((len(candles) if candles is not None else 1) - 1, 0)
    context.paper_pnl = exit_price - 100 if direction == "BULLISH" else 100 - exit_price
    context.setup_score = 100
    context.entry_trigger_type = "CONFIRMATION_CANDLE"
    context.current_price_zone = "DISCOUNT"
    context.in_ote_zone = True
    context.matched_pois = ["FVG"]
    return context


def _record(context: MarketContext):
    return VirtualExitDiagnosticsEngine().collect_from_context(context, 1)


def test_no_trades_returns_empty_diagnostics() -> None:
    diagnostics = VirtualExitDiagnosticsEngine().summarize_trade_contexts([MarketContext()])

    assert diagnostics.total_trades == 0
    assert diagnostics.records == []


def test_long_tp_1r_win() -> None:
    record = _record(_context(candles=_candles([{"high": 110, "low": 99, "close": 109}])))

    assert record.policy_results["TP_1R"].result == "WIN"
    assert record.policy_results["TP_1R"].virtual_pnl_r == 1.0


def test_long_tp_2r_open_if_not_hit() -> None:
    record = _record(_context(status="PAPER_OPEN", exit_price=105, candles=_candles([{"high": 115, "low": 99, "close": 105}])))

    assert record.policy_results["TP_2R"].result == "OPEN"


def test_long_fixed_tp_same_candle_sl_first() -> None:
    record = _record(_context(candles=_candles([{"high": 110, "low": 90, "close": 100}])))

    assert record.policy_results["TP_1R"].result == "LOSS"


def test_short_tp_1r_win() -> None:
    record = _record(_context(direction="BEARISH", exit_price=90, candles=_candles([{"high": 101, "low": 90, "close": 91}])))

    assert record.policy_results["TP_1R"].result == "WIN"


def test_short_fixed_tp_same_candle_sl_first() -> None:
    record = _record(_context(direction="BEARISH", exit_price=110, candles=_candles([{"high": 110, "low": 90, "close": 100}])))

    assert record.policy_results["TP_1R"].result == "LOSS"


def test_be_after_half_r_long_breakeven() -> None:
    record = _record(_context(candles=_candles([{"high": 106, "low": 99, "close": 105}, {"high": 104, "low": 100, "close": 101}])))

    assert record.policy_results["BE_AFTER_0_5R"].result == "BREAKEVEN"


def test_be_after_1r_short_breakeven() -> None:
    record = _record(_context(direction="BEARISH", exit_price=100, candles=_candles([{"high": 101, "low": 89, "close": 90}, {"high": 100, "low": 95, "close": 99}])))

    assert record.policy_results["BE_AFTER_1R"].result == "BREAKEVEN"


def test_be_original_sl_before_activation_returns_loss() -> None:
    record = _record(_context(candles=_candles([{"high": 104, "low": 90, "close": 91}])))

    assert record.policy_results["BE_AFTER_0_5R"].result == "LOSS"


def test_be_original_tp_before_sl_returns_win() -> None:
    record = _record(_context(status="PAPER_CLOSED_TP", exit_price=160, candles=_candles([{"high": 160, "low": 99, "close": 150}])))

    assert record.policy_results["BE_AFTER_1R"].result == "WIN"


def test_invalid_risk_returns_unknown() -> None:
    context = _context(candles=_candles([{"high": 110, "low": 99, "close": 105}]))
    context.paper_stop_loss = 100

    record = _record(context)

    assert record.policy_results["TP_1R"].result == "UNKNOWN"


def test_missing_candles_does_not_crash() -> None:
    record = _record(_context(candles=None))

    assert record.policy_results["TP_1R"].result == "UNKNOWN"


def test_missing_indices_does_not_crash() -> None:
    context = _context(candles=_candles([{"high": 110, "low": 99, "close": 105}]))
    context.paper_entry_index = None

    record = _record(context)

    assert record.policy_results["TP_1R"].result == "UNKNOWN"


def test_open_virtual_result_calculates_unrealized_r() -> None:
    record = _record(_context(status="PAPER_OPEN", exit_price=105, candles=_candles([{"high": 105, "low": 99, "close": 105}])))

    assert record.policy_results["TP_2R"].result == "OPEN"
    assert record.policy_results["TP_2R"].virtual_pnl_r == 0.5


def test_policy_summary_counts_results() -> None:
    contexts = [
        _context(candles=_candles([{"high": 110, "low": 99, "close": 109}])),
        _context(candles=_candles([{"high": 105, "low": 90, "close": 91}])),
    ]

    summary = VirtualExitDiagnosticsEngine().summarize_trade_contexts(contexts).policy_summaries["TP_1R"]

    assert summary.wins == 1
    assert summary.losses == 1


def test_policy_summary_win_rate_excludes_unknowns() -> None:
    valid = _context(candles=_candles([{"high": 110, "low": 99, "close": 109}]))
    invalid = _context(candles=None)

    summary = VirtualExitDiagnosticsEngine().summarize_trade_contexts([valid, invalid]).policy_summaries["TP_1R"]

    assert summary.win_rate == 100


def test_best_policy_by_total_pnl_selected() -> None:
    diagnostics = VirtualExitDiagnosticsEngine().summarize_trade_contexts([
        _context(candles=_candles([{"high": 130, "low": 99, "close": 130}]))
    ])

    assert diagnostics.best_policy_by_total_pnl_r == "TP_3R"


def test_improvement_counts_tp_1r() -> None:
    diagnostics = VirtualExitDiagnosticsEngine().summarize_trade_contexts([
        _context(candles=_candles([{"high": 110, "low": 99, "close": 109}]))
    ])

    assert diagnostics.tp_1r_would_have_won_count == 1


def test_be_help_count() -> None:
    diagnostics = VirtualExitDiagnosticsEngine().summarize_trade_contexts([
        _context(candles=_candles([{"high": 106, "low": 99, "close": 105}, {"high": 104, "low": 100, "close": 101}]))
    ])

    assert diagnostics.be_0_5r_would_help_count == 1


def test_high_rr_loss_analysis() -> None:
    diagnostics = VirtualExitDiagnosticsEngine().summarize_trade_contexts([
        _context(candles=_candles([{"high": 110, "low": 99, "close": 109}]))
    ])

    assert diagnostics.high_rr_loss_count == 1
    assert diagnostics.high_rr_loss_tp_1r_wins == 1


def test_does_not_mutate_contexts() -> None:
    context = _context(candles=_candles([{"high": 110, "low": 99, "close": 109}]))
    before = deepcopy(context.__dict__)

    VirtualExitDiagnosticsEngine().summarize_trade_contexts([context])

    pd.testing.assert_frame_equal(context.candles, before.pop("candles"))
    current = dict(context.__dict__)
    current.pop("candles")
    assert current == before


def test_str_includes_event_type() -> None:
    assert "VIRTUAL_EXIT_DIAGNOSTICS" in str(VirtualExitDiagnostics(total_trades=1))
