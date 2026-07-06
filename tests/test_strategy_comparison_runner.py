from __future__ import annotations

import json

import pytest

from scripts.run_strategy_comparison import main


FIXTURE_PATH = "tests/fixtures/btcusdt_100_candles.json"


def test_help_works(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])

    captured = capsys.readouterr()
    assert exc.value.code == 0
    assert "Compare rolling backtest strategy configurations" in captured.out


def test_default_run_on_fixture_exits_successfully(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--strategy-set", "default"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[strategy-comparison] starting" in captured.out
    assert "[strategy-comparison] finished" in captured.out
    assert "===== STRATEGY COMPARISON REPORT =====" in captured.out
    assert "Strategies   : 7" in captured.out


def test_exit_modes_recent_50_strategy_set_works(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--strategy-set", "exit_modes_recent_50"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "recent_50|fixed_1r|min_rr=1.0|dir=all" in captured.out
    assert "recent_50|fixed_3r|min_rr=3.0|dir=all" in captured.out


def test_direction_modes_recent_50_fixed_1_5r_strategy_set_works(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "direction_modes_recent_50_fixed_1_5r",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 3" in captured.out
    assert "dir=all" in captured.out
    assert "dir=long_only" in captured.out
    assert "dir=short_only" in captured.out
    assert "Rank | Strategy | Profile | DecisionFilter | ScoreThreshold | DR Mode | Exit | MinRR | Dir | DQ | LongPreset | TrendFB" in captured.out


def test_trend_direction_recent_50_fixed_1_5r_strategy_set_works(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "trend_direction_recent_50_fixed_1_5r",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 5" in captured.out
    assert "dir=auto_trend|trend_fallback=all" in captured.out
    assert "dir=auto_trend|trend_fallback=block" in captured.out


def test_regime_direction_recent_50_fixed_1_5r_strategy_set_works(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "regime_direction_recent_50_fixed_1_5r",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 9" in captured.out
    assert "dir=regime_trend|regime=rolling_return|lookback=100|thr=0.0|regime_fb=all" in captured.out
    assert "dir=regime_trend|regime=rolling_return|lookback=200|thr=0.0|regime_fb=block" in captured.out


def test_long_strict_recent_50_fixed_1_5r_strategy_set_works(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "long_strict_recent_50_fixed_1_5r",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 10" in captured.out
    assert "dq=long_strict|long_preset=regime_known" in captured.out
    assert "dq=long_strict|long_preset=regime_bullish_displacement_score100" in captured.out
    assert "Rank | Strategy | Profile | DecisionFilter | ScoreThreshold | DR Mode | Exit | MinRR | Dir | DQ | LongPreset" in captured.out


def test_recommended_profiles_strategy_set_works(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "recommended_profiles",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 4" in captured.out
    assert "profile=balanced_smc" in captured.out
    assert "profile=bearish_smc" in captured.out
    assert "profile=research_baseline" in captured.out
    assert "profile=default" in captured.out
    assert "Rank | Strategy | Profile | DecisionFilter | ScoreThreshold | DR Mode" in captured.out


def test_recommended_profiles_with_costs_strategy_set_works(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "recommended_profiles_with_costs",
            "--sort-by",
            "net_pnl_after_costs",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 5" in captured.out
    assert "Sort By      : net_pnl_after_costs" in captured.out
    assert "profile=balanced_smc|cost=percent" in captured.out
    assert "Cost | NetAfterCost" in captured.out


def test_decision_gate_profiles_with_costs_strategy_set_works(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "decision_gate_profiles_with_costs",
            "--sort-by",
            "net_pnl_after_costs",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 10" in captured.out
    assert "profile=balanced_smc|cost=percent|decision=approve_only" in captured.out
    assert "profile=bearish_smc|cost=percent|decision=warning_only" in captured.out
    assert "DecisionFilter" in captured.out


def test_decision_threshold_profiles_with_costs_strategy_set_works(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "decision_threshold_profiles_with_costs",
            "--sort-by",
            "net_pnl_after_costs",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 14" in captured.out
    assert "profile=balanced_smc|cost=percent|threshold=0.60" in captured.out
    assert "profile=bearish_smc|cost=percent|threshold=0.85" in captured.out
    assert "ScoreThreshold" in captured.out


def test_recommended_decision_profiles_with_costs_strategy_set_works(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "recommended_decision_profiles_with_costs",
            "--sort-by",
            "net_pnl_after_costs",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 5" in captured.out
    assert "profile=balanced_smc_decision_065|cost=percent" in captured.out
    assert "profile=bearish_smc_decision_065|cost=percent" in captured.out
    assert "ScoreThreshold" in captured.out
    assert "0.65" in captured.out


def test_show_recommendation_prints_validation_report(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "recommended_decision_profiles_with_costs",
            "--sort-by",
            "net_pnl_after_costs",
            "--show-recommendation",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "===== RECOMMENDED PROFILE VALIDATION =====" in captured.out
    assert "Recommended Strategy :" in captured.out
    assert "Candidate Ranking:" in captured.out


def test_default_comparison_does_not_print_recommendation_report(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "recommended_decision_profiles_with_costs",
            "--sort-by",
            "net_pnl_after_costs",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "===== STRATEGY COMPARISON REPORT =====" in captured.out
    assert "===== RECOMMENDED PROFILE VALIDATION =====" not in captured.out


def test_current_external_only_strategy_set_works(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--strategy-set", "current_external_only"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 4" in captured.out
    assert "current_external|fixed_1_5r|min_rr=1.5|dir=all" in captured.out


def test_custom_strategy_set_works(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "custom",
            "--dealing-range-modes",
            "recent_50",
            "--exit-modes",
            "fixed_1r,fixed_1_5r",
            "--min-risk-rewards",
            "1.0,1.5",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 4" in captured.out
    assert "recent_50|fixed_1_5r|min_rr=1.5|dir=all" in captured.out


def test_custom_strategy_set_accepts_direction_modes(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "custom",
            "--dealing-range-modes",
            "recent_50",
            "--exit-modes",
            "fixed_1_5r",
            "--min-risk-rewards",
            "1.5",
            "--direction-modes",
            "all,short_only",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 2" in captured.out
    assert "recent_50|fixed_1_5r|min_rr=1.5|dir=short_only" in captured.out


def test_custom_strategy_set_accepts_auto_trend_fallbacks(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "custom",
            "--dealing-range-modes",
            "recent_50",
            "--exit-modes",
            "fixed_1_5r",
            "--min-risk-rewards",
            "1.5",
            "--direction-modes",
            "auto_trend",
            "--auto-trend-fallbacks",
            "all,block",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 2" in captured.out
    assert "recent_50|fixed_1_5r|min_rr=1.5|dir=auto_trend|trend_fallback=all" in captured.out
    assert "recent_50|fixed_1_5r|min_rr=1.5|dir=auto_trend|trend_fallback=block" in captured.out


def test_custom_strategy_set_accepts_regime_options(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "custom",
            "--dealing-range-modes",
            "recent_50",
            "--exit-modes",
            "fixed_1_5r",
            "--min-risk-rewards",
            "1.5",
            "--direction-modes",
            "regime_trend",
            "--regime-lookbacks",
            "50",
            "--regime-threshold-pcts",
            "0.01",
            "--regime-fallbacks",
            "block",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 1" in captured.out
    assert "recent_50|fixed_1_5r|min_rr=1.5|dir=regime_trend|regime=rolling_return|lookback=50|thr=0.01|regime_fb=block" in captured.out


def test_custom_strategy_set_accepts_direction_quality_options(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "custom",
            "--dealing-range-modes",
            "recent_50",
            "--exit-modes",
            "fixed_1_5r",
            "--min-risk-rewards",
            "1.5",
            "--direction-quality-modes",
            "off,long_strict",
            "--strict-long-presets",
            "displacement",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 2" in captured.out
    assert "recent_50|fixed_1_5r|min_rr=1.5|dir=all|dq=long_strict|long_preset=displacement" in captured.out


def test_custom_strategy_set_accepts_strategy_profiles(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "custom",
            "--strategy-profiles",
            "balanced_smc,bearish_smc",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 2" in captured.out
    assert "profile=balanced_smc" in captured.out
    assert "profile=bearish_smc" in captured.out


def test_fast_mode_exits_successfully(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "current_external_only",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "===== STRATEGY COMPARISON REPORT =====" in captured.out


def test_progress_every_prints_rolling_progress(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "exit_modes_recent_50",
            "--progress-every",
            "25",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "processed=" in captured.out
    assert "duplicates=" in captured.out


def test_output_json_writes_valid_json(tmp_path) -> None:
    output_path = tmp_path / "comparison.json"

    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "current_external_only",
            "--output-json",
            str(output_path),
        ]
    )

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert return_code == 0
    assert data["event_type"] == "STRATEGY_COMPARISON_REPORT"
    assert data["strategies"]
    assert "elapsed_seconds" in data["strategies"][0]
    assert "strategy_profile" in data["strategies"][0]
    assert "direction_mode" in data["strategies"][0]
    assert "auto_trend_fallback" in data["strategies"][0]
    assert "regime_mode" in data["strategies"][0]
    assert "regime_lookback" in data["strategies"][0]
    assert "regime_threshold_pct" in data["strategies"][0]
    assert "regime_fallback" in data["strategies"][0]
    assert "direction_quality_mode" in data["strategies"][0]
    assert "strict_long_preset" in data["strategies"][0]
    assert "long_in_bearish_count" in data["strategies"][0]
    assert "short_in_bullish_pnl" in data["strategies"][0]
    assert "cost_model" in data["strategies"][0]
    assert "commission_pct" in data["strategies"][0]
    assert "slippage_pct" in data["strategies"][0]
    assert "spread_pct" in data["strategies"][0]
    assert "gross_net_pnl" in data["strategies"][0]
    assert "total_cost" in data["strategies"][0]
    assert "net_pnl_after_costs" in data["strategies"][0]
    assert "decision_filter_mode" in data["strategies"][0]
    assert "decision_filtered" in data["strategies"][0]
    assert "decision_filter_bucket" in data["strategies"][0]
    assert "decision_score_threshold" in data["strategies"][0]
    assert "decision_threshold_filtered" in data["strategies"][0]
    assert "decision_threshold_bucket" in data["strategies"][0]
    assert "average_execution_quality" in data["strategies"][0]
    assert "average_decision_score" in data["strategies"][0]


def test_output_csv_writes_headers(tmp_path) -> None:
    output_path = tmp_path / "comparison.csv"

    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "current_external_only",
            "--output-csv",
            str(output_path),
        ]
    )

    text = output_path.read_text(encoding="utf-8")
    assert return_code == 0
    assert "strategy_name" in text.splitlines()[0]
    assert "net_pnl" in text.splitlines()[0]
    assert "elapsed_seconds" in text.splitlines()[0]
    assert "strategy_profile" in text.splitlines()[0]
    assert "direction_mode" in text.splitlines()[0]
    assert "auto_trend_fallback" in text.splitlines()[0]
    assert "regime_mode" in text.splitlines()[0]
    assert "regime_lookback" in text.splitlines()[0]
    assert "regime_threshold_pct" in text.splitlines()[0]
    assert "regime_fallback" in text.splitlines()[0]
    assert "direction_quality_mode" in text.splitlines()[0]
    assert "strict_long_preset" in text.splitlines()[0]
    assert "long_in_bearish_count" in text.splitlines()[0]
    assert "short_in_bullish_pnl" in text.splitlines()[0]
    assert "cost_model" in text.splitlines()[0]
    assert "commission_pct" in text.splitlines()[0]
    assert "slippage_pct" in text.splitlines()[0]
    assert "spread_pct" in text.splitlines()[0]
    assert "gross_net_pnl" in text.splitlines()[0]
    assert "total_cost" in text.splitlines()[0]
    assert "net_pnl_after_costs" in text.splitlines()[0]
    assert "decision_filter_mode" in text.splitlines()[0]
    assert "decision_filtered" in text.splitlines()[0]
    assert "decision_filter_bucket" in text.splitlines()[0]
    assert "decision_score_threshold" in text.splitlines()[0]
    assert "decision_threshold_filtered" in text.splitlines()[0]
    assert "decision_threshold_bucket" in text.splitlines()[0]
    assert "average_execution_quality" in text.splitlines()[0]
    assert "average_decision_score" in text.splitlines()[0]


def test_invalid_strategy_set_rejected_by_argparse() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--fixture", FIXTURE_PATH, "--strategy-set", "bad"])

    assert exc.value.code == 2


def test_invalid_exit_mode_in_custom_returns_error(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--strategy-set",
            "custom",
            "--dealing-range-modes",
            "recent_50",
            "--exit-modes",
            "fixed_4r",
            "--min-risk-rewards",
            "1.0",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 1
    assert "Unsupported exit mode" in captured.out


def test_invalid_direction_mode_in_custom_returns_error(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--strategy-set",
            "custom",
            "--dealing-range-modes",
            "recent_50",
            "--exit-modes",
            "fixed_1_5r",
            "--min-risk-rewards",
            "1.5",
            "--direction-modes",
            "sideways_only",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 1
    assert "Unsupported direction mode" in captured.out


def test_invalid_auto_trend_fallback_in_custom_returns_error(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--strategy-set",
            "custom",
            "--dealing-range-modes",
            "recent_50",
            "--exit-modes",
            "fixed_1_5r",
            "--min-risk-rewards",
            "1.5",
            "--direction-modes",
            "auto_trend",
            "--auto-trend-fallbacks",
            "sideways",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 1
    assert "Unsupported auto trend fallback" in captured.out


def test_invalid_regime_fallback_in_custom_returns_error(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--strategy-set",
            "custom",
            "--dealing-range-modes",
            "recent_50",
            "--exit-modes",
            "fixed_1_5r",
            "--min-risk-rewards",
            "1.5",
            "--direction-modes",
            "regime_trend",
            "--regime-fallbacks",
            "sideways",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 1
    assert "Unsupported regime fallback" in captured.out


def test_invalid_direction_quality_mode_in_custom_returns_error(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--strategy-set",
            "custom",
            "--dealing-range-modes",
            "recent_50",
            "--exit-modes",
            "fixed_1_5r",
            "--min-risk-rewards",
            "1.5",
            "--direction-quality-modes",
            "soft",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 1
    assert "Unsupported direction quality mode" in captured.out


def test_invalid_strict_long_preset_in_custom_returns_error(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--strategy-set",
            "custom",
            "--dealing-range-modes",
            "recent_50",
            "--exit-modes",
            "fixed_1_5r",
            "--min-risk-rewards",
            "1.5",
            "--direction-quality-modes",
            "long_strict",
            "--strict-long-presets",
            "moonshot",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 1
    assert "Unsupported strict long preset" in captured.out


def test_invalid_strategy_profile_in_custom_returns_error(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--strategy-set",
            "custom",
            "--strategy-profiles",
            "turbo",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 1
    assert "Unsupported strategy profile" in captured.out


def test_script_does_not_require_historical_file(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--strategy-set", "current_external_only"])

    assert return_code == 0
