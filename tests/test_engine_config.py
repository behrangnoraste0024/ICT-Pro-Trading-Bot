from __future__ import annotations

import pytest

from models.engine_config import EngineConfig


def test_engine_config_defaults() -> None:
    config = EngineConfig()

    assert config.strategy_profile == "default"
    assert config.dealing_range_mode == "current_external"
    assert config.exit_mode == "original"
    assert config.min_risk_reward == 2.0
    assert config.direction_mode == "all"
    assert config.auto_trend_fallback == "all"
    assert config.regime_mode == "rolling_return"
    assert config.regime_lookback == 200
    assert config.regime_threshold_pct == 0.0
    assert config.regime_fallback == "all"
    assert config.direction_quality_mode == "off"
    assert config.cost_model == "off"
    assert config.commission_pct == 0.0
    assert config.slippage_pct == 0.0
    assert config.spread_pct == 0.0
    assert config.decision_filter_mode == "off"
    assert config.decision_score_threshold is None


@pytest.mark.parametrize("exit_mode", ["original", "fixed_1r", "fixed_1_5r", "fixed_2r", "fixed_3r"])
def test_engine_config_accepts_valid_exit_modes(exit_mode: str) -> None:
    config = EngineConfig(exit_mode=exit_mode)

    assert config.exit_mode == exit_mode


@pytest.mark.parametrize("direction_mode", ["all", "long_only", "short_only", "auto_trend", "regime_trend"])
def test_engine_config_accepts_valid_direction_modes(direction_mode: str) -> None:
    config = EngineConfig(direction_mode=direction_mode)

    assert config.direction_mode == direction_mode


def test_engine_config_rejects_invalid_exit_mode() -> None:
    with pytest.raises(ValueError, match="Unsupported exit mode"):
        EngineConfig(exit_mode="fixed_4r")


def test_engine_config_rejects_invalid_dealing_range_mode() -> None:
    with pytest.raises(ValueError, match="Unsupported dealing range mode"):
        EngineConfig(dealing_range_mode="future_range")


def test_engine_config_rejects_invalid_direction_mode() -> None:
    with pytest.raises(ValueError, match="Unsupported direction mode"):
        EngineConfig(direction_mode="sideways_only")


@pytest.mark.parametrize("auto_trend_fallback", ["all", "block"])
def test_engine_config_accepts_valid_auto_trend_fallbacks(auto_trend_fallback: str) -> None:
    config = EngineConfig(auto_trend_fallback=auto_trend_fallback)

    assert config.auto_trend_fallback == auto_trend_fallback


def test_engine_config_rejects_invalid_auto_trend_fallback() -> None:
    with pytest.raises(ValueError, match="Unsupported auto trend fallback"):
        EngineConfig(auto_trend_fallback="sideways")


def test_engine_config_accepts_regime_settings() -> None:
    config = EngineConfig(
        direction_mode="regime_trend",
        regime_mode="rolling_return",
        regime_lookback=50,
        regime_threshold_pct=0.01,
        regime_fallback="block",
    )

    assert config.regime_mode == "rolling_return"
    assert config.regime_lookback == 50
    assert config.regime_threshold_pct == 0.01
    assert config.regime_fallback == "block"


def test_engine_config_rejects_invalid_regime_mode() -> None:
    with pytest.raises(ValueError, match="Unsupported regime mode"):
        EngineConfig(regime_mode="future")


@pytest.mark.parametrize("regime_lookback", [0, -1])
def test_engine_config_rejects_invalid_regime_lookback(regime_lookback: int) -> None:
    with pytest.raises(ValueError, match="Unsupported regime lookback"):
        EngineConfig(regime_lookback=regime_lookback)


def test_engine_config_rejects_invalid_regime_threshold() -> None:
    with pytest.raises(ValueError, match="Unsupported regime threshold pct"):
        EngineConfig(regime_threshold_pct=-0.01)


