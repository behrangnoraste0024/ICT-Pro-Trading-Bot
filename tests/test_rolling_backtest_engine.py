from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from engine.rolling_backtest.rolling_backtest_engine import RollingBacktestEngine
from models.entry_trigger_event import EntryTriggerEvent
from models.market_context import MarketContext
from models.ote_zone import OTEZone
from models.rolling_backtest_result import RollingBacktestResult
from models.setup_event import SetupEvent
from models.trade_quality_event import TradeQualityEvent


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


def _approved_context(direction: str = "BULLISH") -> MarketContext:
    context = MarketContext()
    context.trade_quality_status = "APPROVED"
    context.trade_plan_status = "PLANNED"
    context.trade_direction = direction
    context.trade_plan = SimpleNamespace(status="PLANNED")
    context.planned_entry_price = 100
    context.planned_stop_loss = 95 if direction == "BULLISH" else 105
    context.planned_take_profit = 112 if direction == "BULLISH" else 88
    return context


def _blocked_context(setup_blocker: str = "PRICE_NOT_IN_OTE", entry_blocker: str = "NO_VALID_SETUP") -> MarketContext:
    context = MarketContext()
    context.setup_blockers = [setup_blocker]
    context.entry_blockers = [entry_blocker]
    context.setup_status = "INVALID"
    context.entry_status = "NOT_CONFIRMED"
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

    result = RollingBacktestEngine(ict_engine=fake_engine, min_candles=1, stateful=False).run(_candles(4))

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


def test_stateful_mode_opens_one_trade_and_prevents_duplicates() -> None:
    fake_engine = RecordingICTEngine(contexts=[_approved_context("BULLISH") for _ in range(5)])
    candles = pd.DataFrame(
        [
            {"open": 100, "high": 101, "low": 99, "close": 100},
            {"open": 100, "high": 105, "low": 99, "close": 101},
            {"open": 101, "high": 106, "low": 100, "close": 102},
            {"open": 102, "high": 107, "low": 101, "close": 103},
            {"open": 103, "high": 108, "low": 102, "close": 104},
        ]
    )

    result = RollingBacktestEngine(ict_engine=fake_engine, min_candles=1).run(candles)

    assert result.opened_trades == 1
    assert result.duplicate_signals_skipped > 0
    assert fake_engine.call_lengths == [1]


def test_stateful_trade_closes_tp_on_future_candle() -> None:
    fake_engine = RecordingICTEngine(contexts=[_approved_context("BULLISH")])
    candles = pd.DataFrame(
        [
            {"open": 100, "high": 101, "low": 99, "close": 100},
            {"open": 100, "high": 113, "low": 100, "close": 112},
        ]
    )

    result = RollingBacktestEngine(ict_engine=fake_engine, min_candles=1).run(candles)

    assert result.wins == 1
    assert result.closed_by_state == 1
    assert result.net_pnl == 12


def test_stateful_closed_trade_preserves_entry_context_metadata() -> None:
    context = _approved_context("BULLISH")
    context.dealing_range_mode_applied = "recent_50"
    context.equilibrium = 100
    context.setup_score = 100
    context.setup_bias = "BEARISH"
    context.setup_status = "VALID"
    context.entry_status = "CONFIRMED"
    context.entry_trigger_type = "CONFIRMATION_CANDLE"
    context.current_price_zone = "PREMIUM"
    context.in_ote_zone = True
    context.ote_direction = "BEARISH"
    context.trade_quality_score = 90
    context.active_setup = SetupEvent(
        direction="BEARISH",
        status="VALID",
        score=100,
        price_zone="PREMIUM",
        ote_direction="BEARISH",
        in_ote_zone=True,
        matched_pois=[SimpleNamespace(poi_type="ORDER_BLOCK")],
    )
    context.entry_trigger = EntryTriggerEvent(
        direction="BEARISH",
        status="CONFIRMED",
        trigger_type="CONFIRMATION_CANDLE",
        confirmed=True,
        candle_index=0,
        current_price=100,
    )
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
    context.trade_quality = TradeQualityEvent(status="APPROVED", score=90, risk_reward=2.5)
    fake_engine = RecordingICTEngine(contexts=[context])
    candles = pd.DataFrame(
        [
            {"open": 100, "high": 101, "low": 99, "close": 100},
            {"open": 100, "high": 113, "low": 100, "close": 112},
        ]
    )

    result = RollingBacktestEngine(ict_engine=fake_engine, min_candles=1).run(candles)

    assert result.trade_outcome_diagnostics is not None
    trade = result.trade_outcome_diagnostics.trades[0]
    assert trade.result == "WIN"
    assert trade.setup_score == 100
    assert trade.entry_trigger_type == "CONFIRMATION_CANDLE"
    assert trade.current_price_zone == "PREMIUM"
    assert trade.in_ote_zone is True
    assert trade.ote_direction == "BEARISH"
    assert trade.matched_poi_count == 1
    assert trade.matched_poi_types == ["ORDER_BLOCK"]
    assert trade.trade_quality_score == 90


