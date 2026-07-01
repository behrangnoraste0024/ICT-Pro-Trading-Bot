from __future__ import annotations

from copy import deepcopy

from engine.backtest.trade_outcome_diagnostics_engine import TradeOutcomeDiagnosticsEngine
from models.entry_followthrough_diagnostics import (
    EntryFollowthroughDiagnostics,
    EntryFollowthroughHorizon,
    EntryFollowthroughRecord,
)
from models.market_context import MarketContext


class EntryFollowthroughDiagnosticsEngine:
    HORIZONS = (1, 2, 3, 5, 10)

    def __init__(self):
        self.trade_outcome_engine = TradeOutcomeDiagnosticsEngine()

    def summarize_trade_contexts(self, contexts: list[MarketContext]) -> EntryFollowthroughDiagnostics:
        records: list[EntryFollowthroughRecord] = []
        for context in contexts:
            record = self.collect_from_context(context, len(records) + 1)
            if record is not None:
                records.append(record)

        diagnostics = EntryFollowthroughDiagnostics(records=records, total_trades=len(records))
        diagnostics.closed_trades = sum(1 for record in records if record.result in ("WIN", "LOSS"))
        diagnostics.open_trades = sum(1 for record in records if record.result == "OPEN")
        diagnostics.wins = sum(1 for record in records if record.result == "WIN")
        diagnostics.losses = sum(1 for record in records if record.result == "LOSS")
        diagnostics.next_candle_available_count = sum(1 for record in records if record.next_candle_available)
        diagnostics.next_candle_continuation_count = sum(1 for record in records if record.next_candle_continuation)
        diagnostics.next_candle_rejection_count = sum(1 for record in records if record.next_candle_rejection)
        diagnostics.immediate_favorable_count = sum(1 for record in records if record.immediate_favorable)
        diagnostics.immediate_adverse_count = sum(1 for record in records if record.immediate_adverse)
        diagnostics.no_followthrough_3_count = sum(1 for record in records if record.no_followthrough_3)
        diagnostics.strong_followthrough_3_count = sum(1 for record in records if record.strong_followthrough_3)
        diagnostics.early_reversal_3_count = sum(1 for record in records if record.early_reversal_3)
        diagnostics.average_h1_favorable_r = self._average_horizon(records, 1, "favorable_r")
        diagnostics.average_h1_adverse_r = self._average_horizon(records, 1, "adverse_r")
        diagnostics.average_h3_favorable_r = self._average_horizon(records, 3, "favorable_r")
        diagnostics.average_h3_adverse_r = self._average_horizon(records, 3, "adverse_r")
        diagnostics.average_h5_favorable_r = self._average_horizon(records, 5, "favorable_r")
        diagnostics.average_h5_adverse_r = self._average_horizon(records, 5, "adverse_r")
        winners = [record for record in records if record.result == "WIN"]
        losers = [record for record in records if record.result == "LOSS"]
        diagnostics.winners_average_h3_favorable_r = self._average_horizon(winners, 3, "favorable_r")
        diagnostics.losers_average_h3_favorable_r = self._average_horizon(losers, 3, "favorable_r")
        diagnostics.winners_next_candle_continuation_count = sum(
            1 for record in winners if record.next_candle_continuation
        )
        diagnostics.losers_next_candle_continuation_count = sum(
            1 for record in losers if record.next_candle_continuation
        )
        self._apply_trigger_stats(diagnostics, records)
        diagnostics.long_no_followthrough_3_count = sum(
            1 for record in records if record.direction == "LONG" and record.no_followthrough_3
        )
        diagnostics.short_no_followthrough_3_count = sum(
            1 for record in records if record.direction == "SHORT" and record.no_followthrough_3
        )
        diagnostics.long_early_reversal_3_count = sum(
            1 for record in records if record.direction == "LONG" and record.early_reversal_3
        )
        diagnostics.short_early_reversal_3_count = sum(
            1 for record in records if record.direction == "SHORT" and record.early_reversal_3
        )
        return diagnostics

    def collect_from_context(self, context: MarketContext, trade_number: int) -> EntryFollowthroughRecord | None:
        trade = self.trade_outcome_engine.collect_from_context(context, trade_number)
        if trade is None:
            return None

        record = EntryFollowthroughRecord(
            trade_number=trade.trade_number,
            direction=trade.direction,
            result=trade.result,
            entry_price=trade.entry_price,
            stop_loss=trade.stop_loss,
            take_profit=trade.take_profit,
            risk=trade.risk,
            reward=trade.reward,
            risk_reward=trade.risk_reward,
            bars_held=self._bars_held(trade.entry_index, trade.exit_index, context),
            entry_trigger_type=trade.entry_trigger_type,
            setup_score=trade.setup_score,
            current_price_zone=trade.current_price_zone,
            in_ote_zone=trade.in_ote_zone,
            matched_poi_count=trade.matched_poi_count,
            matched_poi_types=deepcopy(trade.matched_poi_types),
        )
        self._apply_candle_metrics(record, context, trade.entry_index)
        self._apply_flags(record)
        return record

    def _apply_candle_metrics(
        self,
        record: EntryFollowthroughRecord,
        context: MarketContext,
        entry_index: int | None,
    ) -> None:
        candles = getattr(context, "candles", None)
        if candles is None or entry_index is None or len(candles) == 0:
            return
        if record.entry_price is None or record.stop_loss is None or record.take_profit is None:
            return

        entry_index = max(int(entry_index), 0)
        first_after_entry = entry_index + 1
        if first_after_entry >= len(candles):
            return

        next_candle = candles.iloc[first_after_entry]
        self._apply_next_candle(record, next_candle)
        for horizon in self.HORIZONS:
            record.horizons[horizon] = self._horizon_metrics(record, candles, first_after_entry, horizon)

    def _apply_next_candle(self, record: EntryFollowthroughRecord, candle) -> None:
        open_price = float(candle["open"])
        close_price = float(candle["close"])
        entry_price = float(record.entry_price)
        record.next_candle_available = True
        record.next_candle_close = close_price
        if record.direction == "LONG":
            record.next_candle_continuation = close_price > open_price and close_price > entry_price
            record.next_candle_rejection = close_price < entry_price
        elif record.direction == "SHORT":
            record.next_candle_continuation = close_price < open_price and close_price < entry_price
            record.next_candle_rejection = close_price > entry_price

    def _horizon_metrics(self, record: EntryFollowthroughRecord, candles, first_after_entry: int, horizon: int):
        end_index = min(first_after_entry + horizon, len(candles))
        window = candles.iloc[first_after_entry:end_index]
        metrics = EntryFollowthroughHorizon(horizon=horizon)
        if len(window) == 0:
            return metrics

        entry = float(record.entry_price)
        high = window["high"].astype(float)
        low = window["low"].astype(float)
        if record.direction == "LONG":
            favorable_move = float(high.max() - entry)
            adverse_move = float(entry - low.min())
        elif record.direction == "SHORT":
            favorable_move = float(entry - low.min())
            adverse_move = float(high.max() - entry)
        else:
            return metrics

        metrics.available = True
        metrics.candles_used = len(window)
        metrics.favorable_move = max(favorable_move, 0.0)
        metrics.adverse_move = max(adverse_move, 0.0)
        if record.risk is not None and record.risk > 0:
            metrics.favorable_r = metrics.favorable_move / record.risk
            metrics.adverse_r = metrics.adverse_move / record.risk
            metrics.sl_pressure = metrics.adverse_r
        if record.reward is not None and record.reward > 0:
            metrics.tp_progress = metrics.favorable_move / record.reward
        return metrics

    def _apply_flags(self, record: EntryFollowthroughRecord) -> None:
        h1 = record.horizons.get(1)
        h3 = record.horizons.get(3)
        record.immediate_favorable = bool(h1 and h1.favorable_r is not None and h1.favorable_r >= 0.25)
        record.immediate_adverse = bool(h1 and h1.adverse_r is not None and h1.adverse_r >= 0.5)
        record.no_followthrough_3 = bool(h3 and h3.favorable_r is not None and h3.favorable_r < 0.25)
        record.strong_followthrough_3 = bool(h3 and h3.favorable_r is not None and h3.favorable_r >= 1.0)
        record.early_reversal_3 = bool(
            h3
            and h3.adverse_r is not None
            and h3.favorable_r is not None
            and h3.adverse_r >= 1.0
            and h3.favorable_r < 0.5
        )

    def _bars_held(self, entry_index: int | None, exit_index: int | None, context: MarketContext) -> int | None:
        if entry_index is None:
            return None
        candles = getattr(context, "candles", None)
        final_index = exit_index if exit_index is not None else (len(candles) - 1 if candles is not None else None)
        if final_index is None:
            return None
        return max(int(final_index) - int(entry_index) + 1, 0)

    def _apply_trigger_stats(self, diagnostics: EntryFollowthroughDiagnostics, records: list[EntryFollowthroughRecord]):
        triggers = sorted({record.entry_trigger_type or "None" for record in records})
        for trigger in triggers:
            trigger_records = [record for record in records if (record.entry_trigger_type or "None") == trigger]
            diagnostics.trigger_counts[trigger] = len(trigger_records)
            diagnostics.trigger_win_counts[trigger] = sum(1 for record in trigger_records if record.result == "WIN")
            diagnostics.trigger_loss_counts[trigger] = sum(1 for record in trigger_records if record.result == "LOSS")
            fav_avg = self._average_horizon(trigger_records, 3, "favorable_r")
            adv_avg = self._average_horizon(trigger_records, 3, "adverse_r")
            if fav_avg is not None:
                diagnostics.trigger_average_h3_favorable_r[trigger] = fav_avg
            if adv_avg is not None:
                diagnostics.trigger_average_h3_adverse_r[trigger] = adv_avg

    def _average_horizon(
        self,
        records: list[EntryFollowthroughRecord],
        horizon: int,
        field_name: str,
    ) -> float | None:
        values = [
            getattr(record.horizons[horizon], field_name)
            for record in records
            if horizon in record.horizons and getattr(record.horizons[horizon], field_name) is not None
        ]
        return sum(values) / len(values) if values else None
