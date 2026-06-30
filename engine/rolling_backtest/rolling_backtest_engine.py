from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd

from engine.backtest.backtest_diagnostics_engine import BacktestDiagnosticsEngine
from engine.backtest.backtest_engine import BacktestEngine
from engine.ict_engine import ICTEngine
from engine.rolling_backtest.trade_state_manager import TradeStateManager
from models.market_context import MarketContext
from models.rolling_trade_state import RollingTradeState
from models.rolling_backtest_result import RollingBacktestResult

ProgressCallback = Callable[[dict[str, Any]], None]


class RollingBacktestEngine:
    def __init__(
        self,
        ict_engine: ICTEngine | None = None,
        min_candles: int = 50,
        stateful: bool = True,
        progress_callback: ProgressCallback | None = None,
        progress_every: int = 100,
        max_windows: int | None = None,
    ):
        self.ict_engine = ict_engine if ict_engine is not None else ICTEngine()
        self.min_candles = min_candles
        self.stateful = stateful
        self.progress_callback = progress_callback
        self.progress_every = progress_every
        self.max_windows = max_windows
        self.backtest_engine = BacktestEngine()
        self.diagnostics_engine = BacktestDiagnosticsEngine()
        self.trade_state_manager = TradeStateManager()

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
                diagnostic_contexts=[],
            )
            return result, []

        if not self.stateful:
            return self._run_stateless(candles)

        return self._run_stateful(candles)

    def _run_stateless(self, candles: pd.DataFrame) -> tuple[RollingBacktestResult, list[MarketContext]]:
        total_windows = len(candles)
        processed_windows = 0
        skipped_windows = 0
        failed_windows = 0
        contexts: list[MarketContext] = []

        for end_index in range(total_windows):
            if end_index + 1 < self.min_candles:
                skipped_windows += 1
                self._emit_progress(
                    end_index=end_index,
                    total_windows=total_windows,
                    processed_windows=processed_windows,
                    skipped_windows=skipped_windows,
                    failed_windows=failed_windows,
                )
                continue

            if self._max_windows_reached(processed_windows):
                break

            window_candles = candles.iloc[: end_index + 1].copy()
            try:
                context = self._analyze(window_candles)
            except Exception:
                failed_windows += 1
                self._emit_progress(
                    end_index=end_index,
                    total_windows=total_windows,
                    processed_windows=processed_windows,
                    skipped_windows=skipped_windows,
                    failed_windows=failed_windows,
                )
                continue

            contexts.append(context)
            processed_windows += 1
            self._emit_progress(
                end_index=end_index,
                total_windows=total_windows,
                processed_windows=processed_windows,
                skipped_windows=skipped_windows,
                failed_windows=failed_windows,
                force=end_index == total_windows - 1 or self._max_windows_reached(processed_windows),
            )

        result = self._result_from_summary(
            total_windows=total_windows,
            processed_windows=processed_windows,
            skipped_windows=skipped_windows,
            failed_windows=failed_windows,
            contexts=contexts,
            diagnostic_contexts=contexts,
        )
        return result, contexts

    def _run_stateful(self, candles: pd.DataFrame) -> tuple[RollingBacktestResult, list[MarketContext]]:
        total_windows = len(candles)
        processed_windows = 0
        skipped_windows = 0
        failed_windows = 0
        opened_trades = 0
        closed_by_state = 0
        duplicate_signals_skipped = 0
        contexts: list[MarketContext] = []
        completed_trade_contexts: list[MarketContext] = []
        open_state = RollingTradeState()

        for end_index in range(total_windows):
            if end_index + 1 < self.min_candles:
                skipped_windows += 1
                self._emit_progress(
                    end_index=end_index,
                    total_windows=total_windows,
                    processed_windows=processed_windows,
                    skipped_windows=skipped_windows,
                    failed_windows=failed_windows,
                    opened_trades=opened_trades,
                    closed_by_state=closed_by_state,
                    duplicate_signals_skipped=duplicate_signals_skipped,
                )
                continue

            if self._max_windows_reached(processed_windows):
                break

            if open_state.is_open:
                candle = candles.iloc[end_index]
                open_state = self.trade_state_manager.update_with_candle(open_state, candle, end_index)
                duplicate_signals_skipped += 1
                processed_windows += 1

                if not open_state.is_open:
                    closed_by_state += 1
                    completed_trade_contexts.append(self.trade_state_manager.to_paper_trade_context(open_state))
                    open_state = RollingTradeState()
                self._emit_progress(
                    end_index=end_index,
                    total_windows=total_windows,
                    processed_windows=processed_windows,
                    skipped_windows=skipped_windows,
                    failed_windows=failed_windows,
                    opened_trades=opened_trades,
                    closed_by_state=closed_by_state,
                    duplicate_signals_skipped=duplicate_signals_skipped,
                    force=end_index == total_windows - 1 or self._max_windows_reached(processed_windows),
                )
                continue

            window_candles = candles.iloc[: end_index + 1].copy()
            try:
                context = self._analyze(window_candles)
            except Exception:
                failed_windows += 1
                self._emit_progress(
                    end_index=end_index,
                    total_windows=total_windows,
                    processed_windows=processed_windows,
                    skipped_windows=skipped_windows,
                    failed_windows=failed_windows,
                    opened_trades=opened_trades,
                    closed_by_state=closed_by_state,
                    duplicate_signals_skipped=duplicate_signals_skipped,
                )
                continue

            contexts.append(context)
            processed_windows += 1

            if context.trade_quality_status == "APPROVED" and context.trade_plan_status == "PLANNED":
                opened_state = self.trade_state_manager.open_from_context(context, entry_index=end_index)
                if opened_state is not None:
                    open_state = opened_state
                    opened_trades += 1
            self._emit_progress(
                end_index=end_index,
                total_windows=total_windows,
                processed_windows=processed_windows,
                skipped_windows=skipped_windows,
                failed_windows=failed_windows,
                opened_trades=opened_trades,
                closed_by_state=closed_by_state,
                duplicate_signals_skipped=duplicate_signals_skipped,
                force=end_index == total_windows - 1 or self._max_windows_reached(processed_windows),
            )

        if open_state.is_open:
            completed_trade_contexts.append(self.trade_state_manager.to_paper_trade_context(open_state))

        result = self._result_from_summary(
            total_windows=total_windows,
            processed_windows=processed_windows,
            skipped_windows=skipped_windows,
            failed_windows=failed_windows,
            contexts=completed_trade_contexts,
            diagnostic_contexts=contexts,
            opened_trades=opened_trades,
            closed_by_state=closed_by_state,
            duplicate_signals_skipped=duplicate_signals_skipped,
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

    def _max_windows_reached(self, processed_windows: int) -> bool:
        return self.max_windows is not None and processed_windows >= self.max_windows

    def _emit_progress(
        self,
        end_index: int,
        total_windows: int,
        processed_windows: int,
        skipped_windows: int,
        failed_windows: int,
        opened_trades: int = 0,
        closed_by_state: int = 0,
        duplicate_signals_skipped: int = 0,
        force: bool = False,
    ) -> None:
        if self.progress_callback is None or self.progress_every <= 0:
            return

        completed_windows = processed_windows + skipped_windows + failed_windows
        if not force and completed_windows % self.progress_every != 0:
            return

        self.progress_callback(
            {
                "end_index": end_index,
                "total_windows": total_windows,
                "processed_windows": processed_windows,
                "skipped_windows": skipped_windows,
                "failed_windows": failed_windows,
                "opened_trades": opened_trades,
                "closed_by_state": closed_by_state,
                "duplicate_signals_skipped": duplicate_signals_skipped,
            }
        )

    def _result_from_summary(
        self,
        total_windows: int,
        processed_windows: int,
        skipped_windows: int,
        failed_windows: int,
        contexts: list[MarketContext],
        diagnostic_contexts: list[MarketContext] | None = None,
        opened_trades: int = 0,
        closed_by_state: int = 0,
        duplicate_signals_skipped: int = 0,
    ) -> RollingBacktestResult:
        summary = self.backtest_engine.summarize_contexts(contexts)
        diagnostics_source = contexts if diagnostic_contexts is None else diagnostic_contexts
        diagnostics = self.diagnostics_engine.summarize_contexts(diagnostics_source)
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
            stateful_mode=self.stateful,
            opened_trades=opened_trades,
            closed_by_state=closed_by_state,
            duplicate_signals_skipped=duplicate_signals_skipped,
            diagnostics=diagnostics,
            diagnostics_windows_analyzed=diagnostics.windows_analyzed,
        )