def test_stateful_trade_closes_sl_on_future_candle() -> None:
    fake_engine = RecordingICTEngine(contexts=[_approved_context("BULLISH")])
    candles = pd.DataFrame(
        [
            {"open": 100, "high": 101, "low": 99, "close": 100},
            {"open": 100, "high": 101, "low": 94, "close": 95},
        ]
    )

    result = RollingBacktestEngine(ict_engine=fake_engine, min_candles=1).run(candles)

    assert result.losses == 1
    assert result.closed_by_state == 1
    assert result.net_pnl == -5


def test_stateful_open_trade_at_end_counts_as_open() -> None:
    fake_engine = RecordingICTEngine(contexts=[_approved_context("BULLISH")])
    candles = pd.DataFrame(
        [
            {"open": 100, "high": 101, "low": 99, "close": 100},
            {"open": 100, "high": 105, "low": 99, "close": 101},
        ]
    )

    result = RollingBacktestEngine(ict_engine=fake_engine, min_candles=1).run(candles)

    assert result.open_trades == 1
    assert result.closed_trades == 0


def test_non_stateful_mode_preserves_old_per_window_summary() -> None:
    contexts = [
        _context("PAPER_CLOSED_TP", 10),
        _context("PAPER_CLOSED_SL", -5),
        _context("PAPER_OPEN"),
        _context("NO_PAPER_TRADE"),
    ]
    fake_engine = RecordingICTEngine(contexts=contexts)

    result = RollingBacktestEngine(ict_engine=fake_engine, min_candles=1, stateful=False).run(_candles(4))

    assert result.stateful_mode is False
    assert result.total_paper_trades == 3
    assert result.closed_trades == 2
    assert result.open_trades == 1
    assert result.net_pnl == 5


def test_stateful_anti_lookahead_uses_growing_windows_when_no_open_trade() -> None:
    fake_engine = RecordingICTEngine(contexts=[_context("NO_PAPER_TRADE") for _ in range(6)])

    RollingBacktestEngine(ict_engine=fake_engine, min_candles=50).run(_candles(55))

    assert fake_engine.call_lengths == [50, 51, 52, 53, 54, 55]


def test_progress_callback_is_called() -> None:
    progress_events: list[dict[str, int]] = []

    RollingBacktestEngine(
        ict_engine=RecordingICTEngine(),
        min_candles=50,
        progress_callback=progress_events.append,
        progress_every=5,
    ).run(_candles(60))

    assert progress_events
    assert progress_events[-1]["processed_windows"] == 11


def test_progress_every_zero_disables_callback() -> None:
    progress_events: list[dict[str, int]] = []

    RollingBacktestEngine(
        ict_engine=RecordingICTEngine(),
        min_candles=50,
        progress_callback=progress_events.append,
        progress_every=0,
    ).run(_candles(60))

    assert progress_events == []


def test_max_windows_limits_processed_windows() -> None:
    result = RollingBacktestEngine(
        ict_engine=RecordingICTEngine(),
        min_candles=50,
        max_windows=10,
    ).run(_candles(100))

    assert result.processed_windows == 10


def test_max_windows_does_not_change_total_windows() -> None:
    result = RollingBacktestEngine(
        ict_engine=RecordingICTEngine(),
        min_candles=50,
        max_windows=10,
    ).run(_candles(100))

    assert result.total_windows == 100


def test_max_windows_still_counts_warmup_skipped_windows() -> None:
    result = RollingBacktestEngine(
        ict_engine=RecordingICTEngine(),
        min_candles=50,
        max_windows=10,
    ).run(_candles(100))

    assert result.skipped_windows == 49


def test_max_windows_preserves_growing_windows_without_lookahead() -> None:
    fake_engine = RecordingICTEngine()

    RollingBacktestEngine(ict_engine=fake_engine, min_candles=50, max_windows=3).run(_candles(100))

    assert fake_engine.call_lengths == [50, 51, 52]


def test_rolling_result_includes_diagnostics() -> None:
    result = RollingBacktestEngine(
        ict_engine=RecordingICTEngine(contexts=[_blocked_context()]),
        min_candles=1,
    ).run(_candles(1))

    assert result.diagnostics is not None


