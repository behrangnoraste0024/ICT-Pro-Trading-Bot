from __future__ import annotations

from typing import Any

from models.market_context import MarketContext
from models.strategy_signal import StrategySignalResult


class ICTStrategy:
    """Pure advisory ICT/SMC strategy signal evaluator."""

    def check_trend(self, close: float, ema200: float) -> str:
        return "Bullish" if close > ema200 else "Bearish"

    def evaluate(self, context: MarketContext) -> StrategySignalResult:
        direction = self._direction(context)
        reasons = self._reasons(context, direction)
        blockers = self._blockers(context, direction)
        confidence_score = 0.0 if blockers else self._confidence_score(context, direction, reasons)
        signal_status = "SIGNAL" if direction in {"LONG", "SHORT"} and not blockers else "NO_SIGNAL"

        return StrategySignalResult(
            signal_status=signal_status,
            direction=direction if signal_status == "SIGNAL" else "NONE",
            confidence_score=confidence_score,
            reasons=reasons,
            blockers=blockers,
            source_evidence=self._source_evidence(context),
        )

    def _direction(self, context: MarketContext) -> str:
        setup_bias = _normalized(getattr(context, "setup_bias", None))
        entry_direction = _normalized(getattr(context, "entry_direction", None))
        trend = _normalized(getattr(context, "trend", None))
        ote_direction = _normalized(getattr(context, "ote_direction", None))

        long_votes = sum(value in {"LONG", "BULLISH"} for value in (setup_bias, entry_direction, trend, ote_direction))
        short_votes = sum(value in {"SHORT", "BEARISH"} for value in (setup_bias, entry_direction, trend, ote_direction))

        if long_votes >= 2 and long_votes > short_votes:
            return "LONG"
        if short_votes >= 2 and short_votes > long_votes:
            return "SHORT"
        return "NONE"

    def _reasons(self, context: MarketContext, direction: str) -> list[str]:
        reasons: list[str] = []
        if direction in {"LONG", "SHORT"}:
            reasons.append(f"{direction} directional context is aligned")
        if _entry_trigger_present(context):
            reasons.append("entry trigger evidence is present")
        if _entry_confirmed(context):
            reasons.append("entry is confirmed")
        if _entry_status_confirmed(context):
            reasons.append("entry status is confirmed")
        if _normalized(getattr(context, "setup_status", None)) == "VALID":
            reasons.append("setup status is valid")
        if getattr(context, "in_ote_zone", False):
            reasons.append("price is in OTE zone")
        if _liquidity_confirmed(context):
            reasons.append("liquidity evidence is present")
        if _liquidity_sweep_confirmed(context):
            reasons.append("liquidity sweep evidence is present")
        if _fvg_confirmed(context):
            reasons.append("fair value gap evidence is present")
        if _order_block_confirmed(context):
            reasons.append("order block evidence is present")
        if _breaker_block_confirmed(context):
            reasons.append("breaker block evidence is present")
        if _displacement_state(context) in {"CONFIRMED", "PRESENT", "VALID", "STRONG"}:
            reasons.append("displacement evidence is confirmed")
        if _session_filter_state(context) in {"ALLOWED", "ACTIVE", "VALID", "IN_SESSION"}:
            reasons.append("session filter allows strategy evaluation")
        if _premium_discount_aligned(context, direction):
            reasons.append(f"premium/discount evidence supports {direction}")
        if _trend_bias_aligned(context, direction):
            reasons.append(f"trend bias supports {direction}")
        if _market_structure_confirmed(context):
            reasons.append("market structure evidence is present")
        if _swing_context_confirmed(context):
            reasons.append("swing context evidence is present")
        if not reasons:
            reasons.append("no aligned advisory strategy evidence")
        return reasons

    def _blockers(self, context: MarketContext, direction: str) -> list[str]:
        blockers: list[str] = []
        blockers.extend(_strings(getattr(context, "setup_blockers", None)))
        blockers.extend(_strings(getattr(context, "entry_blockers", None)))

        if direction == "NONE":
            blockers.append("directional context is not aligned")
        if _normalized(getattr(context, "setup_status", None)) != "VALID":
            blockers.append("setup status is not valid")
        if not _entry_trigger_present(context):
            blockers.append("entry trigger evidence is missing")
        if not _entry_confirmed(context):
            blockers.append("entry is not confirmed")
        if not _entry_status_confirmed(context):
            blockers.append("entry status is not confirmed")
        if _displacement_state(context) not in {"CONFIRMED", "PRESENT", "VALID", "STRONG"}:
            blockers.append("displacement evidence is not confirmed")
        if _session_filter_state(context) not in {"ALLOWED", "ACTIVE", "VALID", "IN_SESSION"}:
            blockers.append("session filter does not allow strategy evaluation")
        if direction in {"LONG", "SHORT"} and not _premium_discount_aligned(context, direction):
            blockers.append("premium/discount evidence is not aligned")
        if direction in {"LONG", "SHORT"} and not _trend_bias_aligned(context, direction):
            blockers.append("trend bias is not aligned")
        if not _market_structure_confirmed(context):
            blockers.append("market structure evidence is missing")
        if not _swing_context_confirmed(context):
            blockers.append("swing context evidence is insufficient")
        if not _liquidity_confirmed(context):
            blockers.append("liquidity evidence is missing")
        if not _liquidity_sweep_confirmed(context):
            blockers.append("liquidity sweep evidence is missing")
        if not _fvg_confirmed(context):
            blockers.append("fair value gap evidence is missing")
        if not _order_block_confirmed(context):
            blockers.append("order block evidence is missing")
        if not _breaker_block_confirmed(context):
            blockers.append("breaker block evidence is missing")

        return _unique(blockers)

    def _confidence_score(self, context: MarketContext, direction: str, reasons: list[str]) -> float:
        score = 0.35
        if direction in {"LONG", "SHORT"}:
            score += 0.15
        if _normalized(getattr(context, "setup_status", None)) == "VALID":
            score += 0.15
        if _entry_trigger_present(context):
            score += 0.05
        if _entry_confirmed(context):
            score += 0.15
        if _entry_status_confirmed(context):
            score += 0.05
        if getattr(context, "in_ote_zone", False):
            score += 0.05
        if _liquidity_confirmed(context):
            score += 0.05
        if _liquidity_sweep_confirmed(context):
            score += 0.05
        if _fvg_confirmed(context):
            score += 0.05
        if _order_block_confirmed(context):
            score += 0.05
        if _breaker_block_confirmed(context):
            score += 0.05
        if _displacement_state(context) in {"CONFIRMED", "PRESENT", "VALID", "STRONG"}:
            score += 0.05
        if _session_filter_state(context) in {"ALLOWED", "ACTIVE", "VALID", "IN_SESSION"}:
            score += 0.05
        if _premium_discount_aligned(context, direction):
            score += 0.05
        if _trend_bias_aligned(context, direction):
            score += 0.05
        if _market_structure_confirmed(context):
            score += 0.05
        if _swing_context_confirmed(context):
            score += 0.05
        if len(reasons) >= 5:
            score += 0.05
        return round(min(score, 1.0), 4)

    def _source_evidence(self, context: MarketContext) -> dict[str, Any]:
        return {
            "candles_present": getattr(context, "candles", None) is not None,
            "swings_count": _count(getattr(context, "swings", None)),
            "structure_count": _count(getattr(context, "structure", None)),
            "trend": getattr(context, "trend", None),
            "bos_count": _count(getattr(context, "bos", None)),
            "choch_count": _count(getattr(context, "choch", None)),
            "liquidity_count": _count(getattr(context, "liquidity", None)),
            "liquidity_sweeps_count": _count(getattr(context, "liquidity_sweeps", None)),
            "fvgs_count": _count(getattr(context, "fvgs", None)),
            "order_blocks_count": _count(getattr(context, "order_blocks", None)),
            "breaker_blocks_count": _count(getattr(context, "breaker_blocks", None)),
            "dealing_range_high_present": getattr(context, "dealing_range_high", None) is not None,
            "dealing_range_low_present": getattr(context, "dealing_range_low", None) is not None,
            "current_price_zone": getattr(context, "current_price_zone", None),
            "current_price_present": getattr(context, "current_price", None) is not None,
            "premium_zone_present": getattr(context, "premium_zone", None) is not None,
            "discount_zone_present": getattr(context, "discount_zone", None) is not None,
            "ote_direction": getattr(context, "ote_direction", None),
            "in_ote_zone": getattr(context, "in_ote_zone", None),
            "setup_bias": getattr(context, "setup_bias", None),
            "setup_status": getattr(context, "setup_status", None),
            "setup_score": getattr(context, "setup_score", None),
            "entry_trigger_present": _entry_trigger_present(context),
            "entry_status": getattr(context, "entry_status", None),
            "entry_direction": getattr(context, "entry_direction", None),
            "entry_trigger_type": getattr(context, "entry_trigger_type", None),
            "entry_confirmed": _entry_confirmed(context),
            "entry_blockers_count": _count(getattr(context, "entry_blockers", None)),
            "entry_present": getattr(context, "entry", None) is not None,
            "displacement_state": _displacement_state(context),
            "session_filter_state": _session_filter_state(context),
            "premium_discount_state": _premium_discount_state(context),
            "trend_bias_state": _trend_bias_state(context),
            "market_structure_present": _market_structure_confirmed(context),
            "swing_context_present": _swing_context_confirmed(context),
            "liquidity_present": _liquidity_confirmed(context),
            "liquidity_sweep_present": _liquidity_sweep_confirmed(context),
            "fvg_present": _fvg_confirmed(context),
            "order_block_present": _order_block_confirmed(context),
            "breaker_block_present": _breaker_block_confirmed(context),
            "external_structure_present": getattr(context, "external_high", None) is not None
            and getattr(context, "external_low", None) is not None,
            "internal_structure_count": _count(getattr(context, "internal_highs", None))
            + _count(getattr(context, "internal_lows", None)),
        }


