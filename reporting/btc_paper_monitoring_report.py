from __future__ import annotations

from models.btc_paper_monitoring import BTCPaperMonitoringStatus, BTCPaperMonitoringValidationReport


def format_btc_paper_monitoring_validation_report(report: BTCPaperMonitoringValidationReport) -> str:
    config = report.config
    lines = [
        "===== BTC PAPER MONITORING CONFIG VALIDATION =====",
        f"Config Path       : {report.config_path}",
        f"Status            : {report.status}",
        f"Symbol            : {_get(config, 'symbol')}",
        f"Profile           : {_get(config, 'strategy_profile')}",
        f"Monitoring Only   : {_fmt_bool(_get(config, 'monitoring_only'))}",
        f"Paper Expected    : {_fmt_bool(_get(config, 'paper_execution_expected'))}",
        f"Live Expected     : {_fmt_bool(_get(config, 'live_trading_expected'))}",
        f"Order Expected    : {_fmt_bool(_get(config, 'order_submission_expected'))}",
        f"Runtime Config    : {report.diagnostics.get('runtime_config_status', 'UNKNOWN')}",
        "",
        "Thresholds:",
        f"Heartbeat Stale   : {_get(config, 'heartbeat_stale_after_seconds')}s",
        f"Signal Stale      : {_get(config, 'signal_stale_after_minutes')}m",
        f"Gate Stale        : {_get(config, 'validation_gate_stale_after_hours')}h",
        f"Runtime Stale     : {_get(config, 'runtime_config_stale_after_hours')}h",
        f"Max Errors        : {_get(config, 'max_consecutive_errors')}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    if report.issues:
        lines.extend(f"{issue.name} | {issue.severity} | {issue.message}" for issue in report.issues)
    else:
        lines.append("None | INFO | No issues found.")
    return "\n".join(lines)


def format_btc_paper_monitoring_status_report(status: BTCPaperMonitoringStatus) -> str:
    lines = [
        "===== BTC PAPER MONITORING STATUS =====",
        f"Project Scope      : {status.project_scope}",
        f"Symbol             : {status.symbol}",
        f"Profile            : {status.strategy_profile}",
        f"Monitoring Status  : {status.monitoring_status}",
        f"Runtime Config     : {status.runtime_config_status}",
        f"Validation Gate    : {status.validation_gate_status}",
        f"Paper Execution    : {_fmt_bool(status.paper_execution_enabled)}",
        f"Live Trading       : {_fmt_bool(status.live_trading_enabled)}",
        f"Order Submission   : {_fmt_bool(status.order_submission_enabled)}",
        f"Dry Run            : {_fmt_bool(status.dry_run)}",
        f"Kill Switch        : {_fmt_bool(status.kill_switch_enabled)}",
        f"Heartbeat          : {status.last_heartbeat_at}",
        f"Last Signal        : {status.last_signal_at}",
        f"Consecutive Errors : {status.consecutive_errors}",
        "",
        "Notes:",
    ]
    lines.extend(f"- {note}" for note in status.notes) if status.notes else lines.append("- None")
    lines.extend(["", "Issues:", "Name | Severity | Message"])
    if status.issues:
        lines.extend(f"{issue.name} | {issue.severity} | {issue.message}" for issue in status.issues)
    else:
        lines.append("None | INFO | No issues found.")
    return "\n".join(lines)


def _get(config, name: str):
    if config is None:
        return None
    return getattr(config, name)


def _fmt_bool(value) -> str:
    if value is None:
        return "None"
    return str(bool(value)).lower()
