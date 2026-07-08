from __future__ import annotations

from models.historical_sample_preparation import HistoricalSamplePreparationPlan


def format_historical_sample_preparation_report(plan: HistoricalSamplePreparationPlan) -> str:
    lines = [
        "===== HISTORICAL SAMPLE PREPARATION PLAN =====",
        f"Registry      : {plan.registry_path}",
        f"Total Samples : {plan.total_samples}",
        f"Ready Samples : {plan.ready_samples}",
        f"Need Action   : {plan.action_required_samples}",
        f"Full Ready    : {_yes_no(plan.required_full_ready)}",
        f"CI Ready      : {_yes_no(plan.required_ci_ready)}",
        "",
        "Actions:",
        "Sample | Symbol | TF | CurrentStatus | Action | RequiredFull | RequiredCI | MinCandles | Destination | Reason",
    ]
    for action in plan.actions:
        lines.append(
            f"{action.sample_name} | {action.symbol} | {action.timeframe} | "
            f"{action.current_status} | {action.action_type} | "
            f"{_yes_no(action.required_for_full_gate)} | {_yes_no(action.required_for_ci_gate)} | "
            f"{action.expected_min_candles} | {action.fixture_path} | {action.reason}"
        )
    lines.extend(["", "Suggested Commands:"])
    for action in plan.actions:
        if action.action_type == "NONE":
            continue
        lines.append(f"- {action.sample_name}: {action.suggested_import_command}")
        lines.append(f"- {action.sample_name}: {action.suggested_download_command}")
    if all(action.action_type == "NONE" for action in plan.actions):
        lines.append("- None")
    return "\n".join(lines)


def _yes_no(value: bool) -> str:
    return "YES" if value else "NO"
