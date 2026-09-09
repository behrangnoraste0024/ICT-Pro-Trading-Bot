from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator

from models.local_paper_evidence import (
    LocalPaperEvidenceArtifact,
    LocalPaperEvidenceConfig,
    LocalPaperEvidenceCounters,
    LocalPaperEvidenceStatus,
    LocalPaperHeartbeatEvidence,
    LocalPaperInterruptionEvidence,
    LocalPaperOperatorObservation,
    LocalPaperStopReason,
    SUCCESSFUL_STOP_REASONS,
)
from reporting.local_paper_evidence_report import artifact_to_json


SANITIZED_OK = "SANITIZED"
SENSITIVE_RE = re.compile(
    r"(api[_-]?key|secret|password|token|signature|authorization|bearer|authenticated url|signed url|traceback|select\s+|insert\s+|update\s+|delete\s+|postgresql://|mysql://)",
    re.IGNORECASE,
)


class LocalPaperEvidenceHarness:
    def __init__(self, repo_root: str | Path | None = None) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)

    def load_config(self, config_path: str | Path = "configs/local_paper_evidence_harness.json") -> LocalPaperEvidenceConfig:
        path = self._resolve(config_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        config = LocalPaperEvidenceConfig.from_dict(payload)
        return replace(config, config_reference=self._relative_reference(path))

    def start(
        self,
        *,
        run_id: str,
        commit_sha: str,
        config: LocalPaperEvidenceConfig,
        wall_timestamp: str,
        monotonic_seconds: float,
    ) -> LocalPaperEvidenceArtifact:
        reason = self._configuration_failure(config)
        if reason is not None:
            return self._failed_artifact(
                run_id=run_id,
                commit_sha=commit_sha,
                config=config,
                wall_timestamp=wall_timestamp,
                monotonic_seconds=monotonic_seconds,
                stop_reason=reason,
            )
        safe_run_id = self._sanitize_code(run_id)
        if safe_run_id != run_id or not safe_run_id:
            return self._failed_artifact(
                run_id="INVALID_RUN_ID",
                commit_sha=commit_sha,
                config=config,
                wall_timestamp=wall_timestamp,
                monotonic_seconds=monotonic_seconds,
                stop_reason=LocalPaperStopReason.SANITIZATION_FAILURE.value,
            )
        return LocalPaperEvidenceArtifact(
            schema_version=config.artifact_schema_version,
            run_id=run_id,
            commit_sha=self._safe_commit(commit_sha),
            config_reference=config.config_reference,
            config_schema_version=config.schema_version,
            runtime_mode=config.runtime_mode,
            symbol=config.symbol,
            environment_classification=config.environment_classification,
            production_disabled=config.production_disabled,
            start_timestamp=wall_timestamp,
            end_timestamp=None,
            start_monotonic_seconds=monotonic_seconds,
            end_monotonic_seconds=None,
            elapsed_seconds=0.0,
            minimum_elapsed_seconds=config.minimum_elapsed_seconds(),
            continuity_state="CONTINUOUS",
            status=LocalPaperEvidenceStatus.RUNNING.value,
            stop_reason=None,
            sanitization_status=SANITIZED_OK,
            evidence_complete=False,
            heartbeat=LocalPaperHeartbeatEvidence(
                last_heartbeat_timestamp=wall_timestamp,
                last_heartbeat_monotonic_seconds=monotonic_seconds,
                max_allowed_gap_seconds=config.max_heartbeat_gap_seconds(),
                liveness_status="PASS",
            ),
            counters=LocalPaperEvidenceCounters(),
        )

    def record_heartbeat(
        self,
        artifact: LocalPaperEvidenceArtifact,
        *,
        config: LocalPaperEvidenceConfig,
        wall_timestamp: str,
        monotonic_seconds: float,
    ) -> LocalPaperEvidenceArtifact:
        failed = self._runtime_failure(artifact, config, monotonic_seconds)
        if failed is not None:
            return self._finish(artifact, config, wall_timestamp, monotonic_seconds, failed, complete=False)
        counters = replace(artifact.counters, heartbeat_count=artifact.counters.heartbeat_count + 1)
        heartbeat = LocalPaperHeartbeatEvidence(
            last_heartbeat_timestamp=wall_timestamp,
            last_heartbeat_monotonic_seconds=monotonic_seconds,
            max_allowed_gap_seconds=config.max_heartbeat_gap_seconds(),
            liveness_status="PASS",
        )
        return replace(
            artifact,
            heartbeat=heartbeat,
            counters=counters,
            elapsed_seconds=self._elapsed(artifact, monotonic_seconds),
        )

    def record_operator_observation(
        self,
        artifact: LocalPaperEvidenceArtifact,
        *,
        config: LocalPaperEvidenceConfig,
        observation_code: str,
        wall_timestamp: str,
        monotonic_seconds: float,
    ) -> LocalPaperEvidenceArtifact:
        safe_code = self._sanitize_code(observation_code)
        if not safe_code:
            return self._finish(
                artifact,
                config,
                wall_timestamp,
                monotonic_seconds,
                LocalPaperStopReason.SANITIZATION_FAILURE.value,
                complete=False,
            )
        failed = self._runtime_failure(artifact, config, monotonic_seconds)
        if failed is not None:
            return self._finish(artifact, config, wall_timestamp, monotonic_seconds, failed, complete=False)
        observation = LocalPaperOperatorObservation(
            observed_at=wall_timestamp,
            monotonic_seconds=monotonic_seconds,
            observation_code=safe_code,
        )
        counters = replace(
            artifact.counters,
            operator_observation_count=artifact.counters.operator_observation_count + 1,
        )
        return replace(
            artifact,
            operator_observations=tuple([*artifact.operator_observations, observation]),
            counters=counters,
            elapsed_seconds=self._elapsed(artifact, monotonic_seconds),
        )

    def capture_operator_observation(
        self,
        artifact: LocalPaperEvidenceArtifact,
        *,
        config: LocalPaperEvidenceConfig,
        observation_code: str,
        clock: Any | None = None,
    ) -> LocalPaperEvidenceArtifact:
        runtime_clock = clock or _SystemClock()
        monotonic_seconds = self._artifact_relative_monotonic(artifact, runtime_clock.wall_timestamp())
        return self.record_operator_observation(
            artifact,
            config=config,
            observation_code=observation_code,
            wall_timestamp=runtime_clock.wall_timestamp(),
            monotonic_seconds=monotonic_seconds,
        )

    def record_interruption(
        self,
        artifact: LocalPaperEvidenceArtifact,
        *,
        config: LocalPaperEvidenceConfig,
        reason_code: str,
        wall_timestamp: str,
        monotonic_seconds: float,
    ) -> LocalPaperEvidenceArtifact:
        interruption = LocalPaperInterruptionEvidence(
            occurred_at=wall_timestamp,
            monotonic_seconds=monotonic_seconds,
            reason_code=self._public_reason(reason_code),
        )
        counters = replace(
            artifact.counters,
            interruption_count=artifact.counters.interruption_count + 1,
        )
        interrupted = replace(
            artifact,
            continuity_state="INTERRUPTED",
            interruptions=tuple([*artifact.interruptions, interruption]),
            counters=counters,
            elapsed_seconds=self._elapsed(artifact, monotonic_seconds),
        )
        return self._finish(
            interrupted,
            config,
            wall_timestamp,
            monotonic_seconds,
            LocalPaperStopReason.PREMATURE_TERMINATION.value,
            complete=False,
        )

    def finalize(
        self,
        artifact: LocalPaperEvidenceArtifact,
        *,
        config: LocalPaperEvidenceConfig,
        stop_reason: str,
        wall_timestamp: str,
        monotonic_seconds: float,
    ) -> LocalPaperEvidenceArtifact:
        failed = self._runtime_failure(artifact, config, monotonic_seconds)
        if failed is not None:
            return self._finish(artifact, config, wall_timestamp, monotonic_seconds, failed, complete=False)
        reason = self._public_reason(stop_reason)
        elapsed = self._elapsed(artifact, monotonic_seconds)
        complete = (
            reason in SUCCESSFUL_STOP_REASONS
            and elapsed >= config.minimum_elapsed_seconds()
            and artifact.continuity_state == "CONTINUOUS"
            and not artifact.interruptions
            and self._observations_cover_window(artifact, config, monotonic_seconds)
        )
        if reason not in SUCCESSFUL_STOP_REASONS:
            reason = LocalPaperStopReason.SAFETY_BOUNDARY_VIOLATION.value
        elif elapsed < config.minimum_elapsed_seconds():
            reason = LocalPaperStopReason.PREMATURE_TERMINATION.value
        elif not self._observations_cover_window(artifact, config, monotonic_seconds):
            reason = LocalPaperStopReason.OPERATOR_OBSERVATION_MISSED.value
        return self._finish(artifact, config, wall_timestamp, monotonic_seconds, reason, complete=complete)

    def write_artifact(self, artifact: LocalPaperEvidenceArtifact, output_path: str | Path) -> bool:
        path = self._resolve(output_path)
        if not self._safe_artifact_path(path):
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as handle:
                handle.write(artifact_to_json(artifact))
            return True
        except OSError:
            return False

    def update_artifact(
        self,
        artifact_path: str | Path,
        output_path: str | Path,
        *,
        run_id: str,
        config: LocalPaperEvidenceConfig,
        operation: str,
        transition: Callable[[LocalPaperEvidenceArtifact], LocalPaperEvidenceArtifact],
    ) -> LocalPaperEvidenceArtifact | None:
        source = self._resolve(artifact_path)
        target = self._resolve(output_path)
        if source != target or operation not in {"heartbeat", "observe", "finalize"}:
            return None
        if target.name != f"{run_id}.json":
            return None
        if not self._safe_artifact_path(target):
            return None
        try:
            with self._artifact_lock(target):
                artifact = self.read_artifact(target)
                if not self._update_allowed(artifact, run_id=run_id, config=config):
                    return None
                updated = transition(artifact)
                serialized = artifact_to_json(updated)
                temp_path = target.with_name(f"{target.name}.tmp")
                if temp_path.exists():
                    return None
                try:
                    with temp_path.open("x", encoding="utf-8") as handle:
                        handle.write(serialized)
                    temp_path.replace(target)
                finally:
                    if temp_path.exists():
                        temp_path.unlink()
                return updated
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def run_automatic_heartbeat(
        self,
        *,
        run_id: str,
        output_path: str | Path,
        commit_sha: str,
        config: LocalPaperEvidenceConfig,
        clock: Any | None = None,
        sleeper: Callable[[float], None] | None = None,
        max_cycles: int | None = None,
    ) -> LocalPaperEvidenceArtifact:
        runtime_clock = clock or _SystemClock()
        sleep = sleeper or time.sleep
        start_seconds = float(runtime_clock.monotonic())
        artifact = self.start(
            run_id=run_id,
            commit_sha=commit_sha,
            config=config,
            wall_timestamp=runtime_clock.wall_timestamp(),
            monotonic_seconds=start_seconds,
        )
        if artifact.status != LocalPaperEvidenceStatus.RUNNING.value:
            return artifact
        if not self.write_artifact(artifact, output_path):
            return self.finalize(
                artifact,
                config=config,
                stop_reason=LocalPaperStopReason.ARTIFACT_WRITE_FAILURE.value,
                wall_timestamp=runtime_clock.wall_timestamp(),
                monotonic_seconds=float(runtime_clock.monotonic()),
            )

        cycles = 0
        path = self._resolve(output_path)
        while max_cycles is None or cycles < max_cycles:
            current = self.read_artifact(path)
            if current.status != LocalPaperEvidenceStatus.RUNNING.value:
                return current
            if current.elapsed_seconds >= config.minimum_elapsed_seconds():
                finalized = self.update_artifact(
                    path,
                    path,
                    run_id=run_id,
                    config=config,
                    operation="finalize",
                    transition=lambda item: self.finalize(
                        item,
                        config=config,
                        stop_reason=LocalPaperStopReason.THRESHOLD_REACHED.value,
                        wall_timestamp=runtime_clock.wall_timestamp(),
                        monotonic_seconds=float(runtime_clock.monotonic()),
                    ),
                )
                return finalized or current

            last = current.heartbeat.last_heartbeat_monotonic_seconds or current.start_monotonic_seconds
            delay = max(0.0, (last + config.heartbeat_interval_seconds) - float(runtime_clock.monotonic()))
            if delay:
                sleep(delay)
            updated = self.update_artifact(
                path,
                path,
                run_id=run_id,
                config=config,
                operation="heartbeat",
                transition=lambda item: self.record_heartbeat(
                    item,
                    config=config,
                    wall_timestamp=runtime_clock.wall_timestamp(),
                    monotonic_seconds=float(runtime_clock.monotonic()),
                ),
            )
            if updated is None:
                current = self.read_artifact(path)
                return self.finalize(
                    current,
                    config=config,
                    stop_reason=LocalPaperStopReason.ARTIFACT_WRITE_FAILURE.value,
                    wall_timestamp=runtime_clock.wall_timestamp(),
                    monotonic_seconds=float(runtime_clock.monotonic()),
                )
            cycles += 1
        return self.read_artifact(path)

    def read_artifact(self, path: str | Path) -> LocalPaperEvidenceArtifact:
        return LocalPaperEvidenceArtifact.from_dict(json.loads(self._resolve(path).read_text(encoding="utf-8")))

    def _configuration_failure(self, config: LocalPaperEvidenceConfig) -> str | None:
        if config.symbol != "BTCUSDT":
            return LocalPaperStopReason.SAFETY_BOUNDARY_VIOLATION.value
        if not config.production_disabled:
            return LocalPaperStopReason.SAFETY_BOUNDARY_VIOLATION.value
        if config.network_allowed or config.exchange_transport_allowed or config.credentials_allowed:
            return LocalPaperStopReason.SAFETY_BOUNDARY_VIOLATION.value
        if config.runtime_state_resume_allowed:
            return LocalPaperStopReason.SAFETY_BOUNDARY_VIOLATION.value
        if config.runtime_mode != "local_paper_evidence":
            return LocalPaperStopReason.UNSUPPORTED_RUNTIME_STATE.value
        if config.minimum_elapsed_hours != 72:
            return LocalPaperStopReason.SAFETY_BOUNDARY_VIOLATION.value
        if config.operator_observation_interval_hours != 12:
            return LocalPaperStopReason.SAFETY_BOUNDARY_VIOLATION.value
        if config.liveness_multiplier != 2 or config.heartbeat_interval_seconds <= 0:
            return LocalPaperStopReason.SAFETY_BOUNDARY_VIOLATION.value
        if tuple(config.allowed_successful_stop_reasons) != tuple(LocalPaperEvidenceConfig().allowed_successful_stop_reasons):
            return LocalPaperStopReason.SAFETY_BOUNDARY_VIOLATION.value
        return None

    def _runtime_failure(
        self,
        artifact: LocalPaperEvidenceArtifact,
        config: LocalPaperEvidenceConfig,
        monotonic_seconds: float,
    ) -> str | None:
        if artifact.status != LocalPaperEvidenceStatus.RUNNING.value:
            return LocalPaperStopReason.UNSUPPORTED_RUNTIME_STATE.value
        if artifact.run_id == "" or artifact.continuity_state != "CONTINUOUS":
            return LocalPaperStopReason.PREMATURE_TERMINATION.value
        if artifact.counters.external_transport_count != 0 or artifact.counters.credential_access_count != 0:
            return LocalPaperStopReason.SAFETY_BOUNDARY_VIOLATION.value
        if artifact.counters.persistence_write_count != 0:
            return LocalPaperStopReason.SAFETY_BOUNDARY_VIOLATION.value
        last = artifact.heartbeat.last_heartbeat_monotonic_seconds
        if monotonic_seconds < artifact.start_monotonic_seconds:
            return LocalPaperStopReason.UNSUPPORTED_RUNTIME_STATE.value
        if last is not None and monotonic_seconds - last > config.max_heartbeat_gap_seconds():
            return LocalPaperStopReason.HEARTBEAT_GAP_EXCEEDED.value
        if last is not None and monotonic_seconds < last:
            return LocalPaperStopReason.UNSUPPORTED_RUNTIME_STATE.value
        if artifact.operator_observations and monotonic_seconds < artifact.operator_observations[-1].monotonic_seconds:
            return LocalPaperStopReason.UNSUPPORTED_RUNTIME_STATE.value
        if not self._observation_deadline_ok(artifact, config, monotonic_seconds):
            return LocalPaperStopReason.OPERATOR_OBSERVATION_MISSED.value
        return None

    def _observation_deadline_ok(
        self,
        artifact: LocalPaperEvidenceArtifact,
        config: LocalPaperEvidenceConfig,
        monotonic_seconds: float,
    ) -> bool:
        if monotonic_seconds - artifact.start_monotonic_seconds <= config.observation_interval_seconds():
            return True
        if not artifact.operator_observations:
            return False
        last = artifact.operator_observations[-1].monotonic_seconds
        return monotonic_seconds - last <= config.observation_interval_seconds()

    def _observations_cover_window(
        self,
        artifact: LocalPaperEvidenceArtifact,
        config: LocalPaperEvidenceConfig,
        monotonic_seconds: float,
    ) -> bool:
        points = [artifact.start_monotonic_seconds, *[item.monotonic_seconds for item in artifact.operator_observations], monotonic_seconds]
        return all((right - left) <= config.observation_interval_seconds() for left, right in zip(points, points[1:]))

    def _finish(
        self,
        artifact: LocalPaperEvidenceArtifact,
        config: LocalPaperEvidenceConfig,
        wall_timestamp: str,
        monotonic_seconds: float,
        stop_reason: str,
        *,
        complete: bool,
    ) -> LocalPaperEvidenceArtifact:
        status = LocalPaperEvidenceStatus.COMPLETE.value if complete else LocalPaperEvidenceStatus.FAILED.value
        return replace(
            artifact,
            end_timestamp=wall_timestamp,
            end_monotonic_seconds=monotonic_seconds,
            elapsed_seconds=self._elapsed(artifact, monotonic_seconds),
            status=status,
            stop_reason=self._public_reason(stop_reason),
            evidence_complete=complete,
            heartbeat=replace(
                artifact.heartbeat,
                max_allowed_gap_seconds=config.max_heartbeat_gap_seconds(),
                liveness_status="PASS" if complete else "FAIL",
            ),
        )

    def _failed_artifact(
        self,
        *,
        run_id: str,
        commit_sha: str,
        config: LocalPaperEvidenceConfig,
        wall_timestamp: str,
        monotonic_seconds: float,
        stop_reason: str,
    ) -> LocalPaperEvidenceArtifact:
        return LocalPaperEvidenceArtifact(
            schema_version=config.artifact_schema_version,
            run_id=self._sanitize_code(run_id) or "INVALID_RUN_ID",
            commit_sha=self._safe_commit(commit_sha),
            config_reference=config.config_reference,
            config_schema_version=config.schema_version,
            runtime_mode=config.runtime_mode,
            symbol=config.symbol,
            environment_classification=config.environment_classification,
            production_disabled=config.production_disabled,
            start_timestamp=wall_timestamp,
            end_timestamp=wall_timestamp,
            start_monotonic_seconds=monotonic_seconds,
            end_monotonic_seconds=monotonic_seconds,
            elapsed_seconds=0.0,
            minimum_elapsed_seconds=config.minimum_elapsed_seconds(),
            continuity_state="FAILED_SAFE",
            status=LocalPaperEvidenceStatus.FAILED.value,
            stop_reason=self._public_reason(stop_reason),
            sanitization_status=SANITIZED_OK,
            evidence_complete=False,
            heartbeat=LocalPaperHeartbeatEvidence(max_allowed_gap_seconds=config.max_heartbeat_gap_seconds(), liveness_status="FAIL"),
        )

    def _elapsed(self, artifact: LocalPaperEvidenceArtifact, monotonic_seconds: float) -> float:
        return max(0.0, monotonic_seconds - artifact.start_monotonic_seconds)

    def _artifact_relative_monotonic(self, artifact: LocalPaperEvidenceArtifact, wall_timestamp: str) -> float:
        start = self._parse_wall_timestamp(artifact.start_timestamp)
        current = self._parse_wall_timestamp(wall_timestamp)
        elapsed = (current - start).total_seconds()
        return artifact.start_monotonic_seconds + max(0.0, elapsed)

    def _parse_wall_timestamp(self, value: str | None) -> datetime:
        if not value:
            raise ValueError("missing timestamp")
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return parsed.astimezone(UTC)

    def _sanitize_code(self, value: str) -> str:
        candidate = value.strip()
        if len(candidate) > 128 or SENSITIVE_RE.search(candidate):
            return ""
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", candidate):
            return ""
        return candidate

    def _safe_commit(self, value: str) -> str:
        candidate = value.strip()
        if re.fullmatch(r"[0-9a-fA-F]{7,64}", candidate):
            return candidate
        return "UNKNOWN"

    def _public_reason(self, reason: str) -> str:
        reason_value = reason.strip().upper()
        allowed = {item.value for item in LocalPaperStopReason}
        return reason_value if reason_value in allowed else LocalPaperStopReason.SAFETY_BOUNDARY_VIOLATION.value

    def _update_allowed(
        self,
        artifact: LocalPaperEvidenceArtifact,
        *,
        run_id: str,
        config: LocalPaperEvidenceConfig,
    ) -> bool:
        return (
            artifact.run_id == run_id
            and artifact.schema_version == config.artifact_schema_version
            and artifact.config_schema_version == config.schema_version
            and artifact.status == LocalPaperEvidenceStatus.RUNNING.value
            and artifact.runtime_mode == config.runtime_mode
            and artifact.symbol == config.symbol
            and artifact.production_disabled == config.production_disabled
            and artifact.config_reference == config.config_reference
        )

    @contextmanager
    def _artifact_lock(self, path: Path) -> Iterator[None]:
        lock_path = path.with_name(f"{path.name}.lock")
        handle = lock_path.open("x", encoding="utf-8")
        try:
            handle.write("LOCKED")
            handle.close()
            yield
        finally:
            if not handle.closed:
                handle.close()
            try:
                lock_path.unlink()
            except OSError:
                pass

    def _resolve(self, path_text: str | Path) -> Path:
        path = Path(path_text)
        return path if path.is_absolute() else self.repo_root / path

    def _relative_reference(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.repo_root)).replace("\\", "/")
        except ValueError:
            return path.name

    def _safe_artifact_path(self, path: Path) -> bool:
        try:
            relative = path.relative_to(self.repo_root) if path.is_absolute() else path
        except ValueError:
            return False
        parts = relative.parts
        return len(parts) >= 2 and parts[0] == "reports" and parts[1] == "local_paper_evidence" and ".." not in parts


class _SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def wall_timestamp(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
