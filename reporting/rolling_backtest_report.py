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
    lines = [
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
    ote_diagnostics = getattr(diagnostics, "ote_diagnostics", None)
    if ote_diagnostics is not None:
        lines.extend(_format_ote_diagnostics(ote_diagnostics))
    return lines


def _format_counts(counts: dict[str, int], sort_by_count: bool = False) -> list[str]:
    if not counts:
        return ["None"]

    if sort_by_count:
        items = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    else:
        items = sorted(counts.items())
    return [f"{name:<30}: {count}" for name, count in items]


def _format_ote_diagnostics(diagnostics) -> list[str]:
    return [
        "",
        "===== OTE DISTANCE DIAGNOSTICS =====",
        f"Windows Analyzed           : {diagnostics.windows_analyzed}",
        f"OTE Available              : {diagnostics.ote_available_count}",
        f"OTE Missing                : {diagnostics.ote_missing_count}",
        f"In OTE                     : {diagnostics.in_ote_count}",
        f"Not In OTE                 : {diagnostics.not_in_ote_count}",
        f"Near OTE <= 0.1%           : {diagnostics.near_ote_0_1_pct_count}",
        f"Near OTE <= 0.25%          : {diagnostics.near_ote_0_25_pct_count}",
        f"Near OTE <= 0.5%           : {diagnostics.near_ote_0_5_pct_count}",
        f"Near OTE <= 1.0%           : {diagnostics.near_ote_1_0_pct_count}",
        f"Average Distance To OTE    : {_format_optional_float(diagnostics.average_distance_to_ote)}",
        f"Median Distance To OTE     : {_format_optional_float(diagnostics.median_distance_to_ote)}",
        f"Max Distance To OTE        : {_format_optional_float(diagnostics.max_distance_to_ote)}",
        "",
        "Price Zone Counts:",
        f"PREMIUM                    : {diagnostics.premium_count}",
        f"DISCOUNT                   : {diagnostics.discount_count}",
        f"EQUILIBRIUM                : {diagnostics.equilibrium_count}",
        f"UNKNOWN                    : {diagnostics.unknown_zone_count}",
        "",
        "OTE Direction Counts:",
        f"BULLISH                    : {diagnostics.bullish_ote_count}",
        f"BEARISH                    : {diagnostics.bearish_ote_count}",
        f"NONE                       : {diagnostics.none_ote_count}",
        "",
        "Equilibrium Distance:",
        f"Near EQ <= 0.1%            : {diagnostics.near_equilibrium_0_1_pct_count}",
        f"Near EQ <= 0.25%           : {diagnostics.near_equilibrium_0_25_pct_count}",
        f"Near EQ <= 0.5%            : {diagnostics.near_equilibrium_0_5_pct_count}",
        f"Average Distance To EQ     : {_format_optional_float(diagnostics.average_distance_to_equilibrium)}",
        f"Median Distance To EQ      : {_format_optional_float(diagnostics.median_distance_to_equilibrium)}",
        f"Max Distance To EQ         : {_format_optional_float(diagnostics.max_distance_to_equilibrium)}",
    ]


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return "None"
    return str(value)
