from __future__ import annotations

from models.market_context import MarketContext


class DirectionQualityEngine:
    VALID_MODES = {"off", "long_strict", "short_strict", "both_strict"}

    def apply(
        self,
        context: MarketContext,
        direction_quality_mode: str = "off",
        strict_long_require_regime_known: bool = False,
        strict_long_block_unknown_regime: bool = False,
        strict_long_require_regime_bullish: bool = False,
        strict_long_require_displacement: bool = False,
        strict_long_min_setup_score: int | None = None,
        strict_short_require_regime_known: bool = False,
        strict_short_block_unknown_regime: bool = False,
        strict_short_require_regime_bearish: bool = False,
        strict_short_require_displacement: bool = False,
        strict_short_min_setup_score: int | None = None,
    ) -> MarketContext:
        self._reset(context, direction_quality_mode)

        if direction_quality_mode not in self.VALID_MODES:
            self._block(context, "UNKNOWN", ["INVALID_DIRECTION_QUALITY_MODE"])
            return context

        context.direction_quality_applied = direction_quality_mode

        if getattr(context, "trade_plan_status", None) != "PLANNED":
            context.direction_quality_allowed = None
            context.direction_quality_blocker = "NO_PLANNED_TRADE"
            context.direction_quality_reasons = ["NO_PLANNED_TRADE"]
            self._update_debug(context)
            return context

        direction = self._normalize_direction(getattr(context, "trade_direction", None))
        if direction_quality_mode == "off":
            context.direction_quality_allowed = True
            context.direction_quality_reasons = ["QUALITY_MODE_OFF"]
            self._update_debug(context)
            return context

        if not self._mode_applies(direction_quality_mode, direction):
            context.direction_quality_allowed = True
            context.direction_quality_reasons = ["STRICT_MODE_NOT_APPLICABLE"]
            self._update_debug(context)
            return context

        if direction == "LONG":
            failures = self._long_failures(
                context,
                strict_long_require_regime_known,
                strict_long_block_unknown_regime,
                strict_long_require_regime_bullish,
                strict_long_require_displacement,
                strict_long_min_setup_score,
            )
        elif direction == "SHORT":
            failures = self._short_failures(
                context,
                strict_short_require_regime_known,
                strict_short_block_unknown_regime,
                strict_short_require_regime_bearish,
                strict_short_require_displacement,
                strict_short_min_setup_score,
            )
        else:
            failures = ["INVALID_TRADE_DIRECTION"]

        if failures:
            self._block(context, direction, failures)
            return context

        context.direction_quality_allowed = True
        context.direction_quality_reasons = ["STRICT_RULES_PASSED"]
        self._update_debug(context)
        return context

    def _reset(self, context: MarketContext, mode: str) -> None:
        context.direction_quality_mode_requested = mode
        context.direction_quality_applied = None
        context.direction_quality_allowed = None
        context.direction_quality_blocked_direction = None
        context.direction_quality_blocker = None
        context.direction_quality_reasons = []

    def _block(self, context: MarketContext, direction: str, reasons: list[str]) -> None:
        context.direction_quality_allowed = False
        context.direction_quality_blocked_direction = direction
        context.direction_quality_blocker = reasons[0] if reasons else None
        context.direction_quality_reasons = reasons
        self._update_debug(context)

    def _long_failures(
        self,
        context: MarketContext,
        require_regime_known: bool,
        block_unknown_regime: bool,
        require_regime_bullish: bool,
        require_displacement: bool,
        min_setup_score: int | None,
    ) -> list[str]:
        failures: list[str] = []
        regime = self._regime(context)
        if (require_regime_known or block_unknown_regime) and regime == "UNKNOWN":
            failures.append("STRICT_LONG_UNKNOWN_REGIME")
        if require_regime_bullish and regime != "BULLISH":
            failures.append("STRICT_LONG_NOT_BULLISH_REGIME")
        if require_displacement and self._entry_trigger_type(context) != "DISPLACEMENT":
            failures.append("STRICT_LONG_NO_DISPLACEMENT")
        score = self._setup_score(context)
        if min_setup_score is not None and (score is None or score < min_setup_score):
            failures.append("STRICT_LONG_SETUP_SCORE_TOO_LOW")
        return failures

    def _short_failures(
        self,
        context: MarketContext,
        require_regime_known: bool,
        block_unknown_regime: bool,
        require_regime_bearish: bool,
        require_displacement: bool,
        min_setup_score: int | None,
    ) -> list[str]:
        failures: list[str] = []
        regime = self._regime(context)
        if (require_regime_known or block_unknown_regime) and regime == "UNKNOWN":
            failures.append("STRICT_SHORT_UNKNOWN_REGIME")
        if require_regime_bearish and regime != "BEARISH":
            failures.append("STRICT_SHORT_NOT_BEARISH_REGIME")
        if require_displacement and self._entry_trigger_type(context) != "DISPLACEMENT":
            failures.append("STRICT_SHORT_NO_DISPLACEMENT")
        score = self._setup_score(context)
        if min_setup_score is not None and (score is None or score < min_setup_score):
            failures.append("STRICT_SHORT_SETUP_SCORE_TOO_LOW")
        return failures

    def _mode_applies(self, mode: str, direction: str) -> bool:
        return mode == "both_strict" or (mode == "long_strict" and direction == "LONG") or (
            mode == "short_strict" and direction == "SHORT"
        )

    def _normalize_direction(self, direction) -> str:
        value = str(direction or "UNKNOWN").upper()
        if value in ("BULLISH", "LONG", "BUY"):
            return "LONG"
        if value in ("BEARISH", "SHORT", "SELL"):
            return "SHORT"
        return "UNKNOWN"

    def _regime(self, context: MarketContext) -> str:
        value = str(getattr(context, "market_regime", None) or "UNKNOWN").upper()
        return value if value in ("BULLISH", "BEARISH", "RANGE", "UNKNOWN") else "UNKNOWN"

    def _entry_trigger_type(self, context: MarketContext) -> str:
        for value in (
            getattr(context, "entry_trigger_type", None),
            getattr(getattr(context, "entry_trigger", None), "trigger_type", None),
        ):
            if value:
                return str(value).upper()
        return "NONE"

    def _setup_score(self, context: MarketContext) -> int | None:
        for value in (
            getattr(context, "setup_score", None),
            getattr(getattr(context, "active_setup", None), "score", None),
        ):
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    def _update_debug(self, context: MarketContext) -> None:
        if not hasattr(context, "debug") or context.debug is None:
            return
        context.debug["direction_quality_mode_requested"] = context.direction_quality_mode_requested
        context.debug["direction_quality_applied"] = context.direction_quality_applied
        context.debug["direction_quality_allowed"] = context.direction_quality_allowed
        context.debug["direction_quality_blocked_direction"] = context.direction_quality_blocked_direction
        context.debug["direction_quality_blocker"] = context.direction_quality_blocker
        context.debug["direction_quality_reasons"] = context.direction_quality_reasons
