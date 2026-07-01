from __future__ import annotations

import pytest

from models.engine_config import EngineConfig


def test_engine_config_defaults() -> None:
    config = EngineConfig()

    assert config.dealing_range_mode == "current_external"
    assert config.exit_mode == "original"
    assert config.min_risk_reward == 2.0
    assert config.direction_mode == "all"


@pytest.mark.parametrize("exit_mode", ["original", "fixed_1r", "fixed_1_5r", "fixed_2r", "fixed_3r"])
def test_engine_config_accepts_valid_exit_modes(exit_mode: str) -> None:
    config = EngineConfig(exit_mode=exit_mode)

    assert config.exit_mode == exit_mode


@pytest.mark.parametrize("direction_mode", ["all", "long_only", "short_only"])
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


def test_engine_config_accepts_custom_min_risk_reward() -> None:
    config = EngineConfig(min_risk_reward=1.5)

    assert config.min_risk_reward == 1.5


@pytest.mark.parametrize("min_risk_reward", [0, -1])
def test_engine_config_rejects_invalid_min_risk_reward(min_risk_reward: float) -> None:
    with pytest.raises(ValueError, match="Unsupported min risk reward"):
        EngineConfig(min_risk_reward=min_risk_reward)
