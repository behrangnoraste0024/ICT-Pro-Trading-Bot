from __future__ import annotations

from dataclasses import replace

from models.engine_config import EngineConfig


DEFAULT_PROFILE = "default"
BALANCED_SMC_PROFILE = "balanced_smc"
BEARISH_SMC_PROFILE = "bearish_smc"
RESEARCH_BASELINE_PROFILE = "research_baseline"

VALID_STRATEGY_PROFILES = {
    DEFAULT_PROFILE,
    BALANCED_SMC_PROFILE,
    BEARISH_SMC_PROFILE,
    RESEARCH_BASELINE_PROFILE,
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
