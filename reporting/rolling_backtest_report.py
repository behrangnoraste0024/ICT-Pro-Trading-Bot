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
    diagnostics = getattr(result, "diagnostics", None)
    if diagnostics is not None:
        lines.extend(_format_diagnostics(diagnostics))
    return "\n".join(lines)


def _format_diagnostics(diagnostics) -> list[str]:
    return [
        "",
        "===== BACKTEST DIAGNOSTICS =====",
        f"Windows Analyzed : {diagnostics.windows_analyzed}",
        "",
        "Setup Status Counts:",
        *_format_counts(diagnostics.setup_status_counts),
        "",
        "Setup Blockers:",
        *_format_counts(diagnostics.setup_blockers, sort_by_count=True),
        "",
        "Entry Status Counts:",
        *_format_counts(diagnostics.entry_status_counts),
        "",
        "Entry Blockers:",
        *_format_counts(diagnostics.entry_blockers, sort_by_count=True),
        "",
        "Trade Plan Status Counts:",
        *_format_counts(diagnostics.trade_plan_status_counts),
        "",
        "Trade Plan Blockers:",
        *_format_counts(diagnostics.trade_plan_blockers, sort_by_count=True),
        "",
        "Trade Quality Status Counts:",
        *_format_counts(diagnostics.trade_quality_status_counts),
        "",
        "Trade Quality Blockers:",
        *_format_counts(diagnostics.trade_quality_blockers, sort_by_count=True),
        "",
        "Paper Trade Status Counts:",
        *_format_counts(diagnostics.paper_trade_status_counts),
        "",
        "Paper Trade Blockers:",
        *_format_counts(diagnostics.paper_trade_blockers, sort_by_count=True),
    ]


def _format_counts(counts: dict[str, int], sort_by_count: bool = False) -> list[str]:
    if not counts:
        return ["None"]

    if sort_by_count:
        items = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    else:
        items = sorted(counts.items())
    return [f"{name:<30}: {count}" for name, count in items]
