from __future__ import annotations

from models.btc_paper_runtime_config import BTCPaperRuntimeConfigValidationReport


def format_btc_paper_runtime_config_report(report: BTCPaperRuntimeConfigValidationReport) -> str:
    config = report.config
    lines = [
        "===== BTC PAPER RUNTIME CONFIG VALIDATION =====",
        f"Config Path       : {report.config_path}",
        f"Status            : {report.status}",
        f"Symbol            : {_get(config, 'symbol')}",
        f"Profile           : {_get(config, 'strategy_profile')}",
        f"Scope             : {_get(config, 'project_scope')}",
        f"Execution Enabled : {_fmt_bool(_get(config, 'paper_execution_enabled'))}",
        f"Live Enabled      : {_fmt_bool(_get(config, 'live_trading_enabled'))}",
        f"Order Submission  : {_fmt_bool(_get(config, 'order_submission_enabled'))}",
        f"Dry Run           : {_fmt_bool(_get(config, 'dry_run'))}",
        f"Kill Switch       : {_fmt_bool(_get(config, 'kill_switch_enabled'))}",
        "",
        "Risk:",
        f"Risk/Trade        : {_fmt_pct(_get(config, 'risk_per_trade_pct'))}",
        f"Max Risk/Trade    : {_fmt_pct(_get(config, 'max_risk_per_trade_pct'))}",
        f"Max Daily Loss    : {_fmt_pct(_get(config, 'max_daily_loss_pct'))}",
        f"Max Drawdown      : {_fmt_pct(_get(config, 'max_total_drawdown_pct'))}",
        f"Max Open Positions: {_get(config, 'max_open_positions')}",
        f"Max Trades/Day    : {_get(config, 'max_trades_per_day')}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    if report.issues:
        lines.extend(f"{issue.name} | {issue.severity} | {issue.message}" for issue in report.issues)
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


def _fmt_pct(value) -> str:
    if value is None:
        return "None"
    return f"{float(value) * 100:.2f}%"
