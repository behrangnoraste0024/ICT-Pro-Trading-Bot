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


def build_trend_direction_recent_50_fixed_1_5r_specs() -> list[StrategyConfigSpec]:
    return [
        _spec("recent_50", "fixed_1_5r", 1.5, "all"),
        _spec("recent_50", "fixed_1_5r", 1.5, "short_only"),
        _spec("recent_50", "fixed_1_5r", 1.5, "long_only"),
        _spec("recent_50", "fixed_1_5r", 1.5, "auto_trend", "all"),
        _spec("recent_50", "fixed_1_5r", 1.5, "auto_trend", "block"),
    ]


def build_regime_direction_recent_50_fixed_1_5r_specs() -> list[StrategyConfigSpec]:
    return [
        _spec("recent_50", "fixed_1_5r", 1.5, "all"),
        _spec("recent_50", "fixed_1_5r", 1.5, "short_only"),
        _spec("recent_50", "fixed_1_5r", 1.5, "long_only"),
        _spec("recent_50", "fixed_1_5r", 1.5, "auto_trend", "all"),
        _spec("recent_50", "fixed_1_5r", 1.5, "regime_trend", "all", "rolling_return", 100, 0.0, "all"),
        _spec("recent_50", "fixed_1_5r", 1.5, "regime_trend", "all", "rolling_return", 200, 0.0, "all"),
        _spec("recent_50", "fixed_1_5r", 1.5, "regime_trend", "all", "rolling_return", 300, 0.0, "all"),
        _spec("recent_50", "fixed_1_5r", 1.5, "regime_trend", "all", "rolling_return", 200, 0.01, "all"),
        _spec("recent_50", "fixed_1_5r", 1.5, "regime_trend", "all", "rolling_return", 200, 0.0, "block"),
    ]


def build_long_strict_recent_50_fixed_1_5r_specs() -> list[StrategyConfigSpec]:
    presets = [
        ("all", "off", "none"),
        ("short_only", "off", "none"),
        ("all", "long_strict", "regime_known"),
        ("all", "long_strict", "regime_bullish"),
        ("all", "long_strict", "displacement"),
        ("all", "long_strict", "score100"),
        ("all", "long_strict", "regime_known_displacement"),
        ("all", "long_strict", "regime_bullish_displacement"),
        ("all", "long_strict", "regime_known_displacement_score100"),
        ("all", "long_strict", "regime_bullish_displacement_score100"),
    ]
    return [
        _spec("recent_50", "fixed_1_5r", 1.5, direction_mode, direction_quality_mode=dq_mode, strict_long_preset=preset)
        for direction_mode, dq_mode, preset in presets
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
    auto_trend_fallback: str = "all",
    regime_mode: str = "rolling_return",
    regime_lookback: int = 200,
    regime_threshold_pct: float = 0.0,
    regime_fallback: str = "all",
    direction_quality_mode: str = "off",
    strict_long_preset: str = "none",
) -> StrategyConfigSpec:
    name = f"{dealing_range_mode}|{exit_mode}|min_rr={min_risk_reward}|dir={direction_mode}"
    if direction_mode == "auto_trend":
        name = f"{name}|trend_fallback={auto_trend_fallback}"
    if direction_mode == "regime_trend":
        name = (
            f"{name}|regime={regime_mode}|lookback={regime_lookback}|"
            f"thr={regime_threshold_pct}|regime_fb={regime_fallback}"
        )
    preset_config = direction_quality_preset_config(strict_long_preset)
    if direction_quality_mode != "off":
        name = f"{name}|dq={direction_quality_mode}|long_preset={strict_long_preset}"
    return StrategyConfigSpec(
        name,
        dealing_range_mode,
        exit_mode,
        min_risk_reward,
        direction_mode,
        auto_trend_fallback,
        regime_mode,
        regime_lookback,
        regime_threshold_pct,
        regime_fallback,
        direction_quality_mode,
        strict_long_preset,
        **preset_config,
    )


def direction_quality_preset_config(strict_long_preset: str) -> dict:
    valid = {
        "none",
        "regime_known",
        "regime_bullish",
        "displacement",
        "score100",
        "regime_known_displacement",
        "regime_bullish_displacement",
        "regime_known_score100",
        "regime_bullish_score100",
        "regime_known_displacement_score100",
        "regime_bullish_displacement_score100",
    }
    if strict_long_preset not in valid:
        raise ValueError(f"Unsupported strict long preset: {strict_long_preset}")

    return {
        "strict_long_require_regime_known": "regime_known" in strict_long_preset,
        "strict_long_require_regime_bullish": "regime_bullish" in strict_long_preset,
        "strict_long_require_displacement": "displacement" in strict_long_preset,
        "strict_long_min_setup_score": 100 if "score100" in strict_long_preset else None,
    }


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
                    auto_trend_fallback=spec.auto_trend_fallback,
                    regime_mode=spec.regime_mode,
                    regime_lookback=spec.regime_lookback,
                    regime_threshold_pct=spec.regime_threshold_pct,
                    regime_fallback=spec.regime_fallback,
                    direction_quality_mode=spec.direction_quality_mode,
                    strict_long_require_regime_known=spec.strict_long_require_regime_known,
                    strict_long_block_unknown_regime=spec.strict_long_block_unknown_regime,
                    strict_long_require_regime_bullish=spec.strict_long_require_regime_bullish,
                    strict_long_require_displacement=spec.strict_long_require_displacement,
                    strict_long_min_setup_score=spec.strict_long_min_setup_score,
                    strict_short_require_regime_known=spec.strict_short_require_regime_known,
                    strict_short_block_unknown_regime=spec.strict_short_block_unknown_regime,
                    strict_short_require_regime_bearish=spec.strict_short_require_regime_bearish,
                    strict_short_require_displacement=spec.strict_short_require_displacement,
                    strict_short_min_setup_score=spec.strict_short_min_setup_score,
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
        regime_direction = result.regime_direction_diagnostics
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
            auto_trend_fallback=spec.auto_trend_fallback,
            regime_mode=spec.regime_mode,
            regime_lookback=spec.regime_lookback,
            regime_threshold_pct=spec.regime_threshold_pct,
            regime_fallback=spec.regime_fallback,
            direction_quality_mode=spec.direction_quality_mode,
            strict_long_preset=spec.strict_long_preset,
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
            long_in_bearish_count=0 if regime_direction is None else regime_direction.long_in_bearish_count,
            long_in_bearish_pnl=0.0 if regime_direction is None else regime_direction.long_in_bearish_pnl,
            short_in_bullish_count=0 if regime_direction is None else regime_direction.short_in_bullish_count,
            short_in_bullish_pnl=0.0 if regime_direction is None else regime_direction.short_in_bullish_pnl,
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
