from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from pathlib import Path

from data.historical_data_utils import load_candles_json
from engine.backtest.strategy_comparison_engine import (
    StrategyComparisonEngine,
    build_recommended_decision_profile_with_cost_specs,
)
from engine.diagnostics.backtest_cache_engine import BacktestCacheEngine
from engine.diagnostics.recommended_profile_validation_engine import RecommendedProfileValidationEngine
from engine.diagnostics.walk_forward_validation_engine import WalkForwardValidationEngine
from engine.rolling_backtest.rolling_backtest_engine import RollingBacktestEngine
from models.engine_config import EngineConfig
from models.multi_sample_validation import (
    MultiSampleDefinition,
    MultiSampleValidationResult,
    MultiSampleValidationRow,
)
from models.strategy_comparison import StrategyConfigSpec


DEFAULT_MULTI_SAMPLE_DEFINITIONS = [
    MultiSampleDefinition("btcusdt_15m_1000", "data/historical/btcusdt_15m_1000.json", "BTC/USDT", "15m"),
    MultiSampleDefinition("btcusdt_1h_1000", "data/historical/btcusdt_1h_1000.json", "BTC/USDT", "1h"),
    MultiSampleDefinition("ethusdt_15m_1000", "data/historical/ethusdt_15m_1000.json", "ETH/USDT", "15m"),
    MultiSampleDefinition("ethusdt_1h_1000", "data/historical/ethusdt_1h_1000.json", "ETH/USDT", "1h"),
]


