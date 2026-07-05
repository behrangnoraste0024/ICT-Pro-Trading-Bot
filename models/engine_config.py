from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EngineConfig:
    VALID_DEALING_RANGE_MODES = {"current_external", "recent_50"}
    VALID_EXIT_MODES = {"original", "fixed_1r", "fixed_1_5r", "fixed_2r", "fixed_3r"}
    VALID_DIRECTION_MODES = {"all", "long_only", "short_only", "auto_trend", "regime_trend"}
    VALID_AUTO_TREND_FALLBACKS = {"all", "block"}
    VALID_REGIME_MODES = {"rolling_return"}
    VALID_REGIME_FALLBACKS = {"all", "block"}
    VALID_DIRECTION_QUALITY_MODES = {"off", "long_strict", "short_strict", "both_strict"}
    VALID_STRATEGY_PROFILES = {
        "default",
        "balanced_smc",
        "bearish_smc",
        "research_baseline",
        "balanced_smc_decision_065",
        "bearish_smc_decision_065",
    }
    VALID_COST_MODELS = {"off", "percent"}
    VALID_DECISION_FILTER_MODES = {"off", "approve_only", "warning_only", "reject_only", "approve_or_warning"}

    strategy_profile: str = "default"
    dealing_range_mode: str = "current_external"
    exit_mode: str = "original"
    min_risk_reward: float = 2.0
    direction_mode: str = "all"
    auto_trend_fallback: str = "all"
    regime_mode: str = "rolling_return"
    regime_lookback: int = 200
    regime_threshold_pct: float = 0.0
    regime_fallback: str = "all"
    direction_quality_mode: str = "off"
    strict_long_require_regime_known: bool = False
    strict_long_block_unknown_regime: bool = False
    strict_long_require_regime_bullish: bool = False
    strict_long_require_displacement: bool = False
    strict_long_min_setup_score: int | None = None
    strict_short_require_regime_known: bool = False
    strict_short_block_unknown_regime: bool = False
    strict_short_require_regime_bearish: bool = False
    strict_short_require_displacement: bool = False
    strict_short_min_setup_score: int | None = None
    cost_model: str = "off"
    commission_pct: float = 0.0
    slippage_pct: float = 0.0
    spread_pct: float = 0.0
    decision_filter_mode: str = "off"
    decision_score_threshold: float | None = None

    def __post_init__(self) -> None:
        if self.strategy_profile not in self.VALID_STRATEGY_PROFILES:
            raise ValueError(f"Unsupported strategy profile: {self.strategy_profile}")
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
        if self.regime_mode not in self.VALID_REGIME_MODES:
            raise ValueError(f"Unsupported regime mode: {self.regime_mode}")
        if self.regime_lookback <= 0:
            raise ValueError(f"Unsupported regime lookback: {self.regime_lookback}")
        if self.regime_threshold_pct < 0:
            raise ValueError(f"Unsupported regime threshold pct: {self.regime_threshold_pct}")
        if self.regime_fallback not in self.VALID_REGIME_FALLBACKS:
            raise ValueError(f"Unsupported regime fallback: {self.regime_fallback}")
        if self.direction_quality_mode not in self.VALID_DIRECTION_QUALITY_MODES:
            raise ValueError(f"Unsupported direction quality mode: {self.direction_quality_mode}")
        for field_name in ("strict_long_min_setup_score", "strict_short_min_setup_score"):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"Unsupported {field_name}: {value}")
        if self.cost_model not in self.VALID_COST_MODELS:
            raise ValueError(f"Unsupported cost model: {self.cost_model}")
        for field_name in ("commission_pct", "slippage_pct", "spread_pct"):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"Unsupported {field_name}: {value}")
        if self.decision_filter_mode not in self.VALID_DECISION_FILTER_MODES:
            raise ValueError(f"Unsupported decision filter mode: {self.decision_filter_mode}")
        if self.decision_score_threshold is not None and not 0 <= self.decision_score_threshold <= 1:
            raise ValueError(f"Unsupported decision score threshold: {self.decision_score_threshold}")
