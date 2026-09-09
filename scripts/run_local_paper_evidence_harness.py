from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.diagnostics.local_paper_evidence_harness import LocalPaperEvidenceHarness
from engine.diagnostics.local_paper_evidence_validator import LocalPaperEvidenceArtifactValidator
from models.local_paper_evidence import LocalPaperEvidenceStatus, LocalPaperStopReason
from reporting.local_paper_evidence_report import artifact_to_json, format_local_paper_evidence_report


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    harness = LocalPaperEvidenceHarness(repo_root=args.repo_root)
    try:
        if args.action == "validate":
            if not args.artifact:
                raise ValueError("artifact is required for this action")
            result = LocalPaperEvidenceArtifactValidator(repo_root=args.repo_root).validate(
                args.artifact,
                config_path=args.config,
            )
            print(json.dumps(result.to_dict(), sort_keys=True, separators=(",", ":")))
            return 0 if result.status == "PASS" else 1

        config = harness.load_config(args.config)
        if args.symbol:
            config = _replace_config_symbol(config, args.symbol)
        if args.allow_production:
            config = _replace_config_production(config, False)
        if args.allow_credentials:
            config = _replace_config_credentials(config, True)
        if args.allow_network:
            config = _replace_config_network(config, True)

        if args.action == "run":
            if not args.run_id or not args.output:
                raise ValueError("run_id and output are required for this action")
            artifact = harness.run_automatic_heartbeat(
                run_id=args.run_id,
                output_path=args.output,
                commit_sha=args.commit_sha,
                config=config,
                max_cycles=args.max_heartbeat_cycles,
            )
            _emit(artifact, json_output=args.json)
            return 0 if artifact.status in {LocalPaperEvidenceStatus.RUNNING.value, LocalPaperEvidenceStatus.COMPLETE.value} else 1

        if args.action in {"heartbeat", "observe", "finalize"} and args.output:
            artifact = _update_action(args, harness, config)
            if artifact is None:
                print("LOCAL_PAPER_EVIDENCE_ERROR: SANITIZED_FAILURE", file=sys.stderr)
                return 1
            _emit(artifact, json_output=args.json)
            return 0 if artifact.status in {LocalPaperEvidenceStatus.RUNNING.value, LocalPaperEvidenceStatus.COMPLETE.value} else 1

        artifact = _run_action(args, harness, config)
        if args.output:
            if not harness.write_artifact(artifact, args.output):
                artifact = harness.finalize(
                    artifact,
                    config=config,
                    stop_reason=LocalPaperStopReason.ARTIFACT_WRITE_FAILURE.value,
                    wall_timestamp=_wall_timestamp(args),
                    monotonic_seconds=_monotonic_seconds(args),
                )
        _emit(artifact, json_output=args.json)
        return 0 if artifact.status in {LocalPaperEvidenceStatus.RUNNING.value, LocalPaperEvidenceStatus.COMPLETE.value} else 1
    except (OSError, ValueError, json.JSONDecodeError):
        print("LOCAL_PAPER_EVIDENCE_ERROR: SANITIZED_FAILURE", file=sys.stderr)
        return 1


def _update_action(args: argparse.Namespace, harness: LocalPaperEvidenceHarness, config):
    if not args.artifact:
        raise ValueError("artifact is required for this action")
    if not args.run_id:
        raise ValueError("run_id is required for this action")
    if args.action == "heartbeat":
        return harness.update_artifact(
            args.artifact,
            args.output,
            run_id=args.run_id,
            config=config,
            operation="heartbeat",
            transition=lambda artifact: harness.record_heartbeat(
                artifact,
                config=config,
                wall_timestamp=_wall_timestamp(args),
                monotonic_seconds=_monotonic_seconds(args),
            ),
        )
    if args.action == "observe":
        if args.monotonic_seconds is None and args.wall_timestamp is None:
            return harness.update_artifact(
                args.artifact,
                args.output,
                run_id=args.run_id,
                config=config,
                operation="observe",
                transition=lambda artifact: harness.capture_operator_observation(
                    artifact,
                    config=config,
                    observation_code=args.observation_code,
                ),
            )
        return harness.update_artifact(
            args.artifact,
            args.output,
            run_id=args.run_id,
            config=config,
            operation="observe",
            transition=lambda artifact: harness.record_operator_observation(
                artifact,
                config=config,
                observation_code=args.observation_code,
                wall_timestamp=_wall_timestamp(args),
                monotonic_seconds=_monotonic_seconds(args),
            ),
        )
    return harness.update_artifact(
        args.artifact,
        args.output,
        run_id=args.run_id,
        config=config,
        operation="finalize",
        transition=lambda artifact: harness.finalize(
            artifact,
            config=config,
            stop_reason=args.stop_reason,
            wall_timestamp=_wall_timestamp(args),
            monotonic_seconds=_monotonic_seconds(args),
        ),
    )


