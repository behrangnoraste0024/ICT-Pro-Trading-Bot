from __future__ import annotations

from copy import deepcopy

import pandas as pd

from engine.backtest.sl_tp_outcome_diagnostics_engine import SLTPOutcomeDiagnosticsEngine
from models.market_context import MarketContext
from models.sl_tp_outcome_diagnostics import SLTPOutcomeDiagnostics


def _candles(rows: list[dict[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _trade_context(
    status: str = "PAPER_CLOSED_SL",
    direction: str = "BULLISH",
    entry: float = 100,
    stop: float = 90,
    take_profit: float = 120,
    exit_price: float | None = 90,
    entry_index: int | None = 0,
    exit_index: int | None = 2,
    candles: pd.DataFrame | None = None,
) -> MarketContext:
    context = MarketContext(candles=candles)
    context.paper_trade_status = status
    context.paper_trade_direction = direction
    context.paper_entry_price = entry
    context.paper_stop_loss = stop
    context.paper_take_profit = take_profit
    context.paper_exit_price = exit_price
    context.paper_entry_index = entry_index
    context.paper_exit_index = exit_index
    context.paper_pnl = None if exit_price is None else (exit_price - entry if direction == "BULLISH" else entry - exit_price)
    context.setup_score = 100
    context.entry_trigger_type = "CONFIRMATION_CANDLE"
    context.current_price_zone = "DISCOUNT"
    context.in_ote_zone = True
    context.matched_pois = ["ORDER_BLOCK"]
    return context


def test_no_trades_returns_empty_diagnostics() -> None:
    diagnostics = SLTPOutcomeDiagnosticsEngine().summarize_trade_contexts([MarketContext()])

    assert diagnostics.total_trades == 0
    assert diagnostics.records == []


def test_long_loss_calculates_mae_r() -> None:
    context = _trade_context(candles=_candles([{"high": 101, "low": 99}, {"high": 105, "low": 95}, {"high": 102, "low": 90}]))

    record = SLTPOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record.result == "LOSS"
    assert record.mae == 10
    assert record.mae_r == 1


def test_long_favorable_excursion_calculates_tp_progress() -> None:
    context = _trade_context(candles=_candles([{"high": 101, "low": 99}, {"high": 110, "low": 95}, {"high": 102, "low": 90}]))

    record = SLTPOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record.mfe == 10
    assert record.tp_progress == 0.5


def test_short_loss_calculates_mae_r() -> None:
    context = _trade_context(
        direction="BEARISH",
        stop=110,
        take_profit=80,
        exit_price=110,
        candles=_candles([{"high": 101, "low": 99}, {"high": 105, "low": 95}, {"high": 110, "low": 98}]),
    )

    record = SLTPOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record.direction == "SHORT"
    assert record.mae == 10
    assert record.mae_r == 1


def test_short_favorable_excursion_calculates_tp_progress() -> None:
    context = _trade_context(
        direction="BEARISH",
        stop=110,
        take_profit=80,
        exit_price=110,
        candles=_candles([{"high": 101, "low": 99}, {"high": 105, "low": 90}, {"high": 110, "low": 98}]),
    )

    record = SLTPOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record.mfe == 10
    assert record.tp_progress == 0.5


def test_fast_loss_flag() -> None:
    context = _trade_context(candles=_candles([{"high": 101, "low": 99}, {"high": 102, "low": 90}]), exit_index=1)

    record = SLTPOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record.fast_loss is True


def test_almost_tp_then_loss_flag() -> None:
    context = _trade_context(candles=_candles([{"high": 101, "low": 99}, {"high": 116, "low": 95}, {"high": 102, "low": 90}]))

    record = SLTPOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record.tp_progress == 0.8
    assert record.almost_tp_then_loss is True


def test_no_follow_through_loss_flag() -> None:
    context = _trade_context(candles=_candles([{"high": 101, "low": 99}, {"high": 104, "low": 95}, {"high": 102, "low": 90}]))

    record = SLTPOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record.tp_progress < 0.25
    assert record.no_follow_through_loss is True


def test_high_rr_loss_flag() -> None:
    context = _trade_context(take_profit=160, candles=_candles([{"high": 101, "low": 99}, {"high": 104, "low": 90}]), exit_index=1)

    record = SLTPOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record.risk_reward == 6
    assert record.high_rr_loss is True


def test_open_trade_uses_candles_to_last_row() -> None:
    context = _trade_context(
        status="PAPER_OPEN",
        exit_price=None,
        exit_index=None,
        candles=_candles([{"high": 101, "low": 99}, {"high": 108, "low": 96}, {"high": 106, "low": 97}]),
    )

    diagnostics = SLTPOutcomeDiagnosticsEngine().summarize_trade_contexts([context])

    assert diagnostics.open_trades == 1
    assert diagnostics.records[0].bars_held == 3
    assert diagnostics.records[0].mfe == 8


def test_missing_indices_do_not_crash() -> None:
    context = _trade_context(entry_index=None, exit_index=None, candles=_candles([{"high": 101, "low": 99}]))

    record = SLTPOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record is not None
    assert record.mae is None


def test_missing_candles_do_not_crash() -> None:
    context = _trade_context(candles=None)

    record = SLTPOutcomeDiagnosticsEngine().collect_from_context(context, 1)

    assert record is not None
    assert record.mfe is None


def test_aggregates_average_metrics() -> None:
    contexts = [
        _trade_context(candles=_candles([{"high": 110, "low": 99}, {"high": 102, "low": 90}]), exit_index=1),
        _trade_context(candles=_candles([{"high": 105, "low": 99}, {"high": 102, "low": 90}]), exit_index=1),
    ]

    diagnostics = SLTPOutcomeDiagnosticsEngine().summarize_trade_contexts(contexts)

    assert diagnostics.average_mae_r == 1
    assert diagnostics.average_mfe_r == 0.75
    assert diagnostics.average_tp_progress == 0.375


def test_direction_outcome_counts() -> None:
    long_win = _trade_context(status="PAPER_CLOSED_TP", exit_price=120, candles=_candles([{"high": 120, "low": 99}]), exit_index=0)
    short_loss = _trade_context(
        direction="BEARISH",
        stop=110,
        take_profit=80,
        exit_price=110,
        candles=_candles([{"high": 110, "low": 99}]),
        exit_index=0,
    )

    diagnostics = SLTPOutcomeDiagnosticsEngine().summarize_trade_contexts([long_win, short_loss])

    assert diagnostics.long_win_count == 1
    assert diagnostics.short_loss_count == 1


def test_summarize_trade_contexts_does_not_mutate_contexts() -> None:
    context = _trade_context(candles=_candles([{"high": 101, "low": 99}, {"high": 102, "low": 90}]), exit_index=1)
    before = deepcopy(context.__dict__)

    SLTPOutcomeDiagnosticsEngine().summarize_trade_contexts([context])

    pd.testing.assert_frame_equal(context.candles, before.pop("candles"))
    current = dict(context.__dict__)
    current.pop("candles")
    assert current == before


def test_str_includes_event_type() -> None:
    output = str(SLTPOutcomeDiagnostics(total_trades=1, fast_loss_count=1, high_rr_loss_count=1))

    assert "SL_TP_OUTCOME_DIAGNOSTICS" in output
