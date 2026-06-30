from models.bos_event import BOSEvent
from models.market_context import MarketContext
from models.structure_event import StructureEvent


class StructureEngineV2:

    """
    Main Smart Money Structure Engine

    Responsible for:

    - HH HL LH LL
    - External Structure
    - Internal Structure
    - BOS
    - CHOCHpython 
    - Trend
    """

    def build(self, context: MarketContext):

        context = self.classify_structure(context)

        context = self.detect_external_structure(context)

        context = self.detect_internal_structure(context)

        context = self.detect_bos(context)

        context = self.detect_choch(context)

        context = self.detect_trend(context)

        return context

    # -----------------------------------

    def classify_structure(self, context):

        if not context.structure:
            context.structure = [
                StructureEvent(
                    index=swing.index,
                    price=swing.price,
                    swing_type=swing.swing_type,
                    label=getattr(swing, "label", ""),
                )
                for swing in context.swings
            ]

        previous_high = None
        previous_low = None

        for event in context.structure:

            if event.swing_type == "HIGH":
                event.label = "HH" if previous_high is None or event.price > previous_high.price else "LH"
                previous_high = event

            elif event.swing_type == "LOW":
                event.label = "HL" if previous_low is None or event.price > previous_low.price else "LL"
                previous_low = event

            self._sync_swing(context, event)

        return context

    # -----------------------------------

    def detect_external_structure(self, context):

        for event in context.structure:
            event.is_external = False
            event.is_internal = False

        external_high = self._first_event(context.structure, "HIGH")
        external_low = self._first_event(context.structure, "LOW")

        if external_high:
            self._set_external_level(external_high)
            context.external_high = external_high.price
            context.external_high_index = external_high.index

        if external_low:
            self._set_external_level(external_low)
            context.external_low = external_low.price
            context.external_low_index = external_low.index

        context.debug["active_external_high"] = context.external_high
        context.debug["active_external_low"] = context.external_low

        return context

    # -----------------------------------

    def detect_internal_structure(self, context):

        context.internal_highs = []
        context.internal_lows = []

        for event in context.structure:
            if event.is_external:
                event.is_internal = False
                continue

            event.is_internal = True

            if event.swing_type == "HIGH":
                context.internal_highs.append(event)
            elif event.swing_type == "LOW":
                context.internal_lows.append(event)

        return context

    # -----------------------------------

    def detect_bos(self, context):

        context.bos = []
        context.debug["bos_candidates_checked"] = 0
        context.debug["bos_events_created"] = 0

        candles = context.candles

        if candles is None or "close" not in candles:
            return context

        active_high = self._external_event(context.structure, "HIGH")
        active_low = self._external_event(context.structure, "LOW")
        protected_high = None
        protected_low = None
        trend = context.trend if context.trend not in ("", "UNKNOWN") else "RANGE"

        for candle_index in range(len(candles)):

            close = float(candles["close"].iloc[candle_index])

            if trend in ("UNKNOWN", "RANGE", "UPTREND"):
                if self._can_check_level(active_high, candle_index):
                    context.debug["bos_candidates_checked"] += 1

                    if close > active_high.price:
                        self._mark_bos(context, active_high, candle_index, "BULLISH")
                        context.debug["bos_events_created"] += 1
                        trend = "UPTREND"
                        protected_low = self._protected_low_before(context.structure, candle_index)
                        if protected_low:
                            self._set_external_level(protected_low)
                            context.external_low = protected_low.price
                            context.external_low_index = protected_low.index
                        active_high = self._next_event_after(context.structure, "HIGH", active_high.index)
                        if active_high:
                            self._set_external_level(active_high)
                            context.external_high = active_high.price
                            context.external_high_index = active_high.index

            if trend in ("UNKNOWN", "RANGE", "DOWNTREND"):
                if self._can_check_level(active_low, candle_index):
                    context.debug["bos_candidates_checked"] += 1

                    if close < active_low.price:
                        self._mark_bos(context, active_low, candle_index, "BEARISH")
                        context.debug["bos_events_created"] += 1
                        trend = "DOWNTREND"
                        protected_high = self._protected_high_before(context.structure, candle_index)
                        if protected_high:
                            self._set_external_level(protected_high)
                            context.external_high = protected_high.price
                            context.external_high_index = protected_high.index
                        active_low = self._next_event_after(context.structure, "LOW", active_low.index)
                        if active_low:
                            self._set_external_level(active_low)
                            context.external_low = active_low.price
                            context.external_low_index = active_low.index

        context.debug["active_external_high"] = context.external_high
        context.debug["active_external_low"] = context.external_low
        context.debug["protected_high"] = protected_high.price if protected_high else None
        context.debug["protected_low"] = protected_low.price if protected_low else None

        context = self.detect_internal_structure(context)

        return context

    # -----------------------------------

    def detect_choch(self, context):

        context.choch = []
        context.debug["choch_events_created"] = 0

        candles = context.candles

        if candles is None or "close" not in candles:
            return context

        trend = self._trend_from_latest_market_event(context.bos, context.choch)

        if trend == "UPTREND":
            protected_low = self._protected_low_for_choch(context)

            if protected_low:
                break_index = self._first_close_break(
                    candles,
                    protected_low.index,
                    protected_low.price,
                    "BELOW",
                )

                if break_index is not None:
                    self._mark_choch(context, protected_low, break_index, "BEARISH", "DOWNTREND")
                    context.debug["choch_events_created"] += 1

        elif trend == "DOWNTREND":
            protected_high = self._protected_high_for_choch(context)

            if protected_high:
                break_index = self._first_close_break(
                    candles,
                    protected_high.index,
                    protected_high.price,
                    "ABOVE",
                )

                if break_index is not None:
                    self._mark_choch(context, protected_high, break_index, "BULLISH", "UPTREND")
                    context.debug["choch_events_created"] += 1

        return context

    # -----------------------------------

    def detect_trend(self, context):

        new_trend = self._trend_from_latest_market_event(context.bos, context.choch)

        if new_trend == "RANGE":
            new_trend = self._trend_from_structure(context.structure)

        context.previous_trend = context.trend
        context.trend = new_trend

        for event in context.structure:
            if event.trend_after == "":
                event.trend_after = context.trend

        return context

    # -----------------------------------

    def _mark_bos(self, context, event, candle_index, direction):

        event.bos = True
        event.broken = True
        event.is_external = True
        event.is_internal = False
        event.trend_before = context.trend
        event.trend_after = "UPTREND" if direction == "BULLISH" else "DOWNTREND"

        context.bos.append(
            BOSEvent(
                candle_index=candle_index,
                level=event.price,
                direction=direction,
                event_type="BOS",
            )
        )

        self._sync_swing(context, event)

    def _mark_choch(self, context, event, candle_index, direction, trend_after):

        event.choch = True
        event.broken = True
        event.is_external = True
        event.is_internal = False
        event.trend_before = context.trend
        event.trend_after = trend_after

        context.choch.append(
            BOSEvent(
                candle_index=candle_index,
                level=event.price,
                direction=direction,
                event_type="CHOCH",
            )
        )

        self._sync_swing(context, event)

    def _sync_swing(self, context, event):

        for swing in context.swings:
            if swing.index == event.index and swing.swing_type == event.swing_type:
                swing.label = event.label
                swing.bos = event.bos
                swing.choch = event.choch
                swing.broken = event.broken
                break

    def _latest_event(self, structure, swing_type, label):

        matches = [
            event
            for event in structure
            if event.swing_type == swing_type and event.label == label
        ]

        if not matches:
            return None

        return max(matches, key=lambda event: event.index)

    def _first_event(self, structure, swing_type):

        for event in structure:
            if event.swing_type == swing_type:
                return event

        return None

    def _external_event(self, structure, swing_type):

        for event in structure:
            if event.swing_type == swing_type and event.is_external:
                return event

        return self._first_event(structure, swing_type)

    def _set_external_level(self, event):

        event.is_external = True
        event.is_internal = False

    def _can_check_level(self, event, candle_index):

        return event is not None and not event.broken and candle_index > event.index

    def _next_event_after(self, structure, swing_type, index):

        for event in structure:
            if event.swing_type == swing_type and event.index > index:
                return event

        return None

    def _protected_low_before(self, structure, candle_index):

        lows = [
            event
            for event in structure
            if event.swing_type == "LOW"
            and event.label == "HL"
            and event.index < candle_index
            and not event.choch
        ]

        if not lows:
            return None

        return max(lows, key=lambda event: event.index)

    def _protected_high_before(self, structure, candle_index):

        highs = [
            event
            for event in structure
            if event.swing_type == "HIGH"
            and event.label == "LH"
            and event.index < candle_index
            and not event.choch
        ]

        if not highs:
            return None

        return max(highs, key=lambda event: event.index)

    def _protected_low_for_choch(self, context):

        protected_low_index = context.external_low_index

        for event in context.structure:
            if event.index == protected_low_index and event.swing_type == "LOW" and event.label == "HL":
                return event

        return self._protected_low_before(context.structure, len(context.candles))

    def _protected_high_for_choch(self, context):

        protected_high_index = context.external_high_index

        for event in context.structure:
            if event.index == protected_high_index and event.swing_type == "HIGH" and event.label == "LH":
                return event

        return self._protected_high_before(context.structure, len(context.candles))

    def _first_close_break(self, candles, start_index, level, direction):

        for candle_index in range(start_index + 1, len(candles)):
            close = float(candles["close"].iloc[candle_index])

            if direction == "ABOVE" and close > level:
                return candle_index

            if direction == "BELOW" and close < level:
                return candle_index

        return None

    def _trend_from_latest_market_event(self, bos_events, choch_events):

        events = list(bos_events) + list(choch_events)

        if not events:
            return "RANGE"

        latest_event = max(events, key=lambda event: event.candle_index)

        if latest_event.direction == "BULLISH":
            return "UPTREND"

        if latest_event.direction == "BEARISH":
            return "DOWNTREND"

        return "RANGE"

    def _trend_from_structure(self, structure):

        latest_high = None
        latest_low = None

        for event in structure:
            if event.swing_type == "HIGH":
                latest_high = event
            elif event.swing_type == "LOW":
                latest_low = event

        if latest_high and latest_low:
            if latest_high.label == "HH" and latest_low.label == "HL":
                return "UPTREND"

            if latest_high.label == "LH" and latest_low.label == "LL":
                return "DOWNTREND"

        return "RANGE"