def _run_action(args: argparse.Namespace, harness: LocalPaperEvidenceHarness, config):
    if args.action == "start":
        if not args.run_id:
            raise ValueError("run_id is required for this action")
        return harness.start(
            run_id=args.run_id,
            commit_sha=args.commit_sha,
            config=config,
            wall_timestamp=_wall_timestamp(args),
            monotonic_seconds=_monotonic_seconds(args),
        )
    if not args.artifact:
        raise ValueError("artifact is required for this action")
    if not args.run_id:
        raise ValueError("run_id is required for this action")
    artifact = harness.read_artifact(args.artifact)
    if artifact.run_id != args.run_id:
        return harness.record_interruption(
            artifact,
            config=config,
            reason_code=LocalPaperStopReason.SAFETY_BOUNDARY_VIOLATION.value,
            wall_timestamp=_wall_timestamp(args),
            monotonic_seconds=_monotonic_seconds(args),
        )
    if args.action == "heartbeat":
        return harness.record_heartbeat(
            artifact,
            config=config,
            wall_timestamp=_wall_timestamp(args),
            monotonic_seconds=_monotonic_seconds(args),
        )
    if args.action == "observe":
        if args.monotonic_seconds is None and args.wall_timestamp is None:
            return harness.capture_operator_observation(
                artifact,
                config=config,
                observation_code=args.observation_code,
            )
        return harness.record_operator_observation(
            artifact,
            config=config,
            observation_code=args.observation_code,
            wall_timestamp=_wall_timestamp(args),
            monotonic_seconds=_monotonic_seconds(args),
        )
    if args.action == "interrupt":
        return harness.record_interruption(
            artifact,
            config=config,
            reason_code=args.stop_reason,
            wall_timestamp=_wall_timestamp(args),
            monotonic_seconds=_monotonic_seconds(args),
        )
    return harness.finalize(
        artifact,
        config=config,
        stop_reason=args.stop_reason,
        wall_timestamp=_wall_timestamp(args),
        monotonic_seconds=_monotonic_seconds(args),
    )


def _emit(artifact, *, json_output: bool) -> None:
    if json_output:
        print(artifact_to_json(artifact))
    else:
        print(format_local_paper_evidence_report(artifact))


def _wall_timestamp(args: argparse.Namespace) -> str:
    if args.wall_timestamp is not None:
        return args.wall_timestamp
    from time import gmtime, strftime

    return strftime("%Y-%m-%dT%H:%M:%SZ", gmtime())


def _monotonic_seconds(args: argparse.Namespace) -> float:
    return 0.0 if args.monotonic_seconds is None else args.monotonic_seconds


def _replace_config_symbol(config, symbol: str):
    from dataclasses import replace

    return replace(config, symbol=symbol)


def _replace_config_production(config, production_disabled: bool):
    from dataclasses import replace

    return replace(config, production_disabled=production_disabled)


def _replace_config_credentials(config, credentials_allowed: bool):
    from dataclasses import replace

    return replace(config, credentials_allowed=credentials_allowed)


def _replace_config_network(config, network_allowed: bool):
    from dataclasses import replace

    return replace(config, network_allowed=network_allowed, exchange_transport_allowed=network_allowed)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate local paper evidence harness contracts without running a sustained runtime.")
    parser.add_argument("action", choices=["start", "heartbeat", "observe", "interrupt", "finalize", "validate", "run"])
    parser.add_argument("--repo-root", default=str(ROOT_DIR))
    parser.add_argument("--config", default="configs/local_paper_evidence_harness.json")
    parser.add_argument("--artifact", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--commit-sha", default="85e36081823bb56349eb2c844412b7382e7214b1")
    parser.add_argument("--wall-timestamp", default=None)
    parser.add_argument("--monotonic-seconds", type=float, default=None)
    parser.add_argument("--observation-code", default="OPERATOR_OBSERVED")
    parser.add_argument("--stop-reason", default=LocalPaperStopReason.THRESHOLD_REACHED.value)
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--allow-credentials", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--max-heartbeat-cycles", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
