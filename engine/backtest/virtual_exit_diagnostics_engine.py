from __future__ import annotations

from copy import deepcopy

from engine.backtest.trade_outcome_diagnostics_engine import TradeOutcomeDiagnosticsEngine
from models.market_context import MarketContext
from models.virtual_exit_diagnostics import (
    VirtualExitDiagnostics,
    VirtualExitPolicyResult,
    VirtualExitPolicySummary,
    VirtualExitRecord,
)


class VirtualExitDiagnosticsEngine:
    POLICIES = ["TP_1R", "TP_1_5R", "TP_2R", "TP_3R", "BE_AFTER_0_5R", "BE_AFTER_1R", "TP_1R_STOP", "TP_1_5R_STOP"]
    FIXED_TARGETS = {"TP_1R": 1.0, "TP_1_5R": 1.5, "TP_2R": 2.0, "TP_3R": 3.0, "TP_1R_STOP": 1.0, "TP_1_5R_STOP": 1.5}

    def __init__(self):
        self.trade_outcome_engine = TradeOutcomeDiagnosticsEngine()

    def summarize_trade_contexts(self, contexts: list[MarketContext]) -> VirtualExitDiagnostics:
        records = [record for index, context in enumerate(contexts, start=1) if (record := self.collect_from_context(context, index))]
        diagnostics = VirtualExitDiagnostics(records=records, total_trades=len(records))
        diagnostics.actual_wins = sum(1 for record in records if record.actual_result == "WIN")
        diagnostics.actual_losses = sum(1 for record in records if record.actual_result == "LOSS")
        diagnostics.actual_open_trades = sum(1 for record in records if record.actual_result == "OPEN")
        actual_values = [record.actual_pnl_r for record in records if record.actual_pnl_r is not None]
        diagnostics.actual_total_pnl_r = sum(actual_values) if actual_values else None
        diagnostics.policy_summaries = self.build_policy_summaries(records)
        diagnostics.best_policy_by_total_pnl_r = self._best_policy(diagnostics.policy_summaries, "total_pnl_r")
        diagnostics.best_policy_by_win_rate = self._best_policy(diagnostics.policy_summaries, "win_rate")
        diagnostics.best_policy_by_average_pnl_r = self._best_policy(diagnostics.policy_summaries, "average_pnl_r")
        diagnostics.tp_1r_would_have_won_count = sum(1 for record in records if record.policy_results.get("TP_1R") and record.actual_result == "LOSS" and record.policy_results["TP_1R"].result == "WIN")
        diagnostics.tp_1_5r_would_have_won_count = sum(1 for record in records if record.policy_results.get("TP_1_5R") and record.actual_result == "LOSS" and record.policy_results["TP_1_5R"].result == "WIN")
        diagnostics.tp_2r_would_have_won_count = sum(1 for record in records if record.would_tp_2r_win)
        diagnostics.tp_3r_would_have_won_count = sum(1 for record in records if record.policy_results.get("TP_3R") and record.actual_result == "LOSS" and record.policy_results["TP_3R"].result == "WIN")
        diagnostics.be_0_5r_would_help_count = sum(1 for record in records if record.would_be_0_5r_help)
        diagnostics.be_1r_would_help_count = sum(1 for record in records if record.would_be_1r_help)
        high_rr_losses = [record for record in records if record.actual_result == "LOSS" and record.original_rr is not None and record.original_rr >= 5.0]
        diagnostics.high_rr_loss_count = len(high_rr_losses)
        diagnostics.high_rr_loss_tp_1r_wins = sum(1 for record in high_rr_losses if record.policy_results.get("TP_1R") and record.policy_results["TP_1R"].result == "WIN")
        diagnostics.high_rr_loss_tp_1_5r_wins = sum(1 for record in high_rr_losses if record.policy_results.get("TP_1_5R") and record.policy_results["TP_1_5R"].result == "WIN")
        diagnostics.high_rr_loss_be_0_5r_saved = sum(1 for record in high_rr_losses if record.policy_results.get("BE_AFTER_0_5R") and record.policy_results["BE_AFTER_0_5R"].result in ("BREAKEVEN", "WIN"))
        diagnostics.high_rr_loss_be_1r_saved = sum(1 for record in high_rr_losses if record.policy_results.get("BE_AFTER_1R") and record.policy_results["BE_AFTER_1R"].result in ("BREAKEVEN", "WIN"))
        return diagnostics

    def collect_from_context(self, context: MarketContext, trade_number: int) -> VirtualExitRecord | None:
        trade = self.trade_outcome_engine.collect_from_context(context, trade_number)
        if trade is None:
            return None

        record = VirtualExitRecord(
            trade_number=trade.trade_number,
            direction=trade.direction,
            actual_result=trade.result,
            entry_price=trade.entry_price,
            stop_loss=trade.stop_loss,
            take_profit=trade.take_profit,
            risk=trade.risk,
            original_rr=trade.risk_reward,
            actual_pnl=trade.pnl,
            actual_pnl_r=self._actual_pnl_r(trade, context),
            bars_held=self._bars_held(trade.entry_index, trade.exit_index, context),
            setup_score=trade.setup_score,
            entry_trigger_type=trade.entry_trigger_type,
            current_price_zone=trade.current_price_zone,
            in_ote_zone=trade.in_ote_zone,
            matched_poi_count=trade.matched_poi_count,
            matched_poi_types=deepcopy(trade.matched_poi_types),
        )
        candles = self._trade_candles(context, trade.entry_index, trade.exit_index)
        for policy, target_r in self.FIXED_TARGETS.items():
            record.policy_results[policy] = self.simulate_fixed_tp_policy(record, candles, target_r, policy)
        record.policy_results["BE_AFTER_0_5R"] = self.simulate_be_policy(record, candles, 0.5, "BE_AFTER_0_5R")
        record.policy_results["BE_AFTER_1R"] = self.simulate_be_policy(record, candles, 1.0, "BE_AFTER_1R")
        self._apply_convenience(record)
        return record

    def simulate_fixed_tp_policy(self, record: VirtualExitRecord, candles, target_r: float, policy_name: str) -> VirtualExitPolicyResult:
        result = VirtualExitPolicyResult(policy_name=policy_name, target_r=target_r)
        if not self._valid(record, candles):
            return result

        entry, risk = float(record.entry_price), float(record.risk)
        tp = entry + risk * target_r if record.direction == "LONG" else entry - risk * target_r
        sl = float(record.stop_loss)
        for offset, (index, candle) in enumerate(candles.iterrows(), start=1):
            high, low = float(candle["high"]), float(candle["low"])
            tp_hit = high >= tp if record.direction == "LONG" else low <= tp
            sl_hit = low <= sl if record.direction == "LONG" else high >= sl
            # Conservative same-candle rule: if target and stop are both touched, count stop first.
            if sl_hit:
                return self._finished(result, "LOSS", -1.0, sl, int(index), offset)
            if tp_hit:
                return self._finished(result, "WIN", target_r, tp, int(index), offset)
        return self._open_result(result, record, candles)

    def simulate_be_policy(self, record: VirtualExitRecord, candles, activation_r: float, policy_name: str) -> VirtualExitPolicyResult:
        result = VirtualExitPolicyResult(policy_name=policy_name, target_r=activation_r)
        if not self._valid(record, candles):
            return result

        entry, risk = float(record.entry_price), float(record.risk)
        original_sl = float(record.stop_loss)
        original_tp = float(record.take_profit)
        active_be = False
        for offset, (index, candle) in enumerate(candles.iterrows(), start=1):
            high, low = float(candle["high"]), float(candle["low"])
            original_sl_hit = low <= original_sl if record.direction == "LONG" else high >= original_sl
            original_tp_hit = high >= original_tp if record.direction == "LONG" else low <= original_tp
            activation_hit = high >= entry + risk * activation_r if record.direction == "LONG" else low <= entry - risk * activation_r
            be_hit = low <= entry if record.direction == "LONG" else high >= entry
            # Conservative ordering: original SL has priority before activation, and BE is used on same-candle activation.
            if not active_be and original_sl_hit:
                return self._finished(result, "LOSS", -1.0, original_sl, int(index), offset)
            if original_tp_hit:
                return self._finished(result, "WIN", record.original_rr, original_tp, int(index), offset)
            if activation_hit and not active_be:
                active_be = True
                result.activated_be = True
                result.bars_to_be_activation = offset
            if active_be and be_hit:
                return self._finished(result, "BREAKEVEN", 0.0, entry, int(index), offset)
        open_result = self._open_result(result, record, candles)
        open_result.activated_be = result.activated_be
        open_result.bars_to_be_activation = result.bars_to_be_activation
        return open_result

    def build_policy_summaries(self, records: list[VirtualExitRecord]) -> dict[str, VirtualExitPolicySummary]:
        summaries: dict[str, VirtualExitPolicySummary] = {}
        for policy in self.POLICIES:
            results = [record.policy_results[policy] for record in records if policy in record.policy_results]
            summary = VirtualExitPolicySummary(policy_name=policy, total_trades=len(results))
            summary.wins = sum(1 for result in results if result.result == "WIN")
            summary.losses = sum(1 for result in results if result.result == "LOSS")
            summary.breakevens = sum(1 for result in results if result.result == "BREAKEVEN")
            summary.opens = sum(1 for result in results if result.result == "OPEN")
            summary.unknowns = sum(1 for result in results if result.result == "UNKNOWN")
            known_count = summary.total_trades - summary.unknowns
            summary.win_rate = summary.wins / known_count * 100 if known_count else None
            pnl_values = [result.virtual_pnl_r for result in results if result.virtual_pnl_r is not None]
            summary.total_pnl_r = sum(pnl_values)
            summary.average_pnl_r = summary.total_pnl_r / len(pnl_values) if pnl_values else None
            bars = [result.bars_to_exit for result in results if result.bars_to_exit is not None]
            summary.average_bars_to_exit = sum(bars) / len(bars) if bars else None
            summaries[policy] = summary
        return summaries

    def _trade_candles(self, context: MarketContext, entry_index: int | None, exit_index: int | None):
        candles = getattr(context, "candles", None)
        if candles is None or entry_index is None or len(candles) == 0:
            return None
        start = max(int(entry_index), 0)
        end = int(exit_index) if exit_index is not None else len(candles) - 1
        end = min(end, len(candles) - 1)
        if start > end:
            return None
        # Strict non-lookahead: closed trades only simulate through actual exit; open trades use available context end.
        return candles.iloc[start : end + 1]

    def _valid(self, record: VirtualExitRecord, candles) -> bool:
        return (
            candles is not None
            and len(candles) > 0
            and record.entry_price is not None
            and record.stop_loss is not None
            and record.take_profit is not None
            and record.risk is not None
            and record.risk > 0
            and record.direction in ("LONG", "SHORT")
        )

    def _finished(self, result: VirtualExitPolicyResult, outcome: str, pnl_r: float | None, price: float, index: int, bars: int):
        result.result = outcome
        result.virtual_pnl_r = pnl_r
        result.exit_price = price
        result.exit_index = index
        result.bars_to_exit = bars
        return result

    def _open_result(self, result: VirtualExitPolicyResult, record: VirtualExitRecord, candles):
        result.result = "OPEN"
        if candles is not None and len(candles) > 0 and record.risk:
            last_close = float(candles.iloc[-1]["close"])
            result.virtual_pnl_r = (last_close - record.entry_price) / record.risk if record.direction == "LONG" else (record.entry_price - last_close) / record.risk
        return result

    def _actual_pnl_r(self, trade, context: MarketContext) -> float | None:
        if trade.result == "WIN":
            return trade.risk_reward
        if trade.result == "LOSS":
            return -1.0
        if trade.result == "OPEN" and trade.entry_price is not None and trade.risk and trade.risk > 0:
            candles = getattr(context, "candles", None)
            if candles is not None and len(candles) > 0:
                last_close = float(candles.iloc[-1]["close"])
                return (last_close - trade.entry_price) / trade.risk if trade.direction == "LONG" else (trade.entry_price - last_close) / trade.risk
        return None

    def _bars_held(self, entry_index: int | None, exit_index: int | None, context: MarketContext) -> int | None:
        if entry_index is None:
            return None
        candles = getattr(context, "candles", None)
        final_index = exit_index if exit_index is not None else (len(candles) - 1 if candles is not None else None)
        return None if final_index is None else max(int(final_index) - int(entry_index) + 1, 0)

    def _apply_convenience(self, record: VirtualExitRecord) -> None:
        known = [result for result in record.policy_results.values() if result.virtual_pnl_r is not None]
        if known:
            best = max(known, key=lambda result: result.virtual_pnl_r)
            record.best_policy_name = best.policy_name
            record.best_policy_pnl_r = best.virtual_pnl_r
        record.would_tp_1r_win = record.actual_result == "LOSS" and record.policy_results["TP_1R"].result == "WIN"
        record.would_tp_2r_win = record.actual_result == "LOSS" and record.policy_results["TP_2R"].result == "WIN"
        record.would_be_0_5r_help = record.actual_result == "LOSS" and record.policy_results["BE_AFTER_0_5R"].result in ("BREAKEVEN", "WIN")
        record.would_be_1r_help = record.actual_result == "LOSS" and record.policy_results["BE_AFTER_1R"].result in ("BREAKEVEN", "WIN")

    def _best_policy(self, summaries: dict[str, VirtualExitPolicySummary], field_name: str) -> str | None:
        usable = [summary for summary in summaries.values() if getattr(summary, field_name) is not None]
        return max(usable, key=lambda summary: getattr(summary, field_name)).policy_name if usable else None
