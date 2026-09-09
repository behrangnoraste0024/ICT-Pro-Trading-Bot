from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from engine.diagnostics.local_paper_evidence_harness import LocalPaperEvidenceHarness
from models.local_paper_evidence import LocalPaperEvidenceConfig
from reporting.local_paper_evidence_report import artifact_to_json


RUN_ID = "paper-run-001"
COMMIT = "85e36081823bb56349eb2c844412b7382e7214b1"


def _harness() -> LocalPaperEvidenceHarness:
    return LocalPaperEvidenceHarness()


def _config(**overrides) -> LocalPaperEvidenceConfig:
    return replace(LocalPaperEvidenceConfig(), **overrides)


def _started(config: LocalPaperEvidenceConfig | None = None):
    cfg = config or _config()
    return _harness().start(
        run_id=RUN_ID,
        commit_sha=COMMIT,
        config=cfg,
        wall_timestamp="2026-08-21T00:00:00Z",
        monotonic_seconds=0.0,
    )


class FakeClock:
    def __init__(self) -> None:
        self.current = 0.0

    def monotonic(self) -> float:
        return self.current

    def wall_timestamp(self) -> str:
        return f"2026-08-21T00:{int(self.current):02d}:00Z"

    def sleep(self, seconds: float) -> None:
        self.current += seconds


class FakeWallClock:
    def __init__(self, wall_timestamp: str) -> None:
        self._wall_timestamp = wall_timestamp

    def wall_timestamp(self) -> str:
        return self._wall_timestamp


def _observe_every_12h(artifact, config):
    harness = _harness()
    current = artifact
    for index, seconds in enumerate(range(12 * 60 * 60, config.minimum_elapsed_seconds() + 1, 12 * 60 * 60), start=1):
        current = harness.record_heartbeat(
            current,
            config=config,
            wall_timestamp=f"2026-08-21T{index:02d}:00:00Z",
            monotonic_seconds=float(seconds),
        )
        current = harness.record_operator_observation(
            current,
            config=config,
            observation_code=f"OBS_{index}",
            wall_timestamp=f"2026-08-21T{index:02d}:00:01Z",
            monotonic_seconds=float(seconds),
        )
    return current


def test_btcusdt_only_and_production_disabled_are_enforced() -> None:
    bad_symbol = _started(_config(symbol="ETHUSDT"))
    production = _started(_config(production_disabled=False))

    assert bad_symbol.status == "FAILED"
    assert bad_symbol.stop_reason == "SAFETY_BOUNDARY_VIOLATION"
    assert production.status == "FAILED"
    assert production.stop_reason == "SAFETY_BOUNDARY_VIOLATION"


def test_credentials_network_exchange_and_resume_are_forbidden() -> None:
    for config in (
        _config(credentials_allowed=True),
        _config(network_allowed=True),
        _config(exchange_transport_allowed=True),
        _config(runtime_state_resume_allowed=True),
        _config(minimum_elapsed_hours=168),
        _config(minimum_elapsed_hours=96),
    ):
        artifact = _started(config)
        assert artifact.status == "FAILED"
        assert artifact.evidence_complete is False
        assert artifact.counters.external_transport_count == 0
        assert artifact.counters.credential_access_count == 0


def test_immutable_run_id_and_threshold_complete_zero_trade_semantics() -> None:
    config = _config(heartbeat_interval_seconds=12 * 60 * 60)
    artifact = _observe_every_12h(_started(config), config)
    complete = _harness().finalize(
        artifact,
        config=config,
        stop_reason="THRESHOLD_REACHED",
        wall_timestamp="2026-08-28T00:00:00Z",
        monotonic_seconds=float(config.minimum_elapsed_seconds()),
    )

    assert complete.run_id == RUN_ID
    assert config.minimum_elapsed_hours == 72
    assert config.minimum_elapsed_seconds() == 259200
    assert complete.evidence_complete is True
    assert complete.elapsed_seconds == config.minimum_elapsed_seconds()
    assert complete.counters.simulated_order_intent_count == 0
    assert complete.counters.simulated_fill_count == 0
    assert complete.counters.market_sample_event_count == 0


