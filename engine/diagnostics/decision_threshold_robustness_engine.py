from __future__ import annotations

from models.cost_diagnostics import CostDiagnostics
from models.decision_threshold_robustness import DecisionThresholdRobustnessResult
from models.decision_threshold_robustness import DecisionThresholdSegmentBucket
from models.decision_threshold_robustness import DecisionThresholdSegmentSummary
from models.market_context import MarketContext


class DecisionThresholdRobustnessEngine:
    DEFAULT_THRESHOLDS = [0.60, 0.65, 0.70, 0.75, 0.80, 0.85]
    DEFAULT_SEGMENT_COUNT = 4

    def summarize_contexts(
        self,
        contexts: list[MarketContext],
        cost_diagnostics: CostDiagnostics | None = None,
        thresholds: list[float] | None = None,
        segment_count: int = DEFAULT_SEGMENT_COUNT,
    ) -> DecisionThresholdRobustnessResult:
        selected_thresholds = self.DEFAULT_THRESHOLDS if thresholds is None else thresholds
        selected_segment_count = max(segment_count, 1)
        trades = [context for context in contexts if self._is_trade(context)]
        cost_by_index = {
            trade.trade_index: trade
            for trade in getattr(cost_diagnostics, "trades", [])
        }
        trade_rows = [
            (index, context, cost_by_index.get(index))
            for index, context in enumerate(trades, start=1)
        ]
        segments = self._split_segments(trade_rows, selected_segment_count)
        summaries = [
            self._segment_summary(index, rows, selected_thresholds)
            for index, rows in enumerate(segments, start=1)
        ]
        stability = self._threshold_stability(summaries, selected_thresholds)
        missing_score_count = sum(1 for context in trades if getattr(context, "decision_score", None) is None)
        return DecisionThresholdRobustnessResult(
            segment_count=selected_segment_count,
            thresholds=list(selected_thresholds),
            segment_summaries=summaries,
            threshold_stability=stability,
            best_overall_threshold=self._best_overall_threshold(stability),
            robust_threshold=self._robust_threshold(stability),
            diagnostics={
                "source_trades": len(trades),
                "segment_count": selected_segment_count,
                "cost_diagnostics_available": cost_diagnostics is not None,
                "trades_with_decision_score": len(trades) - missing_score_count,
                "trades_missing_decision_score": missing_score_count,
            },
        )

    def _split_segments(self, trade_rows: list[tuple], segment_count: int) -> list[list[tuple]]:
        total = len(trade_rows)
        base_size, remainder = divmod(total, segment_count)
        segments = []
        cursor = 0
        for index in range(segment_count):
            size = base_size + (1 if index < remainder else 0)
            segments.append(trade_rows[cursor : cursor + size])
            cursor += size
        return segments

    def _segment_summary(
        self,
        segment_index: int,
        rows: list[tuple],
        thresholds: list[float],
    ) -> DecisionThresholdSegmentSummary:
        segment_name = f"segment_{segment_index}"
        buckets = [self._bucket(segment_index, segment_name, threshold, rows) for threshold in thresholds]
        return DecisionThresholdSegmentSummary(
            segment_index=segment_index,
            segment_name=segment_name,
            start_trade_index=rows[0][0] if rows else 0,
            end_trade_index=rows[-1][0] if rows else 0,
            total_source_trades=len(rows),
            best_by_net_after_costs=self._best_by_net_after_costs(buckets),
            best_by_drawdown=self._best_by_drawdown(buckets),
            buckets=buckets,
        )

    def _bucket(
        self,
        segment_index: int,
        segment_name: str,
        threshold: float,
        trade_rows: list[tuple],
    ) -> DecisionThresholdSegmentBucket:
        rows = self._matching_rows(threshold, trade_rows)
        gross_pnls = [self._gross_pnl(context, cost) for _index, context, cost in rows if self._is_closed(context)]
        net_pnls = [self._net_after_costs(context, cost) for _index, context, cost in rows if self._is_closed(context)]
        total_trades = len(rows)
        wins = sum(1 for _index, context, _cost in rows if self._is_win(context))
        losses = sum(1 for _index, context, _cost in rows if self._is_loss(context))
        closed_trades = wins + losses
        gross_net_pnl = sum(gross_pnls)
        total_cost = sum(self._total_cost(cost) for _index, context, cost in rows if self._is_closed(context))
        net_pnl_after_costs = sum(net_pnls)
        return DecisionThresholdSegmentBucket(
            segment_index=segment_index,
            segment_name=segment_name,
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
            average_execution_quality=self._average([getattr(context, "execution_quality_score", None) for _index, context, _cost in rows]),
            average_decision_score=self._average([getattr(context, "decision_score", None) for _index, context, _cost in rows]),
        )

    def _matching_rows(self, threshold: float, trade_rows: list[tuple]) -> list[tuple]:
        rows = []
        for index, context, cost in trade_rows:
            score = getattr(context, "decision_score", None)
            if score is None:
                continue
            if float(score) >= threshold:
                rows.append((index, context, cost))
        return rows

    def _threshold_stability(
        self,
        summaries: list[DecisionThresholdSegmentSummary],
        thresholds: list[float],
    ) -> dict:
        stability = {}
        for threshold in thresholds:
            name = self._bucket_name(threshold)
            buckets = [
                bucket
                for summary in summaries
                for bucket in summary.buckets
                if bucket.name == name
            ]
            active_buckets = [bucket for bucket in buckets if bucket.total_trades > 0]
            total_trades = sum(bucket.total_trades for bucket in active_buckets)
            total_wins = sum(bucket.wins for bucket in active_buckets)
            total_losses = sum(bucket.losses for bucket in active_buckets)
            total_net = sum(bucket.net_pnl_after_costs for bucket in active_buckets)
            stability[threshold] = {
                "segments_with_trades": len(active_buckets),
                "profitable_segments": sum(1 for bucket in active_buckets if bucket.net_pnl_after_costs > 0),
                "losing_segments": sum(1 for bucket in active_buckets if bucket.net_pnl_after_costs < 0),
                "total_net_pnl_after_costs": total_net,
                "average_net_pnl_after_costs": total_net / len(active_buckets) if active_buckets else 0.0,
                "worst_segment_net_pnl_after_costs": min((bucket.net_pnl_after_costs for bucket in active_buckets), default=0.0),
                "average_drawdown": self._average([bucket.max_drawdown for bucket in active_buckets]) or 0.0,
                "max_drawdown": max((bucket.max_drawdown for bucket in active_buckets), default=0.0),
                "total_trades": total_trades,
                "total_wins": total_wins,
                "total_losses": total_losses,
                "aggregate_win_rate": (total_wins / (total_wins + total_losses)) * 100 if (total_wins + total_losses) else 0.0,
            }
        return stability

    def _best_overall_threshold(self, stability: dict) -> float | None:
        candidates = [
            (threshold, values)
            for threshold, values in stability.items()
            if values["total_trades"] > 0
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item[1]["total_net_pnl_after_costs"], -item[0]))[0]

    def _robust_threshold(self, stability: dict) -> float | None:
        candidates = [
            (threshold, values)
            for threshold, values in stability.items()
            if values["total_trades"] > 0
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: (
                item[1]["profitable_segments"],
                item[1]["worst_segment_net_pnl_after_costs"],
                item[1]["total_net_pnl_after_costs"],
                -item[0],
            ),
        )[0]

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

    def _best_by_net_after_costs(self, buckets: list[DecisionThresholdSegmentBucket]) -> str | None:
        candidates = [bucket for bucket in buckets if bucket.total_trades > 0]
        if not candidates:
            return None
        return max(candidates, key=lambda bucket: bucket.net_pnl_after_costs).name

    def _best_by_drawdown(self, buckets: list[DecisionThresholdSegmentBucket]) -> str | None:
        candidates = [bucket for bucket in buckets if bucket.total_trades > 0]
        if not candidates:
            return None
        return min(candidates, key=lambda bucket: bucket.max_drawdown).name
