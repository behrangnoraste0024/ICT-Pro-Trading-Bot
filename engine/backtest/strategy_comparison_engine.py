from __future__ import annotations

import time
from collections.abc import Callable

from data.historical_data_utils import load_candles_json
from engine.rolling_backtest.rolling_backtest_engine import RollingBacktestEngine
from models.engine_config import EngineConfig
from models.rolling_backtest_result import RollingBacktestResult
from models.strategy_comparison import StrategyComparisonReport, StrategyComparisonRow, StrategyConfigSpec

ComparisonProgressCallback = Callable[[dict], None]


def build_default_strategy_specs() -> list[StrategyConfigSpec]:
    return [
        _spec("current_external", "original", 2.0),
        _spec("current_external", "fixed_1_5r", 1.5),
        _spec("recent_50", "original", 2.0),
        _spec("recent_50", "fixed_1r", 1.0),
        _spec("recent_50", "fixed_1_5r", 1.5),
        _spec("recent_50", "fixed_2r", 2.0),
        _spec("recent_50", "fixed_3r", 3.0),
    ]


def build_exit_modes_recent_50_specs() -> list[StrategyConfigSpec]:
    return [
        _spec("recent_50", "original", 2.0),
        _spec("recent_50", "fixed_1r", 1.0),
        _spec("recent_50", "fixed_1_5r", 1.5),
        _spec("recent_50", "fixed_2r", 2.0),
        _spec("recent_50", "fixed_3r", 3.0),
    ]


def build_direction_modes_recent_50_fixed_1_5r_specs() -> list[StrategyConfigSpec]:
    return [
        _spec("recent_50", "fixed_1_5r", 1.5, "all"),
        _spec("recent_50", "fixed_1_5r", 1.5, "long_only"),
        _spec("recent_50", "fixed_1_5r", 1.5, "short_only"),
    ]


def build_current_external_only_specs() -> list[StrategyConfigSpec]:
    return [
        _spec("current_external", "original", 2.0),
        _spec("current_external", "fixed_1r", 1.0),
        _spec("current_external", "fixed_1_5r", 1.5),
        _spec("current_external", "fixed_2r", 2.0),
    ]


def _spec(
    dealing_range_mode: str,
    exit_mode: str,
    min_risk_reward: float,
    direction_mode: str = "all",
) -> StrategyConfigSpec:
    name = f"{dealing_range_mode}|{exit_mode}|min_rr={min_risk_reward}|dir={direction_mode}"
    return StrategyConfigSpec(name, dealing_range_mode, exit_mode, min_risk_reward, direction_mode)