def test_premature_finalize_fails_even_with_success_reason() -> None:
    config = _config(heartbeat_interval_seconds=3600)
    artifact = _started(config)

    result = _harness().finalize(
        artifact,
        config=config,
        stop_reason="THRESHOLD_REACHED",
        wall_timestamp="2026-08-21T01:00:00Z",
        monotonic_seconds=3600.0,
    )

    assert result.status == "FAILED"
    assert result.evidence_complete is False
    assert result.stop_reason == "PREMATURE_TERMINATION"


def test_threshold_boundary_rejects_below_72_hours_and_accepts_exact_72_hours() -> None:
    config = _config(heartbeat_interval_seconds=12 * 60 * 60)
    below_artifact = _started(config)
    for index, seconds in enumerate(range(12 * 60 * 60, config.minimum_elapsed_seconds(), 12 * 60 * 60), start=1):
        below_artifact = _harness().record_heartbeat(
            below_artifact,
            config=config,
            wall_timestamp=f"2026-08-21T{index:02d}:00:00Z",
            monotonic_seconds=float(seconds),
        )
        below_artifact = _harness().record_operator_observation(
            below_artifact,
            config=config,
            observation_code=f"OBS_BELOW_{index}",
            wall_timestamp=f"2026-08-21T{index:02d}:00:01Z",
            monotonic_seconds=float(seconds),
        )
    exact_artifact = _observe_every_12h(_started(config), config)

    below = _harness().finalize(
        below_artifact,
        config=config,
        stop_reason="THRESHOLD_REACHED",
        wall_timestamp="2026-08-23T23:59:59Z",
        monotonic_seconds=float(config.minimum_elapsed_seconds() - 1),
    )
    exact = _harness().finalize(
        exact_artifact,
        config=config,
        stop_reason="THRESHOLD_REACHED",
        wall_timestamp="2026-08-24T00:00:00Z",
        monotonic_seconds=float(config.minimum_elapsed_seconds()),
    )

    assert below.status == "FAILED"
    assert below.stop_reason == "PREMATURE_TERMINATION"
    assert below.evidence_complete is False
    assert exact.status == "COMPLETE"
    assert exact.evidence_complete is True
    assert exact.elapsed_seconds == 72 * 60 * 60


def test_monotonic_elapsed_and_heartbeat_gap_boundary() -> None:
    config = _config(heartbeat_interval_seconds=30, liveness_multiplier=2)
    harness = _harness()
    artifact = _started(config)

    ok = harness.record_heartbeat(
        artifact,
        config=config,
        wall_timestamp="2026-08-21T00:01:00Z",
        monotonic_seconds=60.0,
    )
    failed = harness.record_heartbeat(
        ok,
        config=config,
        wall_timestamp="2026-08-21T00:02:01Z",
        monotonic_seconds=121.0,
    )

    assert ok.status == "RUNNING"
    assert ok.elapsed_seconds == 60.0
    assert failed.status == "FAILED"
    assert failed.stop_reason == "HEARTBEAT_GAP_EXCEEDED"


def test_operator_observation_deadline_behavior() -> None:
    config = _config(heartbeat_interval_seconds=13 * 60 * 60)
    artifact = _started(config)

    result = _harness().record_heartbeat(
        artifact,
        config=config,
        wall_timestamp="2026-08-21T13:00:00Z",
        monotonic_seconds=float(13 * 60 * 60),
    )

    assert result.status == "FAILED"
    assert result.stop_reason == "OPERATOR_OBSERVATION_MISSED"


def test_interruption_and_no_restart_resume_acceptance() -> None:
    config = _config()
    interrupted = _harness().record_interruption(
        _started(config),
        config=config,
        reason_code="PROCESS_EXIT",
        wall_timestamp="2026-08-21T01:00:00Z",
        monotonic_seconds=3600.0,
    )

    assert interrupted.status == "FAILED"
    assert interrupted.evidence_complete is False
    assert interrupted.continuity_state == "INTERRUPTED"
    assert interrupted.counters.interruption_count == 1


