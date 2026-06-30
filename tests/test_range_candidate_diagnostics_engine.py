from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pandas as pd

from engine.backtest.range_candidate_diagnostics_engine import RangeCandidateDiagnosticsEngine
from models.market_context import MarketContext


def _candles(length: int, high_start: float = 100, low_start: float = 80) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"open": 90 + index, "high": high_start + index, "low": low_start + index, "close": 90 + index}
            for index in range(length)
        ]
    )


def _context() -> MarketContext:
    context = MarketContext()
    context.current_price = 100
    context.dealing_range_high = 110
    context.dealing_range_low = 90
    context.ote_direction = "BEARISH"
    context.candles = _candles(120)
    return context


def _stats(context: MarketContext, name: str):
    return RangeCandidateDiagnosticsEngine().collect_from_context(context).candidates[name]


def test_current_external_range_candidate_is_calculated() -> None:
    stats = _stats(_context(), "CURRENT_EXTERNAL_RANGE")

    assert stats.available_count == 1
    assert stats.average_range_size == 20


def test_recent_50_candle_range_is_calculated_from_last_50_candles() -> None:
    context = _context()
    context.current_price = 180

    stats = _stats(context, "RECENT_50_CANDLE_RANGE")

    assert stats.available_count == 1
    assert stats.average_range_size == 69


def test_recent_100_candle_range_missing_if_fewer_than_100_candles() -> None:
    context = _context()
    context.candles = _candles(99)

    stats = _stats(context, "RECENT_100_CANDLE_RANGE")

    assert stats.missing_count == 1


def test_recent_200_candle_range_missing_if_fewer_than_200_candles() -> None:
    stats = _stats(_context(), "RECENT_200_CANDLE_RANGE")

    assert stats.missing_count == 1


def test_candidate_zone_premium_discount_and_equilibrium() -> None:
    premium = _context()
    premium.current_price = 101
    discount = _context()
    discount.current_price = 99
    equilibrium = _context()
    equilibrium.current_price = 100

    diagnostics = RangeCandidateDiagnosticsEngine().summarize_contexts([premium, discount, equilibrium])
    stats = diagnostics.candidates["CURRENT_EXTERNAL_RANGE"]

    assert stats.premium_count == 1
    assert stats.discount_count == 1
    assert stats.equilibrium_count == 1


def test_candidate_ote_for_bullish_uses_retracement_formula() -> None:
    context = _context()
    context.ote_direction = "BULLISH"
    context.current_price = 95

    stats = _stats(context, "CURRENT_EXTERNAL_RANGE")

    assert stats.in_ote_count == 1


def test_candidate_ote_for_bearish_uses_retracement_formula() -> None:
    context = _context()
    context.ote_direction = "BEARISH"
    context.current_price = 104

    stats = _stats(context, "CURRENT_EXTERNAL_RANGE")

    assert stats.in_ote_count == 1


def test_candidate_in_ote_count_increments() -> None:
    context = _context()
    context.current_price = 104

    assert _stats(context, "CURRENT_EXTERNAL_RANGE").in_ote_count == 1


def test_near_ote_thresholds_increment() -> None:
    context = _context()
    context.current_price = 106

    stats = _stats(context, "CURRENT_EXTERNAL_RANGE")

    assert stats.near_ote_1_0_pct_count == 1


def test_alignment_counts() -> None:
    bearish_premium = _context()
    bearish_premium.ote_direction = "BEARISH"
    bearish_premium.current_price = 105
    bearish_discount = _context()
    bearish_discount.ote_direction = "BEARISH"
    bearish_discount.current_price = 95
    bullish_discount = _context()
    bullish_discount.ote_direction = "BULLISH"
    bullish_discount.current_price = 95
    bullish_premium = _context()
    bullish_premium.ote_direction = "BULLISH"
    bullish_premium.current_price = 105

    stats = RangeCandidateDiagnosticsEngine().summarize_contexts(
        [bearish_premium, bearish_discount, bullish_discount, bullish_premium]
    ).candidates["CURRENT_EXTERNAL_RANGE"]

    assert stats.bearish_ote_premium_count == 1
    assert stats.bearish_ote_discount_count == 1
    assert stats.bullish_ote_discount_count == 1
    assert stats.bullish_ote_premium_count == 1
    assert stats.candidate_aligned_zone_count == 2
    assert stats.candidate_wrong_zone_count == 2


