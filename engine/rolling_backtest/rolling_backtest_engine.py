from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd

from engine.backtest.backtest_diagnostics_engine import BacktestDiagnosticsEngine
from engine.backtest.backtest_engine import BacktestEngine
from engine.backtest.cost_diagnostics_engine import CostDiagnosticsEngine
from engine.backtest.entry_followthrough_diagnostics_engine import EntryFollowthroughDiagnosticsEngine
from engine.backtest.sl_tp_outcome_diagnostics_engine import SLTPOutcomeDiagnosticsEngine
from engine.backtest.trade_outcome_diagnostics_engine import TradeOutcomeDiagnosticsEngine
from engine.backtest.virtual_exit_diagnostics_engine import VirtualExitDiagnosticsEngine
from engine.diagnostics.regime_direction_diagnostics_engine import RegimeDirectionDiagnosticsEngine
from engine.ict_engine import ICTEngine
from engine.rolling_backtest.trade_state_manager import TradeStateManager
from models.engine_config import EngineConfig
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
        config: EngineConfig | None = None,
        strategy_profile: str | None = None,
        dealing_range_mode: str | None = None,
        exit_mode: str | None = None,
        min_risk_reward: float | None = None,
        direction_mode: str | None = None,
        auto_trend_fallback: str | None = None,
        regime_mode: str | None = None,
        regime_lookback: int | None = None,
        regime_threshold_pct: float | None = None,
        regime_fallback: str | None = None,
        direction_quality_mode: str | None = None,
        strict_long_require_regime_known: bool | None = None,
        strict_long_block_unknown_regime: bool | None = None,
        strict_long_require_regime_bullish: bool | None = None,
        strict_long_require_displacement: bool | None = None,
        strict_long_min_setup_score: int | None = None,
        strict_short_require_regime_known: bool | None = None,
        strict_short_block_unknown_regime: bool | None = None,
        strict_short_require_regime_bearish: bool | None = None,
        strict_short_require_displacement: bool | None = None,
        strict_short_min_setup_score: int | None = None,
        cost_model: str | None = None,
        commission_pct: float | None = None,
        slippage_pct: float | None = None,
        spread_pct: float | None = None,
        enable_diagnostics: bool = True,
    ):
        self.config = config if config is not None else EngineConfig()
        if strategy_profile is not None:
            if strategy_profile not in EngineConfig.VALID_STRATEGY_PROFILES:
                raise ValueError(f"Unsupported strategy profile: {strategy_profile}")
            self.config.strategy_profile = strategy_profile
        if dealing_range_mode is not None:
            if dealing_range_mode not in EngineConfig.VALID_DEALING_RANGE_MODES:
                raise ValueError(f"Unsupported dealing range mode: {dealing_range_mode}")
            self.config.dealing_range_mode = dealing_range_mode
        if exit_mode is not None:
            if exit_mode not in EngineConfig.VALID_EXIT_MODES:
                raise ValueError(f"Unsupported exit mode: {exit_mode}")
            self.config.exit_mode = exit_mode
        if min_risk_reward is not None:
            if min_risk_reward <= 0:
                raise ValueError(f"Unsupported min risk reward: {min_risk_reward}")
            self.config.min_risk_reward = min_risk_reward
        if direction_mode is not None:
            if direction_mode not in EngineConfig.VALID_DIRECTION_MODES:
                raise ValueError(f"Unsupported direction mode: {direction_mode}")
            self.config.direction_mode = direction_mode
        if auto_trend_fallback is not None:
            if auto_trend_fallback not in EngineConfig.VALID_AUTO_TREND_FALLBACKS:
                raise ValueError(f"Unsupported auto trend fallback: {auto_trend_fallback}")
            self.config.auto_trend_fallback = auto_trend_fallback
        if regime_mode is not None:
            if regime_mode not in EngineConfig.VALID_REGIME_MODES:
                raise ValueError(f"Unsupported regime mode: {regime_mode}")
            self.config.regime_mode = regime_mode
        if regime_lookback is not None:
            if regime_lookback <= 0:
                raise ValueError(f"Unsupported regime lookback: {regime_lookback}")
            self.config.regime_lookback = regime_lookback
        if regime_threshold_pct is not None:
            if regime_threshold_pct < 0:
                raise ValueError(f"Unsupported regime threshold pct: {regime_threshold_pct}")
            self.config.regime_threshold_pct = regime_threshold_pct
        if regime_fallback is not None:
            if regime_fallback not in EngineConfig.VALID_REGIME_FALLBACKS:
                raise ValueError(f"Unsupported regime fallback: {regime_fallback}")
            self.config.regime_fallback = regime_fallback
        if direction_quality_mode is not None:
            if direction_quality_mode not in EngineConfig.VALID_DIRECTION_QUALITY_MODES:
                raise ValueError(f"Unsupported direction quality mode: {direction_quality_mode}")
            self.config.direction_quality_mode = direction_quality_mode
        for field_name, value in {
            "strict_long_require_regime_known": strict_long_require_regime_known,
            "strict_long_block_unknown_regime": strict_long_block_unknown_regime,
            "strict_long_require_regime_bullish": strict_long_require_regime_bullish,
            "strict_long_require_displacement": strict_long_require_displacement,
            "strict_short_require_regime_known": strict_short_require_regime_known,
            "strict_short_block_unknown_regime": strict_short_block_unknown_regime,
            "strict_short_require_regime_bearish": strict_short_require_regime_bearish,
            "strict_short_require_displacement": strict_short_require_displacement,
        }.items():
            if value is not None:
                setattr(self.config, field_name, value)
        for field_name, value in {
            "strict_long_min_setup_score": strict_long_min_setup_score,
            "strict_short_min_setup_score": strict_short_min_setup_score,
        }.items():
            if value is not None:
                if value < 0:
                    raise ValueError(f"Unsupported {field_name}: {value}")
                setattr(self.config, field_name, value)
        if cost_model is not None:
            if cost_model not in EngineConfig.VALID_COST_MODELS:
                raise ValueError(f"Unsupported cost model: {cost_model}")
            self.config.cost_model = cost_model
        for field_name, value in {
            "commission_pct": commission_pct,
            "slippage_pct": slippage_pct,
            "spread_pct": spread_pct,
        }.items():
            if value is not None:
                if value < 0:
                    raise ValueError(f"Unsupported {field_name}: {value}")
                setattr(self.config, field_name, value)
        self.ict_engine = ict_engine if ict_engine is not None else ICTEngine(config=self.config)
        self.min_candles = min_candles
        self.stateful = stateful
        self.progress_callback = progress_callback
        self.progress_every = progress_every
        self.max_windows = max_windows
        self.enable_diagnostics = enable_diagnostics
        self.backtest_engine = BacktestEngine()
        self.diagnostics_engine = BacktestDiagnosticsEngine()
        self.trade_outcome_diagnostics_engine = TradeOutcomeDiagnosticsEngine()
        self.sl_tp_outcome_diagnostics_engine = SLTPOutcomeDiagnosticsEngine()
        self.entry_followthrough_diagnostics_engine = EntryFollowthroughDiagnosticsEngine()
        self.virtual_exit_diagnostics_engine = VirtualExitDiagnosticsEngine()
        self.regime_direction_diagnostics_engine = RegimeDirectionDiagnosticsEngine()
        self.cost_diagnostics_engine = CostDiagnosticsEngine()
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
        fallback_count = self._range_mode_fallback_count(diagnostics_source)
        exit_mode_fallback_counts = self._exit_mode_fallback_counts(diagnostics_source)
        direction_mode_fallback_counts = self._direction_mode_fallback_counts(diagnostics_source)
        diagnostics = None
        diagnostics_windows_analyzed = 0
        trade_outcomes = None
        sl_tp_outcomes = None
        entry_followthrough = None
        virtual_exit = None
        regime_direction = None
        cost_diagnostics = None
        if self.enable_diagnostics:
            diagnostics = self.diagnostics_engine.summarize_contexts(diagnostics_source)
            diagnostics_windows_analyzed = diagnostics.windows_analyzed
            trade_outcomes = self.trade_outcome_diagnostics_engine.summarize_contexts(contexts)
            sl_tp_outcomes = self.sl_tp_outcome_diagnostics_engine.summarize_trade_contexts(contexts)
            entry_followthrough = self.entry_followthrough_diagnostics_engine.summarize_trade_contexts(contexts)
            virtual_exit = self.virtual_exit_diagnostics_engine.summarize_trade_contexts(contexts)
        else:
            trade_outcomes = self.trade_outcome_diagnostics_engine.summarize_contexts(contexts)
        regime_direction = self.regime_direction_diagnostics_engine.summarize_trades(
            [] if trade_outcomes is None else trade_outcomes.trades
        )
        cost_diagnostics = self.cost_diagnostics_engine.summarize_contexts(contexts, self.config)
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
            diagnostics_windows_analyzed=diagnostics_windows_analyzed,
            strategy_profile=self.config.strategy_profile,
            dealing_range_mode=self.config.dealing_range_mode,
            range_mode_fallback_count=fallback_count,
            exit_mode=self.config.exit_mode,
            exit_mode_fallback_counts=exit_mode_fallback_counts,
            min_risk_reward=self.config.min_risk_reward,
            direction_mode=self.config.direction_mode,
            auto_trend_fallback=self.config.auto_trend_fallback,
            regime_mode=self.config.regime_mode,
            regime_lookback=self.config.regime_lookback,
            regime_threshold_pct=self.config.regime_threshold_pct,
            regime_fallback=self.config.regime_fallback,
            direction_quality_mode=self.config.direction_quality_mode,
            strict_long_require_regime_known=self.config.strict_long_require_regime_known,
            strict_long_block_unknown_regime=self.config.strict_long_block_unknown_regime,
            strict_long_require_regime_bullish=self.config.strict_long_require_regime_bullish,
            strict_long_require_displacement=self.config.strict_long_require_displacement,
            strict_long_min_setup_score=self.config.strict_long_min_setup_score,
            strict_short_require_regime_known=self.config.strict_short_require_regime_known,
            strict_short_block_unknown_regime=self.config.strict_short_block_unknown_regime,
            strict_short_require_regime_bearish=self.config.strict_short_require_regime_bearish,
            strict_short_require_displacement=self.config.strict_short_require_displacement,
            strict_short_min_setup_score=self.config.strict_short_min_setup_score,
            direction_mode_fallback_counts=direction_mode_fallback_counts,
            trade_outcome_diagnostics=trade_outcomes,
            sl_tp_outcome_diagnostics=sl_tp_outcomes,
            entry_followthrough_diagnostics=entry_followthrough,
            virtual_exit_diagnostics=virtual_exit,
            regime_direction_diagnostics=regime_direction,
            cost_diagnostics=cost_diagnostics,
            gross_net_pnl=summary.net_pnl,
            net_pnl_after_costs=cost_diagnostics.net_pnl_after_costs,
            total_cost=cost_diagnostics.total_cost,
            trade_outcome_contexts=contexts,
        )

    def _range_mode_fallback_count(self, contexts: list[MarketContext]) -> int:
        return sum(
            1
            for context in contexts
            if getattr(context, "dealing_range_mode_requested", self.config.dealing_range_mode)
            != getattr(context, "dealing_range_mode_applied", self.config.dealing_range_mode)
        )

    def _exit_mode_fallback_counts(self, contexts: list[MarketContext]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for context in contexts:
            reason = getattr(context, "exit_mode_fallback_reason", None)
            if reason is None:
                continue
            counts[reason] = counts.get(reason, 0) + 1
        return counts

    def _direction_mode_fallback_counts(self, contexts: list[MarketContext]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for context in contexts:
            reason = getattr(context, "direction_mode_fallback_reason", None)
            if reason is None:
                continue
            counts[reason] = counts.get(reason, 0) + 1
        return counts
