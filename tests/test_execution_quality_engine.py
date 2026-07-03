from __future__ import annotations

import pandas as pd

from engine.execution_quality.execution_quality_engine import ExecutionQualityEngine
from models.market_context import MarketContext


def _context(candles: pd.DataFrame, entry_index: int = 0) -> MarketContext:
    context = MarketContext(candles=candles)
    context.paper_trade_status = "PAPER_CLOSED_TP"
    context.paper_trade_direction = "BULLISH"
    context.paper_entry_index = entry_index
    context.paper_entry_price = float(candles.iloc[entry_index]["close"])
    context.paper_pnl = 10.0
    context.setup_score = 80
    context.planned_risk_reward = 2.0
    context.liquidity_sweeps = [object()]
    context.matched_pois = [object()]
    return context


def test_execution_quality_is_deterministic_and_bounded() -> None:
    candles = pd.DataFrame(
        [
            {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
            {"open": 100, "high": 120, "low": 80, "close": 110, "volume": 1},
        ]
    )

    result_one = ExecutionQualityEngine().evaluate(_context(candles))
    result_two = ExecutionQualityEngine().evaluate(_context(candles))

    assert result_one.score == result_two.score
    assert 0.0 <= result_one.score <= 1.0
    assert result_one.reasoning["uses_entry_candle_only"] is True


def test_execution_quality_ignores_future_candles() -> None:
    base = pd.DataFrame(
        [
            {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
            {"open": 100, "high": 120, "low": 80, "close": 110, "volume": 1},
        ]
    )
    altered_future = pd.DataFrame(
        [
            {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
            {"open": 100, "high": 200, "low": 50, "close": 150, "volume": 1},
        ]
    )

    score_one = ExecutionQualityEngine().evaluate(_context(base)).score
    score_two = ExecutionQualityEngine().evaluate(_context(altered_future)).score

    assert score_one == score_two


def test_execution_quality_attach_populates_context() -> None:
    candles = pd.DataFrame(
        [
            {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
        ]
    )

    context = ExecutionQualityEngine().attach(_context(candles))

    assert context.execution_quality_result is not None
    assert context.execution_quality_score == context.execution_quality_result.score
