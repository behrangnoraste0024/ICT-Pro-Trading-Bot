from __future__ import annotations

from models.evolution import GenerationResult


def format_generation_result(result: GenerationResult) -> str:
    lines = [
        "===== GENERATION LOOP REPORT =====",
        f"Generation : {result.generation}",
        f"Top K      : {result.top_k}",
        f"Evaluated  : {len(result.evaluated)}",
        f"Selected   : {len(result.selected)}",
        f"Generated  : {len(result.next_generation)}",
        "",
        "Selected Candidates:",
    ]
    if not result.selected:
        lines.append("None")
    else:
        for rank, evaluation in enumerate(result.selected, start=1):
            lines.append(
                f"{rank}. {evaluation.candidate.strategy_spec.name} | "
                f"fitness={_fmt(evaluation.fitness)} | "
                f"net_after_cost={_fmt(evaluation.net_pnl_after_costs)} | "
                f"win_rate={_fmt(evaluation.win_rate)} | "
                f"drawdown={_fmt(evaluation.max_drawdown)} | "
                f"trades={evaluation.total_trades}"
            )

    lines.extend(["", "Next Generation Candidates:"])
    if not result.next_generation:
        lines.append("None")
    else:
        for candidate in result.next_generation:
            spec = candidate.strategy_spec
            lines.append(
                f"{candidate.candidate_id} | parent={candidate.parent_id} | "
                f"reason={candidate.mutation_reason} | "
                f"{spec.name} | rr={_fmt(spec.min_risk_reward)} | "
                f"dir={spec.direction_mode} | dq={spec.direction_quality_mode} | "
                f"slippage={_fmt(spec.slippage_pct)}"
            )
    return "\n".join(lines)


def _fmt(value) -> str:
    if value is None:
        return "None"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
