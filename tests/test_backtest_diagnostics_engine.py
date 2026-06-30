from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from engine.backtest.backtest_diagnostics_engine import BacktestDiagnosticsEngine
from models.market_context import MarketContext


def _context() -> MarketContext:
    return MarketContext()


def test_collect_from_context_counts_setup_blockers() -> None:
    context = _context()
    context.setup_blockers = ["A", "B"]
    context.setup_status = "INVALID"

    diagnostics = BacktestDiagnosticsEngine().collect_from_context(context)

    assert diagnostics.setup_blockers == {"A": 1, "B": 1}
    assert diagnostics.setup_status_counts == {"INVALID": 1}


def test_collect_from_context_handles_missing_fields_safely() -> None:
    context = SimpleNamespace()

    diagnostics = BacktestDiagnosticsEngine().collect_from_context(context)

    assert diagnostics.setup_blockers == {}
    assert diagnostics.setup_status_counts == {"UNKNOWN": 1}
    assert diagnostics.entry_status_counts == {"UNKNOWN": 1}


def test_summarize_contexts_aggregates_multiple_contexts() -> None:
    first = _context()
    first.setup_blockers = ["A"]
    second = _context()
    second.setup_blockers = ["A", "B"]

    diagnostics = BacktestDiagnosticsEngine().summarize_contexts([first, second])

    assert diagnostics.setup_blockers == {"A": 2, "B": 1}
    assert diagnostics.windows_analyzed == 2


def test_entry_blockers_are_counted() -> None:
    context = _context()
    context.entry_blockers = ["NO_VALID_SETUP"]

    diagnostics = BacktestDiagnosticsEngine().collect_from_context(context)

    assert diagnostics.entry_blockers == {"NO_VALID_SETUP": 1}


def test_trade_plan_blockers_are_counted() -> None:
    context = _context()
    context.trade_plan_blockers = ["NO_CONFIRMED_ENTRY"]

    diagnostics = BacktestDiagnosticsEngine().collect_from_context(context)

    assert diagnostics.trade_plan_blockers == {"NO_CONFIRMED_ENTRY": 1}


def test_trade_quality_blockers_are_counted() -> None:
    context = _context()
    context.trade_quality_blockers = ["NO_PLANNED_TRADE"]

    diagnostics = BacktestDiagnosticsEngine().collect_from_context(context)

    assert diagnostics.trade_quality_blockers == {"NO_PLANNED_TRADE": 1}


def test_paper_trade_blockers_are_counted() -> None:
    context = _context()
    context.paper_trade_blockers = ["TRADE_QUALITY_NOT_APPROVED"]

    diagnostics = BacktestDiagnosticsEngine().collect_from_context(context)

    assert diagnostics.paper_trade_blockers == {"TRADE_QUALITY_NOT_APPROVED": 1}


def test_status_counts_are_aggregated_for_all_stages() -> None:
    first = _context()
    first.setup_status = "INVALID"
    first.entry_status = "NOT_CONFIRMED"
    first.trade_plan_status = "NO_TRADE"
    first.trade_quality_status = "REJECTED"
    first.paper_trade_status = "NO_PAPER_TRADE"
    second = _context()
    second.setup_status = "VALID"
    second.entry_status = "CONFIRMED"
    second.trade_plan_status = "PLANNED"
    second.trade_quality_status = "APPROVED"
    second.paper_trade_status = "PAPER_OPEN"

    diagnostics = BacktestDiagnosticsEngine().summarize_contexts([first, second])

    assert diagnostics.setup_status_counts == {"INVALID": 1, "VALID": 1}
    assert diagnostics.entry_status_counts == {"NOT_CONFIRMED": 1, "CONFIRMED": 1}
    assert diagnostics.trade_plan_status_counts == {"NO_TRADE": 1, "PLANNED": 1}
    assert diagnostics.trade_quality_status_counts == {"REJECTED": 1, "APPROVED": 1}
    assert diagnostics.paper_trade_status_counts == {"NO_PAPER_TRADE": 1, "PAPER_OPEN": 1}


def test_diagnostics_does_not_mutate_input_contexts() -> None:
    context = _context()
    context.setup_blockers = ["A", "B", "A"]
    before = deepcopy(context.setup_blockers)

    BacktestDiagnosticsEngine().collect_from_context(context)

    assert context.setup_blockers == before


def test_str_includes_event_type_and_windows() -> None:
    context = _context()

    diagnostics = BacktestDiagnosticsEngine().summarize_contexts([context])
    output = str(diagnostics)

    assert "BACKTEST_DIAGNOSTICS" in output
    assert "WINDOWS=1" in output


