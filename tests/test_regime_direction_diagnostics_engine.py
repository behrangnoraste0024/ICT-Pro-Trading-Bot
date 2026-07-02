from __future__ import annotations

from copy import deepcopy

from engine.diagnostics.regime_direction_diagnostics_engine import RegimeDirectionDiagnosticsEngine
from models.trade_outcome_diagnostics import TradeOutcomeRecord


def _trade(
    direction: str,
    regime: str | None,
    pnl: float | None,
    result: str = "WIN",
    reason: str | None = None,
    dir_reason: str | None = None,
    resolved: str | None = None,
) -> TradeOutcomeRecord:
    return TradeOutcomeRecord(
        trade_number=1,
        direction=direction,
        status="PAPER_OPEN" if result == "OPEN" else "PAPER_CLOSED_TP",
        pnl=pnl,
        result=result,
        market_regime=regime,
        market_regime_reason=reason,
        direction_mode_fallback_reason=dir_reason,
        direction_mode_resolved_direction=resolved,
    )


def test_aggregates_short_bearish() -> None:
    diagnostics = RegimeDirectionDiagnosticsEngine().summarize_trades(
        [_trade("SHORT", "BEARISH", 10, reason="BEARISH_ROLLING_RETURN", dir_reason="ALL_MODE", resolved="ALL")]
    )

    bucket = diagnostics.by_direction_regime["SHORT|BEARISH"]
    assert bucket.count == 1
    assert bucket.wins == 1
    assert bucket.pnl == 10


def test_aggregates_long_bearish() -> None:
    diagnostics = RegimeDirectionDiagnosticsEngine().summarize_trades(
        [_trade("LONG", "BEARISH", -5, result="LOSS", reason="BEARISH_ROLLING_RETURN", dir_reason="ALL_MODE", resolved="ALL")]
    )

    bucket = diagnostics.by_direction_regime["LONG|BEARISH"]
    assert bucket.losses == 1
    assert bucket.pnl == -5


def test_aggregates_short_bullish() -> None:
    diagnostics = RegimeDirectionDiagnosticsEngine().summarize_trades(
        [_trade("SHORT", "BULLISH", -7, result="LOSS", reason="BULLISH_ROLLING_RETURN", dir_reason="ALL_MODE", resolved="ALL")]
    )

    assert diagnostics.by_direction_regime["SHORT|BULLISH"].pnl == -7


def test_aggregates_long_bullish() -> None:
    diagnostics = RegimeDirectionDiagnosticsEngine().summarize_trades(
        [_trade("LONG", "BULLISH", 12, reason="BULLISH_ROLLING_RETURN", dir_reason="ALL_MODE", resolved="ALL")]
    )

    assert diagnostics.by_direction_regime["LONG|BULLISH"].pnl == 12


def test_counts_long_in_bearish_count_and_pnl() -> None:
    diagnostics = RegimeDirectionDiagnosticsEngine().summarize_trades(
        [
            _trade("LONG", "BEARISH", -5, result="LOSS", reason="BEARISH_ROLLING_RETURN", dir_reason="ALL_MODE", resolved="ALL"),
            _trade("LONG", "BEARISH", 3, reason="BEARISH_ROLLING_RETURN", dir_reason="ALL_MODE", resolved="ALL"),
        ]
    )

    assert diagnostics.long_in_bearish_count == 2
    assert diagnostics.long_in_bearish_pnl == -2


def test_counts_short_in_bullish_count_and_pnl() -> None:
    diagnostics = RegimeDirectionDiagnosticsEngine().summarize_trades(
        [
            _trade("SHORT", "BULLISH", -4, result="LOSS", reason="BULLISH_ROLLING_RETURN", dir_reason="ALL_MODE", resolved="ALL"),
            _trade("SHORT", "BULLISH", 6, reason="BULLISH_ROLLING_RETURN", dir_reason="ALL_MODE", resolved="ALL"),
        ]
    )

    assert diagnostics.short_in_bullish_count == 2
    assert diagnostics.short_in_bullish_pnl == 2


def test_handles_missing_metadata() -> None:
    diagnostics = RegimeDirectionDiagnosticsEngine().summarize_trades([_trade("LONG", None, 0)])

    assert diagnostics.trades_missing_regime == 1
    assert diagnostics.missing_metadata_count == 1
    assert "LONG|UNKNOWN" in diagnostics.by_direction_regime


def test_handles_open_trades() -> None:
    diagnostics = RegimeDirectionDiagnosticsEngine().summarize_trades(
        [_trade("SHORT", "BEARISH", None, result="OPEN", reason="BEARISH_ROLLING_RETURN", dir_reason="ALL_MODE", resolved="ALL")]
    )

    assert diagnostics.by_direction_regime["SHORT|BEARISH"].open_trades == 1


def test_groups_by_market_regime_reason() -> None:
    diagnostics = RegimeDirectionDiagnosticsEngine().summarize_trades(
        [_trade("SHORT", "BEARISH", 10, reason="BEARISH_ROLLING_RETURN", dir_reason="ALL_MODE", resolved="ALL")]
    )

    assert diagnostics.by_regime_reason["BEARISH_ROLLING_RETURN"].pnl == 10


def test_groups_by_direction_mode_fallback_reason() -> None:
    diagnostics = RegimeDirectionDiagnosticsEngine().summarize_trades(
        [
            _trade(
                "SHORT",
                "BEARISH",
                10,
                reason="BEARISH_ROLLING_RETURN",
                dir_reason="REGIME_TREND_BEARISH_SHORT_ONLY",
                resolved="SHORT",
            )
        ]
    )

    assert diagnostics.by_direction_mode_reason["REGIME_TREND_BEARISH_SHORT_ONLY"].count == 1


def test_groups_by_resolved_direction() -> None:
    diagnostics = RegimeDirectionDiagnosticsEngine().summarize_trades(
        [_trade("SHORT", "BEARISH", 10, reason="BEARISH_ROLLING_RETURN", dir_reason="ALL_MODE", resolved="SHORT")]
    )

    assert diagnostics.by_resolved_direction["SHORT"].count == 1


def test_groups_by_direction_quality_reason() -> None:
    trade = _trade("LONG", "BULLISH", -10, result="LOSS", reason="BULLISH_ROLLING_RETURN", dir_reason="ALL_MODE", resolved="ALL")
    trade.direction_quality_blocker = "STRICT_LONG_NO_DISPLACEMENT"
    trade.direction_quality_reasons = ["STRICT_LONG_NO_DISPLACEMENT"]

    diagnostics = RegimeDirectionDiagnosticsEngine().summarize_trades([trade])

    assert diagnostics.by_direction_quality_reason["STRICT_LONG_NO_DISPLACEMENT"].count == 1
    assert diagnostics.by_direction_quality_reason["STRICT_LONG_NO_DISPLACEMENT"].pnl == -10


def test_does_not_mutate_trades() -> None:
    trade = _trade("SHORT", "BEARISH", 10, reason="BEARISH_ROLLING_RETURN", dir_reason="ALL_MODE", resolved="SHORT")
    before = deepcopy(trade)

    RegimeDirectionDiagnosticsEngine().summarize_trades([trade])

    assert trade == before


def test_empty_trade_list_returns_zero_diagnostics() -> None:
    diagnostics = RegimeDirectionDiagnosticsEngine().summarize_trades([])

    assert diagnostics.total_trades == 0
    assert diagnostics.by_direction_regime == {}