def test_unsupported_stop_reasons_fail_closed_and_counters_are_deterministic() -> None:
    config = _config(heartbeat_interval_seconds=12 * 60 * 60)
    artifact = _observe_every_12h(_started(config), config)
    result = _harness().finalize(
        artifact,
        config=config,
        stop_reason="operator said secret token value",
        wall_timestamp="2026-08-28T00:00:00Z",
        monotonic_seconds=float(config.minimum_elapsed_seconds()),
    )

    assert result.status == "FAILED"
    assert result.stop_reason == "SAFETY_BOUNDARY_VIOLATION"
    assert result.counters.external_transport_count == 0
    assert result.counters.credential_access_count == 0


def test_artifact_collision_fails_closed_without_overwrite(tmp_path) -> None:
    harness = LocalPaperEvidenceHarness(repo_root=tmp_path)
    config = _config()
    artifact = harness.start(
        run_id=RUN_ID,
        commit_sha=COMMIT,
        config=config,
        wall_timestamp="2026-08-21T00:00:00Z",
        monotonic_seconds=0.0,
    )
    path = tmp_path / "reports" / "local_paper_evidence" / f"{RUN_ID}.json"

    assert harness.write_artifact(artifact, path) is True
    original = path.read_bytes()

    replacement = harness.record_interruption(
        artifact,
        config=config,
        reason_code="PROCESS_EXIT",
        wall_timestamp="2026-08-21T01:00:00Z",
        monotonic_seconds=3600.0,
    )

    assert harness.write_artifact(replacement, path) is False
    assert path.read_bytes() == original
    assert sorted(item.name for item in path.parent.iterdir()) == [f"{RUN_ID}.json"]


def test_artifact_write_rejects_paths_outside_authorized_namespace(tmp_path) -> None:
    harness = LocalPaperEvidenceHarness(repo_root=tmp_path)
    artifact = harness.start(
        run_id=RUN_ID,
        commit_sha=COMMIT,
        config=_config(),
        wall_timestamp="2026-08-21T00:00:00Z",
        monotonic_seconds=0.0,
    )

    assert harness.write_artifact(artifact, tmp_path / "reports" / f"{RUN_ID}.json") is False
    assert harness.write_artifact(artifact, tmp_path / "outside.json") is False


def test_same_run_lifecycle_updates_existing_artifact_atomically(tmp_path) -> None:
    harness = LocalPaperEvidenceHarness(repo_root=tmp_path)
    config = _config(heartbeat_interval_seconds=12 * 60 * 60)
    path = tmp_path / "reports" / "local_paper_evidence" / f"{RUN_ID}.json"
    started = harness.start(
        run_id=RUN_ID,
        commit_sha=COMMIT,
        config=config,
        wall_timestamp="2026-08-21T00:00:00Z",
        monotonic_seconds=0.0,
    )

    assert harness.write_artifact(started, path) is True
    heartbeat = harness.update_artifact(
        path,
        path,
        run_id=RUN_ID,
        config=config,
        operation="heartbeat",
        transition=lambda artifact: harness.record_heartbeat(
            artifact,
            config=config,
            wall_timestamp="2026-08-21T12:00:00Z",
            monotonic_seconds=float(12 * 60 * 60),
        ),
    )
    observation = harness.update_artifact(
        path,
        path,
        run_id=RUN_ID,
        config=config,
        operation="observe",
        transition=lambda artifact: harness.record_operator_observation(
            artifact,
            config=config,
            observation_code="OBS_1",
            wall_timestamp="2026-08-21T12:00:01Z",
            monotonic_seconds=float(12 * 60 * 60),
        ),
    )

    assert heartbeat is not None
    assert observation is not None
    assert observation.run_id == RUN_ID
    assert observation.counters.heartbeat_count == 1
    assert observation.counters.operator_observation_count == 1
    assert not (Path(f"{path}.tmp")).exists()
    assert not (Path(f"{path}.lock")).exists()


