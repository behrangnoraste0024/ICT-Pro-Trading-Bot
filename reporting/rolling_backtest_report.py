from __future__ import annotations

from models.rolling_backtest_result import RollingBacktestResult


def format_rolling_backtest_report(
    result: RollingBacktestResult,
    fixture_path: str,
    min_candles: int,
    max_windows: int | None = None,
) -> str:
    failed_windows = getattr(result, "failed_windows", 0)
    stateful_mode = getattr(result, "stateful_mode", False)
    opened_trades = getattr(result, "opened_trades", 0)
    closed_by_state = getattr(result, "closed_by_state", 0)
    duplicate_signals_skipped = getattr(result, "duplicate_signals_skipped", 0)

    lines = [
        "===== ROLLING BACKTEST REPORT =====",
        f"Fixture           : {fixture_path}",
        f"Min Candles       : {min_candles}",
    ]
    if max_windows is not None:
        lines.append(f"Max Windows       : {max_windows}")
    lines.extend(
        [
            f"Stateful Mode     : {stateful_mode}",
            f"Total Windows     : {result.total_windows}",
            f"Processed Windows : {result.processed_windows}",
            f"Skipped Windows   : {result.skipped_windows}",
            f"Failed Windows    : {failed_windows}",
            f"Opened Trades     : {opened_trades}",
            f"Closed By State   : {closed_by_state}",
            f"Duplicates Skipped: {duplicate_signals_skipped}",
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
    return "\n".join(lines)
