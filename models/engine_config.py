from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EngineConfig:
    VALID_DEALING_RANGE_MODES = {"current_external", "recent_50"}
    VALID_EXIT_MODES = {"original", "fixed_1r", "fixed_1_5r", "fixed_2r", "fixed_3r"}
    VALID_DIRECTION_MODES = {"all", "long_only", "short_only", "auto_trend"}
    VALID_AUTO_TREND_FALLBACKS = {"all", "block"}

    dealing_range_mode: str = "current_external"
    exit_mode: str = "original"
    min_risk_reward: float = 2.0
    direction_mode: str = "all"
    auto_trend_fallback: str = "all"

    def __post_init__(self) -> None:
        if self.dealing_range_mode not in self.VALID_DEALING_RANGE_MODES:
            raise ValueError(f"Unsupported dealing range mode: {self.dealing_range_mode}")
        if self.exit_mode not in self.VALID_EXIT_MODES:
            raise ValueError(f"Unsupported exit mode: {self.exit_mode}")
        if self.min_risk_reward <= 0:
            raise ValueError(f"Unsupported min risk reward: {self.min_risk_reward}")
        if self.direction_mode not in self.VALID_DIRECTION_MODES:
            raise ValueError(f"Unsupported direction mode: {self.direction_mode}")
        if self.auto_trend_fallback not in self.VALID_AUTO_TREND_FALLBACKS:
            raise ValueError(f"Unsupported auto trend fallback: {self.auto_trend_fallback}")
