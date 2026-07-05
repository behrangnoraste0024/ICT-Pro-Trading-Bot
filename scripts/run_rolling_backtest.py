from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data.historical_data_utils import load_candles_json
from engine.backtest.trade_outcome_diagnostics_engine import debug_extract_available_trade_metadata
from engine.rolling_backtest.rolling_backtest_engine import RollingBacktestEngine
from models.engine_config import EngineConfig
from models.strategy_profile import apply_strategy_profile
from reporting.rolling_backtest_report import format_rolling_backtest_report


DEFAULT_FIXTURE = "tests/fixtures/btcusdt_100_candles.json"
PROFILE_FLAG_TO_FIELD = {
    "--dealing-range-mode": "dealing_range_mode",
    "--exit-mode": "exit_mode",
    "--min-risk-reward": "min_risk_reward",
    "--direction-mode": "direction_mode",
    "--auto-trend-fallback": "auto_trend_fallback",
    "--regime-mode": "regime_mode",
    "--regime-lookback": "regime_lookback",
    "--regime-threshold-pct": "regime_threshold_pct",
    "--regime-fallback": "regime_fallback",
    "--direction-quality-mode": "direction_quality_mode",
    "--strict-long-require-regime-known": "strict_long_require_regime_known",
    "--strict-long-block-unknown-regime": "strict_long_block_unknown_regime",
    "--strict-long-require-regime-bullish": "strict_long_require_regime_bullish",
    "--strict-long-require-displacement": "strict_long_require_displacement",
    "--strict-long-min-setup-score": "strict_long_min_setup_score",
    "--strict-short-require-regime-known": "strict_short_require_regime_known",
    "--strict-short-block-unknown-regime": "strict_short_block_unknown_regime",
    "--strict-short-require-regime-bearish": "strict_short_require_regime_bearish",
    "--strict-short-require-displacement": "strict_short_require_displacement",
    "--strict-short-min-setup-score": "strict_short_min_setup_score",
    "--cost-model": "cost_model",
    "--commission-pct": "commission_pct",
    "--slippage-pct": "slippage_pct",
    "--spread-pct": "spread_pct",
}


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be greater than or equal to 0")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be greater than or equal to 0")
    return parsed


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description="Run deterministic rolling backtest from a candle fixture.")
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--min-candles", type=int, default=50)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--max-windows", type=int, default=None)
    parser.add_argument(
        "--strategy-profile",
        choices=[
            "default",
            "balanced_smc",
            "bearish_smc",
            "research_baseline",
            "balanced_smc_decision_065",
            "bearish_smc_decision_065",
        ],
        default="default",
    )
    parser.add_argument("--dealing-range-mode", choices=["current_external", "recent_50"], default="current_external")
    parser.add_argument(
        "--exit-mode",
        choices=["original", "fixed_1r", "fixed_1_5r", "fixed_2r", "fixed_3r"],
        default="original",
    )
    parser.add_argument("--min-risk-reward", type=positive_float, default=2.0)
    parser.add_argument(
        "--direction-mode",
        choices=["all", "long_only", "short_only", "auto_trend", "regime_trend"],
        default="all",
    )
    parser.add_argument("--auto-trend-fallback", choices=["all", "block"], default="all")
    parser.add_argument("--regime-mode", choices=["rolling_return"], default="rolling_return")
    parser.add_argument("--regime-lookback", type=int, default=200)
    parser.add_argument("--regime-threshold-pct", type=float, default=0.0)
    parser.add_argument("--regime-fallback", choices=["all", "block"], default="all")
    parser.add_argument(
        "--direction-quality-mode",
        choices=["off", "long_strict", "short_strict", "both_strict"],
        default="off",
    )
    parser.add_argument("--strict-long-require-regime-known", action="store_true")
    parser.add_argument("--strict-long-block-unknown-regime", action="store_true")
    parser.add_argument("--strict-long-require-regime-bullish", action="store_true")
    parser.add_argument("--strict-long-require-displacement", action="store_true")
    parser.add_argument("--strict-long-min-setup-score", type=non_negative_int, default=None)
    parser.add_argument("--strict-short-require-regime-known", action="store_true")
    parser.add_argument("--strict-short-block-unknown-regime", action="store_true")
    parser.add_argument("--strict-short-require-regime-bearish", action="store_true")
    parser.add_argument("--strict-short-require-displacement", action="store_true")
    parser.add_argument("--strict-short-min-setup-score", type=non_negative_int, default=None)
    parser.add_argument("--cost-model", choices=["off", "percent"], default="off")
    parser.add_argument("--commission-pct", type=non_negative_float, default=0.0)
    parser.add_argument("--slippage-pct", type=non_negative_float, default=0.0)
    parser.add_argument("--spread-pct", type=non_negative_float, default=0.0)
    parser.add_argument("--show-trades", action="store_true")
    parser.add_argument("--debug-first-trade-metadata", action="store_true")
    args = parser.parse_args(raw_args)

    if args.min_candles <= 0:
        print("Error: --min-candles must be greater than 0.")
        return 1
    if args.progress_every < 0:
        print("Error: --progress-every must be greater than or equal to 0.")
        return 1
    if args.max_windows is not None and args.max_windows <= 0:
        print("Error: --max-windows must be greater than 0.")
        return 1
    if args.regime_lookback <= 0:
        print("Error: --regime-lookback must be greater than 0.")
        return 1
    if args.regime_threshold_pct < 0:
        print("Error: --regime-threshold-pct must be greater than or equal to 0.")
        return 1

    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        print(f"Error: fixture not found: {fixture_path}")
        return 1

    try:
        candles = load_candles_json(fixture_path)
    except Exception as exc:
        print(f"Error: failed to load fixture: {exc}")
        return 1

    explicit_overrides = _explicit_profile_overrides(raw_args)
    config = apply_strategy_profile(EngineConfig(), args.strategy_profile, explicit_overrides)
    config = _apply_explicit_cli_overrides(config, args, explicit_overrides)

    progress_callback = _print_progress if args.progress_every > 0 else None
    result = RollingBacktestEngine(
        min_candles=args.min_candles,
        progress_callback=progress_callback,
        progress_every=args.progress_every,
        max_windows=args.max_windows,
        config=config,
    ).run(candles)
    report = format_rolling_backtest_report(
        result,
        str(fixture_path),
        args.min_candles,
        args.max_windows,
        show_trades=args.show_trades,
    )
    print(report)
    if args.debug_first_trade_metadata:
        print(_format_first_trade_metadata_debug(result))
    return 0