def evaluate_strategy_signal(context: MarketContext) -> StrategySignalResult:
    return ICTStrategy().evaluate(context)


def _normalized(value: Any) -> str:
    if value is None:
        return "NONE"
    return str(value).strip().upper()


def _displacement_state(context: MarketContext) -> str:
    return _first_normalized(
        context,
        (
            "displacement_state",
            "displacement_status",
            "displacement",
            "has_displacement",
        ),
    )


def _session_filter_state(context: MarketContext) -> str:
    return _first_normalized(
        context,
        (
            "session_filter_state",
            "session_status",
            "session",
            "in_session",
        ),
    )


def _premium_discount_state(context: MarketContext) -> str:
    return _first_normalized(
        context,
        (
            "premium_discount_state",
            "premium_discount_zone",
            "price_zone",
            "current_price_zone",
        ),
    )


def _trend_bias_state(context: MarketContext) -> str:
    return _first_normalized(
        context,
        (
            "trend_bias_state",
            "trend_bias",
            "trend",
        ),
    )


def _premium_discount_aligned(context: MarketContext, direction: str) -> bool:
    state = _premium_discount_state(context)
    if direction == "LONG":
        return state == "DISCOUNT"
    if direction == "SHORT":
        return state == "PREMIUM"
    return False


def _trend_bias_aligned(context: MarketContext, direction: str) -> bool:
    state = _trend_bias_state(context)
    if direction == "LONG":
        return state in {"LONG", "BULLISH"}
    if direction == "SHORT":
        return state in {"SHORT", "BEARISH"}
    return False


