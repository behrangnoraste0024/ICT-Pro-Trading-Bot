from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from engine.diagnostics.btc_paper_signal_evaluation_engine import BTCPaperSignalEvaluationEngine
from engine.diagnostics.btc_paper_candidate_journal_engine import BTCPaperCandidateJournalEngine
from engine.diagnostics.btc_paper_trade_candidate_engine import BTCPaperTradeCandidateEngine
from engine.diagnostics.btc_forward_test_loop_engine import BTCForwardTestLoopEngine
from engine.diagnostics.binance_futures_testnet_adapter_engine import BinanceFuturesTestnetAdapterEngine
from engine.diagnostics.binance_futures_testnet_read_only_engine import BinanceFuturesTestnetReadOnlyEngine
from engine.diagnostics.binance_futures_testnet_order_test_engine import BinanceFuturesTestnetOrderTestEngine
from engine.diagnostics.btc_futures_read_only_feed_engine import BTCFuturesReadOnlyFeedEngine
from engine.diagnostics.btc_futures_paper_position_engine import BTCFuturesPaperPositionEngine
from engine.diagnostics.btc_futures_risk_model_engine import BTCFuturesRiskModelEngine
from engine.diagnostics.btc_live_market_feed_engine import BTCLiveMarketFeedEngine
from engine.diagnostics.btc_paper_account_engine import BTCPaperAccountEngine
from models.btc_forward_test_loop import BTCForwardTestIssue
from models.binance_futures_testnet_adapter import BinanceFuturesTestnetIssue
from models.binance_futures_testnet_read_only import BinanceFuturesTestnetReadOnlyIssue
from models.binance_futures_testnet_order_test import BinanceFuturesTestnetOrderTestIssue
from models.btc_futures_read_only_feed import BTCFuturesReadOnlyIssue
from models.btc_futures_paper_position import BTCFuturesPaperIssue
from models.btc_futures_risk_model import BTCFuturesRiskIssue
from models.btc_live_market_feed import BTCLiveMarketFeedIssue
from models.btc_paper_account import BTCPaperAccountIssue
from models.btc_paper_candidate_journal import BTCPaperCandidateJournalIssue
from models.btc_paper_signal_evaluation import BTCPaperSignalEvaluationIssue
from models.btc_paper_trade_candidate import BTCPaperTradeCandidateIssue
from reporting.btc_forward_test_loop_report import format_btc_forward_test_run_result
from reporting.binance_futures_testnet_adapter_report import format_binance_futures_testnet_adapter_result
from reporting.binance_futures_testnet_read_only_report import format_binance_futures_testnet_read_only_result
from reporting.binance_futures_testnet_order_test_report import format_binance_futures_testnet_order_test_result
from reporting.btc_futures_read_only_feed_report import format_btc_futures_read_only_observation_result
from reporting.btc_futures_paper_position_report import format_btc_futures_paper_action_result
from reporting.btc_futures_risk_model_report import format_btc_futures_risk_result
from reporting.btc_live_market_feed_report import format_btc_live_market_observation_result
from reporting.btc_paper_account_report import format_btc_paper_account_action_result
from reporting.btc_paper_candidate_journal_report import format_btc_paper_candidate_journal_record_result
from reporting.btc_paper_runner_report import format_btc_paper_runner_status_report
from reporting.btc_paper_signal_evaluation_report import format_btc_paper_signal_evaluation_result
from reporting.btc_paper_trade_candidate_report import format_btc_paper_trade_candidate_result


