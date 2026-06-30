from __future__ import annotations

from copy import copy
from typing import Any

from models.market_context import MarketContext
from models.trade_outcome_diagnostics import TradeOutcomeDiagnostics, TradeOutcomeRecord


class TradeOutcomeDiagnosticsEngine:
    TRADE_STATUSES = {"PAPER_OPEN", "PAPER_CLOSED_TP", "PAPER_CLOSED_SL"}

    def summarize_contexts(self, contexts: list[MarketContext]) -> TradeOutcomeDiagnostics:
        trades: list[TradeOutcomeRecord] = []
        for context in contexts:
            record = self.collect_from_context(context, len(trades) + 1)
            if record is not None:
                trades.append(record)

        diagnostics = TradeOutcomeDiagnostics(trades=trades, total_trades=len(trades))
        diagnostics.closed_trades = sum(1 for trade in trades if trade.result in ("WIN", "LOSS"))
        diagnostics.open_trades = sum(1 for trade in trades if trade.result == "OPEN")
        diagnostics.wins = sum(1 for trade in trades if trade.result == "WIN")
        diagnostics.losses = sum(1 for trade in trades if trade.result == "LOSS")
        diagnostics.net_pnl = sum(float(trade.pnl or 0) for trade in trades)
        diagnostics.average_pnl = diagnostics.net_pnl / diagnostics.closed_trades if diagnostics.closed_trades else 0.0
        diagnostics.win_rate = (diagnostics.wins / diagnostics.closed_trades * 100) if diagnostics.closed_trades else 0.0

        wins = [float(trade.pnl) for trade in trades if trade.result == "WIN" and trade.pnl is not None]
        losses = [float(trade.pnl) for trade in trades if trade.result == "LOSS" and trade.pnl is not None]
        rrs = [float(trade.risk_reward) for trade in trades if trade.risk_reward is not None]
        setup_scores = [float(trade.setup_score) for trade in trades if trade.setup_score is not None]
        diagnostics.average_win = sum(wins) / len(wins) if wins else None
        diagnostics.average_loss = sum(losses) / len(losses) if losses else None
        diagnostics.largest_win = max(wins) if wins else None
        diagnostics.largest_loss = min(losses) if losses else None
        diagnostics.average_rr = sum(rrs) / len(rrs) if rrs else None
        diagnostics.average_setup_score = sum(setup_scores) / len(setup_scores) if setup_scores else None
        return diagnostics

    def collect_from_context(self, context: MarketContext, trade_number: int) -> TradeOutcomeRecord | None:
        status = getattr(context, "paper_trade_status", "NO_PAPER_TRADE")
        if status not in self.TRADE_STATUSES:
            return None

        direction = self._normalize_direction(
            self._first_value(
                context,
                ["paper_trade_direction", "trade_direction", "entry_direction", "trade_plan_direction"],
                "UNKNOWN",
            )
        )
        entry_price = self._float_or_none(self._first_value(context, ["paper_entry_price", "planned_entry_price"]))
        stop_loss = self._float_or_none(self._first_value(context, ["paper_stop_loss", "planned_stop_loss"]))
        take_profit = self._float_or_none(self._first_value(context, ["paper_take_profit", "planned_take_profit"]))
        exit_price = self._float_or_none(getattr(context, "paper_exit_price", None))
        pnl = self._float_or_none(getattr(context, "paper_pnl", None))
        entry_index = self._int_or_none(getattr(context, "paper_entry_index", None))
        exit_index = self._int_or_none(getattr(context, "paper_exit_index", None))
        risk, reward, risk_reward = self._risk_metrics(direction, entry_price, stop_loss, take_profit)
        matched_pois = self._matched_pois(context)

        return TradeOutcomeRecord(
            trade_number=trade_number,
            direction=direction,
            status=status,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            exit_price=exit_price,
            pnl=pnl,
            result=self._result(status),
            risk=risk,
            reward=reward,
            risk_reward=risk_reward,
            entry_index=entry_index,
            exit_index=exit_index,
            entry_timestamp=self._timestamp_at(context, entry_index),
            exit_timestamp=self._timestamp_at(context, exit_index),
            setup_status=getattr(context, "setup_status", None),
            setup_bias=getattr(context, "setup_bias", None),
            setup_score=getattr(context, "setup_score", None),
            entry_status=getattr(context, "entry_status", None),
            entry_trigger_type=getattr(context, "entry_trigger_type", None),
            dealing_range_mode=getattr(context, "dealing_range_mode_applied", None),
            current_price_zone=getattr(context, "current_price_zone", None),
            in_ote_zone=getattr(context, "in_ote_zone", None),
            ote_direction=getattr(context, "ote_direction", None),
            dealing_range_high=self._float_or_none(getattr(context, "dealing_range_high", None)),
            dealing_range_low=self._float_or_none(getattr(context, "dealing_range_low", None)),
            equilibrium=self._float_or_none(getattr(context, "equilibrium", None)),
            matched_poi_count=len(matched_pois),
            matched_poi_types=[self._poi_type(poi) for poi in matched_pois],
            trade_quality_status=getattr(context, "trade_quality_status", None),
            trade_quality_score=getattr(context, "trade_quality_score", None),
            setup_blockers=self._safe_list(getattr(context, "setup_blockers", [])),
            entry_blockers=self._safe_list(getattr(context, "entry_blockers", [])),
            trade_plan_blockers=self._safe_list(getattr(context, "trade_plan_blockers", [])),
            trade_quality_blockers=self._safe_list(getattr(context, "trade_quality_blockers", [])),
            paper_trade_blockers=self._safe_list(getattr(context, "paper_trade_blockers", [])),
            reasons=self._safe_list(self._first_value(context, ["paper_trade_reasons", "reasons"], [])),
        )

    def _result(self, status: str) -> str:
        if status == "PAPER_CLOSED_TP":
            return "WIN"
        if status == "PAPER_CLOSED_SL":
            return "LOSS"
        if status == "PAPER_OPEN":
            return "OPEN"
        return "UNKNOWN"

    def _risk_metrics(
        self,
        direction: str,
        entry_price: float | None,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> tuple[float | None, float | None, float | None]:
        if entry_price is None or stop_loss is None or take_profit is None:
            return None, None, None
        if direction == "LONG":
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
        elif direction == "SHORT":
            risk = stop_loss - entry_price
            reward = entry_price - take_profit
        else:
            return None, None, None
        risk_reward = reward / risk if risk > 0 and reward > 0 else None
        return risk, reward, risk_reward

    def _normalize_direction(self, direction: Any) -> str:
        value = str(direction or "UNKNOWN").upper()
        if value in ("BULLISH", "LONG", "BUY"):
            return "LONG"
        if value in ("BEARISH", "SHORT", "SELL"):
            return "SHORT"
        return value

    def _matched_pois(self, context: MarketContext) -> list[Any]:
        active_setup = getattr(context, "active_setup", None)
        for source in [
            getattr(active_setup, "matched_pois", None) if active_setup is not None else None,
            getattr(context, "matched_pois", None),
            getattr(context, "setup_matched_pois", None),
        ]:
            if source:
                return list(source)
        return []

    def _poi_type(self, poi: Any) -> str:
        for field_name in ("poi_type", "type", "event_type", "direction"):
            value = getattr(poi, field_name, None)
            if value is not None:
                return str(value)
        return poi.__class__.__name__

    def _timestamp_at(self, context: MarketContext, index: int | None) -> str | int | None:
        candles = getattr(context, "candles", None)
        if candles is None or index is None or index < 0 or index >= len(candles):
            return None
        try:
            value = candles.iloc[index]["timestamp"]
        except (KeyError, TypeError, IndexError):
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value.item() if hasattr(value, "item") else value

    def _first_value(self, context: MarketContext, field_names: list[str], default=None):
        for field_name in field_names:
            value = getattr(context, field_name, None)
            if value is not None:
                return value
        return default

    def _safe_list(self, values) -> list[str]:
        if values is None:
            return []
        if isinstance(values, list):
            return [str(value) for value in copy(values)]
        return [str(values)]

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
