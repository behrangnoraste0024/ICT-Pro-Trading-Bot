from __future__ import annotations

from copy import deepcopy

import pandas as pd

from engine.backtest.dealing_range_diagnostics_engine import DealingRangeDiagnosticsEngine
from models.market_context import MarketContext


def _context(high: float | None = 110, low: float | None = 90, current_price: float | None = 100) -> MarketContext:
    context = MarketContext()
    context.dealing_range_high = high
    context.dealing_range_low = low
    context.current_price = current_price
    context.equilibrium = 100
    return context


def test_available_range_calculates_range_size() -> None:
    diagnostics = DealingRangeDiagnosticsEngine().collect_from_context(_context())

    assert diagnostics.range_available_count == 1
    assert diagnostics.average_range_size == 20
    assert diagnostics.average_range_size_percent == 0.2


def test_missing_range_increments_missing_count() -> None:
    diagnostics = DealingRangeDiagnosticsEngine().collect_from_context(_context(high=None, low=None))

    assert diagnostics.range_missing_count == 1
    assert diagnostics.range_available_count == 0


def test_invalid_range_increments_invalid_count() -> None:
    diagnostics = DealingRangeDiagnosticsEngine().collect_from_context(_context(high=90, low=100))

    assert diagnostics.invalid_range_count == 1
    assert diagnostics.range_available_count == 0


def test_equilibrium_distance_is_calculated() -> None:
    diagnostics = DealingRangeDiagnosticsEngine().collect_from_context(_context(current_price=105))

    assert diagnostics.average_distance_to_equilibrium == 5
    assert diagnostics.average_distance_to_equilibrium_percent == 5 / 105


def test_zone_counts() -> None:
    contexts = [_context(), _context(), _context(), _context()]
    contexts[0].current_price_zone = "PREMIUM"
    contexts[1].current_price_zone = "DISCOUNT"
    contexts[2].current_price_zone = "EQUILIBRIUM"
    contexts[3].current_price_zone = "SIDEWAYS"

    diagnostics = DealingRangeDiagnosticsEngine().summarize_contexts(contexts)

    assert diagnostics.premium_count == 1
    assert diagnostics.discount_count == 1
    assert diagnostics.equilibrium_count == 1
    assert diagnostics.unknown_zone_count == 1


def test_trend_counts() -> None:
    contexts = [_context(), _context(), _context(), _context()]
    contexts[0].trend = "UPTREND"
    contexts[1].trend = "DOWNTREND"
    contexts[2].trend = "RANGE"
    contexts[3].trend = "CHOP"

    diagnostics = DealingRangeDiagnosticsEngine().summarize_contexts(contexts)

    assert diagnostics.uptrend_count == 1
    assert diagnostics.downtrend_count == 1
    assert diagnostics.range_trend_count == 1
    assert diagnostics.unknown_trend_count == 1


def test_trend_zone_matrix_counts_correctly() -> None:
    context = _context()
    context.trend = "DOWNTREND"
    context.current_price_zone = "DISCOUNT"

    diagnostics = DealingRangeDiagnosticsEngine().collect_from_context(context)

    assert diagnostics.trend_zone_counts == {"DOWNTREND|DISCOUNT": 1}


def test_ote_direction_zone_matrix_counts_correctly() -> None:
    context = _context()
    context.ote_direction = "BEARISH"
    context.current_price_zone = "DISCOUNT"

    diagnostics = DealingRangeDiagnosticsEngine().collect_from_context(context)

    assert diagnostics.ote_direction_zone_counts == {"BEARISH|DISCOUNT": 1}


def test_mismatch_counts() -> None:
    bearish_discount = _context()
    bearish_discount.ote_direction = "BEARISH"
    bearish_discount.current_price_zone = "DISCOUNT"
    bullish_premium = _context()
    bullish_premium.ote_direction = "BULLISH"
    bullish_premium.current_price_zone = "PREMIUM"
    downtrend_discount = _context()
    downtrend_discount.trend = "DOWNTREND"
    downtrend_discount.current_price_zone = "DISCOUNT"
    uptrend_premium = _context()
    uptrend_premium.trend = "UPTREND"
    uptrend_premium.current_price_zone = "PREMIUM"

    diagnostics = DealingRangeDiagnosticsEngine().summarize_contexts(
        [bearish_discount, bullish_premium, downtrend_discount, uptrend_premium]
    )

    assert diagnostics.bearish_ote_discount_count == 1
    assert diagnostics.bullish_ote_premium_count == 1
    assert diagnostics.downtrend_discount_count == 1
    assert diagnostics.uptrend_premium_count == 1


def test_range_age_metrics_when_external_indexes_exist() -> None:
    context = _context()
    context.external_high_index = 10
    context.external_low_index = 20
    context.candles = pd.DataFrame([{"close": index} for index in range(31)])

    diagnostics = DealingRangeDiagnosticsEngine().collect_from_context(context)

    assert diagnostics.average_external_high_age == 20
    assert diagnostics.average_external_low_age == 10
    assert diagnostics.max_external_high_age == 20
    assert diagnostics.max_external_low_age == 10


def test_missing_external_indexes_leave_age_metrics_none() -> None:
    context = _context()
    context.candles = pd.DataFrame([{"close": index} for index in range(31)])
    context.external_high_index = None
    context.external_low_index = None

    diagnostics = DealingRangeDiagnosticsEngine().collect_from_context(context)

    assert diagnostics.average_external_high_age is None
    assert diagnostics.average_external_low_age is None


def test_summarize_contexts_aggregates_median_average_min_and_max() -> None:
    contexts = [_context(high=110, low=90), _context(high=120, low=90), _context(high=130, low=90)]

    diagnostics = DealingRangeDiagnosticsEngine().summarize_contexts(contexts)

    assert diagnostics.average_range_size == 30
    assert diagnostics.median_range_size == 30
    assert diagnostics.min_range_size == 20
    assert diagnostics.max_range_size == 40


def test_summarize_contexts_does_not_mutate_input_contexts() -> None:
    context = _context()
    before = deepcopy(context.__dict__)

    DealingRangeDiagnosticsEngine().summarize_contexts([context])

    assert context.__dict__ == before


def test_str_includes_event_type_and_key_metrics() -> None:
    diagnostics = DealingRangeDiagnosticsEngine().collect_from_context(_context())
    output = str(diagnostics)

    assert "DEALING_RANGE_DIAGNOSTICS" in output
    assert "WINDOWS=1" in output
    assert "RANGE_AVAILABLE=1" in output