def test_backtest_diagnostics_include_ote_diagnostics_after_summary() -> None:
    context = _context()

    diagnostics = BacktestDiagnosticsEngine().summarize_contexts([context])

    assert diagnostics.ote_diagnostics is not None
    assert diagnostics.ote_diagnostics.windows_analyzed == 1


def test_existing_blocker_counts_remain_unchanged_with_ote_diagnostics() -> None:
    context = _context()
    context.setup_blockers = ["A", "A", "B"]

    diagnostics = BacktestDiagnosticsEngine().summarize_contexts([context])

    assert diagnostics.setup_blockers == {"A": 2, "B": 1}
    assert diagnostics.ote_diagnostics is not None


def test_missing_ote_fields_do_not_break_backtest_diagnostics() -> None:
    context = SimpleNamespace(setup_blockers=["A"], setup_status="INVALID")

    diagnostics = BacktestDiagnosticsEngine().summarize_contexts([context])

    assert diagnostics.setup_blockers == {"A": 1}
    assert diagnostics.ote_diagnostics is not None
    assert diagnostics.ote_diagnostics.ote_missing_count == 1


def test_backtest_diagnostics_include_dealing_range_diagnostics_after_summary() -> None:
    context = _context()

    diagnostics = BacktestDiagnosticsEngine().summarize_contexts([context])

    assert diagnostics.dealing_range_diagnostics is not None
    assert diagnostics.dealing_range_diagnostics.windows_analyzed == 1


def test_existing_blocker_counts_remain_unchanged_with_dealing_range_diagnostics() -> None:
    context = _context()
    context.setup_blockers = ["A", "A", "B"]

    diagnostics = BacktestDiagnosticsEngine().summarize_contexts([context])

    assert diagnostics.setup_blockers == {"A": 2, "B": 1}
    assert diagnostics.dealing_range_diagnostics is not None


def test_existing_ote_diagnostics_remain_present_with_dealing_range_diagnostics() -> None:
    context = _context()

    diagnostics = BacktestDiagnosticsEngine().summarize_contexts([context])

    assert diagnostics.ote_diagnostics is not None
    assert diagnostics.dealing_range_diagnostics is not None


def test_missing_dealing_range_fields_do_not_break_diagnostics() -> None:
    context = SimpleNamespace(setup_blockers=["A"], setup_status="INVALID")

    diagnostics = BacktestDiagnosticsEngine().summarize_contexts([context])

    assert diagnostics.setup_blockers == {"A": 1}
    assert diagnostics.dealing_range_diagnostics is not None
    assert diagnostics.dealing_range_diagnostics.range_missing_count == 1


def test_backtest_diagnostics_include_range_candidate_diagnostics_after_summary() -> None:
    diagnostics = BacktestDiagnosticsEngine().summarize_contexts([_context()])

    assert diagnostics.range_candidate_diagnostics is not None
    assert diagnostics.range_candidate_diagnostics.windows_analyzed == 1


def test_blocker_counts_remain_unchanged_with_range_candidate_diagnostics() -> None:
    context = _context()
    context.setup_blockers = ["A", "B"]

    diagnostics = BacktestDiagnosticsEngine().summarize_contexts([context])

    assert diagnostics.setup_blockers == {"A": 1, "B": 1}
    assert diagnostics.range_candidate_diagnostics is not None


def test_ote_diagnostics_remain_present_with_range_candidate_diagnostics() -> None:
    diagnostics = BacktestDiagnosticsEngine().summarize_contexts([_context()])

    assert diagnostics.ote_diagnostics is not None
    assert diagnostics.range_candidate_diagnostics is not None


def test_dealing_range_diagnostics_remain_present_with_range_candidate_diagnostics() -> None:
    diagnostics = BacktestDiagnosticsEngine().summarize_contexts([_context()])

    assert diagnostics.dealing_range_diagnostics is not None
    assert diagnostics.range_candidate_diagnostics is not None


def test_missing_candidate_data_does_not_break_diagnostics() -> None:
    context = SimpleNamespace(setup_blockers=["A"], setup_status="INVALID")

    diagnostics = BacktestDiagnosticsEngine().summarize_contexts([context])

    assert diagnostics.range_candidate_diagnostics is not None
    assert diagnostics.range_candidate_diagnostics.candidates["CURRENT_EXTERNAL_RANGE"].missing_count == 1
