from __future__ import annotations

import json
from datetime import UTC, datetime

from engine.diagnostics.local_paper_evidence_harness import LocalPaperEvidenceHarness
from models.local_paper_evidence import LocalPaperEvidenceConfig
from reporting.local_paper_evidence_report import artifact_to_json
from scripts import run_local_paper_evidence_harness


def _write_config(root, **overrides):
    (root / "configs").mkdir()
    payload = {
        "schema_version": "1.0",
        "artifact_schema_version": "1.0",
        "symbol": "BTCUSDT",
        "production_disabled": True,
        "runtime_mode": "local_paper_evidence",
        "environment_classification": "LOCAL_PAPER",
        "minimum_elapsed_hours": 72,
        "operator_observation_interval_hours": 12,
        "heartbeat_interval_seconds": 30,
        "liveness_multiplier": 2,
        "network_allowed": False,
        "credentials_allowed": False,
        "exchange_transport_allowed": False,
        "runtime_state_resume_allowed": False,
        "allowed_successful_stop_reasons": ["THRESHOLD_REACHED", "OPERATOR_STOP_AFTER_THRESHOLD"],
        "config_reference": "configs/local_paper_evidence_harness.json",
    }
    payload.update(overrides)
    path = root / "configs" / "local_paper_evidence_harness.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _main(tmp_path, args):
    return run_local_paper_evidence_harness.main(["--repo-root", str(tmp_path), *args])


def _write_complete_artifact(tmp_path):
    config = LocalPaperEvidenceConfig(heartbeat_interval_seconds=12 * 60 * 60)
    harness = LocalPaperEvidenceHarness(repo_root=tmp_path)
    artifact = harness.start(
        run_id="run-1",
        commit_sha="85e36081823bb56349eb2c844412b7382e7214b1",
        config=config,
        wall_timestamp="2026-08-21T00:00:00Z",
        monotonic_seconds=0.0,
    )
    for index, seconds in enumerate(range(12 * 60 * 60, config.minimum_elapsed_seconds() + 1, 12 * 60 * 60), start=1):
        artifact = harness.record_heartbeat(
            artifact,
            config=config,
            wall_timestamp=f"2026-08-21T{index:02d}:00:00Z",
            monotonic_seconds=float(seconds),
        )
        artifact = harness.record_operator_observation(
            artifact,
            config=config,
            observation_code=f"OBS_{index}",
            wall_timestamp=f"2026-08-21T{index:02d}:00:01Z",
            monotonic_seconds=float(seconds),
        )
    complete = harness.finalize(
        artifact,
        config=config,
        stop_reason="OPERATOR_STOP_AFTER_THRESHOLD",
        wall_timestamp="2026-08-24T00:00:00Z",
        monotonic_seconds=float(config.minimum_elapsed_seconds()),
    )
    path = tmp_path / "reports" / "local_paper_evidence" / "run-1.json"
    path.parent.mkdir(parents=True)
    path.write_text(artifact_to_json(complete), encoding="utf-8")
    return path


