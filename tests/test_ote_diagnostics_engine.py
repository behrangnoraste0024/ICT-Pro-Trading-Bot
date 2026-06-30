from __future__ import annotations

from copy import deepcopy

from engine.backtest.ote_diagnostics_engine import OTEDiagnosticsEngine
from models.market_context import MarketContext


def _context(
    current_price: float | None = 100,
    lower: float | None = 95,
    upper: float | None = 105,
    in_ote: bool = True,
) -> MarketContext:
    context = MarketContext()
    context.current_price = current_price
    context.ote_lower_bound = lower
    context.ote_upper_bound = upper
    context.in_ote_zone = in_ote
    return context


def test_in_ote_gives_zero_distance_and_counts_near_thresholds() -> None:
    diagnostics = OTEDiagnosticsEngine().collect_from_context(_context())

    assert diagnostics.average_distance_to_ote == 0
    assert diagnostics.median_distance_to_ote == 0
    assert diagnostics.max_distance_to_ote == 0
    assert diagnostics.in_ote_count == 1
    assert diagnostics.near_ote_0_1_pct_count == 1
    assert diagnostics.near_ote_0_25_pct_count == 1
    assert diagnostics.near_ote_0_5_pct_count == 1
    assert diagnostics.near_ote_1_0_pct_count == 1


def test_price_below_ote_calculates_distance() -> None:
    diagnostics = OTEDiagnosticsEngine().collect_from_context(_context(current_price=90, in_ote=False))

    assert diagnostics.average_distance_to_ote == 5
    assert diagnostics.not_in_ote_count == 1


def test_price_above_ote_calculates_distance() -> None:
    diagnostics = OTEDiagnosticsEngine().collect_from_context(_context(current_price=110, in_ote=False))

    assert diagnostics.average_distance_to_ote == 5
    assert diagnostics.not_in_ote_count == 1


def test_missing_ote_values_increment_missing_count_safely() -> None:
    diagnostics = OTEDiagnosticsEngine().collect_from_context(_context(current_price=None, lower=None, upper=None))

    assert diagnostics.ote_missing_count == 1
    assert diagnostics.ote_available_count == 0
    assert diagnostics.average_distance_to_ote is None


def test_zone_counts() -> None:
    contexts = [_context(), _context(), _context(), _context()]
    contexts[0].current_price_zone = "PREMIUM"
    contexts[1].current_price_zone = "DISCOUNT"
    contexts[2].current_price_zone = "EQUILIBRIUM"
    contexts[3].current_price_zone = "SIDEWAYS"

    diagnostics = OTEDiagnosticsEngine().summarize_contexts(contexts)

    assert diagnostics.premium_count == 1
    assert diagnostics.discount_count == 1
    assert diagnostics.equilibrium_count == 1
    assert diagnostics.unknown_zone_count == 1


def test_ote_direction_counts() -> None:
    contexts = [_context(), _context(), _context()]
    contexts[0].ote_direction = "BULLISH"
    contexts[1].ote_direction = "BEARISH"
    contexts[2].ote_direction = "UNKNOWN"

    diagnostics = OTEDiagnosticsEngine().summarize_contexts(contexts)

    assert diagnostics.bullish_ote_count == 1
    assert diagnostics.bearish_ote_count == 1
    assert diagnostics.none_ote_count == 1


def test_equilibrium_distance_counts() -> None:
    context = _context(current_price=100)
    context.equilibrium = 100.05

    diagnostics = OTEDiagnosticsEngine().collect_from_context(context)

    assert diagnostics.near_equilibrium_0_1_pct_count == 1
    assert diagnostics.near_equilibrium_0_25_pct_count == 1
    assert diagnostics.near_equilibrium_0_5_pct_count == 1


def test_summarize_contexts_aggregates_average_median_and_max() -> None:
    contexts = [
        _context(current_price=100, lower=95, upper=105, in_ote=True),
        _context(current_price=90, lower=95, upper=105, in_ote=False),
        _context(current_price=85, lower=95, upper=105, in_ote=False),
    ]

    diagnostics = OTEDiagnosticsEngine().summarize_contexts(contexts)

    assert diagnostics.average_distance_to_ote == 5
    assert diagnostics.median_distance_to_ote == 5
    assert diagnostics.max_distance_to_ote == 10


def test_summarize_contexts_does_not_mutate_input_contexts() -> None:
    context = _context(current_price=90, in_ote=False)
    before = deepcopy(context.__dict__)

    OTEDiagnosticsEngine().summarize_contexts([context])

    assert context.__dict__ == before


def test_str_includes_event_type_and_key_metrics() -> None:
    diagnostics = OTEDiagnosticsEngine().collect_from_context(_context())
    output = str(diagnostics)

    assert "OTE_DIAGNOSTICS" in output
    assert "WINDOWS=1" in output
    assert "IN_OTE=1" in output
