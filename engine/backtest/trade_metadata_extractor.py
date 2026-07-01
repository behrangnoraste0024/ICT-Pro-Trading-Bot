from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from dataclasses import is_dataclass
from typing import Any


METADATA_PATHS: dict[str, list[str]] = {
    "setup_score": [
        "setup_score",
        "setup_event.score",
        "active_setup.score",
        "active_setup.setup_score",
        "active_setup.total_score",
        "setup.score",
        "setup.score_total",
        "latest_valid_setup.score",
        "latest_setup.score",
    ],
    "setup_status": [
        "setup_status",
        "active_setup.status",
        "setup_event.status",
        "setup.status",
        "latest_valid_setup.status",
        "latest_setup.status",
    ],
    "setup_bias": [
        "setup_bias",
        "active_setup.bias",
        "active_setup.direction",
        "setup_event.bias",
        "setup_event.direction",
        "setup.bias",
        "setup.direction",
        "latest_valid_setup.direction",
        "latest_setup.direction",
    ],
    "entry_status": [
        "entry_trigger_status",
        "entry_status",
        "entry_trigger.status",
        "entry_trigger_event.status",
        "entry.status",
        "latest_confirmed_entry_trigger.status",
        "latest_entry_trigger.status",
    ],
    "entry_trigger_type": [
        "entry_trigger_type",
        "entry_trigger.trigger_type",
        "entry_trigger_event.trigger_type",
        "entry_trigger.event_type",
        "entry.trigger_type",
        "latest_confirmed_entry_trigger.trigger_type",
        "latest_entry_trigger.trigger_type",
    ],
    "dealing_range_mode_applied": ["dealing_range_mode_applied"],
    "dealing_range_mode_requested": ["dealing_range_mode_requested"],
    "dealing_range_mode_fallback_reason": ["dealing_range_mode_fallback_reason"],
    "current_price_zone": [
        "current_price_zone",
        "premium_discount.current_price_zone",
        "premium_discount.zone",
        "price_zone",
        "active_setup.price_zone",
        "setup_event.price_zone",
        "setup.price_zone",
        "latest_valid_setup.price_zone",
        "latest_setup.price_zone",
    ],
    "in_ote_zone": [
        "in_ote_zone",
        "ote.in_ote_zone",
        "ote.in_zone",
        "active_setup.in_ote_zone",
        "setup_event.in_ote_zone",
        "setup.in_ote_zone",
        "latest_valid_setup.in_ote_zone",
        "latest_setup.in_ote_zone",
    ],
    "ote_direction": [
        "ote_direction",
        "ote.direction",
        "ote.ote_direction",
        "active_setup.ote_direction",
        "setup_event.ote_direction",
        "setup.ote_direction",
        "latest_valid_setup.ote_direction",
        "latest_setup.ote_direction",
    ],
    "dealing_range_high": ["dealing_range_high", "ote.dealing_range_high"],
    "dealing_range_low": ["dealing_range_low", "ote.dealing_range_low"],
    "equilibrium": ["equilibrium"],
    "active_setup": ["active_setup"],
    "matched_pois": [
        "active_setup.matched_pois",
        "setup_event.matched_pois",
        "matched_pois",
        "setup_matched_pois",
        "poi_matches",
        "active_setup.poi_matches",
        "latest_valid_setup.matched_pois",
        "latest_setup.matched_pois",
    ],
    "setup_matched_pois": ["setup_matched_pois"],
    "trade_quality_status": [
        "trade_quality_status",
        "trade_quality.status",
        "trade_quality_event.status",
        "latest_trade_quality_event.status",
    ],
    "trade_quality_score": [
        "trade_quality_score",
        "trade_quality.score",
        "trade_quality_event.score",
        "latest_trade_quality_event.score",
    ],
    "setup_blockers": [
        "setup_blockers",
        "active_setup.blockers",
        "setup_event.blockers",
        "latest_valid_setup.blockers",
        "latest_setup.blockers",
    ],
    "entry_blockers": [
        "entry_blockers",
        "entry_trigger.blockers",
        "entry_trigger_event.blockers",
        "latest_entry_trigger.blockers",
    ],
    "trade_plan_blockers": ["trade_plan_blockers", "trade_plan.blockers"],
    "trade_quality_blockers": [
        "trade_quality_blockers",
        "trade_quality.blockers",
        "trade_quality_event.blockers",
        "latest_trade_quality_event.blockers",
    ],
    "paper_trade_blockers": ["paper_trade_blockers", "paper_trade.blockers"],
    "trade_quality_reasons": [
        "trade_quality_reasons",
        "trade_quality.reasons",
        "trade_quality_event.reasons",
        "latest_trade_quality_event.reasons",
    ],
    "trade_direction": ["trade_direction", "trade_plan.direction"],
    "entry_direction": [
        "entry_direction",
        "entry_trigger.direction",
        "entry_trigger_event.direction",
        "latest_confirmed_entry_trigger.direction",
        "latest_entry_trigger.direction",
    ],
    "trade_plan_direction": ["trade_plan_direction"],
    "planned_entry_price": ["planned_entry_price", "trade_plan.entry_price"],
    "planned_stop_loss": ["planned_stop_loss", "trade_plan.stop_loss"],
    "planned_take_profit": ["planned_take_profit", "trade_plan.take_profit"],
    "planned_risk": ["planned_risk", "trade_plan.risk"],
    "planned_reward": ["planned_reward", "trade_plan.reward"],
    "planned_risk_reward": ["planned_risk_reward", "trade_plan.risk_reward"],
    "current_price": [
        "current_price",
        "active_setup.current_price",
        "entry_trigger.current_price",
        "latest_confirmed_entry_trigger.current_price",
        "latest_entry_trigger.current_price",
    ],
    "market_regime": ["market_regime"],
    "market_regime_mode": ["market_regime_mode"],
    "market_regime_lookback": ["market_regime_lookback"],
    "market_regime_threshold_pct": ["market_regime_threshold_pct"],
    "market_regime_return_pct": ["market_regime_return_pct"],
    "market_regime_fallback": ["market_regime_fallback"],
    "market_regime_reason": ["market_regime_reason"],
    "direction_mode_requested": ["direction_mode_requested"],
    "direction_mode_applied": ["direction_mode_applied"],
    "direction_mode_allowed": ["direction_mode_allowed"],
    "direction_mode_blocked_direction": ["direction_mode_blocked_direction"],
    "direction_mode_fallback_reason": ["direction_mode_fallback_reason"],
    "direction_mode_resolved_direction": ["direction_mode_resolved_direction"],
    "auto_trend_source_trend": ["auto_trend_source_trend"],
    "auto_trend_fallback": ["auto_trend_fallback"],
    "regime_source_regime": ["regime_source_regime"],
    "regime_fallback": ["regime_fallback"],
}