def test_lifecycle_update_wrong_run_malformed_completed_and_conflict_fail_closed(tmp_path) -> None:
    harness = LocalPaperEvidenceHarness(repo_root=tmp_path)
    config = _config(heartbeat_interval_seconds=12 * 60 * 60)
    path = tmp_path / "reports" / "local_paper_evidence" / f"{RUN_ID}.json"
    started = harness.start(
        run_id=RUN_ID,
        commit_sha=COMMIT,
        config=config,
        wall_timestamp="2026-08-21T00:00:00Z",
        monotonic_seconds=0.0,
    )
    assert harness.write_artifact(started, path) is True
    original = path.read_bytes()

    assert harness.update_artifact(path, path, run_id="other-run", config=config, operation="heartbeat", transition=lambda item: item) is None
    assert path.read_bytes() == original
    wrong_path = path.with_name("wrong-name.json")
    wrong_path.write_bytes(original)
    assert harness.update_artifact(wrong_path, wrong_path, run_id=RUN_ID, config=config, operation="heartbeat", transition=lambda item: item) is None
    assert wrong_path.read_bytes() == original

    path.write_text("{not-json", encoding="utf-8")
    malformed = path.read_bytes()
    assert harness.update_artifact(path, path, run_id=RUN_ID, config=config, operation="heartbeat", transition=lambda item: item) is None
    assert path.read_bytes() == malformed

    path.write_bytes(original)
    lock_path = Path(f"{path}.lock")
    lock_path.write_text("LOCKED", encoding="utf-8")
    assert harness.update_artifact(path, path, run_id=RUN_ID, config=config, operation="heartbeat", transition=lambda item: item) is None
    assert path.read_bytes() == original
    lock_path.unlink()

    current = started
    for index, seconds in enumerate(range(12 * 60 * 60, config.minimum_elapsed_seconds() + 1, 12 * 60 * 60), start=1):
        current = harness.record_heartbeat(current, config=config, wall_timestamp=f"2026-08-21T{index:02d}:00:00Z", monotonic_seconds=float(seconds))
        current = harness.record_operator_observation(current, config=config, observation_code=f"OBS_{index}", wall_timestamp=f"2026-08-21T{index:02d}:00:01Z", monotonic_seconds=float(seconds))
    complete = harness.finalize(current, config=config, stop_reason="THRESHOLD_REACHED", wall_timestamp="2026-08-24T00:00:00Z", monotonic_seconds=float(config.minimum_elapsed_seconds()))
    path.write_text(artifact_to_json(complete), encoding="utf-8")
    complete_bytes = path.read_bytes()
    assert harness.update_artifact(path, path, run_id=RUN_ID, config=config, operation="heartbeat", transition=lambda item: item) is None
    assert path.read_bytes() == complete_bytes


def test_automatic_heartbeat_uses_fake_clock_and_updates_same_artifact(tmp_path) -> None:
    harness = LocalPaperEvidenceHarness(repo_root=tmp_path)
    config = _config()
    clock = FakeClock()
    path = tmp_path / "reports" / "local_paper_evidence" / f"{RUN_ID}.json"

    artifact = harness.run_automatic_heartbeat(
        run_id=RUN_ID,
        output_path=path,
        commit_sha=COMMIT,
        config=config,
        clock=clock,
        sleeper=clock.sleep,
        max_cycles=3,
    )
    stored = harness.read_artifact(path)

    assert artifact.status == "RUNNING"
    assert stored.run_id == RUN_ID
    assert stored.counters.heartbeat_count == 3
    assert stored.heartbeat.last_heartbeat_monotonic_seconds == 90.0
    assert clock.current == 90.0
    assert stored.counters.credential_access_count == 0
    assert stored.counters.external_transport_count == 0


def test_automatic_heartbeat_gap_failure_is_persisted_fail_closed(tmp_path) -> None:
    harness = LocalPaperEvidenceHarness(repo_root=tmp_path)
    config = _config()
    clock = FakeClock()
    path = tmp_path / "reports" / "local_paper_evidence" / f"{RUN_ID}.json"

    def late_sleep(seconds: float) -> None:
        clock.current += seconds + 31.0

    artifact = harness.run_automatic_heartbeat(
        run_id=RUN_ID,
        output_path=path,
        commit_sha=COMMIT,
        config=config,
        clock=clock,
        sleeper=late_sleep,
        max_cycles=1,
    )
    stored = harness.read_artifact(path)

    assert artifact.status == "FAILED"
    assert artifact.stop_reason == "HEARTBEAT_GAP_EXCEEDED"
    assert stored.status == "FAILED"
    assert stored.evidence_complete is False


