from __future__ import annotations

from models.btc_paper_trade_candidate import BTCPaperTradeCandidateResult, BTCPaperTradeCandidateValidationReport


def format_btc_paper_trade_candidate_validation_report(report: BTCPaperTradeCandidateValidationReport) -> str:
    config = report.config
    lines = [
        "===== BTC PAPER TRADE CANDIDATE CONFIG VALIDATION =====",
        f"Config Path       : {report.config_path}",
        f"Status            : {report.status}",
        f"Symbol            : {_get(config, 'symbol')}",
        f"Profile           : {_get(config, 'strategy_profile')}",
        f"Dry Run Only      : {_fmt_bool(_get(config, 'dry_run_only'))}",
        f"Candidate Allowed : {_fmt_bool(_get(config, 'allow_candidate_creation'))}",
        f"Executable Trade  : {_fmt_bool(_get(config, 'allow_executable_trade_creation'))}",
        f"Paper Persistence : {_fmt_bool(_get(config, 'allow_paper_trade_persistence'))}",
        f"Position Creation : {_fmt_bool(_get(config, 'allow_position_creation'))}",
        f"Order Submission  : {_fmt_bool(_get(config, 'allow_order_submission'))}",
        f"Exchange Connect  : {_fmt_bool(_get(config, 'allow_exchange_connection'))}",
        f"State Mutation    : {_fmt_bool(_get(config, 'allow_state_mutation'))}",
        f"Runtime Config    : {report.diagnostics.get('runtime_config_status', 'UNKNOWN')}",
        f"Monitoring Config : {report.diagnostics.get('monitoring_config_status', 'UNKNOWN')}",
        f"Runner Config     : {report.diagnostics.get('runner_config_status', 'UNKNOWN')}",
        f"Signal Config     : {report.diagnostics.get('signal_config_status', 'UNKNOWN')}",
        "",
        "Issues:",
        "Name | Severity | Message",
    ]
    if report.issues:
        lines.extend(f"{issue.name} | {issue.severity} | {issue.message}" for issue in report.issues)
    else:
        lines.append("None | INFO | No issues found.")
    return "\n".join(lines)


def format_btc_paper_trade_candidate_result(result: BTCPaperTradeCandidateResult) -> str:
    candidate = result.candidate
    lines = [
        "===== BTC PAPER TRADE CANDIDATE DRY-RUN =====",
        f"Project Scope       : {result.project_scope}",
        f"Symbol              : {result.symbol}",
        f"Profile             : {result.strategy_profile}",
        f"Status              : {result.status}",
        f"Decision            : {result.decision}",
        f"Candidate Created   : {_fmt_bool(result.candidate_created)}",
        f"Signal Decision     : {result.signal_decision}",
        f"Signal Score        : {result.signal_score}",
        f"Threshold           : {result.signal_threshold}",
        f"Reason              : {result.reason}",
        "",
        "Candidate:",
        f"Direction           : {_get(candidate, 'direction')}",
        f"Entry               : {_get(candidate, 'entry_price')}",
        f"Stop Loss           : {_get(candidate, 'stop_loss')}",
        f"Take Profit         : {_get(candidate, 'take_profit')}",
        f"Risk/Reward         : {_get(candidate, 'risk_reward')}",
        f"Risk Amount         : {_get(candidate, 'estimated_risk_amount')}",
        f"Position Size       : {_get(candidate, 'estimated_position_size')}",
        f"Notional            : {_get(candidate, 'estimated_notional')}",
        f"Max Notional        : {_get(candidate, 'max_candidate_notional')}",
        f"Executable          : {_fmt_bool(_get(candidate, 'candidate_is_executable'))}",
        f"Persisted           : {_fmt_bool(_get(candidate, 'candidate_is_persisted'))}",
        f"Opens Position      : {_fmt_bool(_get(candidate, 'candidate_opens_position'))}",
        "",
        "Safety:",
        f"Dry Run Only        : {_fmt_bool(result.dry_run_only)}",
        f"Executable Trade    : {_fmt_bool(result.executable_trade_created)}",
        f"Paper Persisted     : {_fmt_bool(result.paper_trade_persisted)}",
        f"Position Created    : {_fmt_bool(result.position_created)}",
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


def _get(obj, name: str):
    if obj is None:
        return None
    return getattr(obj, name)


def _fmt_bool(value) -> str:
    if value is None:
        return "None"
    return str(bool(value)).lower()