def _explicit_profile_overrides(argv: list[str]) -> set[str]:
    explicit: set[str] = set()
    for token in argv:
        flag = token.split("=", 1)[0]
        field_name = PROFILE_FLAG_TO_FIELD.get(flag)
        if field_name is not None:
            explicit.add(field_name)
    return explicit


def _apply_explicit_cli_overrides(config: EngineConfig, args, explicit_overrides: set[str]) -> EngineConfig:
    for field_name in explicit_overrides:
        setattr(config, field_name, getattr(args, field_name))
    return EngineConfig(**config.__dict__)


def _format_first_trade_metadata_debug(result) -> str:
    contexts = getattr(result, "trade_outcome_contexts", [])
    if not contexts:
        return "\n===== FIRST TRADE METADATA DEBUG =====\nNo trade outcome context available."

    debug = debug_extract_available_trade_metadata(contexts[0])
    lines = ["", "===== FIRST TRADE METADATA DEBUG =====", "Top Level Candidate Fields:"]
    top_level = debug.get("top_level_candidate_fields", {})
    if top_level:
        lines.extend(f"{key}: {value}" for key, value in sorted(top_level.items()))
    else:
        lines.append("None")

    lines.append("Nested Candidate Objects:")
    nested = debug.get("nested_candidate_objects", {})
    if nested:
        lines.extend(f"{key}: {value}" for key, value in sorted(nested.items()))
    else:
        lines.append("None")

    lines.append("Extracted Metadata:")
    extracted = debug.get("extracted_metadata", {})
    if extracted:
        lines.extend(f"{key}: {value}" for key, value in sorted(extracted.items()))
    else:
        lines.append("None")
    return "\n".join(lines)


def _print_progress(payload: dict[str, int]) -> None:
    print(
        "[rolling] "
        f"processed={payload['processed_windows']} "
        f"skipped={payload['skipped_windows']} "
        f"failed={payload['failed_windows']} "
        f"opened={payload['opened_trades']} "
        f"closed={payload['closed_by_state']} "
        f"duplicates={payload['duplicate_signals_skipped']} "
        f"/ total={payload['total_windows']}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
