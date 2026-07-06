from __future__ import annotations

from models.recommended_profile_validation import RecommendedProfileValidationResult


def format_recommended_profile_validation_report(result: RecommendedProfileValidationResult) -> str:
    selected = result.selected
    lines = [
        "===== RECOMMENDED PROFILE VALIDATION =====",
        f"Recommended Strategy : {None if selected is None else selected.recommended_strategy_name}",
        f"Recommended Profile  : {None if selected is None else selected.recommended_profile}",
        f"Reason               : {None if selected is None else selected.recommendation_reason}",
        f"Score Threshold      : {None if selected is None else _fmt(selected.score_threshold)}",
        "",
        "Performance:",
        f"Trades               : {0 if selected is None else selected.total_trades}",
        f"Wins/Losses          : {'0/0' if selected is None else f'{selected.wins}/{selected.losses}'}",
        f"Win Rate             : {None if selected is None else _fmt(selected.win_rate)}",
        f"Gross PnL            : {None if selected is None else _fmt(selected.gross_net_pnl)}",
        f"Total Cost           : {None if selected is None else _fmt(selected.total_cost)}",
        f"Net After Costs      : {None if selected is None else _fmt(selected.net_pnl_after_costs)}",
        f"Max Drawdown         : {None if selected is None else _fmt(selected.max_drawdown)}",
        f"Profit Factor        : {None if selected is None else _fmt(selected.profit_factor)}",
        f"Decision Score       : {None if selected is None else _fmt(selected.average_decision_score)}",
        f"Execution Quality    : {None if selected is None else _fmt(selected.average_execution_quality)}",
        "",
        "Baseline:",
        f"Baseline Strategy    : {None if selected is None else selected.baseline_strategy_name}",
        f"Baseline Net After   : {None if selected is None else _fmt(selected.baseline_net_pnl_after_costs)}",
        f"Baseline MaxDD       : {None if selected is None else _fmt(selected.baseline_max_drawdown)}",
        f"Improvement vs Base  : {None if selected is None else _fmt(selected.improvement_vs_baseline)}",
        "",
        "Candidate Ranking:",
        "Rank | Strategy | Profile | ScoreThreshold | Trades | W/L | Win% | NetAfterCost | MaxDD | DecisionScore | ExecQ",
    ]
    for rank, candidate in enumerate(result.ranking, start=1):
        lines.append(
            f"{rank} | {candidate.recommended_strategy_name} | {candidate.recommended_profile} | "
            f"{_fmt(candidate.score_threshold)} | {candidate.total_trades} | {candidate.wins}/{candidate.losses} | "
            f"{_fmt(candidate.win_rate)} | {_fmt(candidate.net_pnl_after_costs)} | "
            f"{_fmt(candidate.max_drawdown)} | {_fmt(candidate.average_decision_score)} | "
            f"{_fmt(candidate.average_execution_quality)}"
        )
    return "\n".join(lines)


def _fmt(value) -> str:
    if value is None:
        return "None"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