def test_stateful_diagnostics_windows_equal_evaluated_contexts() -> None:
    fake_engine = RecordingICTEngine(contexts=[_approved_context("BULLISH") for _ in range(5)])
    candles = pd.DataFrame(
        [
            {"open": 100, "high": 101, "low": 99, "close": 100},
            {"open": 100, "high": 101, "low": 99, "close": 100},
            {"open": 100, "high": 101, "low": 99, "close": 100},
            {"open": 100, "high": 101, "low": 99, "close": 100},
            {"open": 100, "high": 101, "low": 99, "close": 100},
        ]
    )

    result = RollingBacktestEngine(ict_engine=fake_engine, min_candles=1).run(candles)

    assert result.diagnostics is not None
    assert result.diagnostics.windows_analyzed == 1
    assert fake_engine.call_lengths == [1]


def test_diagnostics_counts_setup_blockers_from_fake_contexts() -> None:
    contexts = [_blocked_context("A"), _blocked_context("A"), _blocked_context("B")]

    result = RollingBacktestEngine(
        ict_engine=RecordingICTEngine(contexts=contexts),
        min_candles=1,
        stateful=False,
    ).run(_candles(3))

    assert result.diagnostics is not None
    assert result.diagnostics.setup_blockers == {"A": 2, "B": 1}


def test_diagnostics_counts_entry_blockers_from_fake_contexts() -> None:
    contexts = [_blocked_context(entry_blocker="ENTRY_A"), _blocked_context(entry_blocker="ENTRY_A")]

    result = RollingBacktestEngine(
        ict_engine=RecordingICTEngine(contexts=contexts),
        min_candles=1,
        stateful=False,
    ).run(_candles(2))

    assert result.diagnostics is not None
    assert result.diagnostics.entry_blockers == {"ENTRY_A": 2}


def test_non_stateful_mode_collects_diagnostics() -> None:
    contexts = [_blocked_context("A"), _blocked_context("B")]

    result = RollingBacktestEngine(
        ict_engine=RecordingICTEngine(contexts=contexts),
        min_candles=1,
        stateful=False,
    ).run(_candles(2))

    assert result.diagnostics is not None
    assert result.diagnostics.windows_analyzed == 2


def test_default_dealing_range_mode_is_current_external() -> None:
    result = RollingBacktestEngine(ict_engine=RecordingICTEngine(), min_candles=1).run(_candles(1))

    assert result.dealing_range_mode == "current_external"


def test_dealing_range_mode_recent_50_reaches_default_ict_engine_config() -> None:
    engine = RollingBacktestEngine(min_candles=50, dealing_range_mode="recent_50")

    assert engine.ict_engine.config.dealing_range_mode == "recent_50"


def test_result_reports_recent_50_dealing_range_mode() -> None:
    result = RollingBacktestEngine(
        ict_engine=RecordingICTEngine(),
        min_candles=1,
        dealing_range_mode="recent_50",
    ).run(_candles(1))

    assert result.dealing_range_mode == "recent_50"


def test_range_mode_fallback_count_is_reported() -> None:
    context = _context("NO_PAPER_TRADE")
    context.dealing_range_mode_requested = "recent_50"
    context.dealing_range_mode_applied = "current_external"

    result = RollingBacktestEngine(
        ict_engine=RecordingICTEngine(contexts=[context]),
        min_candles=1,
        dealing_range_mode="recent_50",
    ).run(_candles(1))

    assert result.range_mode_fallback_count == 1


def test_rolling_result_includes_trade_outcome_diagnostics() -> None:
    result = RollingBacktestEngine(ict_engine=RecordingICTEngine(), min_candles=1).run(_candles(1))

    assert result.trade_outcome_diagnostics is not None


def test_trade_outcome_total_trades_matches_result_total_trades() -> None:
    contexts = [_context("PAPER_CLOSED_TP", 10), _context("PAPER_CLOSED_SL", -5)]

    result = RollingBacktestEngine(
        ict_engine=RecordingICTEngine(contexts=contexts),
        min_candles=1,
        stateful=False,
    ).run(_candles(2))

    assert result.trade_outcome_diagnostics is not None
    assert result.trade_outcome_diagnostics.total_trades == result.total_paper_trades


def test_rolling_result_includes_sl_tp_outcome_diagnostics() -> None:
    result = RollingBacktestEngine(ict_engine=RecordingICTEngine(), min_candles=1).run(_candles(1))

    assert result.sl_tp_outcome_diagnostics is not None


def test_sl_tp_total_trades_matches_trade_outcomes() -> None:
    contexts = [_context("PAPER_CLOSED_TP", 10), _context("PAPER_CLOSED_SL", -5)]
    for context in contexts:
        context.paper_trade_direction = "BULLISH"
        context.paper_entry_price = 100
        context.paper_stop_loss = 90
        context.paper_take_profit = 120
        context.paper_entry_index = 0
        context.paper_exit_index = 0
        context.candles = pd.DataFrame([{"open": 100, "high": 120, "low": 90, "close": 100}])

    result = RollingBacktestEngine(
        ict_engine=RecordingICTEngine(contexts=contexts),
        min_candles=1,
        stateful=False,
    ).run(_candles(2))

    assert result.trade_outcome_diagnostics is not None
    assert result.sl_tp_outcome_diagnostics is not None
    assert result.sl_tp_outcome_diagnostics.total_trades == result.trade_outcome_diagnostics.total_trades


