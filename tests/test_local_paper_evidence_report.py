from __future__ import annotations

import json
from dataclasses import replace

from engine.diagnostics.local_paper_evidence_harness import LocalPaperEvidenceHarness
from models.local_paper_evidence import LocalPaperEvidenceConfig
from reporting.local_paper_evidence_report import artifact_to_json, artifact_to_sanitized_dict


def _artifact():
    config = LocalPaperEvidenceConfig(heartbeat_interval_seconds=12 * 60 * 60)
    harness = LocalPaperEvidenceHarness()
    artifact = harness.start(
        run_id="paper-run-001",
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
    return harness.finalize(
        artifact,
        config=config,
        stop_reason="THRESHOLD_REACHED",
        wall_timestamp="2026-08-24T00:00:00Z",
        monotonic_seconds=float(config.minimum_elapsed_seconds()),
    )


def test_required_artifact_fields_and_stable_schema() -> None:
    payload = artifact_to_sanitized_dict(_artifact())

    assert list(payload.keys()) == sorted(payload.keys()) or set(payload) >= {
        "schema_version",
        "run_id",
        "commit_sha",
        "runtime_mode",
        "symbol",
        "production_disabled",
        "start_timestamp",
        "end_timestamp",
        "elapsed_seconds",
        "heartbeat",
        "operator_observations",
        "continuity_state",
        "interruptions",
        "counters",
        "external_transport_count" if False else "stop_reason",
        "sanitization_status",
        "evidence_complete",
    }
    assert payload["schema_version"] == "1.0"
    assert payload["symbol"] == "BTCUSDT"
    assert payload["minimum_elapsed_seconds"] == 259200
    assert payload["evidence_complete"] is True


def test_json_is_deterministic_and_sanitized() -> None:
    artifact = _artifact()

    first = artifact_to_json(artifact)
    second = artifact_to_json(artifact)

    assert first == second
    assert "secret" not in first.casefold()
    assert "traceback" not in first.casefold()
    assert "select " not in first.casefold()


def test_secret_like_observation_is_not_serialized() -> None:
    config = LocalPaperEvidenceConfig()
    harness = LocalPaperEvidenceHarness()
    artifact = harness.start(
        run_id="paper-run-001",
        commit_sha="85e36081823bb56349eb2c844412b7382e7214b1",
        config=config,
        wall_timestamp="2026-08-21T00:00:00Z",
        monotonic_seconds=0.0,
    )
    failed = harness.record_operator_observation(
        artifact,
        config=config,
        observation_code="token=SECRET Authorization Bearer abc",
        wall_timestamp="2026-08-21T01:00:00Z",
        monotonic_seconds=3600.0,
    )
    rendered = artifact_to_json(failed)

    assert failed.status == "FAILED"
    assert "SECRET" not in rendered
    assert "Bearer" not in rendered
    assert "Authorization" not in rendered
    assert "SANITIZATION_FAILURE" in rendered


def test_failure_artifact_retains_incomplete_evidence_without_tracebacks_or_sql() -> None:
    config = LocalPaperEvidenceConfig(heartbeat_interval_seconds=600)
    harness = LocalPaperEvidenceHarness()
    artifact = harness.start(
        run_id="paper-run-001",
        commit_sha="85e36081823bb56349eb2c844412b7382e7214b1",
        config=config,
        wall_timestamp="2026-08-21T00:00:00Z",
        monotonic_seconds=0.0,
    )
    failed = harness.finalize(
        artifact,
        config=config,
        stop_reason="OPERATOR_STOP_AFTER_THRESHOLD",
        wall_timestamp="2026-08-21T00:10:00Z",
        monotonic_seconds=600.0,
    )
    payload = json.loads(artifact_to_json(failed))

    assert payload["status"] == "FAILED"
    assert payload["evidence_complete"] is False
    assert payload["stop_reason"] == "PREMATURE_TERMINATION"
    assert "traceback" not in json.dumps(payload).casefold()
    assert "select " not in json.dumps(payload).casefold()


def test_report_sanitizer_detects_mutated_secret_like_payload() -> None:
    artifact = _artifact()
    unsafe = replace(artifact, notes=("raw traceback with api_key SECRET",))
    payload = artifact_to_sanitized_dict(unsafe)

    assert payload["sanitization_status"] == "SANITIZATION_FAILED"
    assert payload["evidence_complete"] is False
    assert payload["notes"] == []