ACTION_FLAGS = {
    "initialize": "INITIALIZE",
    "start": "START",
    "pause": "PAUSE",
    "resume": "RESUME",
    "stop": "STOP",
    "heartbeat": "HEARTBEAT",
    "status": "STATUS",
    "reset_error": "RESET_ERROR",
}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    engine = BTCPaperRunnerEngine(repo_root=ROOT_DIR)
    action = _selected_action(args)
    state = None
    if args.state_file:
        state_path = ROOT_DIR / args.state_file if not Path(args.state_file).is_absolute() else Path(args.state_file)
        if state_path.exists():
            state = engine.load_state(args.state_file)
    if args.analyze_futures_risk_dry_run:
        status = engine.build_status(config_path=args.config, expected_profile=args.expected_profile, state=state)
        risk_model_engine = BTCFuturesRiskModelEngine(repo_root=ROOT_DIR)
        risk_result = risk_model_engine.analyze_live(expected_profile=args.expected_profile)
        if status.state != "RUNNING":
            risk_result.issues.append(
                BTCFuturesRiskIssue(
                    name="runner_not_running",
                    severity="WARNING",
                    message="Runner is not running; futures risk analysis executed as standalone dry-run diagnostic.",
                    details={"runner_state": status.state},
                )
            )
            if risk_result.status == "PASS":
                risk_result.status = "WARNING"
        transition = None
        payload = {"runner_status": status.to_dict(), "futures_risk_analysis": risk_result.to_dict()}
        rendered = format_btc_paper_runner_status_report(status, transition) + "\n\n" + format_btc_futures_risk_result(risk_result)
        accepted = risk_result.status in ("PASS", "WARNING")
    elif args.validate_binance_futures_testnet_adapter_dry_run:
        status = engine.build_status(config_path=args.config, expected_profile=args.expected_profile, state=state)
        adapter_engine = BinanceFuturesTestnetAdapterEngine(repo_root=ROOT_DIR, env={})
        adapter_result = adapter_engine.build_order_intent(
            intent_id="runner-testnet-intent-dry-run",
            side="BUY",
            order_type="MARKET",
            quantity=0.001,
            config_path="configs/binance_futures_testnet_adapter.json",
            expected_profile=args.expected_profile,
        )
        if status.state != "RUNNING":
            adapter_result.issues.append(
                BinanceFuturesTestnetIssue(
                    name="runner_not_running",
                    severity="WARNING",
                    message="Runner is not running; Binance futures testnet adapter validation executed as standalone disabled dry-run diagnostic.",
                    details={"runner_state": status.state},
                )
            )
            if adapter_result.status == "PASS":
                adapter_result.status = "WARNING"
        transition = None
        payload = {"runner_status": status.to_dict(), "binance_futures_testnet_adapter": adapter_result.to_dict()}
        rendered = format_btc_paper_runner_status_report(status, transition) + "\n\n" + format_binance_futures_testnet_adapter_result(adapter_result)
        accepted = adapter_result.status in ("PASS", "WARNING")
    elif args.validate_binance_futures_testnet_read_only_dry_run:
        status = engine.build_status(config_path=args.config, expected_profile=args.expected_profile, state=state)
        read_only_engine = BinanceFuturesTestnetReadOnlyEngine(repo_root=ROOT_DIR, env={})
        read_only_result = read_only_engine.runner_validate(
            config_path="configs/binance_futures_testnet_read_only.json",
            expected_profile=args.expected_profile,
        )
        if status.state != "RUNNING":
            read_only_result.issues.append(
                BinanceFuturesTestnetReadOnlyIssue(
                    name="runner_not_running",
                    severity="WARNING",
                    message="Runner is not running; Binance futures testnet read-only validation executed as standalone explicit-only dry-run diagnostic.",
                    details={"runner_state": status.state},
                )
            )
            if read_only_result.status == "PASS":
                read_only_result.status = "WARNING"
        transition = None
        payload = {"runner_status": status.to_dict(), "binance_futures_testnet_read_only": read_only_result.to_dict()}
        rendered = format_btc_paper_runner_status_report(status, transition) + "\n\n" + format_binance_futures_testnet_read_only_result(read_only_result)
        accepted = read_only_result.status in ("PASS", "WARNING")
    elif args.validate_binance_futures_testnet_order_test_dry_run:
        status = engine.build_status(config_path=args.config, expected_profile=args.expected_profile, state=state)
        order_test_engine = BinanceFuturesTestnetOrderTestEngine(repo_root=ROOT_DIR, env={})
        order_test_result = order_test_engine.runner_validate(
            config_path="configs/binance_futures_testnet_order_test.json",
            expected_profile=args.expected_profile,
        )
        if status.state != "RUNNING":
            order_test_result.issues.append(
                BinanceFuturesTestnetOrderTestIssue(
                    name="runner_not_running",
                    severity="WARNING",
                    message="Runner is not running; Binance futures Test Order preflight validation executed as standalone local dry-run diagnostic.",
                    details={"runner_state": status.state},
                )
            )
            if order_test_result.status == "PASS":
                order_test_result.status = "WARNING"
        transition = None
        payload = {"runner_status": status.to_dict(), "binance_futures_testnet_order_test": order_test_result.to_dict()}
        rendered = format_btc_paper_runner_status_report(status, transition) + "\n\n" + format_binance_futures_testnet_order_test_result(order_test_result)
        accepted = order_test_result.status in ("PASS", "WARNING")
    elif args.simulate_futures_paper_position_lifecycle_dry_run:
        status = engine.build_status(config_path=args.config, expected_profile=args.expected_profile, state=state)
        futures_position_engine = BTCFuturesPaperPositionEngine(repo_root=ROOT_DIR)
        lifecycle_result = futures_position_engine.simulate_lifecycle(expected_profile=args.expected_profile)
        if status.state != "RUNNING":
            lifecycle_result.issues.append(
                BTCFuturesPaperIssue(
                    name="runner_not_running",
                    severity="WARNING",
                    message="Runner is not running; futures paper position lifecycle executed as standalone local dry-run simulation.",
                    details={"runner_state": status.state},
                )
            )
            if lifecycle_result.status == "PASS":
                lifecycle_result.status = "WARNING"
        transition = None
        payload = {"runner_status": status.to_dict(), "futures_paper_position_lifecycle": lifecycle_result.to_dict()}
        rendered = format_btc_paper_runner_status_report(status, transition) + "\n\n" + format_btc_futures_paper_action_result(lifecycle_result)
        accepted = lifecycle_result.status in ("PASS", "WARNING")
    elif args.observe_futures_read_only_dry_run:
        status = engine.build_status(config_path=args.config, expected_profile=args.expected_profile, state=state)
        futures_feed_engine = BTCFuturesReadOnlyFeedEngine(repo_root=ROOT_DIR)
        observation = futures_feed_engine.observe_once(expected_profile=args.expected_profile)
        if status.state != "RUNNING":
            observation.issues.append(
                BTCFuturesReadOnlyIssue(
                    name="runner_not_running",
                    severity="WARNING",
                    message="Runner is not running; futures read-only observation executed as standalone dry-run diagnostic.",
                    details={"runner_state": status.state},
                )
            )
            if observation.status == "PASS":
                observation.status = "WARNING"
        transition = None
        payload = {"runner_status": status.to_dict(), "futures_read_only_observation": observation.to_dict()}
        rendered = format_btc_paper_runner_status_report(status, transition) + "\n\n" + format_btc_futures_read_only_observation_result(observation)
        accepted = observation.status in ("PASS", "WARNING")
    elif args.simulate_local_paper_account:
        status = engine.build_status(config_path=args.config, expected_profile=args.expected_profile, state=state)
        paper_account_engine = BTCPaperAccountEngine(repo_root=ROOT_DIR)
        account_result = paper_account_engine.simulate_live_observation(expected_profile=args.expected_profile, initialize_if_missing=True)
        if status.state != "RUNNING":
            account_result.issues.append(
                BTCPaperAccountIssue(
                    name="runner_not_running",
                    severity="WARNING",
                    message="Runner is not running; local paper account simulation executed as standalone dry-run diagnostic.",
                    details={"runner_state": status.state},
                )
            )
            if account_result.status == "PASS":
                account_result.status = "WARNING"
        transition = None
        payload = {"runner_status": status.to_dict(), "paper_account": account_result.to_dict()}
        rendered = format_btc_paper_runner_status_report(status, transition) + "\n\n" + format_btc_paper_account_action_result(account_result)
        accepted = account_result.status in ("PASS", "WARNING")
    elif args.observe_live_market_read_only_dry_run:
        status = engine.build_status(config_path=args.config, expected_profile=args.expected_profile, state=state)
        live_feed_engine = BTCLiveMarketFeedEngine(repo_root=ROOT_DIR)
        observation = live_feed_engine.observe_once(expected_profile=args.expected_profile)
        if status.state != "RUNNING":
            observation.issues.append(
                BTCLiveMarketFeedIssue(
                    name="runner_not_running",
                    severity="WARNING",
                    message="Runner is not running; live market read-only observation executed as standalone dry-run diagnostic.",
                    details={"runner_state": status.state},
                )
            )
            if observation.status == "PASS":
                observation.status = "WARNING"
        transition = None
        payload = {"runner_status": status.to_dict(), "live_market_observation": observation.to_dict()}
        rendered = format_btc_paper_runner_status_report(status, transition) + "\n\n" + format_btc_live_market_observation_result(observation)
        accepted = observation.status in ("PASS", "WARNING")
    elif args.run_forward_test_dry_run:
        status = engine.build_status(config_path=args.config, expected_profile=args.expected_profile, state=state)
        forward_engine = BTCForwardTestLoopEngine(repo_root=ROOT_DIR)
        forward_result = forward_engine.run(expected_profile=args.expected_profile)
        if status.state != "RUNNING":
            forward_result.issues.append(
                BTCForwardTestIssue(
                    name="runner_not_running",
                    severity="WARNING",
                    message="Runner is not running; forward test loop executed as standalone dry-run diagnostic.",
                    details={"runner_state": status.state},
                )
            )
            if forward_result.status == "PASS":
                forward_result.status = "WARNING"
        transition = None
        payload = {"runner_status": status.to_dict(), "forward_test": forward_result.to_dict()}
        rendered = format_btc_paper_runner_status_report(status, transition) + "\n\n" + format_btc_forward_test_run_result(forward_result)
        accepted = forward_result.status in ("PASS", "WARNING")
    elif args.simulate_and_journal_candidate_dry_run:
        status = engine.build_status(config_path=args.config, expected_profile=args.expected_profile, state=state)
        journal_engine = BTCPaperCandidateJournalEngine(repo_root=ROOT_DIR)
        journal_result = journal_engine.simulate_and_record(expected_profile=args.expected_profile, runner_state=status.state)
        if status.state != "RUNNING":
            journal_result.issues.append(
                BTCPaperCandidateJournalIssue(
                    name="runner_not_running",
                    severity="WARNING",
                    message="Runner is not running; candidate journaling executed as standalone dry-run diagnostic.",
                    details={"runner_state": status.state},
                )
            )
            if journal_result.status == "PASS":
                journal_result.status = "WARNING"
        transition = None
        payload = {"runner_status": status.to_dict(), "candidate_journal": journal_result.to_dict()}
        rendered = format_btc_paper_runner_status_report(status, transition) + "\n\n" + format_btc_paper_candidate_journal_record_result(journal_result)
        accepted = journal_result.status in ("PASS", "WARNING")
    elif args.simulate_trade_candidate_dry_run:
        status = engine.build_status(config_path=args.config, expected_profile=args.expected_profile, state=state)
        candidate_engine = BTCPaperTradeCandidateEngine(repo_root=ROOT_DIR)
        candidate_result = candidate_engine.simulate(expected_profile=args.expected_profile)
        if status.state != "RUNNING":
            candidate_result.issues.append(
                BTCPaperTradeCandidateIssue(
                    name="runner_not_running",
                    severity="WARNING",
                    message="Runner is not running; trade candidate simulation executed as standalone dry-run diagnostic.",
                    details={"runner_state": status.state},
                )
            )
            if candidate_result.status == "PASS":
                candidate_result.status = "WARNING"
        transition = None
        payload = {"runner_status": status.to_dict(), "trade_candidate": candidate_result.to_dict()}
        rendered = format_btc_paper_runner_status_report(status, transition) + "\n\n" + format_btc_paper_trade_candidate_result(candidate_result)
        accepted = candidate_result.status in ("PASS", "WARNING")
    elif args.evaluate_signal_dry_run:
        status = engine.build_status(config_path=args.config, expected_profile=args.expected_profile, state=state)
        signal_engine = BTCPaperSignalEvaluationEngine(repo_root=ROOT_DIR)
        evaluation = signal_engine.evaluate(expected_profile=args.expected_profile)
        if status.state not in ("RUNNING", "PAUSED"):
            evaluation.issues.append(
                BTCPaperSignalEvaluationIssue(
                    name="runner_not_active",
                    severity="WARNING",
                    message="Runner is not running; signal evaluation executed as standalone dry-run diagnostic.",
                    details={"runner_state": status.state},
                )
            )
            if evaluation.status == "PASS":
                evaluation.status = "WARNING"
        transition = None
        payload = {"runner_status": status.to_dict(), "signal_evaluation": evaluation.to_dict()}
        rendered = format_btc_paper_runner_status_report(status, transition) + "\n\n" + format_btc_paper_signal_evaluation_result(evaluation)
        accepted = evaluation.status in ("PASS", "WARNING")
    elif action == "STATUS":
        status = engine.build_status(config_path=args.config, expected_profile=args.expected_profile, state=state)
        transition = None
        payload = status.to_dict()
        rendered = format_btc_paper_runner_status_report(status, transition)
        accepted = not any(issue.severity == "FAIL" for issue in status.issues)
    else:
        transition = engine.apply(action, status=state, config_path=args.config, expected_profile=args.expected_profile)
        status = transition.status
        payload = transition.to_dict()
        rendered = format_btc_paper_runner_status_report(status, transition)
        accepted = transition.accepted
        if args.state_file and (accepted or action == "HEARTBEAT"):
            engine.save_state(status, args.state_file)
    if args.export_json:
        _atomic_write(args.export_json, json.dumps(payload, indent=2))
        print(f"[btc-paper-runner] wrote {args.export_json}", file=sys.stderr if args.json else sys.stdout)
    if args.export_md:
        _atomic_write(args.export_md, rendered)
        print(f"[btc-paper-runner] wrote {args.export_md}", file=sys.stderr if args.json else sys.stdout)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(rendered)
    if (
        args.evaluate_signal_dry_run
        or args.simulate_trade_candidate_dry_run
        or args.simulate_and_journal_candidate_dry_run
        or args.run_forward_test_dry_run
        or args.observe_live_market_read_only_dry_run
        or args.simulate_local_paper_account
        or args.observe_futures_read_only_dry_run
        or args.analyze_futures_risk_dry_run
        or args.validate_binance_futures_testnet_adapter_dry_run
        or args.validate_binance_futures_testnet_read_only_dry_run
        or args.validate_binance_futures_testnet_order_test_dry_run
        or args.simulate_futures_paper_position_lifecycle_dry_run
    ) and not accepted:
        return 1
    if not accepted and action not in ("HEARTBEAT", "STATUS"):
        return 1
    if any(issue.severity == "FAIL" for issue in status.issues):
        return 1
    return 0


