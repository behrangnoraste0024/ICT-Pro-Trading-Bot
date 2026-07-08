from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from reporting.btc_paper_runner_report import format_btc_paper_runner_status_report


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
    if action == "STATUS":
        status = engine.build_status(config_path=args.config, expected_profile=args.expected_profile, state=state)
        transition = None
        payload = status.to_dict()
        accepted = not any(issue.severity == "FAIL" for issue in status.issues)
    else:
        transition = engine.apply(action, status=state, config_path=args.config, expected_profile=args.expected_profile)
        status = transition.status
        payload = transition.to_dict()
        accepted = transition.accepted
        if args.state_file and (accepted or action == "HEARTBEAT"):
            engine.save_state(status, args.state_file)
    rendered = format_btc_paper_runner_status_report(status, transition)
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