MISSING_VALUES: dict[str, set[Any]] = {
    "setup_score": {0},
    "setup_status": {"INVALID"},
    "setup_bias": {"NONE"},
    "entry_status": {"NOT_CONFIRMED"},
    "entry_trigger_type": {"NONE"},
    "current_price_zone": {"UNKNOWN"},
    "in_ote_zone": {False},
    "ote_direction": {"NONE"},
    "trade_quality_status": {"REJECTED"},
    "trade_quality_score": {0},
    "trade_direction": {"NONE"},
    "entry_direction": {"NONE"},
    "trade_plan_direction": {"NONE"},
}

CANDIDATE_TOKENS = (
    "setup",
    "entry",
    "trigger",
    "quality",
    "zone",
    "ote",
    "poi",
    "premium",
    "discount",
    "range",
    "regime",
    "direction",
)

NESTED_CANDIDATE_FIELDS = (
    "active_setup",
    "setup_event",
    "entry_trigger",
    "entry_trigger_event",
    "trade_quality",
    "trade_quality_event",
    "premium_discount",
    "ote",
    "paper_trade",
    "trade_plan",
)


def extract_trade_metadata_from_context(context) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for field_name, paths in METADATA_PATHS.items():
        value = _get_first_available(context, paths, missing=MISSING_VALUES.get(field_name))
        if value is not None:
            metadata[field_name] = deepcopy(value)
    return metadata


def apply_trade_metadata_to_context(context, metadata: dict[str, Any]) -> None:
    for field_name, value in metadata.items():
        setattr(context, field_name, deepcopy(value))


