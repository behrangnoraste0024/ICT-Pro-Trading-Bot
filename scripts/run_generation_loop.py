from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.backtest.strategy_comparison_engine import StrategyComparisonEngine
from engine.backtest.strategy_comparison_engine import build_recommended_profile_with_cost_specs
from engine.evolution.generation_loop_engine import GenerationLoopEngine
from reporting.generation_loop_report import format_generation_result
from scripts.run_strategy_comparison import build_profile_strategy_specs

DEFAULT_FIXTURE = "tests/fixtures/btcusdt_100_candles.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic strategy generation loop.")
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--min-candles", type=int, default=50)
    parser.add_argument("--generations", type=int, default=1)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--seed-profiles", default="recommended_profiles_with_costs")
    parser.add_argument("--fast", action="store_true")
    args = parser.parse_args(argv)

    if args.generations <= 0:
        print("Error: --generations must be greater than 0.")
        return 1
    if args.top_k <= 0:
        print("Error: --top-k must be greater than 0.")
        return 1
    if args.min_candles <= 0:
        print("Error: --min-candles must be greater than 0.")
        return 1

    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        print(f"Error: fixture not found: {fixture_path}")
        return 1

    try:
        specs = _seed_specs(args.seed_profiles)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    comparison_engine = StrategyComparisonEngine()
    generation_engine = GenerationLoopEngine()
    current_specs = specs
    last_result = None
    for generation in range(args.generations):
        comparison_report = comparison_engine.run_comparison(
            fixture_path=str(fixture_path),
            strategy_specs=current_specs,
            min_candles=args.min_candles,
            enable_diagnostics=not args.fast,
        )
        last_result = generation_engine.run_generation(
            comparison_report,
            generation=generation,
            top_k=args.top_k,
        )
        current_specs = [candidate.strategy_spec for candidate in last_result.next_generation]

    if last_result is None:
        print("No generation result.")
        return 1
    print(format_generation_result(last_result))
    return 0


def _seed_specs(seed_profiles: str):
    if seed_profiles == "recommended_profiles_with_costs":
        return build_recommended_profile_with_cost_specs()
    profiles = [profile.strip() for profile in seed_profiles.split(",") if profile.strip()]
    if not profiles:
        raise ValueError("--seed-profiles must not be empty")
    return build_profile_strategy_specs(profiles)


if __name__ == "__main__":
    raise SystemExit(main())
