from __future__ import annotations

import pytest

from models.engine_config import EngineConfig
from models.strategy_profile import apply_strategy_profile


def test_default_profile_does_not_change_config() -> None:
    config = EngineConfig()
    profiled = apply_strategy_profile(config, "default")

    assert profiled == config
    assert profiled is not config


def test_balanced_smc_applies_expected_fields() -> None:
    config = apply_strategy_profile(EngineConfig(), "balanced_smc")

    assert config.strategy_profile == "balanced_smc"
    assert config.dealing_range_mode == "recent_50"
    assert config.exit_mode == "fixed_1_5r"
    assert config.min_risk_reward == 1.5
    assert config.direction_mode == "all"
    assert config.direction_quality_mode == "long_strict"
    assert config.strict_long_require_regime_known is True
    assert config.strict_long_require_displacement is True
    assert config.strict_long_min_setup_score is None
    assert config.regime_mode == "rolling_return"
    assert config.regime_lookback == 200
    assert config.regime_threshold_pct == 0.0
    assert config.regime_fallback == "all"
    assert config.decision_score_threshold is None


def test_bearish_smc_applies_expected_fields() -> None:
    config = apply_strategy_profile(EngineConfig(), "bearish_smc")

    assert config.dealing_range_mode == "recent_50"
    assert config.exit_mode == "fixed_1_5r"
    assert config.min_risk_reward == 1.5
    assert config.direction_mode == "short_only"
    assert config.direction_quality_mode == "off"
    assert config.decision_score_threshold is None


def test_balanced_smc_decision_065_applies_balanced_fields_with_threshold() -> None:
    base = apply_strategy_profile(EngineConfig(), "balanced_smc")
    config = apply_strategy_profile(EngineConfig(), "balanced_smc_decision_065")

    assert config.strategy_profile == "balanced_smc_decision_065"
    assert config.dealing_range_mode == base.dealing_range_mode
    assert config.exit_mode == base.exit_mode
    assert config.min_risk_reward == base.min_risk_reward
    assert config.direction_mode == base.direction_mode
    assert config.direction_quality_mode == base.direction_quality_mode
    assert config.strict_long_require_regime_known == base.strict_long_require_regime_known
    assert config.strict_long_require_displacement == base.strict_long_require_displacement
    assert config.regime_mode == base.regime_mode
    assert config.regime_lookback == base.regime_lookback
    assert config.regime_threshold_pct == base.regime_threshold_pct
    assert config.regime_fallback == base.regime_fallback
    assert config.decision_score_threshold == 0.65


def test_bearish_smc_decision_065_applies_bearish_fields_with_threshold() -> None:
    base = apply_strategy_profile(EngineConfig(), "bearish_smc")
    config = apply_strategy_profile(EngineConfig(), "bearish_smc_decision_065")

    assert config.strategy_profile == "bearish_smc_decision_065"
    assert config.dealing_range_mode == base.dealing_range_mode
    assert config.exit_mode == base.exit_mode
    assert config.min_risk_reward == base.min_risk_reward
    assert config.direction_mode == base.direction_mode
    assert config.direction_quality_mode == base.direction_quality_mode
    assert config.regime_mode == base.regime_mode
    assert config.regime_lookback == base.regime_lookback
    assert config.regime_threshold_pct == base.regime_threshold_pct
    assert config.regime_fallback == base.regime_fallback
    assert config.decision_score_threshold == 0.65


def test_research_baseline_applies_expected_fields() -> None:
    config = apply_strategy_profile(EngineConfig(), "research_baseline")

    assert config.dealing_range_mode == "recent_50"
    assert config.exit_mode == "fixed_1_5r"
    assert config.min_risk_reward == 1.5
    assert config.direction_mode == "all"
    assert config.direction_quality_mode == "off"


def test_invalid_profile_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unsupported strategy profile"):
        apply_strategy_profile(EngineConfig(), "turbo")


def test_explicit_exit_mode_override_beats_balanced_smc() -> None:
    config = apply_strategy_profile(
        EngineConfig(exit_mode="fixed_2r"),
        "balanced_smc",
        {"exit_mode"},
    )

    assert config.exit_mode == "fixed_2r"
    assert config.dealing_range_mode == "recent_50"


def test_explicit_direction_mode_override_beats_balanced_smc() -> None:
    config = apply_strategy_profile(
        EngineConfig(direction_mode="short_only"),
        "balanced_smc",
        {"direction_mode"},
    )

    assert config.direction_mode == "short_only"
    assert config.direction_quality_mode == "long_strict"


def test_explicit_min_risk_reward_override_beats_balanced_smc() -> None:
    config = apply_strategy_profile(
        EngineConfig(min_risk_reward=2.0),
        "balanced_smc",
        {"min_risk_reward"},
    )

    assert config.min_risk_reward == 2.0
    assert config.exit_mode == "fixed_1_5r"


def test_explicit_strict_long_flag_override_can_disable_profile_rule() -> None:
    config = apply_strategy_profile(
        EngineConfig(strict_long_require_displacement=False),
        "balanced_smc",
        {"strict_long_require_displacement"},
    )

    assert config.strict_long_require_displacement is False
    assert config.strict_long_require_regime_known is True


def test_apply_strategy_profile_does_not_mutate_input_config() -> None:
    config = EngineConfig()

    apply_strategy_profile(config, "balanced_smc")

    assert config.strategy_profile == "default"
    assert config.dealing_range_mode == "current_external"
    assert config.exit_mode == "original"
