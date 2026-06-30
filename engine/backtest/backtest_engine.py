from __future__ import annotations

from models.backtest_result import BacktestResult
from models.market_context import MarketContext


class BacktestEngine:
    def detect(self, context: MarketContext) -> MarketContext:
        result = self.summarize_contexts([context])
        context.backtest_result = result
        context.backtest_total_trades = result.total_paper_trades
        context.backtest_closed_trades = result.closed_trades
        context.backtest_open_trades = result.open_trades
        context.backtest_wins = result.wins
        context.backtest_losses = result.losses
        context.backtest_win_rate = result.win_rate
        context.backtest_net_pnl = result.net_pnl
        context.backtest_average_pnl = result.average_pnl
        context.backtest_max_drawdown = result.max_drawdown
        context.backtest_ignored_contexts = result.ignored_contexts
        self._update_debug(context)
        return context

    def summarize_contexts(self, contexts: list[MarketContext]) -> BacktestResult:
        total_paper_trades = 0
        closed_trades = 0
        open_trades = 0
        wins = 0
        losses = 0
        ignored_contexts = 0
        closed_pnls: list[float] = []

        for context in contexts:
            status = getattr(context, "paper_trade_status", "NO_PAPER_TRADE")

            if status == "NO_PAPER_TRADE":
                ignored_contexts += 1
                continue

            if status == "PAPER_OPEN":
                total_paper_trades += 1
                open_trades += 1
                continue

            if status == "PAPER_CLOSED_TP":
                total_paper_trades += 1
                closed_trades += 1
                wins += 1
                closed_pnls.append(self._paper_pnl(context))
                continue

            if status == "PAPER_CLOSED_SL":
                total_paper_trades += 1
                closed_trades += 1
                losses += 1
                closed_pnls.append(self._paper_pnl(context))

        net_pnl = sum(closed_pnls)
        win_rate = wins / closed_trades * 100 if closed_trades > 0 else 0
        average_pnl = net_pnl / closed_trades if closed_trades > 0 else 0
        max_drawdown = self._max_drawdown(closed_pnls)

        return BacktestResult(
            total_paper_trades=total_paper_trades,
            closed_trades=closed_trades,
            open_trades=open_trades,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            net_pnl=net_pnl,
            average_pnl=average_pnl,
            max_drawdown=max_drawdown,
            ignored_contexts=ignored_contexts,
        )

    def _paper_pnl(self, context: MarketContext) -> float:
        value = getattr(context, "paper_pnl", None)
        return 0 if value is None else float(value)

    def _max_drawdown(self, closed_pnls: list[float]) -> float:
        equity = 0
        peak = 0
        max_drawdown = 0

        for pnl in closed_pnls:
            equity += pnl
            peak = max(peak, equity)
            drawdown = peak - equity
            max_drawdown = max(max_drawdown, drawdown)

        return max_drawdown

    def _update_debug(self, context: MarketContext) -> None:
        if not hasattr(context, "debug") or context.debug is None:
            return

        context.debug["backtest_total_trades"] = context.backtest_total_trades
        context.debug["backtest_closed_trades"] = context.backtest_closed_trades
        context.debug["backtest_open_trades"] = context.backtest_open_trades
        context.debug["backtest_wins"] = context.backtest_wins
        context.debug["backtest_losses"] = context.backtest_losses
        context.debug["backtest_win_rate"] = context.backtest_win_rate
        context.debug["backtest_net_pnl"] = context.backtest_net_pnl
        context.debug["backtest_average_pnl"] = context.backtest_average_pnl
        context.debug["backtest_max_drawdown"] = context.backtest_max_drawdown
        context.debug["backtest_ignored_contexts"] = context.backtest_ignored_contexts
