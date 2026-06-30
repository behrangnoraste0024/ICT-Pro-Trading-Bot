from __future__ import annotations

from typing import Any

from models.backtest_diagnostics import BacktestDiagnostics
from models.market_context import MarketContext


class BacktestDiagnosticsEngine:
    def collect_from_context(self, context: MarketContext) -> BacktestDiagnostics:
        diagnostics = BacktestDiagnostics(windows_analyzed=1)

        self._count_blockers(diagnostics.setup_blockers, self._get_blockers(context, "setup_blockers"))
        self._count_blockers(diagnostics.entry_blockers, self._get_blockers(context, "entry_blockers"))
        self._count_blockers(diagnostics.trade_plan_blockers, self._get_blockers(context, "trade_plan_blockers"))
        self._count_blockers(diagnostics.trade_quality_blockers, self._get_blockers(context, "trade_quality_blockers"))
        self._count_blockers(diagnostics.paper_trade_blockers, self._get_blockers(context, "paper_trade_blockers"))

        self._count_status(diagnostics.setup_status_counts, self._get_status(context, "setup_status"))
        self._count_status(diagnostics.entry_status_counts, self._get_status(context, "entry_status"))
        self._count_status(diagnostics.trade_plan_status_counts, self._get_status(context, "trade_plan_status"))
        self._count_status(diagnostics.trade_quality_status_counts, self._get_status(context, "trade_quality_status"))
        self._count_status(diagnostics.paper_trade_status_counts, self._get_status(context, "paper_trade_status"))

        return diagnostics

    def summarize_contexts(self, contexts: list[MarketContext]) -> BacktestDiagnostics:
        summary = BacktestDiagnostics(windows_analyzed=len(contexts))

        for context in contexts:
            diagnostics = self.collect_from_context(context)
            self._merge_counts(summary.setup_blockers, diagnostics.setup_blockers)
            self._merge_counts(summary.entry_blockers, diagnostics.entry_blockers)
            self._merge_counts(summary.trade_plan_blockers, diagnostics.trade_plan_blockers)
            self._merge_counts(summary.trade_quality_blockers, diagnostics.trade_quality_blockers)
            self._merge_counts(summary.paper_trade_blockers, diagnostics.paper_trade_blockers)
            self._merge_counts(summary.setup_status_counts, diagnostics.setup_status_counts)
            self._merge_counts(summary.entry_status_counts, diagnostics.entry_status_counts)
            self._merge_counts(summary.trade_plan_status_counts, diagnostics.trade_plan_status_counts)
            self._merge_counts(summary.trade_quality_status_counts, diagnostics.trade_quality_status_counts)
            self._merge_counts(summary.paper_trade_status_counts, diagnostics.paper_trade_status_counts)

        return summary

    def _get_blockers(self, context: MarketContext, field_name: str) -> list[str]:
        blockers = getattr(context, field_name, [])
        if blockers is None:
            return []
        if isinstance(blockers, list):
            return [str(blocker) for blocker in blockers]
        return [str(blockers)]

    def _get_status(self, context: MarketContext, field_name: str) -> str:
        status = getattr(context, field_name, "UNKNOWN")
        if status is None:
            return "UNKNOWN"
        return str(status)

    def _count_blockers(self, target: dict[str, int], blockers: list[str]) -> None:
        for blocker in blockers:
            target[blocker] = target.get(blocker, 0) + 1

    def _count_status(self, target: dict[str, int], status: str) -> None:
        target[status] = target.get(status, 0) + 1

    def _merge_counts(self, target: dict[str, int], source: dict[str, int]) -> None:
        for key, count in source.items():
            target[key] = target.get(key, 0) + count