def test_engine_config_rejects_invalid_regime_fallback() -> None:
    with pytest.raises(ValueError, match="Unsupported regime fallback"):
        EngineConfig(regime_fallback="sideways")


@pytest.mark.parametrize("direction_quality_mode", ["off", "long_strict", "short_strict", "both_strict"])
def test_engine_config_accepts_valid_direction_quality_modes(direction_quality_mode: str) -> None:
    config = EngineConfig(direction_quality_mode=direction_quality_mode)

    assert config.direction_quality_mode == direction_quality_mode


def test_engine_config_rejects_invalid_direction_quality_mode() -> None:
    with pytest.raises(ValueError, match="Unsupported direction quality mode"):
        EngineConfig(direction_quality_mode="medium_spicy")


@pytest.mark.parametrize("strategy_profile", ["default", "balanced_smc", "bearish_smc", "research_baseline"])
def test_engine_config_accepts_valid_strategy_profiles(strategy_profile: str) -> None:
    config = EngineConfig(strategy_profile=strategy_profile)

    assert config.strategy_profile == strategy_profile


def test_engine_config_rejects_invalid_strategy_profile() -> None:
    with pytest.raises(ValueError, match="Unsupported strategy profile"):
        EngineConfig(strategy_profile="turbo")


@pytest.mark.parametrize("field_name", ["strict_long_min_setup_score", "strict_short_min_setup_score"])
def test_engine_config_rejects_invalid_strict_min_setup_score(field_name: str) -> None:
    with pytest.raises(ValueError, match=f"Unsupported {field_name}"):
        EngineConfig(**{field_name: -1})


def test_engine_config_accepts_custom_min_risk_reward() -> None:
    config = EngineConfig(min_risk_reward=1.5)

    assert config.min_risk_reward == 1.5


@pytest.mark.parametrize("min_risk_reward", [0, -1])
def test_engine_config_rejects_invalid_min_risk_reward(min_risk_reward: float) -> None:
    with pytest.raises(ValueError, match="Unsupported min risk reward"):
        EngineConfig(min_risk_reward=min_risk_reward)


@pytest.mark.parametrize("cost_model", ["off", "percent"])
def test_engine_config_accepts_valid_cost_model(cost_model: str) -> None:
    config = EngineConfig(cost_model=cost_model)

    assert config.cost_model == cost_model


def test_engine_config_rejects_invalid_cost_model() -> None:
    with pytest.raises(ValueError, match="Unsupported cost model"):
        EngineConfig(cost_model="ticks")


@pytest.mark.parametrize("field_name", ["commission_pct", "slippage_pct", "spread_pct"])
def test_engine_config_rejects_negative_cost_pct(field_name: str) -> None:
    with pytest.raises(ValueError, match=f"Unsupported {field_name}"):
        EngineConfig(**{field_name: -0.1})


@pytest.mark.parametrize("decision_filter_mode", ["off", "approve_only", "warning_only", "reject_only", "approve_or_warning"])
def test_engine_config_accepts_valid_decision_filter_modes(decision_filter_mode: str) -> None:
    config = EngineConfig(decision_filter_mode=decision_filter_mode)

    assert config.decision_filter_mode == decision_filter_mode


def test_engine_config_rejects_invalid_decision_filter_mode() -> None:
    with pytest.raises(ValueError, match="Unsupported decision filter mode"):
        EngineConfig(decision_filter_mode="approve_sometimes")


def test_engine_config_accepts_decision_score_threshold() -> None:
    config = EngineConfig(decision_score_threshold=0.75)

    assert config.decision_score_threshold == 0.75


@pytest.mark.parametrize("threshold", [-0.1, 1.1])
def test_engine_config_rejects_invalid_decision_score_threshold(threshold: float) -> None:
    with pytest.raises(ValueError, match="Unsupported decision score threshold"):
        EngineConfig(decision_score_threshold=threshold)