def _market_structure_confirmed(context: MarketContext) -> bool:
    return (
        _has_items(getattr(context, "structure", None))
        or _has_items(getattr(context, "bos", None))
        or _has_items(getattr(context, "choch", None))
        or (
            getattr(context, "external_high", None) is not None
            and getattr(context, "external_low", None) is not None
        )
        or _has_items(getattr(context, "internal_highs", None))
        or _has_items(getattr(context, "internal_lows", None))
    )


def _swing_context_confirmed(context: MarketContext) -> bool:
    return _count(getattr(context, "swings", None)) >= 2


def _liquidity_confirmed(context: MarketContext) -> bool:
    return _has_items(getattr(context, "liquidity", None))


def _liquidity_sweep_confirmed(context: MarketContext) -> bool:
    return _has_items(getattr(context, "liquidity_sweeps", None))


def _fvg_confirmed(context: MarketContext) -> bool:
    return _has_items(getattr(context, "fvgs", None))


def _order_block_confirmed(context: MarketContext) -> bool:
    return _has_items(getattr(context, "order_blocks", None))


def _breaker_block_confirmed(context: MarketContext) -> bool:
    return _has_items(getattr(context, "breaker_blocks", None))


def _entry_trigger_present(context: MarketContext) -> bool:
    return getattr(context, "entry_trigger", None) is not None or _normalized(
        getattr(context, "entry_trigger_type", None)
    ) not in {"NONE", "MISSING", "NOT_CONFIRMED"}


def _entry_confirmed(context: MarketContext) -> bool:
    return bool(getattr(context, "entry_confirmed", False))


def _entry_status_confirmed(context: MarketContext) -> bool:
    return _normalized(getattr(context, "entry_status", None)) == "CONFIRMED"


def _first_normalized(context: MarketContext, names: tuple[str, ...]) -> str:
    for name in names:
        if hasattr(context, name):
            value = getattr(context, name)
            if isinstance(value, bool):
                return "CONFIRMED" if value else "BLOCKED"
            normalized = _normalized(value)
            if normalized != "NONE":
                return normalized
    return "MISSING"


def _has_items(value: Any) -> bool:
    return _count(value) > 0


def _count(value: Any) -> int:
    if value is None:
        return 0
    try:
        return len(value)
    except TypeError:
        return 1


def _strings(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return [str(item) for item in value]
    except TypeError:
        return [str(value)]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
