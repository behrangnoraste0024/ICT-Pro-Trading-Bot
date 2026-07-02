from __future__ import annotations

import pytest

from engine.backtest.cost_diagnostics_engine import CostDiagnosticsEngine
from models.engine_config import EngineConfig
from models.market_context import MarketContext


def _trade(
    direction: str = "BULLISH",
    status: str = "PAPER_CLOSED_TP",
    entry_price: float | None = 100.0,
    exit_price: float | None = 110.0,
    pnl: float | None = 10.0,
) -> MarketContext:
    context = MarketContext()
    context.paper_trade_status = status
    context.paper_trade_direction = direction
    context.paper_entry_price = entry_price
    context.paper_exit_price = exit_price
    context.paper_pnl = pnl
    return context


def test_cost_model_off_returns_zero_costs_and_net_equals_gross() -> None:
    diagnostics = CostDiagnosticsEngine().summarize_contexts(
        [_trade()],
        EngineConfig(cost_model="off", commission_pct=0.01, slippage_pct=0.01, spread_pct=0.01),
    )

    assert diagnostics.gross_net_pnl == 10
    assert diagnostics.total_cost == 0
    assert diagnostics.net_pnl_after_costs == 10


def test_percent_commission_cost_closed_long() -> None:
    diagnostics = CostDiagnosticsEngine().summarize_contexts(
        [_trade("BULLISH", entry_price=100, exit_price=110, pnl=10)],
        EngineConfig(cost_model="percent", commission_pct=0.001),
    )

    assert diagnostics.total_commission_cost == pytest.approx(0.21)
    assert diagnostics.trades[0].net_pnl_after_costs == pytest.approx(9.79)


def test_percent_commission_cost_closed_short() -> None:
    diagnostics = CostDiagnosticsEngine().summarize_contexts(
        [_trade("BEARISH", entry_price=110, exit_price=100, pnl=10)],
        EngineConfig(cost_model="percent", commission_pct=0.001),
    )

    assert diagnostics.total_commission_cost == pytest.approx(0.21)
    assert diagnostics.trades[0].net_pnl_after_costs == pytest.approx(9.79)


def test_slippage_cost_is_computed() -> None:
    diagnostics = CostDiagnosticsEngine().summarize_contexts(
        [_trade(entry_price=100, exit_price=110)],
        EngineConfig(cost_model="percent", slippage_pct=0.002),
    )

    assert diagnostics.total_slippage_cost == pytest.approx(0.42)


def test_spread_cost_is_computed() -> None:
    diagnostics = CostDiagnosticsEngine().summarize_contexts(
        [_trade(entry_price=100, exit_price=110)],
        EngineConfig(cost_model="percent", spread_pct=0.003),
    )

    assert diagnostics.total_spread_cost == pytest.approx(0.63)


def test_total_cost_combines_components() -> None:
    diagnostics = CostDiagnosticsEngine().summarize_contexts(
        [_trade(entry_price=100, exit_price=110)],
        EngineConfig(cost_model="percent", commission_pct=0.001, slippage_pct=0.002, spread_pct=0.003),
    )

    assert diagnostics.total_cost == pytest.approx(1.26)


def test_net_pnl_after_costs_is_gross_minus_total_cost() -> None:
    diagnostics = CostDiagnosticsEngine().summarize_contexts(
        [_trade(pnl=10, entry_price=100, exit_price=110)],
        EngineConfig(cost_model="percent", commission_pct=0.001),
    )

    assert diagnostics.net_pnl_after_costs == pytest.approx(9.79)


def test_handles_no_trades() -> None:
    diagnostics = CostDiagnosticsEngine().summarize_contexts([], EngineConfig(cost_model="percent", commission_pct=0.1))

    assert diagnostics.total_trades == 0
    assert diagnostics.total_cost == 0
    assert diagnostics.net_pnl_after_costs == 0


def test_handles_missing_exit() -> None:
    diagnostics = CostDiagnosticsEngine().summarize_contexts(
        [_trade(status="PAPER_OPEN", entry_price=100, exit_price=None, pnl=None)],
        EngineConfig(cost_model="percent", commission_pct=0.001),
    )

    assert diagnostics.total_trades == 1
    assert diagnostics.total_cost == 0
    assert diagnostics.trades[0].net_pnl_after_costs == 0


def test_open_trades_have_no_cost_without_exit() -> None:
    diagnostics = CostDiagnosticsEngine().summarize_contexts(
        [_trade(status="PAPER_OPEN", entry_price=100, exit_price=None, pnl=None)],
        EngineConfig(cost_model="percent", commission_pct=0.001),
    )

    assert diagnostics.total_cost == 0


def test_does_not_mutate_trade_pnl() -> None:
    context = _trade(pnl=10)

    CostDiagnosticsEngine().summarize_contexts([context], EngineConfig(cost_model="percent", commission_pct=0.001))

    assert context.paper_pnl == 10