def _selected_action(args: argparse.Namespace) -> str:
    selected = [name for name in ACTION_FLAGS if getattr(args, name)]
    if len(selected) > 1:
        raise SystemExit("Choose only one runner action.")
    if not selected:
        return "STATUS"
    return ACTION_FLAGS[selected[0]]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run BTC paper runner dry-run lifecycle state transitions.")
    parser.add_argument("--config", default="configs/btc_paper_runner.json")
    parser.add_argument("--expected-profile", default="balanced_smc_decision_065")
    parser.add_argument("--state-file", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--export-json", default=None)
    parser.add_argument("--export-md", default=None)
    parser.add_argument("--evaluate-signal-dry-run", action="store_true")
    parser.add_argument("--simulate-trade-candidate-dry-run", action="store_true")
    parser.add_argument("--simulate-and-journal-candidate-dry-run", action="store_true")
    parser.add_argument("--run-forward-test-dry-run", action="store_true")
    parser.add_argument("--observe-live-market-read-only-dry-run", action="store_true")
    parser.add_argument("--simulate-local-paper-account", action="store_true")
    parser.add_argument("--observe-futures-read-only-dry-run", action="store_true")
    parser.add_argument("--analyze-futures-risk-dry-run", action="store_true")
    parser.add_argument("--validate-binance-futures-testnet-adapter-dry-run", action="store_true")
    parser.add_argument("--validate-binance-futures-testnet-read-only-dry-run", action="store_true")
    parser.add_argument("--validate-binance-futures-testnet-order-test-dry-run", action="store_true")
    parser.add_argument("--simulate-futures-paper-position-lifecycle-dry-run", action="store_true")
    for flag in ACTION_FLAGS:
        parser.add_argument(f"--{flag.replace('_', '-')}", dest=flag, action="store_true")
    return parser


def _atomic_write(path_text: str, content: str) -> None:
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
