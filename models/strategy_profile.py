from __future__ import annotations

from dataclasses import replace

from models.engine_config import EngineConfig


DEFAULT_PROFILE = "default"
BALANCED_SMC_PROFILE = "balanced_smc"
BEARISH_SMC_PROFILE = "bearish_smc"
RESEARCH_BASELINE_PROFILE = "research_baseline"
BALANCED_SMC_DECISION_065_PROFILE = "balanced_smc_decision_065"
BEARISH_SMC_DECISION_065_PROFILE = "bearish_smc_decision_065"

VALID_STRATEGY_PROFILES = {
    DEFAULT_PROFILE,
    BALANCED_SMC_PROFILE,
    BEARISH_SMC_PROFILE,
    RESEARCH_BASELINE_PROFILE,
    BALANCED_SMC_DECISION_065_PROFILE,
    BEARISH_SMC_DECISION_065_PROFILE,
}

PROFILE_OVERRIDES: dict[str, dict[str, object]] = {
    DEFAULT_PROFILE: {},
    BALANCED_SMC_PROFILE: {
        "dealing_range_mode": "recent_50",
        "exit_mode": "fixed_1_5r",
        "min_risk_reward": 1.5,
        "direction_mode": "all",
        "direction_quality_mode": "long_strict",
        "strict_long_require_regime_known": True,
        "strict_long_require_displacement": True,
        "strict_long_min_setup_score": None,
        "regime_mode": "rolling_return",
        "regime_lookback": 200,
        "regime_threshold_pct": 0.0,
        "regime_fallback": "all",
    },
    BEARISH_SMC_PROFILE: {
        "dealing_range_mode": "recent_50",
        "exit_mode": "fixed_1_5r",
        "min_risk_reward": 1.5,
        "direction_mode": "short_only",
        "direction_quality_mode": "off",
    },
    RESEARCH_BASELINE_PROFILE: {
        "dealing_range_mode": "recent_50",
        "exit_mode": "fixed_1_5r",
        "min_risk_reward": 1.5,
        "direction_mode": "all",
        "direction_quality_mode": "off",
    },
    BALANCED_SMC_DECISION_065_PROFILE: {
        "dealing_range_mode": "recent_50",
        "exit_mode": "fixed_1_5r",
        "min_risk_reward": 1.5,
        "direction_mode": "all",
        "direction_quality_mode": "long_strict",
        "strict_long_require_regime_known": True,
        "strict_long_require_displacement": True,
        "strict_long_min_setup_score": None,
        "regime_mode": "rolling_return",
        "regime_lookback": 200,
        "regime_threshold_pct": 0.0,
        "regime_fallback": "all",
        "decision_score_threshold": 0.65,
    },
    BEARISH_SMC_DECISION_065_PROFILE: {
        "dealing_range_mode": "recent_50",
        "exit_mode": "fixed_1_5r",
        "min_risk_reward": 1.5,
        "direction_mode": "short_only",
        "direction_quality_mode": "off",
        "regime_mode": "rolling_return",
        "regime_lookback": 200,
        "regime_threshold_pct": 0.0,
        "regime_fallback": "all",
        "decision_score_threshold": 0.65,
    },
}


def apply_strategy_profile(
    config: EngineConfig,
    profile_name: str,
    explicit_overrides: set[str] | None = None,
) -> EngineConfig:
    if profile_name not in VALID_STRATEGY_PROFILES:
        raise ValueError(f"Unsupported strategy profile: {profile_name}")

    explicit = explicit_overrides or set()
    values = {"strategy_profile": profile_name}
    for field_name, value in PROFILE_OVERRIDES[profile_name].items():
        if field_name not in explicit:
            values[field_name] = value
    return replace(config, **values)