def test_no_trades_returns_empty_sl_tp_diagnostics() -> None:
    result = RollingBacktestEngine(ict_engine=RecordingICTEngine(), min_candles=1).run(_candles(1))

    assert result.sl_tp_outcome_diagnostics is not None
    assert result.sl_tp_outcome_diagnostics.total_trades == 0


def test_rolling_result_includes_entry_followthrough_diagnostics() -> None:
    result = RollingBacktestEngine(ict_engine=RecordingICTEngine(), min_candles=1).run(_candles(1))

    assert result.entry_followthrough_diagnostics is not None


def test_entry_followthrough_total_trades_matches_trade_outcomes() -> None:
    context = _context("PAPER_CLOSED_TP", 10)
    context.paper_trade_direction = "BULLISH"
    context.paper_entry_price = 100
    context.paper_stop_loss = 90
    context.paper_take_profit = 120
    context.paper_entry_index = 0
    context.paper_exit_index = 1
    context.candles = pd.DataFrame(
        [
            {"open": 100, "high": 100, "low": 100, "close": 100},
            {"open": 100, "high": 120, "low": 99, "close": 120},
        ]
    )

    result = RollingBacktestEngine(
        ict_engine=RecordingICTEngine(contexts=[context]),
        min_candles=1,
        stateful=False,
    ).run(_candles(1))

    assert result.trade_outcome_diagnostics is not None
    assert result.entry_followthrough_diagnostics is not None
    assert result.entry_followthrough_diagnostics.total_trades == result.trade_outcome_diagnostics.total_trades


def test_no_trades_returns_empty_entry_followthrough_diagnostics() -> None:
    result = RollingBacktestEngine(ict_engine=RecordingICTEngine(), min_candles=1).run(_candles(1))

    assert result.entry_followthrough_diagnostics is not None
    assert result.entry_followthrough_diagnostics.total_trades == 0


def test_rolling_result_includes_virtual_exit_diagnostics() -> None:
    result = RollingBacktestEngine(ict_engine=RecordingICTEngine(), min_candles=1).run(_candles(1))

    assert result.virtual_exit_diagnostics is not None


def test_virtual_exit_total_trades_matches_trade_outcomes() -> None:
    context = _context("PAPER_CLOSED_SL", -10)
    context.paper_trade_direction = "BULLISH"
    context.paper_entry_price = 100
    context.paper_stop_loss = 90
    context.paper_take_profit = 160
    context.paper_entry_index = 0
    context.paper_exit_index = 1
    context.candles = pd.DataFrame(
        [
            {"open": 100, "high": 100, "low": 100, "close": 100},
            {"open": 100, "high": 110, "low": 99, "close": 109},
        ]
    )

    result = RollingBacktestEngine(
        ict_engine=RecordingICTEngine(contexts=[context]),
        min_candles=1,
        stateful=False,
    ).run(_candles(1))

    assert result.trade_outcome_diagnostics is not None
    assert result.virtual_exit_diagnostics is not None
    assert result.virtual_exit_diagnostics.total_trades == result.trade_outcome_diagnostics.total_trades


def test_no_trades_returns_empty_virtual_exit_diagnostics() -> None:
    result = RollingBacktestEngine(ict_engine=RecordingICTEngine(), min_candles=1).run(_candles(1))

    assert result.virtual_exit_diagnostics is not None
    assert result.virtual_exit_diagnostics.total_trades == 0


def test_stateful_open_trades_are_included_as_open_records() -> None:
    fake_engine = RecordingICTEngine(contexts=[_approved_context("BULLISH")])
    candles = pd.DataFrame(
        [
            {"open": 100, "high": 101, "low": 99, "close": 100},
            {"open": 100, "high": 105, "low": 99, "close": 101},
        ]
    )

    result = RollingBacktestEngine(ict_engine=fake_engine, min_candles=1).run(candles)

    assert result.trade_outcome_diagnostics is not None
    assert result.trade_outcome_diagnostics.open_trades == 1
    assert result.trade_outcome_diagnostics.trades[0].result == "OPEN"


def test_no_trades_produces_empty_trade_outcome_diagnostics() -> None:
    result = RollingBacktestEngine(ict_engine=RecordingICTEngine(), min_candles=1).run(_candles(1))

    assert result.trade_outcome_diagnostics is not None
    assert result.trade_outcome_diagnostics.total_trades == 0
