from __future__ import annotations

from statistics import median

from models.dealing_range_diagnostics import DealingRangeDiagnostics
from models.market_context import MarketContext


class DealingRangeDiagnosticsEngine:
    def collect_from_context(self, context: MarketContext) -> DealingRangeDiagnostics:
        return self.summarize_contexts([context])

    def summarize_contexts(self, contexts: list[MarketContext]) -> DealingRangeDiagnostics:
        diagnostics = DealingRangeDiagnostics(windows_analyzed=len(contexts))
        range_sizes: list[float] = []
        range_size_percents: list[float] = []
        equilibrium_distances: list[float] = []
        equilibrium_distance_percents: list[float] = []
        external_high_ages: list[float] = []
        external_low_ages: list[float] = []

        for context in contexts:
            current_price = self._float_or_none(getattr(context, "current_price", None))
            high = self._float_or_none(getattr(context, "dealing_range_high", None))
            low = self._float_or_none(getattr(context, "dealing_range_low", None))
            equilibrium = self._float_or_none(getattr(context, "equilibrium", None))
            zone = self._normalized(getattr(context, "current_price_zone", None), "UNKNOWN")
            trend = self._normalized(getattr(context, "trend", None), "UNKNOWN")
            ote_direction = self._normalized(getattr(context, "ote_direction", None), "NONE")

            self._count_zone(diagnostics, zone)
            self._count_trend(diagnostics, trend)
            self._increment(diagnostics.trend_zone_counts, f"{trend}|{zone}")
            self._increment(diagnostics.ote_direction_zone_counts, f"{ote_direction}|{zone}")
            self._count_mismatches(diagnostics, trend, ote_direction, zone)

            if high is None or low is None:
                diagnostics.range_missing_count += 1
            elif high <= low:
                diagnostics.invalid_range_count += 1
            else:
                diagnostics.range_available_count += 1
                range_size = high - low
                range_sizes.append(range_size)
                if current_price is not None and current_price > 0:
                    range_size_percents.append(range_size / current_price)

            if current_price is not None and equilibrium is not None:
                distance = abs(current_price - equilibrium)
                equilibrium_distances.append(distance)
                if current_price > 0:
                    equilibrium_distance_percents.append(distance / current_price)

            self._collect_range_age(context, external_high_ages, external_low_ages)

        diagnostics.average_range_size = self._average(range_sizes)
        diagnostics.median_range_size = self._median(range_sizes)
        diagnostics.max_range_size = max(range_sizes) if range_sizes else None
        diagnostics.min_range_size = min(range_sizes) if range_sizes else None
        diagnostics.average_range_size_percent = self._average(range_size_percents)
        diagnostics.median_range_size_percent = self._median(range_size_percents)
        diagnostics.max_range_size_percent = max(range_size_percents) if range_size_percents else None
        diagnostics.min_range_size_percent = min(range_size_percents) if range_size_percents else None
        diagnostics.average_distance_to_equilibrium = self._average(equilibrium_distances)
        diagnostics.median_distance_to_equilibrium = self._median(equilibrium_distances)
        diagnostics.max_distance_to_equilibrium = max(equilibrium_distances) if equilibrium_distances else None
        diagnostics.average_distance_to_equilibrium_percent = self._average(equilibrium_distance_percents)
        diagnostics.median_distance_to_equilibrium_percent = self._median(equilibrium_distance_percents)
        diagnostics.max_distance_to_equilibrium_percent = (
            max(equilibrium_distance_percents) if equilibrium_distance_percents else None
        )
        diagnostics.average_external_high_age = self._average(external_high_ages)
        diagnostics.average_external_low_age = self._average(external_low_ages)
        diagnostics.max_external_high_age = max(external_high_ages) if external_high_ages else None
        diagnostics.max_external_low_age = max(external_low_ages) if external_low_ages else None
        return diagnostics

    def _collect_range_age(
        self,
        context: MarketContext,
        external_high_ages: list[float],
        external_low_ages: list[float],
    ) -> None:
        candles = getattr(context, "candles", None)
        if candles is None:
            return

        try:
            current_index = len(candles) - 1
        except TypeError:
            return
        if current_index < 0:
            return

        high_index = self._int_or_none(getattr(context, "external_high_index", None))
        low_index = self._int_or_none(getattr(context, "external_low_index", None))
        if high_index is not None:
            age = current_index - high_index
            if age >= 0:
                external_high_ages.append(float(age))
        if low_index is not None:
            age = current_index - low_index
            if age >= 0:
                external_low_ages.append(float(age))

    def _count_zone(self, diagnostics: DealingRangeDiagnostics, zone: str) -> None:
        if zone == "PREMIUM":
            diagnostics.premium_count += 1
        elif zone == "DISCOUNT":
            diagnostics.discount_count += 1
        elif zone == "EQUILIBRIUM":
            diagnostics.equilibrium_count += 1
        else:
            diagnostics.unknown_zone_count += 1

    def _count_trend(self, diagnostics: DealingRangeDiagnostics, trend: str) -> None:
        if trend == "UPTREND":
            diagnostics.uptrend_count += 1
        elif trend == "DOWNTREND":
            diagnostics.downtrend_count += 1
        elif trend == "RANGE":
            diagnostics.range_trend_count += 1
        else:
            diagnostics.unknown_trend_count += 1

    def _count_mismatches(
        self,
        diagnostics: DealingRangeDiagnostics,
        trend: str,
        ote_direction: str,
        zone: str,
    ) -> None:
        if ote_direction == "BEARISH" and zone == "DISCOUNT":
            diagnostics.bearish_ote_discount_count += 1
        if ote_direction == "BULLISH" and zone == "PREMIUM":
            diagnostics.bullish_ote_premium_count += 1
        if trend == "DOWNTREND" and zone == "DISCOUNT":
            diagnostics.downtrend_discount_count += 1
        if trend == "UPTREND" and zone == "PREMIUM":
            diagnostics.uptrend_premium_count += 1

    def _increment(self, counts: dict[str, int], key: str) -> None:
        counts[key] = counts.get(key, 0) + 1

    def _normalized(self, value, default: str) -> str:
        if value is None or value == "":
            return default
        return str(value)

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

    def _average(self, values: list[float]) -> float | None:
        if not values:
            return None
        return sum(values) / len(values)

    def _median(self, values: list[float]) -> float | None:
        if not values:
            return None
        return float(median(values))
