from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.backtest.strategy_comparison_engine import (
    StrategyComparisonEngine,
    build_current_external_only_specs,
    build_default_strategy_specs,
    build_direction_modes_recent_50_fixed_1_5r_specs,
    build_exit_modes_recent_50_specs,
    build_regime_direction_recent_50_fixed_1_5r_specs,
    build_trend_direction_recent_50_fixed_1_5r_specs,
)
from models.engine_config import EngineConfig
from models.strategy_comparison import StrategyComparisonReport, StrategyConfigSpec
from reporting.strategy_comparison_report import format_strategy_comparison_report


DEFAULT_FIXTURE = "tests/fixtures/btcusdt_100_candles.json"
MAX_CUSTOM_COMBINATIONS = 50


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    if args.min_candles <= 0:
        print("Error: --min-candles must be greater than 0.")
        return 1
    if args.progress_every < 0:
        print("Error: --progress-every must be greater than or equal to 0.")
        return 1
    if args.max_windows is not None and args.max_windows <= 0:
        print("Error: --max-windows must be greater than 0.")
        return 1
    if args.timeout_per_strategy is not None and args.timeout_per_strategy <= 0:
        print("Error: --timeout-per-strategy must be greater than 0.")
        return 1

    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        print(f"Error: fixture not found: {fixture_path}")
        return 1

    try:
        specs = build_strategy_specs(args)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    try:
        descending = _resolve_descending(args.sort_by, args.descending, args.ascending)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1
    report = StrategyComparisonEngine().run_comparison(
        fixture_path=str(fixture_path),
        strategy_specs=specs,
        min_candles=args.min_candles,
        progress_every=args.progress_every,
        max_windows=args.max_windows,
        enable_diagnostics=not args.fast,
        progress_callback=_print_progress,
        timeout_per_strategy=args.timeout_per_strategy,
    )
    output = format_strategy_comparison_report(
        report,
        sort_by=args.sort_by,
        descending=descending,
        show_all=args.show_all,
    )
    print(output)
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_csv:
        _write_csv(report, args.output_csv)
    return 0


