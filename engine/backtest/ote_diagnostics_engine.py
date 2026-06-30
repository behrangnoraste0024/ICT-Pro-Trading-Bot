from __future__ import annotations

from statistics import median

from models.market_context import MarketContext
from models.ote_diagnostics import OTEDiagnostics


class OTEDiagnosticsEngine:
    def collect_from_context(self, context: MarketContext) -> OTEDiagnostics:
        return self.summarize_contexts([context])

    def summarize_contexts(self, contexts: list[MarketContext]) -> OTEDiagnostics:
        diagnostics = OTEDiagnostics(windows_analyzed=len(contexts))
        ote_distances: list[float] = []
        equilibrium_distances: list[float] = []

        for context in contexts:
            self._count_zone(diagnostics, getattr(context, "current_price_zone", "UNKNOWN"))
            self._count_ote_direction(diagnostics, getattr(context, "ote_direction", "NONE"))
            self._collect_ote_distance(context, diagnostics, ote_distances)
            self._collect_equilibrium_distance(context, diagnostics, equilibrium_distances)

        diagnostics.average_distance_to_ote = self._average(ote_distances)
        diagnostics.median_distance_to_ote = self._median(ote_distances)
        diagnostics.max_distance_to_ote = max(ote_distances) if ote_distances else None
        diagnostics.average_distance_to_equilibrium = self._average(equilibrium_distances)
        diagnostics.median_distance_to_equilibrium = self._median(equilibrium_distances)
        diagnostics.max_distance_to_equilibrium = max(equilibrium_distances) if equilibrium_distances else None
        return diagnostics

    def _collect_ote_distance(
        self,
        context: MarketContext,
        diagnostics: OTEDiagnostics,
        distances: list[float],
    ) -> None:
        current_price = self._float_or_none(getattr(context, "current_price", None))
        lower_bound = self._float_or_none(getattr(context, "ote_lower_bound", None))
        upper_bound = self._float_or_none(getattr(context, "ote_upper_bound", None))

        if current_price is None or lower_bound is None or upper_bound is None:
            diagnostics.ote_missing_count += 1
            return

        diagnostics.ote_available_count += 1
        in_ote_zone = bool(getattr(context, "in_ote_zone", False))
        if in_ote_zone:
            distance = 0.0
            diagnostics.in_ote_count += 1
        elif current_price < lower_bound:
            distance = lower_bound - current_price
            diagnostics.not_in_ote_count += 1
        elif current_price > upper_bound:
            distance = current_price - upper_bound
            diagnostics.not_in_ote_count += 1
        else:
            distance = 0.0
            diagnostics.in_ote_count += 1

        distances.append(distance)
        distance_percent = self._safe_percent(distance, current_price)
        if distance_percent is None:
            return
        if distance_percent <= 0.001:
            diagnostics.near_ote_0_1_pct_count += 1
        if distance_percent <= 0.0025:
            diagnostics.near_ote_0_25_pct_count += 1
        if distance_percent <= 0.005:
            diagnostics.near_ote_0_5_pct_count += 1
        if distance_percent <= 0.01:
            diagnostics.near_ote_1_0_pct_count += 1

    def _collect_equilibrium_distance(
        self,
        context: MarketContext,
        diagnostics: OTEDiagnostics,
        distances: list[float],
    ) -> None:
        current_price = self._float_or_none(getattr(context, "current_price", None))
        equilibrium = self._float_or_none(getattr(context, "equilibrium", None))
        if current_price is None or equilibrium is None:
            return

        distance = abs(current_price - equilibrium)
        distances.append(distance)
        distance_percent = self._safe_percent(distance, current_price)
        if distance_percent is None:
            return
        if distance_percent <= 0.001:
            diagnostics.near_equilibrium_0_1_pct_count += 1
        if distance_percent <= 0.0025:
            diagnostics.near_equilibrium_0_25_pct_count += 1
        if distance_percent <= 0.005:
            diagnostics.near_equilibrium_0_5_pct_count += 1

    def _count_zone(self, diagnostics: OTEDiagnostics, zone: str | None) -> None:
        if zone == "PREMIUM":
            diagnostics.premium_count += 1
        elif zone == "DISCOUNT":
            diagnostics.discount_count += 1
        elif zone == "EQUILIBRIUM":
            diagnostics.equilibrium_count += 1
        else:
            diagnostics.unknown_zone_count += 1

    def _count_ote_direction(self, diagnostics: OTEDiagnostics, direction: str | None) -> None:
        if direction == "BULLISH":
            diagnostics.bullish_ote_count += 1
        elif direction == "BEARISH":
            diagnostics.bearish_ote_count += 1
        else:
            diagnostics.none_ote_count += 1

    def _float_or_none(self, value) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _safe_percent(self, distance: float, current_price: float) -> float | None:
        if current_price == 0:
            return None
        return distance / current_price

    def _average(self, values: list[float]) -> float | None:
        if not values:
            return None
        return sum(values) / len(values)

    def _median(self, values: list[float]) -> float | None:
        if not values:
            return None
        return float(median(values))