def debug_extract_available_trade_metadata(context) -> dict[str, Any]:
    top_level = {}
    for field_name in sorted(_context_field_names(context)):
        if any(token in field_name.lower() for token in CANDIDATE_TOKENS):
            top_level[field_name] = _summarize_value(_get_child(context, field_name))

    nested = {}
    for field_name in NESTED_CANDIDATE_FIELDS:
        value = getattr(context, field_name, None)
        if value is not None:
            nested[field_name] = _object_summary(value)

    for list_name in ("setups", "entry_triggers", "trade_quality_events"):
        values = getattr(context, list_name, None)
        if values:
            nested[list_name] = [_object_summary(value) for value in values[-3:]]

    return {
        "top_level_candidate_fields": top_level,
        "nested_candidate_objects": nested,
        "extracted_metadata": {
            key: _summarize_value(value) for key, value in extract_trade_metadata_from_context(context).items()
        },
    }


def _get_first_available(context, paths: list[str], missing: set[Any] | None = None) -> Any:
    for path in paths:
        value = _resolve_path(context, path)
        if _is_meaningful(value, missing):
            return value
    return None


def _resolve_path(context, path: str) -> Any:
    sources = _derived_sources(context)
    current = sources.get(path.split(".", 1)[0], _MISSING)
    if current is _MISSING:
        current = _get_child(context, path.split(".", 1)[0])
    if current is _MISSING:
        return None

    parts = path.split(".")[1:]
    for part in parts:
        current = _get_child(current, part)
        if current is _MISSING:
            return None
    return current


def _derived_sources(context) -> dict[str, Any]:
    setups = list(getattr(context, "setups", []) or [])
    entry_triggers = list(getattr(context, "entry_triggers", []) or [])
    quality_events = list(getattr(context, "trade_quality_events", []) or [])

    latest_valid_setup = _latest_matching(setups, "status", "VALID")
    latest_setup = setups[-1] if setups else None
    latest_confirmed_trigger = _latest_matching(entry_triggers, "confirmed", True) or _latest_matching(
        entry_triggers, "status", "CONFIRMED"
    )
    latest_entry_trigger = entry_triggers[-1] if entry_triggers else None
    latest_quality_event = quality_events[-1] if quality_events else None

    return {
        "latest_valid_setup": latest_valid_setup,
        "latest_setup": latest_setup,
        "latest_confirmed_entry_trigger": latest_confirmed_trigger,
        "latest_entry_trigger": latest_entry_trigger,
        "latest_trade_quality_event": latest_quality_event,
    }


def _latest_matching(values: list[Any], field_name: str, expected: Any) -> Any:
    for value in reversed(values):
        if getattr(value, field_name, None) == expected:
            return value
    return None


def _get_child(value: Any, field_name: str) -> Any:
    if value is None:
        return _MISSING
    if isinstance(value, dict):
        return value.get(field_name, _MISSING)
    return getattr(value, field_name, _MISSING)


def _is_meaningful(value: Any, missing: set[Any] | None = None) -> bool:
    if value is None or value is _MISSING:
        return False
    if missing is not None and value in missing:
        return False
    return True


def _context_field_names(context) -> set[str]:
    names = set(getattr(context, "__dict__", {}).keys())
    if is_dataclass(context):
        names.update(getattr(context, "__dataclass_fields__", {}).keys())
    return names


def _object_summary(value: Any) -> dict[str, Any] | str:
    try:
        if is_dataclass(value):
            raw = asdict(value)
        elif isinstance(value, dict):
            raw = value
        else:
            raw = vars(value)
    except TypeError:
        return _summarize_value(value)

    return {
        key: _summarize_value(item)
        for key, item in raw.items()
        if any(token in key.lower() for token in CANDIDATE_TOKENS)
    }


def _summarize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_summarize_value(item) for item in value[:5]]
    if isinstance(value, tuple):
        return tuple(_summarize_value(item) for item in value[:5])
    if isinstance(value, dict):
        return {str(key): _summarize_value(item) for key, item in list(value.items())[:10]}
    return str(value)


class _Missing:
    pass


_MISSING = _Missing()
