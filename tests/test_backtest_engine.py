from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.backtest.backtest_engine import BacktestEngine
from models.backtest_result import BacktestResult
from models.market_context import MarketContext


def _context(status: str, pnl: float | None = None) -> MarketContext:
    context = MarketContext()
    context.paper_trade_status = status
    context.paper_trade = SimpleNamespace(status=status) if status != "NO_PAPER_TRADE" else None
    context.paper_pnl = pnl
    return context


def test_no_paper_trade_ignored() -> None:
    context = BacktestEngine().detect(_context("NO_PAPER_TRADE"))

    assert context.backtest_total_trades == 0
    assert context.backtest_ignored_contexts == 1
    assert context.backtest_win_rate == 0


def test_closed_tp_counts_as_win() -> None:
    context = BacktestEngine().detect(_context("PAPER_CLOSED_TP", 12))

    assert context.backtest_total_trades == 1
    assert context.backtest_closed_trades == 1
    assert context.backtest_wins == 1
    assert context.backtest_losses == 0
    assert context.backtest_net_pnl == 12
    assert context.backtest_win_rate == 100


def test_closed_sl_counts_as_loss() -> None:
    context = BacktestEngine().detect(_context("PAPER_CLOSED_SL", -5))

    assert context.backtest_total_trades == 1
    assert context.backtest_closed_trades == 1
    assert context.backtest_wins == 0
    assert context.backtest_losses == 1
    assert context.backtest_net_pnl == -5
    assert context.backtest_win_rate == 0


def test_open_paper_trade_counts_as_open() -> None:
    context = BacktestEngine().detect(_context("PAPER_OPEN"))

    assert context.backtest_total_trades == 1
    assert context.backtest_open_trades == 1
    assert context.backtest_closed_trades == 0
    assert context.backtest_win_rate == 0


def test_multiple_contexts_summary() -> None:
    contexts = [
        _context("PAPER_CLOSED_TP", 10),
        _context("PAPER_CLOSED_SL", -5),
        _context("PAPER_CLOSED_TP", 15),
        _context("PAPER_OPEN"),
        _context("NO_PAPER_TRADE"),
    ]

    result = BacktestEngine().summarize_contexts(contexts)

    assert result.total_paper_trades == 4
    assert result.closed_trades == 3
    assert result.open_trades == 1
    assert result.wins == 2
    assert result.losses == 1
    assert result.ignored_contexts == 1
    assert result.win_rate == pytest.approx(66.6667, rel=0.0001)
    assert result.net_pnl == 20
    assert result.average_pnl == pytest.approx(6.6667, rel=0.0001)


def test_max_drawdown_calculation() -> None:
    contexts = [
        _context("PAPER_CLOSED_TP", 10),
        _context("PAPER_CLOSED_SL", -4),
        _context("PAPER_CLOSED_SL", -8),
        _context("PAPER_CLOSED_TP", 6),
    ]

    result = BacktestEngine().summarize_contexts(contexts)

    assert result.max_drawdown == 12


def test_pnl_none_is_treated_safely() -> None:
    result = BacktestEngine().summarize_contexts([_context("PAPER_CLOSED_TP", None)])

    assert result.closed_trades == 1
    assert result.net_pnl == 0
    assert result.average_pnl == 0


def test_summarize_contexts_does_not_mutate_inputs() -> None:
    context = _context("PAPER_CLOSED_TP", 12)
    original_status = context.paper_trade_status
    original_pnl = context.paper_pnl

    BacktestEngine().summarize_contexts([context])

    assert context.paper_trade_status == original_status
    assert context.paper_pnl == original_pnl
    assert context.backtest_result is None


def test_detect_stores_flat_values_on_context() -> None:
    context = BacktestEngine().detect(_context("PAPER_CLOSED_TP", 12))

    assert context.backtest_result is not None
    assert context.backtest_total_trades == 1
    assert context.backtest_closed_trades == 1
    assert context.backtest_open_trades == 0
    assert context.backtest_wins == 1
    assert context.backtest_losses == 0


def test_backtest_result_string_includes_key_metrics() -> None:
    result = BacktestResult(
        total_paper_trades=10,
        closed_trades=8,
        open_trades=2,
        wins=5,
        losses=3,
        win_rate=62.5,
        net_pnl=120.0,
        average_pnl=15.0,
        max_drawdown=10.0,
        ignored_contexts=1,
    )

    output = str(result)

    assert "WIN_RATE=62.5%" in output
    assert "NET_PNL=120.0" in output


def test_existing_context_objects_are_preserved() -> None:
    context = _context("PAPER_CLOSED_TP", 12)
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
    context.trade_plan = "trade_plan"
    context.trade_quality = "trade_quality"
    paper_trade = context.paper_trade

    context = BacktestEngine().detect(context)

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
    assert context.trade_plan == "trade_plan"
    assert context.trade_quality == "trade_quality"
    assert context.paper_trade is paper_trade


def test_debug_values_are_populated() -> None:
    context = BacktestEngine().detect(_context("PAPER_CLOSED_TP", 12))

    assert context.debug["backtest_total_trades"] == 1
    assert context.debug["backtest_closed_trades"] == 1
    assert context.debug["backtest_open_trades"] == 0
    assert context.debug["backtest_wins"] == 1
    assert context.debug["backtest_losses"] == 0
    assert context.debug["backtest_win_rate"] == 100
    assert context.debug["backtest_net_pnl"] == 12
    assert context.debug["backtest_average_pnl"] == 12
    assert context.debug["backtest_max_drawdown"] == 0
    assert context.debug["backtest_ignored_contexts"] == 0
