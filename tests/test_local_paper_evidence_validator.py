from __future__ import annotations

import json
from dataclasses import replace

from engine.diagnostics.local_paper_evidence_harness import LocalPaperEvidenceHarness
from engine.diagnostics.local_paper_evidence_validator import LocalPaperEvidenceArtifactValidator
from models.local_paper_evidence import LocalPaperEvidenceConfig
from reporting.local_paper_evidence_report import artifact_to_json


RUN_ID = "paper-run-001"
COMMIT = "85e36081823bb56349eb2c844412b7382e7214b1"


def _write_config(root, **overrides):
    (root / "configs").mkdir()
    payload = LocalPaperEvidenceConfig().to_dict()
    payload.update(overrides)
    path = root / "configs" / "local_paper_evidence_harness.json"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _complete_payload(tmp_path, **overrides):
    _write_config(tmp_path, heartbeat_interval_seconds=12 * 60 * 60)
    config = replace(LocalPaperEvidenceConfig(), heartbeat_interval_seconds=12 * 60 * 60)
    harness = LocalPaperEvidenceHarness(repo_root=tmp_path)
    artifact = harness.start(
        run_id=RUN_ID,
        commit_sha=COMMIT,
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
        stop_reason="THRESHOLD_REACHED",
        wall_timestamp="2026-08-24T00:00:00Z",
        monotonic_seconds=float(config.minimum_elapsed_seconds()),
    )
    payload = json.loads(artifact_to_json(complete))
    payload.update(overrides)
    return payload


def _write_artifact(tmp_path, payload):
    path = tmp_path / "reports" / "local_paper_evidence" / f"{payload['run_id']}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _validate(tmp_path, path):
    return LocalPaperEvidenceArtifactValidator(repo_root=tmp_path).validate(path)


def test_validator_passes_complete_artifact_without_mutating_bytes(tmp_path) -> None:
    path = _write_artifact(tmp_path, _complete_payload(tmp_path))
    before = path.read_bytes()

    result = _validate(tmp_path, path)

    assert result.status == "PASS"
    assert result.reason_codes == ()
    assert result.run_id == RUN_ID
    assert result.evidence_complete is True
    assert path.read_bytes() == before


def test_validator_fails_closed_for_malformed_json_without_leaking_sensitive_text(tmp_path) -> None:
    _write_config(tmp_path)
    path = tmp_path / "reports" / "local_paper_evidence" / f"{RUN_ID}.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"api_key":"abc"', encoding="utf-8")
    before = path.read_bytes()

    result = _validate(tmp_path, path)
    rendered = json.dumps(result.to_dict(), sort_keys=True)

    assert result.status == "FAIL"
    assert "MALFORMED_JSON" in result.reason_codes
    assert "api_key" not in rendered.lower()
    assert "abc" not in rendered
    assert path.read_bytes() == before


def test_validator_rejects_missing_ambiguous_and_mismatched_required_fields(tmp_path) -> None:
    payload = _complete_payload(tmp_path)
    payload.pop("heartbeat")
    path = _write_artifact(tmp_path, payload)

    result = _validate(tmp_path, path)

    assert result.status == "FAIL"
    assert "REQUIRED_FIELDS_MISSING" in result.reason_codes


def test_validator_rejects_safety_and_acceptance_contract_violations(tmp_path) -> None:
    payload = _complete_payload(
        tmp_path,
        symbol="ETHUSDT",
        production_disabled=False,
        elapsed_seconds=60.0,
        evidence_complete=False,
        stop_reason="PREMATURE_TERMINATION",
        continuity_state="INTERRUPTED",
    )
    payload["counters"]["credential_access_count"] = 1
    payload["interruptions"] = [{"reason_code": "PROCESS_EXIT", "monotonic_seconds": 1.0}]
    path = _write_artifact(tmp_path, payload)

    result = _validate(tmp_path, path)

    assert result.status == "FAIL"
    assert "SYMBOL_INVALID" in result.reason_codes
    assert "PRODUCTION_DISABLED_INVALID" in result.reason_codes
    assert "THRESHOLD_NOT_MET" in result.reason_codes
    assert "EVIDENCE_INCOMPLETE" in result.reason_codes
    assert "STOP_REASON_INVALID" in result.reason_codes
    assert "CONTINUITY_INVALID" in result.reason_codes
    assert "COUNTERS_NONZERO" in result.reason_codes
    assert "INTERRUPTION_PRESENT" in result.reason_codes


def test_validator_rejects_observation_liveness_and_identity_failures(tmp_path) -> None:
    payload = _complete_payload(tmp_path)
    payload["heartbeat"]["liveness_status"] = "FAIL"
    payload["operator_observations"][0]["monotonic_seconds"] = float(24 * 60 * 60)
    path = _write_artifact(tmp_path, payload)
    renamed = path.with_name("different-run.json")
    path.rename(renamed)

    result = _validate(tmp_path, renamed)

    assert result.status == "FAIL"
    assert "RUN_ID_ARTIFACT_MISMATCH" in result.reason_codes
    assert "LIVENESS_INVALID" in result.reason_codes
    assert "OBSERVATION_COVERAGE_GAP" in result.reason_codes


def test_validator_rejects_failed_artifact_even_when_threshold_is_met(tmp_path) -> None:
    payload = _complete_payload(
        tmp_path,
        status="FAILED",
        evidence_complete=False,
        stop_reason="OPERATOR_OBSERVATION_MISSED",
    )
    path = _write_artifact(tmp_path, payload)

    result = _validate(tmp_path, path)

    assert result.status == "FAIL"
    assert "STATUS_NOT_COMPLETE" in result.reason_codes
    assert "EVIDENCE_INCOMPLETE" in result.reason_codes
    assert "STOP_REASON_INVALID" in result.reason_codes
    assert "THRESHOLD_NOT_MET" not in result.reason_codes
