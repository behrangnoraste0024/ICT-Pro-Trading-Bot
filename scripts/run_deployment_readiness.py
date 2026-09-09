from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.deployment_readiness_engine import DeploymentReadinessEngine
from models.deployment_readiness import READY
from reporting.deployment_readiness_report import format_deployment_readiness_report


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = DeploymentReadinessEngine(repo_root=args.repo_root).evaluate()
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_deployment_readiness_report(report))
    return 0 if report.readiness_status == READY else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic local deployment readiness diagnostics.")
    parser.add_argument("--repo-root", default=str(ROOT_DIR))
    parser.add_argument("--json", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
