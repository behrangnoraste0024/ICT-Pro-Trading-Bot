from __future__ import annotations

from models.rolling_backtest_result import RollingBacktestResult


def format_rolling_backtest_report(
    result: RollingBacktestResult,
    fixture_path: str,
    min_candles: int,
) -> str:
    failed_windows = getattr(result, "failed_windows", 0)

    return "\n".join(
        [
            "===== ROLLING BACKTEST REPORT =====",
            f"Fixture           : {fixture_path}",
            f"Min Candles       : {min_candles}",
            f"Total Windows     : {result.total_windows}",
            f"Processed Windows : {result.processed_windows}",
            f"Skipped Windows   : {result.skipped_windows}",
            f"Failed Windows    : {failed_windows}",
            f"Total Trades      : {result.total_paper_trades}",
            f"Closed Trades     : {result.closed_trades}",
            f"Open Trades       : {result.open_trades}",
            f"Wins              : {result.wins}",
            f"Losses            : {result.losses}",
            f"Win Rate          : {result.win_rate}",
            f"Net PnL           : {result.net_pnl}",
            f"Average PnL       : {result.average_pnl}",
            f"Max Drawdown      : {result.max_drawdown}",
        ]
    )
