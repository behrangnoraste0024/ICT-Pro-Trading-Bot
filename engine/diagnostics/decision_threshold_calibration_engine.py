from __future__ import annotations

from models.cost_diagnostics import CostDiagnostics
from models.decision_threshold_calibration import DecisionThresholdBucket
from models.decision_threshold_calibration import DecisionThresholdCalibrationResult
from models.market_context import MarketContext


class DecisionThresholdCalibrationEngine:
    DEFAULT_THRESHOLDS = [0.60, 0.65, 0.70, 0.75, 0.80, 0.85]

    def summarize_contexts(
        self,
        contexts: list[MarketContext],
        cost_diagnostics: CostDiagnostics | None = None,
        thresholds: list[float] | None = None,
    ) -> DecisionThresholdCalibrationResult:
        selected_thresholds = self.DEFAULT_THRESHOLDS if thresholds is None else thresholds
        trades = [context for context in contexts if self._is_trade(context)]
        cost_by_index = {
            trade.trade_index: trade
            for trade in getattr(cost_diagnostics, "trades", [])
        }
        trade_rows = [
            (context, cost_by_index.get(index))
            for index, context in enumerate(trades, start=1)
        ]
        buckets = [self._bucket(threshold, trade_rows) for threshold in selected_thresholds]
        missing_score_count = sum(1 for context in trades if getattr(context, "decision_score", None) is None)
        return DecisionThresholdCalibrationResult(
            thresholds=buckets,
            best_by_net_after_costs=self._best_by_net_after_costs(buckets),
            best_by_drawdown=self._best_by_drawdown(buckets),
            best_by_profit_factor=self._best_by_profit_factor(buckets),
            diagnostics={
                "source_trades": len(trades),
                "cost_diagnostics_available": cost_diagnostics is not None,
                "trades_with_decision_score": len(trades) - missing_score_count,
                "trades_missing_decision_score": missing_score_count,
            },
        )

    def _bucket(self, threshold: float, trade_rows: list[tuple]) -> DecisionThresholdBucket:
        rows = self._matching_rows(threshold, trade_rows)
        gross_pnls = [self._gross_pnl(context, cost) for context, cost in rows if self._is_closed(context)]
        net_pnls = [self._net_after_costs(context, cost) for context, cost in rows if self._is_closed(context)]
        total_trades = len(rows)
        wins = sum(1 for context, _cost in rows if self._is_win(context))
        losses = sum(1 for context, _cost in rows if self._is_loss(context))
        closed_trades = wins + losses
        gross_net_pnl = sum(gross_pnls)
        total_cost = sum(self._total_cost(cost) for context, cost in rows if self._is_closed(context))
        net_pnl_after_costs = sum(net_pnls)
        return DecisionThresholdBucket(
            threshold=threshold,
            name=self._bucket_name(threshold),
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            win_rate=(wins / closed_trades) * 100 if closed_trades else 0.0,
            gross_net_pnl=gross_net_pnl,
            total_cost=total_cost,
            net_pnl_after_costs=net_pnl_after_costs,
            average_pnl=gross_net_pnl / closed_trades if closed_trades else 0.0,
            average_net_pnl_after_costs=net_pnl_after_costs / closed_trades if closed_trades else 0.0,
            max_drawdown=self._max_drawdown(net_pnls),
            profit_factor=self._profit_factor(net_pnls),
            average_execution_quality=self._average([getattr(context, "execution_quality_score", None) for context, _cost in rows]),
            average_decision_score=self._average([getattr(context, "decision_score", None) for context, _cost in rows]),
        )

    def _matching_rows(self, threshold: float, trade_rows: list[tuple]) -> list[tuple]:
        rows = []
        for context, cost in trade_rows:
            score = getattr(context, "decision_score", None)
            if score is None:
                continue
            if float(score) >= threshold:
                rows.append((context, cost))
        return rows

    def _bucket_name(self, threshold: float) -> str:
        return f"score_gte_{threshold:.2f}"

    def _is_trade(self, context: MarketContext) -> bool:
        return getattr(context, "paper_trade_status", "NO_PAPER_TRADE") != "NO_PAPER_TRADE"

    def _is_closed(self, context: MarketContext) -> bool:
        return getattr(context, "paper_trade_status", None) in ("PAPER_CLOSED_TP", "PAPER_CLOSED_SL")

    def _is_win(self, context: MarketContext) -> bool:
        return getattr(context, "paper_trade_status", None) == "PAPER_CLOSED_TP"

    def _is_loss(self, context: MarketContext) -> bool:
        return getattr(context, "paper_trade_status", None) == "PAPER_CLOSED_SL"

    def _gross_pnl(self, context: MarketContext, cost) -> float:
        if cost is not None:
            return float(cost.gross_pnl)
        value = getattr(context, "paper_pnl", None)
        return 0.0 if value is None else float(value)

    def _net_after_costs(self, context: MarketContext, cost) -> float:
        if cost is not None:
            return float(cost.net_pnl_after_costs)
        return self._gross_pnl(context, cost)

    def _total_cost(self, cost) -> float:
        return 0.0 if cost is None else float(cost.total_cost)

    def _max_drawdown(self, pnls: list[float]) -> float:
        peak = 0.0
        equity = 0.0
        max_drawdown = 0.0
        for pnl in pnls:
            equity += pnl
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak - equity)
        return max_drawdown

    def _profit_factor(self, pnls: list[float]) -> float | None:
        gross_profit = sum(pnl for pnl in pnls if pnl > 0)
        gross_loss = abs(sum(pnl for pnl in pnls if pnl < 0))
        if gross_loss > 0:
            return gross_profit / gross_loss
        if gross_profit > 0:
            return None
        return None

    def _average(self, values: list) -> float | None:
        numeric_values = [float(value) for value in values if value is not None]
        if not numeric_values:
            return None
        return sum(numeric_values) / len(numeric_values)

    def _best_by_net_after_costs(self, buckets: list[DecisionThresholdBucket]) -> str | None:
        candidates = [bucket for bucket in buckets if bucket.total_trades > 0]
        if not candidates:
            return None
        return max(candidates, key=lambda bucket: bucket.net_pnl_after_costs).name

    def _best_by_drawdown(self, buckets: list[DecisionThresholdBucket]) -> str | None:
        candidates = [bucket for bucket in buckets if bucket.total_trades > 0]
        if not candidates:
            return None
        return min(candidates, key=lambda bucket: bucket.max_drawdown).name

    def _best_by_profit_factor(self, buckets: list[DecisionThresholdBucket]) -> str | None:
        candidates = [bucket for bucket in buckets if bucket.total_trades > 0 and bucket.profit_factor is not None]
        if not candidates:
            return None
        return max(candidates, key=lambda bucket: bucket.profit_factor).name
