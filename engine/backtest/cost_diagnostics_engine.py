from __future__ import annotations

from models.cost_diagnostics import CostDiagnostics
from models.cost_diagnostics import TradeCostBreakdown
from models.engine_config import EngineConfig
from models.market_context import MarketContext


class CostDiagnosticsEngine:
    def summarize_contexts(self, contexts: list[MarketContext], config: EngineConfig) -> CostDiagnostics:
        trades = [context for context in contexts if self._is_trade(context)]
        breakdowns = [
            self._trade_breakdown(index, context, config)
            for index, context in enumerate(trades, start=1)
        ]
        total_trades = len(breakdowns)
        closed_trades = sum(1 for trade in breakdowns if trade.is_closed)
        gross_net_pnl = sum(trade.gross_pnl for trade in breakdowns if trade.is_closed)
        total_commission_cost = sum(trade.commission_cost for trade in breakdowns)
        total_slippage_cost = sum(trade.slippage_cost for trade in breakdowns)
        total_spread_cost = sum(trade.spread_cost for trade in breakdowns)
        total_cost = sum(trade.total_cost for trade in breakdowns)
        net_pnl_after_costs = sum(trade.net_pnl_after_costs for trade in breakdowns)
        average_cost_per_trade = total_cost / total_trades if total_trades else 0.0
        average_net_pnl_after_costs = net_pnl_after_costs / closed_trades if closed_trades else 0.0
        gross_profit = sum(trade.gross_pnl for trade in breakdowns if trade.is_closed and trade.gross_pnl > 0)
        ratio = total_cost / gross_profit if gross_profit > 0 else None

        return CostDiagnostics(
            cost_model=config.cost_model,
            commission_pct=config.commission_pct,
            slippage_pct=config.slippage_pct,
            spread_pct=config.spread_pct,
            total_trades=total_trades,
            closed_trades=closed_trades,
            gross_net_pnl=gross_net_pnl,
            total_commission_cost=total_commission_cost,
            total_slippage_cost=total_slippage_cost,
            total_spread_cost=total_spread_cost,
            total_cost=total_cost,
            net_pnl_after_costs=net_pnl_after_costs,
            average_cost_per_trade=average_cost_per_trade,
            average_net_pnl_after_costs=average_net_pnl_after_costs,
            cost_to_gross_profit_ratio=ratio,
            trades=breakdowns,
        )

    def _trade_breakdown(self, trade_index: int, context: MarketContext, config: EngineConfig) -> TradeCostBreakdown:
        direction = str(getattr(context, "paper_trade_direction", "NONE") or "NONE")
        entry_price = self._optional_float(getattr(context, "paper_entry_price", None))
        exit_price = self._optional_float(getattr(context, "paper_exit_price", None))
        gross_pnl = self._gross_pnl(context)
        is_closed = self._is_closed(context)
        cost_notional = self._cost_notional(entry_price, exit_price, is_closed)

        if config.cost_model == "off" or cost_notional == 0:
            commission_cost = 0.0
            slippage_cost = 0.0
            spread_cost = 0.0
        else:
            commission_cost = cost_notional * config.commission_pct
            slippage_cost = cost_notional * config.slippage_pct
            spread_cost = cost_notional * config.spread_pct

        total_cost = commission_cost + slippage_cost + spread_cost
        return TradeCostBreakdown(
            trade_index=trade_index,
            direction=direction,
            gross_pnl=gross_pnl,
            commission_cost=commission_cost,
            slippage_cost=slippage_cost,
            spread_cost=spread_cost,
            total_cost=total_cost,
            net_pnl_after_costs=gross_pnl - total_cost,
            entry_price=entry_price,
            exit_price=exit_price,
            is_closed=is_closed,
        )

    def _is_trade(self, context: MarketContext) -> bool:
        return getattr(context, "paper_trade_status", "NO_PAPER_TRADE") != "NO_PAPER_TRADE"

    def _is_closed(self, context: MarketContext) -> bool:
        return getattr(context, "paper_trade_status", None) in ("PAPER_CLOSED_TP", "PAPER_CLOSED_SL")

    def _gross_pnl(self, context: MarketContext) -> float:
        value = getattr(context, "paper_pnl", None)
        return 0.0 if value is None else float(value)

    def _optional_float(self, value) -> float | None:
        return None if value is None else float(value)

    def _cost_notional(
        self,
        entry_price: float | None,
        exit_price: float | None,
        is_closed: bool,
    ) -> float:
        entry_notional = abs(entry_price) if entry_price is not None else 0.0
        exit_notional = abs(exit_price) if exit_price is not None else 0.0
        if is_closed:
            return entry_notional + exit_notional
        return 0.0
