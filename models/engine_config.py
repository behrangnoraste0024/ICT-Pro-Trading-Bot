from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EngineConfig:
    VALID_DEALING_RANGE_MODES = {"current_external", "recent_50"}
    VALID_EXIT_MODES = {"original", "fixed_1r", "fixed_1_5r", "fixed_2r", "fixed_3r"}

    dealing_range_mode: str = "current_external"
    exit_mode: str = "original"
    min_risk_reward: float = 2.0

    def __post_init__(self) -> None:
        if self.dealing_range_mode not in self.VALID_DEALING_RANGE_MODES:
            raise ValueError(f"Unsupported dealing range mode: {self.dealing_range_mode}")
        if self.exit_mode not in self.VALID_EXIT_MODES:
            raise ValueError(f"Unsupported exit mode: {self.exit_mode}")
        if self.min_risk_reward <= 0:
            raise ValueError(f"Unsupported min risk reward: {self.min_risk_reward}")
