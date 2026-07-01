from __future__ import annotations

from models.strategy_comparison import StrategyComparisonReport, StrategyComparisonRow


def format_strategy_comparison_report(
    report: StrategyComparisonReport,
    sort_by: str = "net_pnl",
    descending: bool = True,
    show_all: bool = False,
) -> str:
    rows = report.sorted_by(sort_by, descending=descending)
    ranked_rows = _ranked(rows)
    display_rows = ranked_rows if show_all or len(ranked_rows) <= 20 else ranked_rows[:20]
    lines = [
        "===== STRATEGY COMPARISON REPORT =====",
        f"Fixture      : {report.fixture}",
        f"Min Candles  : {report.min_candles}",
        f"Strategies   : {len(report.strategies)}",
        f"Sort By      : {sort_by}",
        "",
        "Best:",
        f"Net PnL      : {report.best_by_net_pnl}",
        f"Average PnL  : {report.best_by_average_pnl}",
        f"Win Rate     : {report.best_by_win_rate}",
        f"ProfitFactor : {report.best_by_profit_factor}",
        f"Drawdown     : {report.best_by_drawdown}",
        "",
        "Comparison Table:",
        "Rank | Strategy | DR Mode | Exit | MinRR | Trades | W/L | Win% | NetPnL | AvgPnL | MaxDD | PF | LongPnL | ShortPnL | Dups | Elapsed",
    ]
    lines.extend(_format_row(row) for row in display_rows)
    if len(display_rows) < len(ranked_rows):
        lines.append(f"... {len(ranked_rows) - len(display_rows)} more strategies hidden. Use --show-all to display all rows.")

    lines.extend(
        [
            "",
            "Diagnostics Table:",
            "Rank | Strategy | FastLoss | NoFTLoss | HighRRLoss | NextCont | NextReject",
        ]
    )
    lines.extend(_format_diagnostics_row(row) for row in display_rows)
    return "\n".join(lines)


def _ranked(rows: list[StrategyComparisonRow]) -> list[StrategyComparisonRow]:
    ranked: list[StrategyComparisonRow] = []
    for rank, row in enumerate(rows, start=1):
        row.rank = rank
        ranked.append(row)
    return ranked


def _format_row(row: StrategyComparisonRow) -> str:
    return (
        f"{row.rank} | {row.strategy_name} | {row.dealing_range_mode} | {row.exit_mode} | "
        f"{_fmt(row.min_risk_reward)} | {row.total_trades} | {row.wins}/{row.losses} | "
        f"{_fmt(row.win_rate)} | {_fmt(row.net_pnl)} | {_fmt(row.average_pnl)} | "
        f"{_fmt(row.max_drawdown)} | {_fmt(row.profit_factor)} | {_fmt(row.long_pnl)} | "
        f"{_fmt(row.short_pnl)} | {row.duplicate_signals_skipped} | {_fmt(row.elapsed_seconds)}"
    )


def _format_diagnostics_row(row: StrategyComparisonRow) -> str:
    return (
        f"{row.rank} | {row.strategy_name} | {row.fast_losses} | {row.no_followthrough_losses} | "
        f"{row.high_rr_losses} | {row.next_candle_continuation} | {row.next_candle_rejection}"
    )


def _fmt(value) -> str:
    if value is None:
        return "None"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