def _print_progress(payload: dict) -> None:
    event = payload.get("event")
    if event == "comparison_start":
        print(
            f"[strategy-comparison] strategies={payload['strategies']} fixture={payload['fixture']}",
            flush=True,
        )
        print(
            "[strategy-comparison] This may take several minutes. Use --fast or --max-windows for quicker checks.",
            flush=True,
        )
        return
    if event == "strategy_start":
        print(
            f"[strategy-comparison] starting {payload['index']}/{payload['total']} {payload['strategy']}",
            flush=True,
        )
        return
    if event == "strategy_finish":
        print(
            f"[strategy-comparison] finished {payload['index']}/{payload['total']} "
            f"{payload['strategy']} trades={payload['trades']} pnl={payload['pnl']:.2f} "
            f"elapsed={payload['elapsed_seconds']:.2f}s",
            flush=True,
        )
        if payload.get("timeout_warning"):
            print(
                f"[strategy-comparison] warning {payload['strategy']} exceeded timeout-per-strategy",
                flush=True,
            )
        return
    if event == "rolling_progress":
        print(
            "[strategy-comparison] "
            f"{payload['index']}/{payload['total']} {payload['strategy']} "
            f"processed={payload['processed_windows']} skipped={payload['skipped_windows']} "
            f"failed={payload['failed_windows']} opened={payload['opened_trades']} "
            f"closed={payload['closed_by_state']} duplicates={payload['duplicate_signals_skipped']} "
            f"/ total={payload['total_windows']}",
            flush=True,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare rolling backtest strategy configurations.")
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--min-candles", type=int, default=50)
    parser.add_argument("--progress-every", type=int, default=0)
    parser.add_argument("--max-windows", type=int, default=None)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--timeout-per-strategy", type=float, default=None)
    parser.add_argument(
        "--strategy-set",
        choices=[
            "default",
            "exit_modes_recent_50",
            "direction_modes_recent_50_fixed_1_5r",
            "trend_direction_recent_50_fixed_1_5r",
            "regime_direction_recent_50_fixed_1_5r",
            "current_external_only",
            "custom",
        ],
        default="default",
    )
    parser.add_argument("--include-original", action="store_true")
    parser.add_argument("--dealing-range-modes", default="current_external,recent_50")
    parser.add_argument("--exit-modes", default="fixed_1r,fixed_1_5r,fixed_2r,fixed_3r")
    parser.add_argument("--min-risk-rewards", default="1.0,1.5,2.0,3.0")
    parser.add_argument("--direction-modes", default="all")
    parser.add_argument("--auto-trend-fallbacks", default="all")
    parser.add_argument("--regime-modes", default="rolling_return")
    parser.add_argument("--regime-lookbacks", default="200")
    parser.add_argument("--regime-threshold-pcts", default="0.0")
    parser.add_argument("--regime-fallbacks", default="all")
    parser.add_argument(
        "--sort-by",
        choices=["net_pnl", "average_pnl", "win_rate", "max_drawdown", "profit_factor", "total_trades"],
        default="net_pnl",
    )
    parser.add_argument("--descending", action="store_true")
    parser.add_argument("--ascending", action="store_true")
    parser.add_argument("--show-all", action="store_true")
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--output-csv", default=None)
    return parser


def build_strategy_specs(args) -> list[StrategyConfigSpec]:
    if args.strategy_set == "default":
        return build_default_strategy_specs()
    if args.strategy_set == "exit_modes_recent_50":
        return build_exit_modes_recent_50_specs()
    if args.strategy_set == "direction_modes_recent_50_fixed_1_5r":
        return build_direction_modes_recent_50_fixed_1_5r_specs()
    if args.strategy_set == "trend_direction_recent_50_fixed_1_5r":
        return build_trend_direction_recent_50_fixed_1_5r_specs()
    if args.strategy_set == "regime_direction_recent_50_fixed_1_5r":
        return build_regime_direction_recent_50_fixed_1_5r_specs()
    if args.strategy_set == "current_external_only":
        return build_current_external_only_specs()
    return build_custom_strategy_specs(
        dealing_range_modes=args.dealing_range_modes,
        exit_modes=args.exit_modes,
        min_risk_rewards=args.min_risk_rewards,
        direction_modes=args.direction_modes,
        auto_trend_fallbacks=args.auto_trend_fallbacks,
        regime_modes=args.regime_modes,
        regime_lookbacks=args.regime_lookbacks,
        regime_threshold_pcts=args.regime_threshold_pcts,
        regime_fallbacks=args.regime_fallbacks,
        include_original=args.include_original,
    )


def build_custom_strategy_specs(
    dealing_range_modes: str,
    exit_modes: str,
    min_risk_rewards: str,
    direction_modes: str = "all",
    auto_trend_fallbacks: str = "all",
    regime_modes: str = "rolling_return",
    regime_lookbacks: str = "200",
    regime_threshold_pcts: str = "0.0",
    regime_fallbacks: str = "all",
    include_original: bool = False,
) -> list[StrategyConfigSpec]:
    dr_modes = _parse_csv(dealing_range_modes)
    exits = _parse_csv(exit_modes)
    min_rrs = _parse_float_csv(min_risk_rewards)
    directions = _parse_csv(direction_modes)
    trend_fallbacks = _parse_csv(auto_trend_fallbacks)
    regimes = _parse_csv(regime_modes)
    regime_lookback_values = _parse_int_csv(regime_lookbacks)
    regime_threshold_values = _parse_non_negative_float_csv(regime_threshold_pcts)
    regime_fallback_values = _parse_csv(regime_fallbacks)
    for mode in dr_modes:
        if mode not in EngineConfig.VALID_DEALING_RANGE_MODES:
            raise ValueError(f"Unsupported dealing range mode: {mode}")
    for exit_mode in exits:
        if exit_mode not in EngineConfig.VALID_EXIT_MODES:
            raise ValueError(f"Unsupported exit mode: {exit_mode}")
    for direction_mode in directions:
        if direction_mode not in EngineConfig.VALID_DIRECTION_MODES:
            raise ValueError(f"Unsupported direction mode: {direction_mode}")
    for trend_fallback in trend_fallbacks:
        if trend_fallback not in EngineConfig.VALID_AUTO_TREND_FALLBACKS:
            raise ValueError(f"Unsupported auto trend fallback: {trend_fallback}")
    for regime in regimes:
        if regime not in EngineConfig.VALID_REGIME_MODES:
            raise ValueError(f"Unsupported regime mode: {regime}")
    for regime_fallback in regime_fallback_values:
        if regime_fallback not in EngineConfig.VALID_REGIME_FALLBACKS:
            raise ValueError(f"Unsupported regime fallback: {regime_fallback}")

    if include_original and "original" not in exits:
        exits = ["original", *exits]

    specs: list[StrategyConfigSpec] = []
    for dr_mode in dr_modes:
        for exit_mode in exits:
            rr_values = [2.0] if exit_mode == "original" else min_rrs
            for min_rr in rr_values:
                for direction_mode in directions:
                    fallback_values = trend_fallbacks if direction_mode == "auto_trend" else ["all"]
                    for trend_fallback in fallback_values:
                        regime_mode_values = regimes if direction_mode == "regime_trend" else ["rolling_return"]
                        for regime_mode in regime_mode_values:
                            lookback_values = regime_lookback_values if direction_mode == "regime_trend" else [200]
                            for regime_lookback in lookback_values:
                                threshold_values = (
                                    regime_threshold_values if direction_mode == "regime_trend" else [0.0]
                                )
                                for regime_threshold in threshold_values:
                                    fallback_regime_values = (
                                        regime_fallback_values if direction_mode == "regime_trend" else ["all"]
                                    )
                                    for regime_fallback in fallback_regime_values:
                                        name = f"{dr_mode}|{exit_mode}|min_rr={min_rr}|dir={direction_mode}"
                                        if direction_mode == "auto_trend":
                                            name = f"{name}|trend_fallback={trend_fallback}"
                                        if direction_mode == "regime_trend":
                                            name = (
                                                f"{name}|regime={regime_mode}|lookback={regime_lookback}|"
                                                f"thr={regime_threshold}|regime_fb={regime_fallback}"
                                            )
                                        specs.append(
                                            StrategyConfigSpec(
                                                name,
                                                dr_mode,
                                                exit_mode,
                                                min_rr,
                                                direction_mode,
                                                trend_fallback,
                                                regime_mode,
                                                regime_lookback,
                                                regime_threshold,
                                                regime_fallback,
                                            )
                                        )

    if len(specs) > MAX_CUSTOM_COMBINATIONS:
        raise ValueError(f"custom strategy set too large: {len(specs)} combinations")
    return specs


def _parse_csv(value: str) -> list[str]:
    parsed = [item.strip() for item in value.split(",") if item.strip()]
    if not parsed:
        raise ValueError("comma-separated list must not be empty")
    return parsed


def _parse_float_csv(value: str) -> list[float]:
    parsed = []
    for item in _parse_csv(value):
        number = float(item)
        if number <= 0:
            raise ValueError(f"min risk reward must be greater than 0: {number}")
        parsed.append(number)
    return parsed


def _parse_non_negative_float_csv(value: str) -> list[float]:
    parsed = []
    for item in _parse_csv(value):
        number = float(item)
        if number < 0:
            raise ValueError(f"regime threshold pct must be greater than or equal to 0: {number}")
        parsed.append(number)
    return parsed


def _parse_int_csv(value: str) -> list[int]:
    parsed = []
    for item in _parse_csv(value):
        number = int(item)
        if number <= 0:
            raise ValueError(f"regime lookback must be greater than 0: {number}")
        parsed.append(number)
    return parsed


def _resolve_descending(sort_by: str, descending: bool, ascending: bool) -> bool:
    if descending and ascending:
        raise ValueError("--descending and --ascending cannot both be set")
    if descending:
        return True
    if ascending:
        return False
    return sort_by != "max_drawdown"


def _write_json(report: StrategyComparisonReport, output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")


def _write_csv(report: StrategyComparisonReport, output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [row.to_dict() for row in report.strategies]
    fieldnames = list(rows[0].keys()) if rows else ["strategy_name"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
