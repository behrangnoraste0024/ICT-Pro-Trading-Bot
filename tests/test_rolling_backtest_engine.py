from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from engine.rolling_backtest.rolling_backtest_engine import RollingBacktestEngine
from models.market_context import MarketContext
from models.rolling_backtest_result import RollingBacktestResult


def _candles(length: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "open": float(index),
                "high": float(index + 1),
                "low": float(index - 1),
                "close": float(index),
                "volume": 1.0,
            }
            for index in range(length)
        ]
    )


def _context(status: str, pnl: float | None = None) -> MarketContext:
    context = MarketContext()
    context.paper_trade_status = status
    context.paper_trade = SimpleNamespace(status=status) if status != "NO_PAPER_TRADE" else None
    context.paper_pnl = pnl
    return context


class RecordingICTEngine:
    def __init__(self, contexts: list[MarketContext] | None = None):
        self.call_lengths: list[int] = []
        self.contexts = list(contexts or [])

    def analyze(self, candles: pd.DataFrame) -> MarketContext:
        self.call_lengths.append(len(candles))
        if self.contexts:
            return self.contexts.pop(0)
        return _context("NO_PAPER_TRADE")


class FailingICTEngine:
    def __init__(self):
        self.call_count = 0

    def analyze(self, candles: pd.DataFrame) -> MarketContext:
        self.call_count += 1
        if self.call_count == 2:
            raise RuntimeError("window failed")
        return _context("NO_PAPER_TRADE")


def test_empty_candles() -> None:
    result = RollingBacktestEngine(ict_engine=RecordingICTEngine()).run(pd.DataFrame())

    assert result.total_windows == 0
    assert result.processed_windows == 0
    assert result.skipped_windows == 0
    assert result.total_paper_trades == 0


def test_fewer_than_min_candles() -> None:
    result = RollingBacktestEngine(ict_engine=RecordingICTEngine(), min_candles=50).run(_candles(10))

    assert result.total_windows == 10
    assert result.processed_windows == 0
    assert result.skipped_windows == 10


def test_processes_expected_number_of_windows() -> None:
    result = RollingBacktestEngine(ict_engine=RecordingICTEngine(), min_candles=50).run(_candles(60))

    assert result.processed_windows == 11
    assert result.skipped_windows == 49


def test_uses_growing_windows_only() -> None:
    fake_engine = RecordingICTEngine()

    RollingBacktestEngine(ict_engine=fake_engine, min_candles=50).run(_candles(55))

    assert fake_engine.call_lengths == [50, 51, 52, 53, 54, 55]


def test_does_not_mutate_input_candles() -> None:
    candles = _candles(55)
    original = candles.copy(deep=True)

    RollingBacktestEngine(ict_engine=RecordingICTEngine(), min_candles=50).run(candles)

    pd.testing.assert_frame_equal(candles, original)


def test_summarizes_contexts_into_rolling_result() -> None:
    contexts = [
        _context("PAPER_CLOSED_TP", 10),
        _context("PAPER_CLOSED_SL", -5),
        _context("PAPER_OPEN"),
        _context("NO_PAPER_TRADE"),
    ]
    fake_engine = RecordingICTEngine(contexts=contexts)

    result = RollingBacktestEngine(ict_engine=fake_engine, min_candles=1).run(_candles(4))

    assert result.total_paper_trades == 3
    assert result.closed_trades == 2
    assert result.open_trades == 1
    assert result.wins == 1
    assert result.losses == 1
    assert result.ignored_contexts == 1
    assert result.net_pnl == 5
    assert result.win_rate == 50


def test_run_with_contexts_returns_contexts() -> None:
    result, contexts = RollingBacktestEngine(ict_engine=RecordingICTEngine(), min_candles=50).run_with_contexts(
        _candles(55)
    )

    assert isinstance(contexts, list)
    assert len(contexts) == result.processed_windows


def test_rolling_backtest_result_string_includes_key_metrics() -> None:
    result = RollingBacktestResult(
        total_windows=100,
        processed_windows=51,
        skipped_windows=49,
        failed_windows=0,
        min_candles=50,
        total_paper_trades=5,
        closed_trades=5,
        open_trades=0,
        wins=3,
        losses=2,
        win_rate=60.0,
        net_pnl=25.0,
        average_pnl=5.0,
        max_drawdown=10.0,
        ignored_contexts=46,
    )

    output = str(result)

    assert "ROLLING_BACKTEST_RESULT" in output
    assert "WIN_RATE=60.0%" in output
    assert "NET_PNL=25.0" in output


def test_handles_ict_engine_exceptions_safely() -> None:
    result, contexts = RollingBacktestEngine(ict_engine=FailingICTEngine(), min_candles=1).run_with_contexts(_candles(3))

    assert result.total_windows == 3
    assert result.processed_windows == 2
    assert result.failed_windows == 1
    assert len(contexts) == 2


def test_no_live_network_uses_fake_engine_only() -> None:
    fake_engine = RecordingICTEngine()

    result = RollingBacktestEngine(ict_engine=fake_engine, min_candles=3).run(_candles(3))

    assert result.processed_windows == 1
    assert fake_engine.call_lengths == [3]
