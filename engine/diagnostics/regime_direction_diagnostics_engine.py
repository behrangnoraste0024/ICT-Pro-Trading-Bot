from __future__ import annotations

from copy import deepcopy
from typing import Any

from engine.backtest.trade_outcome_diagnostics_engine import TradeOutcomeDiagnosticsEngine
from models.market_context import MarketContext
from models.regime_direction_diagnostics import RegimeDirectionBucket, RegimeDirectionDiagnostics
from models.trade_outcome_diagnostics import TradeOutcomeRecord


class RegimeDirectionDiagnosticsEngine:
    def __init__(self) -> None:
        self.trade_outcome_engine = TradeOutcomeDiagnosticsEngine()

    def summarize_contexts(self, contexts: list[MarketContext]) -> RegimeDirectionDiagnostics:
        trades: list[TradeOutcomeRecord] = []
        for context in contexts:
            trade = self.trade_outcome_engine.collect_from_context(context, len(trades) + 1)
            if trade is not None:
                trades.append(trade)
        return self.summarize_trades(trades)

    def summarize_trades(self, trades: list[TradeOutcomeRecord]) -> RegimeDirectionDiagnostics:
        diagnostics = RegimeDirectionDiagnostics(total_trades=len(trades))

        for source_trade in trades:
            trade = deepcopy(source_trade)
            regime = self._value(getattr(trade, "market_regime", None), "UNKNOWN")
            direction = self._value(getattr(trade, "direction", None), "UNKNOWN")
            result = self._value(getattr(trade, "result", None), "UNKNOWN")
            pnl = getattr(trade, "pnl", None)

            if regime == "UNKNOWN":
                diagnostics.trades_missing_regime += 1
            else:
                diagnostics.trades_with_regime += 1

            if self._has_missing_metadata(trade):
                diagnostics.missing_metadata_count += 1

            self._add(diagnostics.by_direction_regime, f"{direction}|{regime}", result, pnl)
            self._add(
                diagnostics.by_regime_reason,
                self._value(getattr(trade, "market_regime_reason", None), "UNKNOWN"),
                result,
                pnl,
            )
            self._add(
                diagnostics.by_direction_mode_reason,
                self._value(getattr(trade, "direction_mode_fallback_reason", None), "UNKNOWN"),
                result,
                pnl,
            )
            self._add(
                diagnostics.by_resolved_direction,
                self._value(getattr(trade, "direction_mode_resolved_direction", None), "UNKNOWN"),
                result,
                pnl,
            )
            quality_reasons = list(getattr(trade, "direction_quality_reasons", []) or [])
            quality_key = getattr(trade, "direction_quality_blocker", None) or (quality_reasons[0] if quality_reasons else None)
            self._add(
                diagnostics.by_direction_quality_reason,
                self._value(quality_key, "UNKNOWN"),
                result,
                pnl,
            )

            if direction == "LONG" and regime == "BEARISH":
                diagnostics.long_in_bearish_count += 1
                diagnostics.long_in_bearish_pnl += float(pnl or 0)
            if direction == "SHORT" and regime == "BULLISH":
                diagnostics.short_in_bullish_count += 1
                diagnostics.short_in_bullish_pnl += float(pnl or 0)

        return diagnostics

    def _add(self, buckets: dict[str, RegimeDirectionBucket], key: str, result: str, pnl: float | None) -> None:
        if key not in buckets:
            buckets[key] = RegimeDirectionBucket(key=key)
        buckets[key].add_trade(result, pnl)

    def _value(self, value: Any, default: str) -> str:
        if value is None or value == "":
            return default
        return str(value)

    def _has_missing_metadata(self, trade: TradeOutcomeRecord) -> bool:
        return any(
            getattr(trade, field_name, None) is None
            for field_name in (
                "market_regime",
                "market_regime_reason",
                "direction_mode_fallback_reason",
                "direction_mode_resolved_direction",
            )
        )
