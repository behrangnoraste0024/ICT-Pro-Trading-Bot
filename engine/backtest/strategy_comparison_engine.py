from __future__ import annotations

from data.historical_data_utils import load_candles_json
from engine.rolling_backtest.rolling_backtest_engine import RollingBacktestEngine
from models.engine_config import EngineConfig
from models.rolling_backtest_result import RollingBacktestResult
from models.strategy_comparison import StrategyComparisonReport, StrategyComparisonRow, StrategyConfigSpec


def build_default_strategy_specs() -> list[StrategyConfigSpec]:
    return [
        StrategyConfigSpec("current_external|original|min_rr=2.0", "current_external", "original", 2.0),
        StrategyConfigSpec("current_external|fixed_1_5r|min_rr=1.5", "current_external", "fixed_1_5r", 1.5),
        StrategyConfigSpec("recent_50|original|min_rr=2.0", "recent_50", "original", 2.0),
        StrategyConfigSpec("recent_50|fixed_1r|min_rr=1.0", "recent_50", "fixed_1r", 1.0),
        StrategyConfigSpec("recent_50|fixed_1_5r|min_rr=1.5", "recent_50", "fixed_1_5r", 1.5),
        StrategyConfigSpec("recent_50|fixed_2r|min_rr=2.0", "recent_50", "fixed_2r", 2.0),
        StrategyConfigSpec("recent_50|fixed_3r|min_rr=3.0", "recent_50", "fixed_3r", 3.0),
    ]


def build_exit_modes_recent_50_specs() -> list[StrategyConfigSpec]:
    return [
        StrategyConfigSpec("recent_50|original|min_rr=2.0", "recent_50", "original", 2.0),
        StrategyConfigSpec("recent_50|fixed_1r|min_rr=1.0", "recent_50", "fixed_1r", 1.0),
        StrategyConfigSpec("recent_50|fixed_1_5r|min_rr=1.5", "recent_50", "fixed_1_5r", 1.5),
        StrategyConfigSpec("recent_50|fixed_2r|min_rr=2.0", "recent_50", "fixed_2r", 2.0),
        StrategyConfigSpec("recent_50|fixed_3r|min_rr=3.0", "recent_50", "fixed_3r", 3.0),
    ]


def build_current_external_only_specs() -> list[StrategyConfigSpec]:
    return [
        StrategyConfigSpec("current_external|original|min_rr=2.0", "current_external", "original", 2.0),
        StrategyConfigSpec("current_external|fixed_1r|min_rr=1.0", "current_external", "fixed_1r", 1.0),
        StrategyConfigSpec("current_external|fixed_1_5r|min_rr=1.5", "current_external", "fixed_1_5r", 1.5),
        StrategyConfigSpec("current_external|fixed_2r|min_rr=2.0", "current_external", "fixed_2r", 2.0),
    ]


class StrategyComparisonEngine:
    def run_comparison(
        self,
        fixture_path: str,
        strategy_specs: list[StrategyConfigSpec],
        min_candles: int = 50,
        progress_every: int = 0,
        max_windows: int | None = None,
    ) -> StrategyComparisonReport:
        candles = load_candles_json(fixture_path)
        rows: list[StrategyComparisonRow] = []
        for spec in strategy_specs:
            result = RollingBacktestEngine(
                min_candles=min_candles,
                progress_every=progress_every,
                max_windows=max_windows,
                config=EngineConfig(
                    dealing_range_mode=spec.dealing_range_mode,
                    exit_mode=spec.exit_mode,
                    min_risk_reward=spec.min_risk_reward,
                ),
            ).run(candles)
            rows.append(self.row_from_result(spec, result))

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
    ) -> StrategyComparisonRow:
        return self.run_comparison(
            fixture_path=fixture_path,
            strategy_specs=[strategy_spec],
            min_candles=min_candles,
            progress_every=progress_every,
            max_windows=max_windows,
        ).strategies[0]

    def row_from_result(self, spec: StrategyConfigSpec, result: RollingBacktestResult) -> StrategyComparisonRow:
        trade_outcomes = result.trade_outcome_diagnostics
        sl_tp = result.sl_tp_outcome_diagnostics
        followthrough = result.entry_followthrough_diagnostics
        trades = [] if trade_outcomes is None else trade_outcomes.trades
        direction_counts = {} if trade_outcomes is None else trade_outcomes.trades_by_direction()
        direction_pnl = {} if trade_outcomes is None else trade_outcomes.pnl_by_direction()
        profit_factor = self._profit_factor(trades)

        return StrategyComparisonRow(
            strategy_name=spec.name,
            dealing_range_mode=spec.dealing_range_mode,
            exit_mode=spec.exit_mode,
            min_risk_reward=spec.min_risk_reward,
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
        )

    def _profit_factor(self, trades) -> float | None:
        closed_pnls = [float(trade.pnl) for trade in trades if trade.pnl is not None and trade.result in ("WIN", "LOSS")]
        if not closed_pnls:
            return None
        gross_profit = sum(pnl for pnl in closed_pnls if pnl > 0)
        gross_loss_abs = abs(sum(pnl for pnl in closed_pnls if pnl < 0))
        if gross_loss_abs > 0:
            return gross_profit / gross_loss_abs
        if gross_profit > 0:
            return None
        return None
