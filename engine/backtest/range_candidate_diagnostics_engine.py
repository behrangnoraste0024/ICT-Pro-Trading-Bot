from __future__ import annotations

from statistics import median
from typing import Any

import pandas as pd

from models.market_context import MarketContext
from models.range_candidate_diagnostics import RangeCandidateDiagnostics, RangeCandidateStats


class RangeCandidateDiagnosticsEngine:
    CANDIDATE_ORDER = [
        "CURRENT_EXTERNAL_RANGE",
        "RECENT_50_CANDLE_RANGE",
        "RECENT_100_CANDLE_RANGE",
        "RECENT_200_CANDLE_RANGE",
        "RECENT_SWING_RANGE",
    ]

    def collect_from_context(self, context: MarketContext) -> RangeCandidateDiagnostics:
        return self.summarize_contexts([context])

    def summarize_contexts(self, contexts: list[MarketContext]) -> RangeCandidateDiagnostics:
        diagnostics = RangeCandidateDiagnostics(
            windows_analyzed=len(contexts),
            candidates={name: RangeCandidateStats(candidate_name=name) for name in self.CANDIDATE_ORDER},
        )
        distance_lists: dict[str, list[float]] = {name: [] for name in self.CANDIDATE_ORDER}
        range_size_lists: dict[str, list[float]] = {name: [] for name in self.CANDIDATE_ORDER}
        range_size_percent_lists: dict[str, list[float]] = {name: [] for name in self.CANDIDATE_ORDER}

        for context in contexts:
            current_eval = self._evaluate_candidate(context, self._current_external_range(context))
            for name in self.CANDIDATE_ORDER:
                candidate = self._candidate_for_name(context, name)
                evaluation = self._evaluate_candidate(context, candidate)
                stats = diagnostics.candidates[name]
                self._apply_evaluation(stats, evaluation, current_eval)
                if evaluation["distance_to_ote"] is not None:
                    distance_lists[name].append(evaluation["distance_to_ote"])
                if evaluation["range_size"] is not None:
                    range_size_lists[name].append(evaluation["range_size"])
                if evaluation["range_size_percent"] is not None:
                    range_size_percent_lists[name].append(evaluation["range_size_percent"])

        for name, stats in diagnostics.candidates.items():
            distances = distance_lists[name]
            range_sizes = range_size_lists[name]
            range_size_percents = range_size_percent_lists[name]
            stats.average_distance_to_ote = self._average(distances)
            stats.median_distance_to_ote = self._median(distances)
            stats.max_distance_to_ote = max(distances) if distances else None
            stats.average_range_size = self._average(range_sizes)
            stats.median_range_size = self._median(range_sizes)
            stats.average_range_size_percent = self._average(range_size_percents)
            stats.median_range_size_percent = self._median(range_size_percents)

        return diagnostics

    def _candidate_for_name(self, context: MarketContext, name: str) -> tuple[float | None, float | None]:
        if name == "CURRENT_EXTERNAL_RANGE":
            return self._current_external_range(context)
        if name == "RECENT_50_CANDLE_RANGE":
            return self._recent_candle_range(context, 50)
        if name == "RECENT_100_CANDLE_RANGE":
            return self._recent_candle_range(context, 100)
        if name == "RECENT_200_CANDLE_RANGE":
            return self._recent_candle_range(context, 200)
        if name == "RECENT_SWING_RANGE":
            return self._recent_swing_range(context)
        return None, None

    def _current_external_range(self, context: MarketContext) -> tuple[float | None, float | None]:
        return (
            self._float_or_none(getattr(context, "dealing_range_high", None)),
            self._float_or_none(getattr(context, "dealing_range_low", None)),
        )

    def _recent_candle_range(self, context: MarketContext, window: int) -> tuple[float | None, float | None]:
        candles = getattr(context, "candles", None)
        if candles is None or len(candles) < window:
            return None, None
        recent = candles.iloc[-window:] if isinstance(candles, pd.DataFrame) else candles[-window:]
        try:
            highs = recent["high"] if isinstance(recent, pd.DataFrame) else [candle["high"] for candle in recent]
            lows = recent["low"] if isinstance(recent, pd.DataFrame) else [candle["low"] for candle in recent]
        except (KeyError, TypeError):
            return None, None
        return self._float_or_none(max(highs)), self._float_or_none(min(lows))

    def _recent_swing_range(self, context: MarketContext) -> tuple[float | None, float | None]:
        swings = getattr(context, "swings", None) or []
        candles = getattr(context, "candles", None)
        if not swings or candles is None:
            return None, None
        current_index = len(candles) - 1
        min_index = current_index - 100
        high_prices: list[float] = []
        low_prices: list[float] = []
        for swing in swings:
            index = self._int_or_none(getattr(swing, "index", None))
            price = self._float_or_none(getattr(swing, "price", None))
            swing_type = getattr(swing, "swing_type", getattr(swing, "type", None))
            if index is None or price is None or index < min_index:
                continue
            if swing_type == "HIGH":
                high_prices.append(price)
            elif swing_type == "LOW":
                low_prices.append(price)
        if not high_prices or not low_prices:
            return None, None
        return max(high_prices), min(low_prices)

    def _evaluate_candidate(self, context: MarketContext, candidate: tuple[float | None, float | None]) -> dict[str, Any]:
        high, low = candidate
        current_price = self._float_or_none(getattr(context, "current_price", None))
        ote_direction = self._normalized(getattr(context, "ote_direction", None), "NONE")
        result: dict[str, Any] = {
            "missing": high is None or low is None,
            "invalid": False,
            "available": False,
            "zone": "UNKNOWN",
            "aligned": False,
            "wrong": False,
            "in_ote": False,
            "near_ote_0_5": False,
            "ote_available": False,
            "distance_to_ote": None,
            "range_size": None,
            "range_size_percent": None,
            "ote_direction": ote_direction,
        }
        if result["missing"]:
            return result
        if high <= low or current_price is None or current_price <= 0:
            result["invalid"] = True
            return result

        range_size = high - low
        equilibrium = (high + low) / 2
        result["available"] = True
        result["range_size"] = range_size
        result["range_size_percent"] = range_size / current_price
        result["zone"] = self._zone(current_price, equilibrium)
        result["aligned"] = (ote_direction == "BEARISH" and result["zone"] == "PREMIUM") or (
            ote_direction == "BULLISH" and result["zone"] == "DISCOUNT"
        )
        result["wrong"] = (ote_direction == "BEARISH" and result["zone"] == "DISCOUNT") or (
            ote_direction == "BULLISH" and result["zone"] == "PREMIUM"
        )

        ote_bounds = self._candidate_ote_bounds(high, low, ote_direction)
        if ote_bounds is None:
            return result
        ote_lower, ote_upper = ote_bounds
        result["ote_available"] = True
        if ote_lower <= current_price <= ote_upper:
            distance = 0.0
            result["in_ote"] = True
        elif current_price < ote_lower:
            distance = ote_lower - current_price
        else:
            distance = current_price - ote_upper
        result["distance_to_ote"] = distance
        result["near_ote_0_5"] = distance / current_price <= 0.005
        return result

    def _candidate_ote_bounds(self, high: float, low: float, ote_direction: str) -> tuple[float, float] | None:
        range_size = high - low
        if ote_direction == "BULLISH":
            level_62 = high - range_size * 0.62
            level_79 = high - range_size * 0.79
            return level_79, level_62
        if ote_direction == "BEARISH":
            level_62 = low + range_size * 0.62
            level_79 = low + range_size * 0.79
            return level_62, level_79
        return None

    def _apply_evaluation(
        self,
        stats: RangeCandidateStats,
        evaluation: dict[str, Any],
        current_eval: dict[str, Any],
    ) -> None:
        if evaluation["missing"]:
            stats.missing_count += 1
            return
        if evaluation["invalid"]:
            stats.invalid_count += 1
            return

        stats.available_count += 1
        self._count_zone(stats, evaluation["zone"])
        self._count_alignment(stats, evaluation["ote_direction"], evaluation["zone"])

        if not evaluation["ote_available"]:
            stats.ote_unavailable_count += 1
        elif evaluation["in_ote"]:
            stats.in_ote_count += 1
        else:
            stats.not_in_ote_count += 1

        distance = evaluation["distance_to_ote"]
        current_price = None if evaluation["range_size_percent"] is None else evaluation["range_size"] / evaluation["range_size_percent"]
        if distance is not None and current_price:
            distance_percent = distance / current_price
            if distance_percent <= 0.001:
                stats.near_ote_0_1_pct_count += 1
            if distance_percent <= 0.0025:
                stats.near_ote_0_25_pct_count += 1
            if distance_percent <= 0.005:
                stats.near_ote_0_5_pct_count += 1
            if distance_percent <= 0.01:
                stats.near_ote_1_0_pct_count += 1

        if current_eval.get("wrong") and evaluation["aligned"]:
            stats.candidate_fix_wrong_zone_count += 1
        if not current_eval.get("in_ote") and evaluation["in_ote"]:
            stats.candidate_fix_not_in_ote_count += 1
        if not current_eval.get("near_ote_0_5") and evaluation["near_ote_0_5"]:
            stats.candidate_fix_near_ote_0_5_count += 1

    def _count_zone(self, stats: RangeCandidateStats, zone: str) -> None:
        if zone == "PREMIUM":
            stats.premium_count += 1
        elif zone == "DISCOUNT":
            stats.discount_count += 1
        elif zone == "EQUILIBRIUM":
            stats.equilibrium_count += 1
        else:
            stats.unknown_zone_count += 1

    def _count_alignment(self, stats: RangeCandidateStats, ote_direction: str, zone: str) -> None:
        if ote_direction == "BEARISH" and zone == "PREMIUM":
            stats.bearish_ote_premium_count += 1
            stats.candidate_aligned_zone_count += 1
        elif ote_direction == "BEARISH" and zone == "DISCOUNT":
            stats.bearish_ote_discount_count += 1
            stats.candidate_wrong_zone_count += 1
        elif ote_direction == "BULLISH" and zone == "DISCOUNT":
            stats.bullish_ote_discount_count += 1
            stats.candidate_aligned_zone_count += 1
        elif ote_direction == "BULLISH" and zone == "PREMIUM":
            stats.bullish_ote_premium_count += 1
            stats.candidate_wrong_zone_count += 1

    def _zone(self, current_price: float, equilibrium: float) -> str:
        if current_price > equilibrium:
            return "PREMIUM"
        if current_price < equilibrium:
            return "DISCOUNT"
        return "EQUILIBRIUM"

    def _float_or_none(self, value) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _int_or_none(self, value) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _normalized(self, value, default: str) -> str:
        if value is None or value == "":
            return default
        return str(value)

    def _average(self, values: list[float]) -> float | None:
        if not values:
            return None
        return sum(values) / len(values)

    def _median(self, values: list[float]) -> float | None:
        if not values:
            return None
        return float(median(values))