class MultiSampleValidationEngine:
    def __init__(
        self,
        comparison_engine=None,
        recommendation_engine=None,
        walk_forward_engine=None,
        candles_loader: Callable[[str], object] = load_candles_json,
        rolling_engine_factory: Callable[..., RollingBacktestEngine] = RollingBacktestEngine,
        path_exists: Callable[[str], bool] | None = None,
        cache_engine: BacktestCacheEngine | None = None,
    ) -> None:
        self.comparison_engine = comparison_engine or StrategyComparisonEngine()
        self.recommendation_engine = recommendation_engine or RecommendedProfileValidationEngine()
        self.walk_forward_engine = walk_forward_engine or WalkForwardValidationEngine()
        self.candles_loader = candles_loader
        self.rolling_engine_factory = rolling_engine_factory
        self.path_exists = path_exists or (lambda path: Path(path).exists())
        self.cache_engine = cache_engine or BacktestCacheEngine()

    def validate(
        self,
        samples: Iterable[MultiSampleDefinition] | None = None,
        strategy_specs: list[StrategyConfigSpec] | None = None,
        min_candles: int = 50,
        sort_by: str = "net_pnl_after_costs",
        recommended_profile: str = "balanced_smc_decision_065",
        fast: bool = False,
        max_windows: int | None = None,
        progress_callback: Callable[[dict], None] | None = None,
        use_cache: bool = False,
        refresh_cache: bool = False,
        cache_dir: str = ".cache/backtests",
    ) -> MultiSampleValidationResult:
        selected_samples = list(DEFAULT_MULTI_SAMPLE_DEFINITIONS if samples is None else samples)
        specs = build_recommended_decision_profile_with_cost_specs() if strategy_specs is None else strategy_specs
        self._emit(
            progress_callback,
            {
                "event": "start",
                "samples": len(selected_samples),
                "strategy_set": "recommended_decision_profiles_with_costs",
                "sort_by": sort_by,
            },
        )
        rows = [
            self._validate_sample(
                sample,
                specs,
                min_candles=min_candles,
                sort_by=sort_by,
                recommended_profile=recommended_profile,
                fast=fast,
                max_windows=max_windows,
                progress_callback=progress_callback,
                use_cache=use_cache,
                refresh_cache=refresh_cache,
                cache_dir=cache_dir,
            )
            for sample in selected_samples
        ]
        result = self._result(rows, recommended_profile, sort_by)
        self._emit(
            progress_callback,
            {
                "event": "complete",
                "completed": result.completed_samples,
                "skipped": result.skipped_samples,
                "errors": result.error_samples,
            },
        )
        return result

    def _validate_sample(
        self,
        sample: MultiSampleDefinition,
        specs: list[StrategyConfigSpec],
        min_candles: int,
        sort_by: str,
        recommended_profile: str,
        fast: bool,
        max_windows: int | None,
        progress_callback: Callable[[dict], None] | None,
        use_cache: bool,
        refresh_cache: bool,
        cache_dir: str,
    ) -> MultiSampleValidationRow:
        started_at = time.perf_counter()
        if not self.path_exists(sample.fixture_path):
            self._emit(
                progress_callback,
                {
                    "event": "skip_missing",
                    "sample": sample.name,
                    "fixture": sample.fixture_path,
                },
            )
            row = self._skipped_row(sample, started_at)
            self._emit_finished(progress_callback, row)
            return row
        try:
            cache_key = self.cache_engine.build_key(
                fixture_path=sample.fixture_path,
                strategy_set="multi_sample_validation:recommended_decision_profiles_with_costs",
                sort_by=sort_by,
                min_candles=min_candles,
                max_windows=max_windows,
                fast=fast,
                profile_version=BacktestCacheEngine.SCHEMA_VERSION,
            )
            if use_cache and not refresh_cache:
                cached = self.cache_engine.read(cache_dir, cache_key)
                if cached.hit and cached.payload is not None:
                    row = MultiSampleValidationRow(**cached.payload["multi_sample_row"])
                    self._apply_cache_diagnostics(row, cached.diagnostics)
                    self._emit(
                        progress_callback,
                        {
                            "event": "cache_hit",
                            "cache_path": cached.cache_path,
                            "cache_key_hash": row.cache_key_hash,
                            "cache_age_seconds": row.cache_age_seconds,
                            "cache_read_elapsed_seconds": row.cache_read_elapsed_seconds,
                            "original_elapsed_seconds": row.original_elapsed_seconds,
                            "estimated_saved_seconds": row.estimated_saved_seconds,
                        },
                    )
                    self._emit_finished(progress_callback, row)
                    return row
                self._emit(progress_callback, {"event": "cache_miss", "cache_key_hash": self.cache_engine.cache_key_hash(cache_key)})
            elif refresh_cache:
                self._emit(progress_callback, {"event": "cache_refresh", "cache_key_hash": self.cache_engine.cache_key_hash(cache_key)})
            self._emit(
                progress_callback,
                {
                    "event": "sample_start",
                    "sample": sample.name,
                    "symbol": sample.symbol,
                    "timeframe": sample.timeframe,
                    "fixture": sample.fixture_path,
                },
            )
            self._emit(
                progress_callback,
                {
                    "event": "running_validation",
                    "sample": sample.name,
                },
            )
            comparison = self.comparison_engine.run_comparison(
                fixture_path=sample.fixture_path,
                strategy_specs=specs,
                min_candles=min_candles,
                progress_every=0,
                max_windows=max_windows,
                enable_diagnostics=not fast,
            )
            recommendation = self.recommendation_engine.validate(comparison)
            selected = recommendation.selected
            if selected is None:
                return self._failed_row(sample, started_at, "recommendation missing")
            spec = self._selected_spec(specs, selected.recommended_strategy_name, selected.recommended_profile, recommended_profile)
            walk_forward = self._walk_forward(sample.fixture_path, spec, selected.score_threshold, min_candles, fast, max_windows)
            status = self._status_from_walk_forward(walk_forward.validation_status)
            row = MultiSampleValidationRow(
                sample_name=sample.name,
                fixture_path=sample.fixture_path,
                symbol=sample.symbol,
                timeframe=sample.timeframe,
                status=status,
                recommended_profile=selected.recommended_profile,
                recommended_strategy=selected.recommended_strategy_name,
                score_threshold=selected.score_threshold,
                total_trades=walk_forward.total_trades,
                wins=walk_forward.wins,
                losses=walk_forward.losses,
                win_rate=walk_forward.win_rate,
                gross_net_pnl=walk_forward.gross_net_pnl,
                total_cost=walk_forward.total_cost,
                net_pnl_after_costs=walk_forward.net_pnl_after_costs,
                max_drawdown=walk_forward.max_drawdown,
                profitable_segments=walk_forward.profitable_segments,
                losing_segments=walk_forward.losing_segments,
                empty_segments=walk_forward.empty_segments,
                worst_segment_net_pnl_after_costs=walk_forward.worst_segment_net_pnl_after_costs,
                validation_status=walk_forward.validation_status,
                improvement_vs_baseline=selected.improvement_vs_baseline,
                elapsed_seconds=time.perf_counter() - started_at,
            )
            row.original_elapsed_seconds = row.elapsed_seconds
            if use_cache or refresh_cache:
                written = self.cache_engine.write(
                    cache_dir,
                    cache_key,
                    {"multi_sample_row": row.to_dict()},
                    compute_elapsed_seconds=row.elapsed_seconds,
                    cache_status="REFRESH" if refresh_cache else "WRITE",
                )
                if written.error_message is None:
                    self._apply_cache_diagnostics(row, written.diagnostics)
                    self._emit(
                        progress_callback,
                        {
                            "event": "cache_wrote",
                            "cache_path": written.cache_path,
                            "cache_key_hash": row.cache_key_hash,
                            "current_compute_elapsed_seconds": row.original_elapsed_seconds,
                        },
                    )
            self._emit_finished(progress_callback, row)
            return row
        except Exception as exc:
            row = MultiSampleValidationRow(
                sample_name=sample.name,
                fixture_path=sample.fixture_path,
                symbol=sample.symbol,
                timeframe=sample.timeframe,
                status="ERROR",
                elapsed_seconds=time.perf_counter() - started_at,
                error_message=str(exc),
            )
            self._emit_finished(progress_callback, row)
            return row

    def _selected_spec(
        self,
        specs: list[StrategyConfigSpec],
        strategy_name: str | None,
        profile: str | None,
        recommended_profile: str,
    ) -> StrategyConfigSpec:
        spec = next((item for item in specs if item.name == strategy_name), None)
        if spec is not None:
            return spec
        spec = next((item for item in specs if item.strategy_profile == profile), None)
        if spec is not None:
            return spec
        spec = next((item for item in specs if item.strategy_profile == recommended_profile), None)
        if spec is not None:
            return spec
        raise ValueError("recommended strategy spec not found")

    def _walk_forward(
        self,
        fixture_path: str,
        spec: StrategyConfigSpec,
        selected_threshold: float | None,
        min_candles: int,
        fast: bool,
        max_windows: int | None,
    ):
        candles = self.candles_loader(fixture_path)
        rolling_result = self.rolling_engine_factory(
            min_candles=min_candles,
            progress_every=0,
            max_windows=max_windows,
            enable_diagnostics=not fast,
            config=self._config_from_spec(spec),
        ).run(candles)
        return self.walk_forward_engine.validate_contexts(
            rolling_result.trade_outcome_contexts,
            rolling_result.cost_diagnostics,
            profile=spec.strategy_profile,
            strategy_name=spec.name,
            score_threshold=spec.decision_score_threshold if spec.decision_score_threshold is not None else selected_threshold,
        )

    def _config_from_spec(self, spec: StrategyConfigSpec) -> EngineConfig:
        return EngineConfig(
            strategy_profile=spec.strategy_profile,
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
            cost_model=spec.cost_model,
            commission_pct=spec.commission_pct,
            slippage_pct=spec.slippage_pct,
            spread_pct=spec.spread_pct,
            decision_filter_mode=spec.decision_filter_mode,
            decision_score_threshold=spec.decision_score_threshold,
        )

    def _status_from_walk_forward(self, validation_status: str) -> str:
        if validation_status == "PASS":
            return "PASSED"
        if validation_status == "WARNING":
            return "WARNING"
        return "FAILED"

    def _skipped_row(self, sample: MultiSampleDefinition, started_at: float) -> MultiSampleValidationRow:
        return MultiSampleValidationRow(
            sample_name=sample.name,
            fixture_path=sample.fixture_path,
            symbol=sample.symbol,
            timeframe=sample.timeframe,
            status="SKIPPED_MISSING_FILE",
            elapsed_seconds=time.perf_counter() - started_at,
        )

    def _failed_row(self, sample: MultiSampleDefinition, started_at: float, message: str) -> MultiSampleValidationRow:
        return MultiSampleValidationRow(
            sample_name=sample.name,
            fixture_path=sample.fixture_path,
            symbol=sample.symbol,
            timeframe=sample.timeframe,
            status="FAILED",
            elapsed_seconds=time.perf_counter() - started_at,
            error_message=message,
        )

    def _result(
        self,
        rows: list[MultiSampleValidationRow],
        recommended_profile: str,
        sort_by: str,
    ) -> MultiSampleValidationResult:
        completed = [row for row in rows if row.status not in ("SKIPPED_MISSING_FILE", "ERROR")]
        return MultiSampleValidationResult(
            rows=rows,
            total_samples=len(rows),
            completed_samples=len(completed),
            passed_samples=sum(1 for row in rows if row.status == "PASSED"),
            warning_samples=sum(1 for row in rows if row.status == "WARNING"),
            failed_samples=sum(1 for row in rows if row.status == "FAILED"),
            skipped_samples=sum(1 for row in rows if row.status == "SKIPPED_MISSING_FILE"),
            error_samples=sum(1 for row in rows if row.status == "ERROR"),
            recommended_profile=recommended_profile,
            diagnostics={
                "sort_by": sort_by,
                "sample_names": [row.sample_name for row in rows],
            },
        )

    def _emit(self, progress_callback: Callable[[dict], None] | None, payload: dict) -> None:
        if progress_callback is not None:
            progress_callback(payload)

    def _emit_finished(self, progress_callback: Callable[[dict], None] | None, row: MultiSampleValidationRow) -> None:
        payload = {
            "event": "sample_finish",
            "sample": row.sample_name,
            "status": row.status,
            "elapsed_seconds": row.elapsed_seconds,
            "trades": row.total_trades,
            "net_pnl_after_costs": row.net_pnl_after_costs,
            "cache_status": row.cache_status,
            "cache_read_elapsed_seconds": row.cache_read_elapsed_seconds,
            "original_elapsed_seconds": row.original_elapsed_seconds,
            "estimated_saved_seconds": row.estimated_saved_seconds,
        }
        self._emit(progress_callback, payload)

    def _apply_cache_diagnostics(self, row: MultiSampleValidationRow, diagnostics) -> None:
        if diagnostics is None:
            return
        row.cache_status = diagnostics.cache_status
        row.cache_key_hash = diagnostics.cache_key_hash
        row.cache_read_elapsed_seconds = diagnostics.cache_read_elapsed_seconds
        row.original_elapsed_seconds = diagnostics.original_compute_elapsed_seconds or row.original_elapsed_seconds
        row.estimated_saved_seconds = diagnostics.estimated_saved_seconds
        row.cache_age_seconds = diagnostics.cache_age_seconds
