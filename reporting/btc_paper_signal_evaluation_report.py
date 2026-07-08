from __future__ import annotations

from models.btc_paper_signal_evaluation import (
    BTCPaperSignalEvaluationResult,
    BTCPaperSignalEvaluationValidationReport,
)


def format_btc_paper_signal_evaluation_validation_report(report: BTCPaperSignalEvaluationValidationReport) -> str:
    config = report.config
    lines = [
        "===== BTC PAPER SIGNAL EVALUATION CONFIG VALIDATION =====",
        f"Config Path       : {report.config_path}",
        f"Status            : {report.status}",
        f"Symbol            : {_get(config, 'symbol')}",
        f"Profile           : {_get(config, 'strategy_profile')}",
        f"Dry Run Only      : {_fmt_bool(_get(config, 'dry_run_only'))}",
        f"Trade Creation    : {_fmt_bool(_get(config, 'allow_trade_creation'))}",
        f"Order Submission  : {_fmt_bool(_get(config, 'allow_order_submission'))}",
        f"Exchange Connect  : {_fmt_bool(_get(config, 'allow_exchange_connection'))}",
        f"State Mutation    : {_fmt_bool(_get(config, 'allow_state_mutation'))}",
        f"Runtime Config    : {report.diagnostics.get('runtime_config_status', 'UNKNOWN')}",
        f"Monitoring Config : {report.diagnostics.get('monitoring_config_status', 'UNKNOWN')}",
        f"Runner Config     : {report.diagnostics.get('runner_config_status', 'UNKNOWN')}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    if report.issues:
        lines.extend(f"{issue.name} | {issue.severity} | {issue.message}" for issue in report.issues)
    else:
        lines.append("None | INFO | No issues found.")
    return "\n".join(lines)


def format_btc_paper_signal_evaluation_result(result: BTCPaperSignalEvaluationResult) -> str:
    lines = [
        "===== BTC PAPER SIGNAL EVALUATION DRY-RUN =====",
        f"Project Scope       : {result.project_scope}",
        f"Symbol              : {result.symbol}",
        f"Profile             : {result.strategy_profile}",
        f"Status              : {result.status}",
        f"Decision            : {result.decision}",
        f"Sample              : {result.sample_name}",
        f"Confirmation        : {result.confirmation_sample_name}",
        f"Candles             : {result.candle_count}",
        f"Confirmation Candles: {result.confirmation_candle_count}",
        f"Latest Timestamp    : {result.latest_timestamp}",
        f"Direction           : {result.direction}",
        f"Score               : {result.score}",
        f"Threshold           : {result.threshold}",
        f"Reason              : {result.reason}",
        "",
        "Safety:",
        f"Dry Run Only        : {_fmt_bool(result.dry_run_only)}",
        f"Trade Created       : {_fmt_bool(result.trade_created)}",
        f"Order Submitted     : {_fmt_bool(result.order_submitted)}",
        f"Exchange Connected  : {_fmt_bool(result.exchange_connected)}",
        f"State Mutated       : {_fmt_bool(result.state_mutated)}",
        f"Kill Switch         : {_fmt_bool(result.safety_summary.get('kill_switch_enabled'))}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    if result.issues:
        lines.extend(f"{issue.name} | {issue.severity} | {issue.message}" for issue in result.issues)
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
