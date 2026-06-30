from __future__ import annotations

import pandas as pd

from engine.backtest.backtest_engine import BacktestEngine
from engine.ict_engine import ICTEngine
from models.market_context import MarketContext
from models.rolling_backtest_result import RollingBacktestResult


class RollingBacktestEngine:
    def __init__(self, ict_engine: ICTEngine | None = None, min_candles: int = 50):
        self.ict_engine = ict_engine if ict_engine is not None else ICTEngine()
        self.min_candles = min_candles
        self.backtest_engine = BacktestEngine()

    def run(self, candles: pd.DataFrame) -> RollingBacktestResult:
        result, _contexts = self.run_with_contexts(candles)
        return result

    def run_with_contexts(self, candles: pd.DataFrame) -> tuple[RollingBacktestResult, list[MarketContext]]:
        if candles is None or len(candles) == 0:
            result = self._result_from_summary(
                total_windows=0,
                processed_windows=0,
                skipped_windows=0,
                failed_windows=0,
                contexts=[],
            )
            return result, []

        total_windows = len(candles)
        processed_windows = 0
        skipped_windows = 0
        failed_windows = 0
        contexts: list[MarketContext] = []

        for end_index in range(total_windows):
            if end_index + 1 < self.min_candles:
                skipped_windows += 1
                continue

            window_candles = candles.iloc[: end_index + 1].copy()
            try:
                context = self._analyze(window_candles)
            except Exception:
                failed_windows += 1
                continue

            contexts.append(context)
            processed_windows += 1

        result = self._result_from_summary(
            total_windows=total_windows,
            processed_windows=processed_windows,
            skipped_windows=skipped_windows,
            failed_windows=failed_windows,
            contexts=contexts,
        )
        return result, contexts

    def _analyze(self, candles: pd.DataFrame) -> MarketContext:
        if hasattr(self.ict_engine, "analyze"):
            return self.ict_engine.analyze(candles)
        if hasattr(self.ict_engine, "detect"):
            return self.ict_engine.detect(candles)
        if hasattr(self.ict_engine, "run"):
            return self.ict_engine.run(candles)
        raise AttributeError("ICT engine does not expose analyze, detect, or run")

    def _result_from_summary(
        self,
        total_windows: int,
        processed_windows: int,
        skipped_windows: int,
        failed_windows: int,
        contexts: list[MarketContext],
    ) -> RollingBacktestResult:
        summary = self.backtest_engine.summarize_contexts(contexts)
        return RollingBacktestResult(
            total_windows=total_windows,
            processed_windows=processed_windows,
            skipped_windows=skipped_windows,
            failed_windows=failed_windows,
            min_candles=self.min_candles,
            total_paper_trades=summary.total_paper_trades,
            closed_trades=summary.closed_trades,
            open_trades=summary.open_trades,
            wins=summary.wins,
            losses=summary.losses,
            win_rate=summary.win_rate,
            net_pnl=summary.net_pnl,
            average_pnl=summary.average_pnl,
            max_drawdown=summary.max_drawdown,
            ignored_contexts=summary.ignored_contexts,
        )
