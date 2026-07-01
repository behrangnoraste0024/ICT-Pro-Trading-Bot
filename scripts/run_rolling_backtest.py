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
from reporting.rolling_backtest_report import format_rolling_backtest_report


DEFAULT_FIXTURE = "tests/fixtures/btcusdt_100_candles.json"


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic rolling backtest from a candle fixture.")
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--min-candles", type=int, default=50)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--max-windows", type=int, default=None)
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
    parser.add_argument("--show-trades", action="store_true")
    parser.add_argument("--debug-first-trade-metadata", action="store_true")
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

    progress_callback = _print_progress if args.progress_every > 0 else None
    result = RollingBacktestEngine(
        min_candles=args.min_candles,
        progress_callback=progress_callback,
        progress_every=args.progress_every,
        max_windows=args.max_windows,
        dealing_range_mode=args.dealing_range_mode,
        exit_mode=args.exit_mode,
        min_risk_reward=args.min_risk_reward,
        direction_mode=args.direction_mode,
        auto_trend_fallback=args.auto_trend_fallback,
        regime_mode=args.regime_mode,
        regime_lookback=args.regime_lookback,
        regime_threshold_pct=args.regime_threshold_pct,
        regime_fallback=args.regime_fallback,
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
