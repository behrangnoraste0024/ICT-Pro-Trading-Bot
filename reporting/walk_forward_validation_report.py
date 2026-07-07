from __future__ import annotations

from models.walk_forward_validation import WalkForwardRecommendedProfileValidation


def format_walk_forward_validation_report(result: WalkForwardRecommendedProfileValidation) -> str:
    lines = [
        "===== WALK-FORWARD RECOMMENDED PROFILE VALIDATION =====",
        f"Profile              : {result.profile}",
        f"Strategy             : {result.strategy_name}",
        f"Score Threshold      : {_fmt(result.score_threshold)}",
        f"Segments             : {result.segment_count}",
        f"Validation Status    : {result.validation_status}",
        f"Reason               : {result.validation_reason}",
        "",
        "Aggregate:",
        f"Trades               : {result.total_trades}",
        f"Wins/Losses          : {result.wins}/{result.losses}",
        f"Win Rate             : {_fmt(result.win_rate)}",
        f"Gross PnL            : {_fmt(result.gross_net_pnl)}",
        f"Total Cost           : {_fmt(result.total_cost)}",
        f"Net After Costs      : {_fmt(result.net_pnl_after_costs)}",
        f"Max Drawdown         : {_fmt(result.max_drawdown)}",
        f"Profitable Segments  : {result.profitable_segments}/{result.segment_count}",
        f"Losing Segments      : {result.losing_segments}",
        f"Empty Segments       : {result.empty_segments}",
        f"Worst Segment Net    : {_fmt(result.worst_segment_net_pnl_after_costs)}",
        f"Avg Segment Net      : {_fmt(result.average_segment_net_pnl_after_costs)}",
        "",
        "Segments:",
        "Segment | Trades | W/L | Win% | NetAfterCost | MaxDD | AvgDecision | AvgExecQ | Status | FailureReasons",
    ]
    for segment in result.segments:
        lines.append(
            f"{segment.segment_name} | {segment.total_trades} | {segment.wins}/{segment.losses} | "
            f"{_fmt(segment.win_rate)} | {_fmt(segment.net_pnl_after_costs)} | {_fmt(segment.max_drawdown)} | "
            f"{_fmt(segment.average_decision_score)} | {_fmt(segment.average_execution_quality)} | "
            f"{'PASS' if segment.passed else 'FAIL'} | {','.join(segment.failure_reasons)}"
        )
    return "\n".join(lines)


def _fmt(value) -> str:
    if value is None:
        return "None"
    if isinstance(value, (float, int)):
        return f"{value:.2f}"
    return str(value)
