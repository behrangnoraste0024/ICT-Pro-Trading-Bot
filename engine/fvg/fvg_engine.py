from __future__ import annotations

from models.fvg_event import FVGEvent
from models.market_context import MarketContext


class FVGEngine:
    def detect(self, context: MarketContext) -> MarketContext:
        context.fvgs = []

        candles = context.candles
        if candles is None or len(candles) < 3:
            self._update_debug(context)
            return context

        for index in range(2, len(candles)):
            start_index = index - 2
            middle_index = index - 1

            start_high = float(candles["high"].iloc[start_index])
            start_low = float(candles["low"].iloc[start_index])
            end_high = float(candles["high"].iloc[index])
            end_low = float(candles["low"].iloc[index])

            if start_high < end_low:
                context.fvgs.append(
                    FVGEvent(
                        index=index,
                        start_index=start_index,
                        middle_index=middle_index,
                        end_index=index,
                        direction="BULLISH",
                        lower_bound=float(start_high),
                        upper_bound=float(end_low),
                    )
                )
                continue

            if start_low > end_high:
                context.fvgs.append(
                    FVGEvent(
                        index=index,
                        start_index=start_index,
                        middle_index=middle_index,
                        end_index=index,
                        direction="BEARISH",
                        lower_bound=float(end_high),
                        upper_bound=float(start_low),
                    )
                )

        self._evaluate_mitigation(context)
        self._update_debug(context)
        return context

    def _evaluate_mitigation(self, context: MarketContext) -> None:
        candles = context.candles
        if candles is None:
            return

        for fvg in context.fvgs:
            for candle_index in range(fvg.end_index + 1, len(candles)):
                high = float(candles["high"].iloc[candle_index])
                low = float(candles["low"].iloc[candle_index])

                if fvg.direction == "BULLISH":
                    if low <= fvg.lower_bound:
                        self._mark_mitigation(fvg, candle_index, "FULL", False)
                        break
                    if low <= fvg.upper_bound:
                        self._mark_mitigation(fvg, candle_index, "PARTIAL", True)
                        break

                elif fvg.direction == "BEARISH":
                    if high >= fvg.upper_bound:
                        self._mark_mitigation(fvg, candle_index, "FULL", False)
                        break
                    if high >= fvg.lower_bound:
                        self._mark_mitigation(fvg, candle_index, "PARTIAL", True)
                        break

    def _mark_mitigation(self, fvg: FVGEvent, candle_index: int, mitigation_type: str, active: bool) -> None:
        fvg.mitigation_type = mitigation_type
        fvg.mitigation_index = candle_index
        fvg.active = active
        fvg.mitigated = mitigation_type != "NONE"

    def _update_debug(self, context: MarketContext) -> None:
        if not hasattr(context, "debug") or context.debug is None:
            return

        context.debug["fvg_total"] = len(context.fvgs)
        context.debug["fvg_active"] = sum(1 for fvg in context.fvgs if fvg.active)
        context.debug["fvg_partial"] = sum(1 for fvg in context.fvgs if fvg.mitigation_type == "PARTIAL")
        context.debug["fvg_full"] = sum(1 for fvg in context.fvgs if fvg.mitigation_type == "FULL")