def test_cli_start_uses_local_only_configuration(tmp_path, capsys) -> None:
    _write_config(tmp_path)

    code = _main(tmp_path, ["start", "--run-id", "run-1", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["runtime_mode"] == "local_paper_evidence"
    assert payload["symbol"] == "BTCUSDT"
    assert payload["minimum_elapsed_seconds"] == 259200
    assert payload["production_disabled"] is True
    assert payload["counters"]["external_transport_count"] == 0
    assert payload["counters"]["credential_access_count"] == 0


def test_cli_invalid_production_non_btc_credentials_and_network_fail_closed(tmp_path, capsys) -> None:
    _write_config(tmp_path)

    cases = [
        ["start", "--run-id", "run-1", "--symbol", "ETHUSDT", "--json"],
        ["start", "--run-id", "run-1", "--allow-production", "--json"],
        ["start", "--run-id", "run-1", "--allow-credentials", "--json"],
        ["start", "--run-id", "run-1", "--allow-network", "--json"],
    ]
    for args in cases:
        code = _main(tmp_path, args)
        payload = json.loads(capsys.readouterr().out)
        assert code == 1
        assert payload["status"] == "FAILED"
        assert payload["evidence_complete"] is False


def test_cli_non_72_hour_configuration_fails_closed(tmp_path, capsys) -> None:
    _write_config(tmp_path, minimum_elapsed_hours=168)

    code = _main(tmp_path, ["start", "--run-id", "run-1", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "FAILED"
    assert payload["stop_reason"] == "SAFETY_BOUNDARY_VIOLATION"
    assert payload["evidence_complete"] is False


def test_cli_observation_command_is_sanitized(tmp_path, capsys) -> None:
    _write_config(tmp_path)
    artifact = tmp_path / "reports" / "local_paper_evidence" / "run-1.json"

    assert _main(tmp_path, ["start", "--run-id", "run-1", "--output", str(artifact), "--json"]) == 0
    capsys.readouterr()
    code = _main(
        tmp_path,
        [
            "observe",
            "--run-id",
            "run-1",
            "--artifact",
            str(artifact),
            "--observation-code",
            "secret-token-value",
            "--json",
        ],
    )
    output = capsys.readouterr().out

    assert code == 1
    assert "secret-token-value" not in output
    assert "SANITIZATION_FAILURE" in output


def test_cli_premature_finalize_fails(tmp_path, capsys) -> None:
    _write_config(tmp_path)
    artifact = tmp_path / "reports" / "local_paper_evidence" / "run-1.json"

    assert _main(tmp_path, ["start", "--run-id", "run-1", "--output", str(artifact), "--json"]) == 0
    capsys.readouterr()
    code = _main(
        tmp_path,
        [
            "finalize",
            "--run-id",
            "run-1",
            "--artifact",
            str(artifact),
            "--monotonic-seconds",
            "60",
            "--json",
        ],
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["stop_reason"] == "PREMATURE_TERMINATION"
    assert payload["evidence_complete"] is False


def test_cli_same_run_observation_updates_existing_artifact(tmp_path, capsys) -> None:
    _write_config(tmp_path, heartbeat_interval_seconds=604800, liveness_multiplier=2)
    artifact = tmp_path / "reports" / "local_paper_evidence" / "run-1.json"

    assert _main(tmp_path, ["start", "--run-id", "run-1", "--output", str(artifact), "--json"]) == 0
    capsys.readouterr()
    before = artifact.read_bytes()

    code = _main(
        tmp_path,
        [
            "observe",
            "--run-id",
            "run-1",
            "--artifact",
            str(artifact),
            "--output",
            str(artifact),
            "--monotonic-seconds",
            "60",
            "--json",
        ],
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "RUNNING"
    assert payload["run_id"] == "run-1"
    assert payload["counters"]["operator_observation_count"] == 1
    assert artifact.read_bytes() != before


def test_cli_normal_observe_command_captures_time_without_monotonic_argument(tmp_path, capsys) -> None:
    _write_config(tmp_path, heartbeat_interval_seconds=3600)
    config = LocalPaperEvidenceConfig(heartbeat_interval_seconds=3600)
    harness = LocalPaperEvidenceHarness(repo_root=tmp_path)
    artifact = tmp_path / "reports" / "local_paper_evidence" / "run-1.json"
    now = datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    started = harness.start(
        run_id="run-1",
        commit_sha="85e36081823bb56349eb2c844412b7382e7214b1",
        config=config,
        wall_timestamp=now,
        monotonic_seconds=0.0,
    )

    assert harness.write_artifact(started, artifact) is True
    code = _main(
        tmp_path,
        [
            "observe",
            "--run-id",
            "run-1",
            "--artifact",
            str(artifact),
            "--output",
            str(artifact),
            "--observation-code",
            "OBS_INTERNAL_TIME",
            "--json",
        ],
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "RUNNING"
    assert payload["operator_observations"][-1]["observation_code"] == "OBS_INTERNAL_TIME"
    assert payload["operator_observations"][-1]["monotonic_seconds"] >= 0.0
    assert payload["counters"]["operator_observation_count"] == 1


def test_cli_wrong_artifact_identity_fails_closed_without_overwrite(tmp_path, capsys) -> None:
    _write_config(tmp_path, heartbeat_interval_seconds=604800, liveness_multiplier=2)
    artifact = tmp_path / "reports" / "local_paper_evidence" / "run-1.json"
    wrong = tmp_path / "reports" / "local_paper_evidence" / "wrong.json"

    assert _main(tmp_path, ["start", "--run-id", "run-1", "--output", str(artifact), "--json"]) == 0
    capsys.readouterr()
    wrong.write_bytes(artifact.read_bytes())
    before = wrong.read_bytes()

    code = _main(
        tmp_path,
        [
            "heartbeat",
            "--run-id",
            "run-1",
            "--artifact",
            str(wrong),
            "--output",
            str(wrong),
            "--monotonic-seconds",
            "60",
            "--json",
        ],
    )
    captured = capsys.readouterr()

    assert code == 1
    assert "SANITIZED_FAILURE" in captured.err
    assert wrong.read_bytes() == before


def test_cli_validate_reads_artifact_without_runtime_or_mutation(tmp_path, capsys) -> None:
    _write_config(tmp_path, heartbeat_interval_seconds=12 * 60 * 60)
    artifact = _write_complete_artifact(tmp_path)
    before = artifact.read_bytes()

    code = _main(tmp_path, ["validate", "--artifact", str(artifact)])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "PASS"
    assert payload["reason_codes"] == []
    assert artifact.read_bytes() == before


def test_cli_errors_are_sanitized(tmp_path, capsys) -> None:
    code = _main(tmp_path, ["start", "--run-id", "run-1"])
    captured = capsys.readouterr()

    assert code == 1
    assert "SANITIZED_FAILURE" in captured.err
    assert "Traceback" not in captured.err
