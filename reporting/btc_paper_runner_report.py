from __future__ import annotations

from models.btc_paper_runner import BTCPaperRunnerStatus, BTCPaperRunnerTransitionResult


def format_btc_paper_runner_status_report(
    status: BTCPaperRunnerStatus,
    transition: BTCPaperRunnerTransitionResult | None = None,
) -> str:
    lines = [
        "===== BTC PAPER RUNNER DRY-RUN STATUS =====",
        f"Project Scope       : {status.project_scope}",
        f"Symbol              : {status.symbol}",
        f"Profile             : {status.strategy_profile}",
        f"State               : {status.state}",
        f"Last Action         : {status.last_action}",
        f"Runner Enabled      : {_fmt_bool(status.runner_enabled)}",
        f"Dry Run Only        : {_fmt_bool(status.dry_run_only)}",
        f"Signals Enabled     : {_fmt_bool(status.signal_generation_enabled)}",
        f"Paper Trades Enabled: {_fmt_bool(status.paper_trade_creation_enabled)}",
        f"Order Submission    : {_fmt_bool(status.order_submission_enabled)}",
        f"Exchange Connection : {_fmt_bool(status.exchange_connection_enabled)}",
        f"Runtime Config      : {status.runtime_config_status}",
        f"Monitoring Config   : {status.monitoring_config_status}",
        f"Kill Switch         : {_fmt_bool(status.kill_switch_enabled)}",
        f"Last Heartbeat      : {status.last_heartbeat_at}",
        f"Error               : {status.error_message}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    if status.issues:
        lines.extend(f"{issue.name} | {issue.severity} | {issue.message}" for issue in status.issues)
    else:
        lines.append("None | INFO | No issues found.")
    if transition is not None:
        lines.extend(
            [
                "",
                "Transition:",
                f"Action              : {transition.action.lower()}",
                f"Accepted            : {_fmt_bool(transition.accepted)}",
                f"Message             : {transition.message}",
            ]
        )
    return "\n".join(lines)


def _fmt_bool(value) -> str:
    if value is None:
        return "None"
    return str(bool(value)).lower()