def test_improvement_vs_current_counts() -> None:
    context = _context()
    context.ote_direction = "BEARISH"
    context.current_price = 95
    context.dealing_range_high = 110
    context.dealing_range_low = 90
    context.candles = pd.DataFrame([{"high": 100, "low": 80, "close": 95} for _ in range(50)])

    stats = _stats(context, "RECENT_50_CANDLE_RANGE")

    assert stats.candidate_fix_wrong_zone_count == 1
    assert stats.candidate_fix_not_in_ote_count == 1
    assert stats.candidate_fix_near_ote_0_5_count == 1


def test_summarize_contexts_aggregates_stats_and_metrics() -> None:
    first = _context()
    first.current_price = 104
    second = _context()
    second.current_price = 105

    stats = RangeCandidateDiagnosticsEngine().summarize_contexts([first, second]).candidates["CURRENT_EXTERNAL_RANGE"]

    assert stats.available_count == 2
    assert stats.average_range_size == 20
    assert stats.median_range_size == 20


def test_best_candidate_by_aligned_zone_returns_expected_candidate() -> None:
    diagnostics = RangeCandidateDiagnosticsEngine().collect_from_context(_context())
    diagnostics.candidates["RECENT_50_CANDLE_RANGE"].candidate_aligned_zone_count = 5

    assert diagnostics.best_candidate_by_aligned_zone().candidate_name == "RECENT_50_CANDLE_RANGE"


def test_best_candidate_by_in_ote_returns_expected_candidate() -> None:
    diagnostics = RangeCandidateDiagnosticsEngine().collect_from_context(_context())
    diagnostics.candidates["RECENT_100_CANDLE_RANGE"].in_ote_count = 5

    assert diagnostics.best_candidate_by_in_ote().candidate_name == "RECENT_100_CANDLE_RANGE"


def test_best_candidate_by_wrong_zone_fix_returns_expected_candidate() -> None:
    diagnostics = RangeCandidateDiagnosticsEngine().collect_from_context(_context())
    diagnostics.candidates["RECENT_200_CANDLE_RANGE"].candidate_fix_wrong_zone_count = 5

    assert diagnostics.best_candidate_by_wrong_zone_fix().candidate_name == "RECENT_200_CANDLE_RANGE"


def test_summarize_contexts_does_not_mutate_input_contexts() -> None:
    context = _context()
    before = deepcopy(context.__dict__)

    RangeCandidateDiagnosticsEngine().summarize_contexts([context])

    assert context.__dict__.keys() == before.keys()


def test_str_includes_event_type_and_candidates() -> None:
    output = str(RangeCandidateDiagnosticsEngine().collect_from_context(_context()))

    assert "RANGE_CANDIDATE_DIAGNOSTICS" in output
    assert "CANDIDATES=5" in output


def test_recent_swing_range_works_with_existing_swing_shape() -> None:
    context = _context()
    context.candles = _candles(120)
    context.current_price = 100
    context.swings = [
        SimpleNamespace(index=30, price=200, swing_type="HIGH"),
        SimpleNamespace(index=40, price=50, swing_type="LOW"),
    ]

    stats = _stats(context, "RECENT_SWING_RANGE")

    assert stats.available_count == 1
    assert stats.average_range_size == 150


def test_recent_swing_range_missing_safely_if_no_swings() -> None:
    context = _context()
    context.swings = []

    stats = _stats(context, "RECENT_SWING_RANGE")

    assert stats.missing_count == 1
