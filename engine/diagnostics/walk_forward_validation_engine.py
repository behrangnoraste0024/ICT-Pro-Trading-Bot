from __future__ import annotations

from models.cost_diagnostics import CostDiagnostics
from models.market_context import MarketContext
from models.walk_forward_validation import (
    WalkForwardRecommendedProfileValidation,
    WalkForwardSegmentValidation,
)


class WalkForwardValidationEngine:
    DEFAULT_PROFILE = "balanced_smc_decision_065"
    DEFAULT_THRESHOLD = 0.65
    DEFAULT_SEGMENT_COUNT = 4

    def validate_contexts(
        self,
        contexts: list[MarketContext],
        cost_diagnostics: CostDiagnostics | None = None,
        profile: str = DEFAULT_PROFILE,
        strategy_name: str | None = None,
        score_threshold: float | None = DEFAULT_THRESHOLD,
        segment_count: int = DEFAULT_SEGMENT_COUNT,
        max_segment_drawdown: float | None = None,
    ) -> WalkForwardRecommendedProfileValidation:
        if segment_count <= 0:
            raise ValueError("segment_count must be greater than 0")

        trades = [context for context in contexts if self._is_trade(context)]
        cost_by_index = {
            trade.trade_index: trade
            for trade in getattr(cost_diagnostics, "trades", [])
        }
        trade_rows = [
            (index, context, cost_by_index.get(index))
            for index, context in enumerate(trades, start=1)
        ]
        missing_score_count = sum(1 for _index, context, _cost in trade_rows if getattr(context, "decision_score", None) is None)
        segments = [
            self._segment_validation(
                segment_index=index + 1,
                rows=segment_rows,
                score_threshold=score_threshold,
                max_segment_drawdown=max_segment_drawdown,
            )
            for index, segment_rows in enumerate(self._split_segments(trade_rows, segment_count))
        ]
        included_segments = [segment for segment in segments if segment.total_trades > 0]
        total_trades = sum(segment.total_trades for segment in segments)
        wins = sum(segment.wins for segment in segments)
        losses = sum(segment.losses for segment in segments)
        closed_trades = wins + losses
        gross_net_pnl = sum(segment.gross_net_pnl for segment in segments)
        total_cost = sum(segment.total_cost for segment in segments)
        net_pnl_after_costs = sum(segment.net_pnl_after_costs for segment in segments)
        segment_net_values = [segment.net_pnl_after_costs for segment in included_segments]
        profitable_segments = sum(1 for segment in included_segments if segment.net_pnl_after_costs > 0)
        losing_segments = sum(1 for segment in included_segments if segment.net_pnl_after_costs <= 0)
        empty_segments = sum(1 for segment in segments if segment.total_trades == 0)
        passed_segments = sum(1 for segment in segments if segment.passed)
        failed_segments = segment_count - passed_segments
        status, reason = self._validation_status(
            net_pnl_after_costs=net_pnl_after_costs,
            passed_segments=passed_segments,
            empty_segments=empty_segments,
            losing_segments=losing_segments,
        )
        return WalkForwardRecommendedProfileValidation(
            profile=profile,
            strategy_name=strategy_name or f"profile={profile}|cost=percent",
            score_threshold=score_threshold,
            segment_count=segment_count,
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            win_rate=(wins / closed_trades) * 100 if closed_trades else 0.0,
            gross_net_pnl=gross_net_pnl,
            total_cost=total_cost,
            net_pnl_after_costs=net_pnl_after_costs,
            max_drawdown=max((segment.max_drawdown for segment in segments), default=0.0),
            profitable_segments=profitable_segments,
            losing_segments=losing_segments,
            empty_segments=empty_segments,
            passed_segments=passed_segments,
            failed_segments=failed_segments,
            worst_segment_net_pnl_after_costs=min(segment_net_values) if segment_net_values else 0.0,
            average_segment_net_pnl_after_costs=(sum(segment_net_values) / len(segment_net_values)) if segment_net_values else 0.0,
            validation_status=status,
            validation_reason=reason,
            segments=segments,
            diagnostics={
                "source_trades": len(trades),
                "included_trades": total_trades,
                "excluded_missing_decision_score": missing_score_count,
                "cost_diagnostics_available": cost_diagnostics is not None,
                "max_segment_drawdown": max_segment_drawdown,
            },
        )

    def _split_segments(self, rows: list[tuple], segment_count: int) -> list[list[tuple]]:
        total = len(rows)
        base = total // segment_count
        remainder = total % segment_count
        segments: list[list[tuple]] = []
        start = 0
        for index in range(segment_count):
            size = base + (1 if index < remainder else 0)
            end = start + size
            segments.append(rows[start:end])
            start = end
        return segments

    def _segment_validation(
        self,
        segment_index: int,
        rows: list[tuple],
        score_threshold: float | None,
        max_segment_drawdown: float | None,
    ) -> WalkForwardSegmentValidation:
        filtered_rows = self._threshold_rows(rows, score_threshold)
        gross_pnls = [self._gross_pnl(context, cost) for _index, context, cost in filtered_rows if self._is_closed(context)]
        net_pnls = [self._net_after_costs(context, cost) for _index, context, cost in filtered_rows if self._is_closed(context)]
        wins = sum(1 for _index, context, _cost in filtered_rows if self._is_win(context))
        losses = sum(1 for _index, context, _cost in filtered_rows if self._is_loss(context))
        closed_trades = wins + losses
        gross_net_pnl = sum(gross_pnls)
        total_cost = sum(self._total_cost(cost) for _index, context, cost in filtered_rows if self._is_closed(context))
        net_pnl_after_costs = sum(net_pnls)
        max_drawdown = self._max_drawdown(net_pnls)
        failure_reasons = self._failure_reasons(
            total_trades=len(filtered_rows),
            net_pnl_after_costs=net_pnl_after_costs,
            max_drawdown=max_drawdown,
            max_segment_drawdown=max_segment_drawdown,
        )
        return WalkForwardSegmentValidation(
            segment_name=f"segment_{segment_index}",
            segment_index=segment_index,
            start_trade_index=filtered_rows[0][0] if filtered_rows else 0,
            end_trade_index=filtered_rows[-1][0] if filtered_rows else 0,
            total_trades=len(filtered_rows),
            wins=wins,
            losses=losses,
            win_rate=(wins / closed_trades) * 100 if closed_trades else 0.0,
            gross_net_pnl=gross_net_pnl,
            total_cost=total_cost,
            net_pnl_after_costs=net_pnl_after_costs,
            max_drawdown=max_drawdown,
            average_decision_score=self._average([getattr(context, "decision_score", None) for _index, context, _cost in filtered_rows]),
            average_execution_quality=self._average([getattr(context, "execution_quality_score", None) for _index, context, _cost in filtered_rows]),
            passed=not failure_reasons,
            failure_reasons=failure_reasons,
        )

    def _threshold_rows(self, rows: list[tuple], score_threshold: float | None) -> list[tuple]:
        if score_threshold is None:
            return [row for row in rows if getattr(row[1], "decision_score", None) is not None]
        filtered = []
        for row in rows:
            score = getattr(row[1], "decision_score", None)
            if score is None:
                continue
            if float(score) >= score_threshold:
                filtered.append(row)
        return filtered

    def _failure_reasons(
        self,
        total_trades: int,
        net_pnl_after_costs: float,
        max_drawdown: float,
        max_segment_drawdown: float | None,
    ) -> list[str]:
        reasons = []
        if total_trades == 0:
            reasons.append("EMPTY_SEGMENT")
        if total_trades > 0 and net_pnl_after_costs <= 0:
            reasons.append("NON_POSITIVE_NET_AFTER_COSTS")
        if max_segment_drawdown is not None and max_drawdown > max_segment_drawdown:
            reasons.append("MAX_DRAWDOWN_EXCEEDED")
        return reasons

    def _validation_status(
        self,
        net_pnl_after_costs: float,
        passed_segments: int,
        empty_segments: int,
        losing_segments: int,
    ) -> tuple[str, str]:
        if passed_segments == 0 or net_pnl_after_costs <= 0:
            return "FAIL", "no passing segment or aggregate net after costs is non-positive"
        if empty_segments > 0 or losing_segments > 0:
            return "WARNING", "at least one segment passes, but empty or losing segments remain"
        if passed_segments >= 2:
            return "PASS", "all non-empty segments pass and at least two segments have trades"
        return "WARNING", "fewer than two non-empty passing segments"

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

    def _average(self, values: list) -> float | None:
        numeric_values = [float(value) for value in values if value is not None]
        if not numeric_values:
            return None
        return sum(numeric_values) / len(numeric_values)
