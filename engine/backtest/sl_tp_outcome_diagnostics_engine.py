from __future__ import annotations

from copy import deepcopy

from engine.backtest.trade_outcome_diagnostics_engine import TradeOutcomeDiagnosticsEngine
from models.market_context import MarketContext
from models.sl_tp_outcome_diagnostics import SLTPOutcomeDiagnostics, SLTPOutcomeRecord


class SLTPOutcomeDiagnosticsEngine:
    def __init__(self):
        self.trade_outcome_engine = TradeOutcomeDiagnosticsEngine()

    def summarize_trade_contexts(self, contexts: list[MarketContext]) -> SLTPOutcomeDiagnostics:
        records: list[SLTPOutcomeRecord] = []
        for context in contexts:
            record = self.collect_from_context(context, len(records) + 1)
            if record is not None:
                records.append(record)

        diagnostics = SLTPOutcomeDiagnostics(records=records, total_trades=len(records))
        diagnostics.closed_trades = sum(1 for record in records if record.result in ("WIN", "LOSS"))
        diagnostics.open_trades = sum(1 for record in records if record.result == "OPEN")
        diagnostics.wins = sum(1 for record in records if record.result == "WIN")
        diagnostics.losses = sum(1 for record in records if record.result == "LOSS")
        diagnostics.average_bars_held = self._average(record.bars_held for record in records)
        diagnostics.average_mae_r = self._average(record.mae_r for record in records)
        diagnostics.average_mfe_r = self._average(record.mfe_r for record in records)
        diagnostics.average_tp_progress = self._average(record.tp_progress for record in records)
        diagnostics.average_sl_progress = self._average(record.sl_progress for record in records)
        diagnostics.fast_loss_count = sum(1 for record in records if record.fast_loss)
        diagnostics.almost_tp_then_loss_count = sum(1 for record in records if record.almost_tp_then_loss)
        diagnostics.no_follow_through_loss_count = sum(1 for record in records if record.no_follow_through_loss)
        diagnostics.high_rr_loss_count = sum(1 for record in records if record.high_rr_loss)
        diagnostics.reached_25_pct_tp_count = sum(1 for record in records if record.reached_25_pct_tp)
        diagnostics.reached_50_pct_tp_count = sum(1 for record in records if record.reached_50_pct_tp)
        diagnostics.reached_75_pct_tp_count = sum(1 for record in records if record.reached_75_pct_tp)
        diagnostics.reached_25_pct_sl_count = sum(1 for record in records if record.reached_25_pct_sl)
        diagnostics.reached_50_pct_sl_count = sum(1 for record in records if record.reached_50_pct_sl)
        diagnostics.reached_75_pct_sl_count = sum(1 for record in records if record.reached_75_pct_sl)
        winners = diagnostics.winning_records()
        losers = diagnostics.losing_records()
        diagnostics.average_mfe_r_winners = self._average(record.mfe_r for record in winners)
        diagnostics.average_mae_r_winners = self._average(record.mae_r for record in winners)
        diagnostics.average_mfe_r_losers = self._average(record.mfe_r for record in losers)
        diagnostics.average_mae_r_losers = self._average(record.mae_r for record in losers)
        diagnostics.long_loss_count = sum(1 for record in records if record.direction == "LONG" and record.result == "LOSS")
        diagnostics.short_loss_count = sum(1 for record in records if record.direction == "SHORT" and record.result == "LOSS")
        diagnostics.long_win_count = sum(1 for record in records if record.direction == "LONG" and record.result == "WIN")
        diagnostics.short_win_count = sum(1 for record in records if record.direction == "SHORT" and record.result == "WIN")
        return diagnostics

    def collect_from_context(self, context: MarketContext, trade_number: int) -> SLTPOutcomeRecord | None:
        trade = self.trade_outcome_engine.collect_from_context(context, trade_number)
        if trade is None:
            return None

        record = SLTPOutcomeRecord(
            trade_number=trade.trade_number,
            direction=trade.direction,
            result=trade.result,
            entry_price=trade.entry_price,
            stop_loss=trade.stop_loss,
            take_profit=trade.take_profit,
            exit_price=trade.exit_price,
            entry_index=trade.entry_index,
            exit_index=trade.exit_index,
            risk=trade.risk,
            reward=trade.reward,
            risk_reward=trade.risk_reward,
            setup_score=trade.setup_score,
            entry_trigger_type=trade.entry_trigger_type,
            current_price_zone=trade.current_price_zone,
            in_ote_zone=trade.in_ote_zone,
            matched_poi_count=trade.matched_poi_count,
            matched_poi_types=deepcopy(trade.matched_poi_types),
        )
        self._apply_excursions(record, context)
        self._apply_flags(record)
        return record

    def _apply_excursions(self, record: SLTPOutcomeRecord, context: MarketContext) -> None:
        candles = getattr(context, "candles", None)
        if candles is None or record.entry_index is None or len(candles) == 0:
            return

        entry_index = max(int(record.entry_index), 0)
        exit_index = int(record.exit_index) if record.exit_index is not None else len(candles) - 1
        exit_index = min(exit_index, len(candles) - 1)
        if entry_index > exit_index:
            return

        if record.entry_price is None or record.stop_loss is None or record.take_profit is None:
            return

        trade_candles = candles.iloc[entry_index : exit_index + 1]
        if len(trade_candles) == 0:
            return

        entry = float(record.entry_price)
        stop = float(record.stop_loss)
        take_profit = float(record.take_profit)
        high = trade_candles["high"].astype(float)
        low = trade_candles["low"].astype(float)

        if record.direction == "LONG":
            max_favorable = float((high - entry).max())
            max_adverse = float((entry - low).max())
            distance_to_tp = take_profit - entry
            distance_to_sl = entry - stop
        elif record.direction == "SHORT":
            max_favorable = float((entry - low).max())
            max_adverse = float((high - entry).max())
            distance_to_tp = entry - take_profit
            distance_to_sl = stop - entry
        else:
            return

        record.bars_held = exit_index - entry_index + 1
        record.mae = max(max_adverse, 0.0)
        record.mfe = max(max_favorable, 0.0)
        risk = record.risk if record.risk is not None else distance_to_sl
        if risk is not None and risk > 0:
            record.mae_r = record.mae / risk
            record.mfe_r = record.mfe / risk
        if distance_to_tp > 0:
            record.tp_progress = record.mfe / distance_to_tp
        if distance_to_sl > 0:
            record.sl_progress = record.mae / distance_to_sl

        record.reached_25_pct_tp = self._reached(record.tp_progress, 0.25)
        record.reached_50_pct_tp = self._reached(record.tp_progress, 0.50)
        record.reached_75_pct_tp = self._reached(record.tp_progress, 0.75)
        record.reached_25_pct_sl = self._reached(record.sl_progress, 0.25)
        record.reached_50_pct_sl = self._reached(record.sl_progress, 0.50)
        record.reached_75_pct_sl = self._reached(record.sl_progress, 0.75)

    def _apply_flags(self, record: SLTPOutcomeRecord) -> None:
        is_loss = record.result == "LOSS"
        record.fast_loss = bool(is_loss and record.bars_held is not None and record.bars_held <= 3)
        record.almost_tp_then_loss = bool(is_loss and record.tp_progress is not None and record.tp_progress >= 0.75)
        record.no_follow_through_loss = bool(is_loss and record.tp_progress is not None and record.tp_progress < 0.25)
        record.high_rr_loss = bool(is_loss and record.risk_reward is not None and record.risk_reward >= 5.0)

    def _reached(self, value: float | None, threshold: float) -> bool | None:
        if value is None:
            return None
        return value >= threshold

    def _average(self, values) -> float | None:
        usable = [float(value) for value in values if value is not None]
        return sum(usable) / len(usable) if usable else None