class StrategyComparisonEngine:
    def run_comparison(
        self,
        fixture_path: str,
        strategy_specs: list[StrategyConfigSpec],
        min_candles: int = 50,
        progress_every: int = 0,
        max_windows: int | None = None,
        enable_diagnostics: bool = True,
        progress_callback: ComparisonProgressCallback | None = None,
        timeout_per_strategy: float | None = None,
    ) -> StrategyComparisonReport:
        candles = load_candles_json(fixture_path)
        rows: list[StrategyComparisonRow] = []
        total_strategies = len(strategy_specs)
        if progress_callback is not None:
            progress_callback(
                {
                    "event": "comparison_start",
                    "strategies": total_strategies,
                    "fixture": fixture_path,
                }
            )
        for index, spec in enumerate(strategy_specs, start=1):
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "strategy_start",
                        "index": index,
                        "total": total_strategies,
                        "strategy": spec.name,
                    }
                )
            started_at = time.perf_counter()
            result = RollingBacktestEngine(
                min_candles=min_candles,
                progress_every=progress_every,
                max_windows=max_windows,
                progress_callback=self._rolling_progress_callback(progress_callback, spec, index, total_strategies),
                enable_diagnostics=enable_diagnostics,
                config=EngineConfig(
                    dealing_range_mode=spec.dealing_range_mode,
                    exit_mode=spec.exit_mode,
                    min_risk_reward=spec.min_risk_reward,
                    direction_mode=spec.direction_mode,
                ),
            ).run(candles)
            elapsed_seconds = time.perf_counter() - started_at
            row = self.row_from_result(spec, result, elapsed_seconds=elapsed_seconds)
            rows.append(row)
            if progress_callback is not None:
                progress_callback(
                    {
                        "event": "strategy_finish",
                        "index": index,
                        "total": total_strategies,
                        "strategy": spec.name,
                        "trades": row.total_trades,
                        "pnl": row.net_pnl,
                        "elapsed_seconds": elapsed_seconds,
                        "timeout_warning": timeout_per_strategy is not None and elapsed_seconds > timeout_per_strategy,
                    }
                )

        report = StrategyComparisonReport(fixture=fixture_path, min_candles=min_candles, strategies=rows)
        report.populate_best_fields()
        return report

    def run_single_strategy(
        self,
        fixture_path: str,
        strategy_spec: StrategyConfigSpec,
        min_candles: int = 50,
        progress_every: int = 0,
        max_windows: int | None = None,
        enable_diagnostics: bool = True,
    ) -> StrategyComparisonRow:
        return self.run_comparison(
            fixture_path=fixture_path,
            strategy_specs=[strategy_spec],
            min_candles=min_candles,
            progress_every=progress_every,
            max_windows=max_windows,
            enable_diagnostics=enable_diagnostics,
        ).strategies[0]

    def row_from_result(
        self,
        spec: StrategyConfigSpec,
        result: RollingBacktestResult,
        elapsed_seconds: float | None = None,
    ) -> StrategyComparisonRow:
        trade_outcomes = result.trade_outcome_diagnostics
        sl_tp = result.sl_tp_outcome_diagnostics
        followthrough = result.entry_followthrough_diagnostics
        trades = self._trade_records(result)
        direction_counts = self._direction_counts(result)
        direction_pnl = self._direction_pnl(result)
        profit_factor = self._profit_factor(trades)

        return StrategyComparisonRow(
            strategy_name=spec.name,
            dealing_range_mode=spec.dealing_range_mode,
            exit_mode=spec.exit_mode,
            min_risk_reward=spec.min_risk_reward,
            direction_mode=spec.direction_mode,
            total_windows=result.total_windows,
            processed_windows=result.processed_windows,
            failed_windows=result.failed_windows,
            opened_trades=result.opened_trades,
            duplicate_signals_skipped=result.duplicate_signals_skipped,
            total_trades=result.total_paper_trades,
            closed_trades=result.closed_trades,
            open_trades=result.open_trades,
            wins=result.wins,
            losses=result.losses,
            win_rate=result.win_rate,
            net_pnl=result.net_pnl,
            average_pnl=result.average_pnl,
            max_drawdown=result.max_drawdown,
            average_rr=None if trade_outcomes is None else trade_outcomes.average_rr,
            average_setup_score=None if trade_outcomes is None else trade_outcomes.average_setup_score,
            long_count=direction_counts.get("LONG", 0),
            long_pnl=direction_pnl.get("LONG", 0.0),
            short_count=direction_counts.get("SHORT", 0),
            short_pnl=direction_pnl.get("SHORT", 0.0),
            profit_factor=profit_factor,
            average_win=None if trade_outcomes is None else trade_outcomes.average_win,
            average_loss=None if trade_outcomes is None else trade_outcomes.average_loss,
            largest_win=None if trade_outcomes is None else trade_outcomes.largest_win,
            largest_loss=None if trade_outcomes is None else trade_outcomes.largest_loss,
            fast_losses=0 if sl_tp is None else sl_tp.fast_loss_count,
            no_followthrough_losses=0 if sl_tp is None else sl_tp.no_follow_through_loss_count,
            high_rr_losses=0 if sl_tp is None else sl_tp.high_rr_loss_count,
            next_candle_continuation=0 if followthrough is None else followthrough.next_candle_continuation_count,
            next_candle_rejection=0 if followthrough is None else followthrough.next_candle_rejection_count,
            elapsed_seconds=elapsed_seconds,
        )

    def _profit_factor(self, trades) -> float | None:
        closed_pnls = [
            float(pnl)
            for trade in trades
            if (pnl := self._closed_pnl(trade)) is not None
        ]
        if not closed_pnls:
            return None
        gross_profit = sum(pnl for pnl in closed_pnls if pnl > 0)
        gross_loss_abs = abs(sum(pnl for pnl in closed_pnls if pnl < 0))
        if gross_loss_abs > 0:
            return gross_profit / gross_loss_abs
        if gross_profit > 0:
            return None
        return None

    def _closed_pnl(self, trade) -> float | None:
        result = getattr(trade, "result", None)
        if result in ("WIN", "LOSS"):
            return getattr(trade, "pnl", None)
        status = getattr(trade, "paper_trade_status", None)
        if status in ("PAPER_CLOSED_TP", "PAPER_CLOSED_SL"):
            return getattr(trade, "paper_pnl", None)
        return None

    def _trade_records(self, result: RollingBacktestResult) -> list:
        if result.trade_outcome_diagnostics is not None:
            return result.trade_outcome_diagnostics.trades
        return result.trade_outcome_contexts

    def _direction_counts(self, result: RollingBacktestResult) -> dict[str, int]:
        if result.trade_outcome_diagnostics is not None:
            return result.trade_outcome_diagnostics.trades_by_direction()
        counts: dict[str, int] = {}
        for context in result.trade_outcome_contexts:
            direction = self._direction_from_context(context)
            if direction is None:
                continue
            counts[direction] = counts.get(direction, 0) + 1
        return counts

    def _direction_pnl(self, result: RollingBacktestResult) -> dict[str, float]:
        if result.trade_outcome_diagnostics is not None:
            return result.trade_outcome_diagnostics.pnl_by_direction()
        pnl: dict[str, float] = {}
        for context in result.trade_outcome_contexts:
            direction = self._direction_from_context(context)
            if direction is None:
                continue
            pnl[direction] = pnl.get(direction, 0.0) + float(getattr(context, "paper_pnl", 0) or 0)
        return pnl

    def _direction_from_context(self, context) -> str | None:
        direction = getattr(context, "paper_trade_direction", None)
        if direction == "BULLISH":
            return "LONG"
        if direction == "BEARISH":
            return "SHORT"
        if direction in ("LONG", "SHORT"):
            return direction
        return None

    def _rolling_progress_callback(
        self,
        progress_callback: ComparisonProgressCallback | None,
        spec: StrategyConfigSpec,
        index: int,
        total: int,
    ):
        if progress_callback is None:
            return None

        def callback(payload: dict) -> None:
            progress_callback(
                {
                    "event": "rolling_progress",
                    "index": index,
                    "total": total,
                    "strategy": spec.name,
                    **payload,
                }
            )

        return callback