def test_capture_operator_observation_derives_monotonic_from_artifact_wall_time(tmp_path) -> None:
    harness = LocalPaperEvidenceHarness(repo_root=tmp_path)
    config = _config(heartbeat_interval_seconds=3600)
    artifact = harness.start(
        run_id=RUN_ID,
        commit_sha=COMMIT,
        config=config,
        wall_timestamp="2026-08-21T00:00:00Z",
        monotonic_seconds=100.0,
    )

    observed = harness.capture_operator_observation(
        artifact,
        config=config,
        observation_code="OBS_OK",
        clock=FakeWallClock("2026-08-21T00:30:00Z"),
    )

    assert observed.status == "RUNNING"
    assert observed.operator_observations[-1].monotonic_seconds == 1900.0
    assert observed.operator_observations[-1].observed_at == "2026-08-21T00:30:00Z"
    assert observed.counters.operator_observation_count == 1


def test_capture_operator_observation_deadline_and_future_gap_fail_closed() -> None:
    config = _config()
    artifact = _started(config)

    missed = _harness().capture_operator_observation(
        artifact,
        config=config,
        observation_code="OBS_LATE",
        clock=FakeWallClock("2026-08-21T12:00:01Z"),
    )
    future_gap = _harness().capture_operator_observation(
        artifact,
        config=config,
        observation_code="OBS_FUTURE",
        clock=FakeWallClock("2026-08-21T00:01:01Z"),
    )

    assert missed.status == "FAILED"
    assert missed.stop_reason == "HEARTBEAT_GAP_EXCEEDED"
    assert missed.evidence_complete is False
    assert future_gap.status == "FAILED"
    assert future_gap.stop_reason == "HEARTBEAT_GAP_EXCEEDED"


def test_capture_operator_observation_does_not_backdate_before_start() -> None:
    config = _config(heartbeat_interval_seconds=3600)
    artifact = _harness().start(
        run_id=RUN_ID,
        commit_sha=COMMIT,
        config=config,
        wall_timestamp="2026-08-21T00:00:00Z",
        monotonic_seconds=500.0,
    )

    observed = _harness().capture_operator_observation(
        artifact,
        config=config,
        observation_code="OBS_BACKWARD_CLOCK",
        clock=FakeWallClock("2026-08-20T23:59:00Z"),
    )

    assert observed.status == "RUNNING"
    assert observed.operator_observations[-1].monotonic_seconds == 500.0


def test_observation_and_heartbeat_updates_preserve_each_other(tmp_path) -> None:
    harness = LocalPaperEvidenceHarness(repo_root=tmp_path)
    config = _config(heartbeat_interval_seconds=3600)
    now = datetime.now(UTC).replace(microsecond=0)
    path = tmp_path / "reports" / "local_paper_evidence" / f"{RUN_ID}.json"
    started = harness.start(
        run_id=RUN_ID,
        commit_sha=COMMIT,
        config=config,
        wall_timestamp=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        monotonic_seconds=0.0,
    )

    assert harness.write_artifact(started, path) is True
    observation = harness.update_artifact(
        path,
        path,
        run_id=RUN_ID,
        config=config,
        operation="observe",
        transition=lambda artifact: harness.capture_operator_observation(
            artifact,
            config=config,
            observation_code="OBS_COORDINATED",
            clock=FakeWallClock((now + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ),
    )
    heartbeat = harness.update_artifact(
        path,
        path,
        run_id=RUN_ID,
        config=config,
        operation="heartbeat",
        transition=lambda artifact: harness.record_heartbeat(
            artifact,
            config=config,
            wall_timestamp=(now + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            monotonic_seconds=120.0,
        ),
    )
    stored = harness.read_artifact(path)

    assert observation is not None
    assert heartbeat is not None
    assert stored.counters.operator_observation_count == 1
    assert stored.counters.heartbeat_count == 1
    assert stored.operator_observations[-1].observation_code == "OBS_COORDINATED"
    assert stored.heartbeat.last_heartbeat_monotonic_seconds == 120.0
