from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class LocalPaperEvidenceStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    INCOMPLETE = "INCOMPLETE"


class LocalPaperStopReason(StrEnum):
    THRESHOLD_REACHED = "THRESHOLD_REACHED"
    OPERATOR_STOP_AFTER_THRESHOLD = "OPERATOR_STOP_AFTER_THRESHOLD"
    PREMATURE_TERMINATION = "PREMATURE_TERMINATION"
    HEARTBEAT_GAP_EXCEEDED = "HEARTBEAT_GAP_EXCEEDED"
    OPERATOR_OBSERVATION_MISSED = "OPERATOR_OBSERVATION_MISSED"
    SAFETY_BOUNDARY_VIOLATION = "SAFETY_BOUNDARY_VIOLATION"
    UNSUPPORTED_RUNTIME_STATE = "UNSUPPORTED_RUNTIME_STATE"
    SANITIZATION_FAILURE = "SANITIZATION_FAILURE"
    ARTIFACT_WRITE_FAILURE = "ARTIFACT_WRITE_FAILURE"


SUCCESSFUL_STOP_REASONS = {
    LocalPaperStopReason.THRESHOLD_REACHED.value,
    LocalPaperStopReason.OPERATOR_STOP_AFTER_THRESHOLD.value,
}


@dataclass(frozen=True)
class LocalPaperEvidenceConfig:
    schema_version: str = "1.0"
    artifact_schema_version: str = "1.0"
    symbol: str = "BTCUSDT"
    production_disabled: bool = True
    runtime_mode: str = "local_paper_evidence"
    environment_classification: str = "LOCAL_PAPER"
    minimum_elapsed_hours: int = 72
    operator_observation_interval_hours: int = 12
    heartbeat_interval_seconds: int = 30
    liveness_multiplier: int = 2
    network_allowed: bool = False
    credentials_allowed: bool = False
    exchange_transport_allowed: bool = False
    runtime_state_resume_allowed: bool = False
    allowed_successful_stop_reasons: tuple[str, ...] = (
        LocalPaperStopReason.THRESHOLD_REACHED.value,
        LocalPaperStopReason.OPERATOR_STOP_AFTER_THRESHOLD.value,
    )
    config_reference: str = "configs/local_paper_evidence_harness.json"

    def minimum_elapsed_seconds(self) -> int:
        return self.minimum_elapsed_hours * 60 * 60

    def observation_interval_seconds(self) -> int:
        return self.operator_observation_interval_hours * 60 * 60

    def max_heartbeat_gap_seconds(self) -> int:
        return self.heartbeat_interval_seconds * self.liveness_multiplier

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "allowed_successful_stop_reasons": list(self.allowed_successful_stop_reasons)}

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "LocalPaperEvidenceConfig":
        payload = dict(values)
        if "allowed_successful_stop_reasons" in payload:
            payload["allowed_successful_stop_reasons"] = tuple(payload["allowed_successful_stop_reasons"])
        return cls(**{**cls().to_dict(), **payload})


@dataclass(frozen=True)
class LocalPaperEvidenceCounters:
    heartbeat_count: int = 0
    operator_observation_count: int = 0
    interruption_count: int = 0
    loop_cycle_count: int = 0
    market_sample_event_count: int = 0
    advisory_signal_count: int = 0
    simulated_order_intent_count: int = 0
    simulated_fill_count: int = 0
    rejected_action_count: int = 0
    safety_denial_count: int = 0
    external_transport_count: int = 0
    credential_access_count: int = 0
    persistence_write_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "LocalPaperEvidenceCounters":
        return cls(**{**cls().to_dict(), **values})


@dataclass(frozen=True)
class LocalPaperHeartbeatEvidence:
    last_heartbeat_timestamp: str | None = None
    last_heartbeat_monotonic_seconds: float | None = None
    max_allowed_gap_seconds: int = 60
    liveness_status: str = "UNKNOWN"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "LocalPaperHeartbeatEvidence":
        return cls(**{**cls().to_dict(), **values})


@dataclass(frozen=True)
class LocalPaperOperatorObservation:
    observed_at: str
    monotonic_seconds: float
    observation_code: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "LocalPaperOperatorObservation":
        return cls(**values)


@dataclass(frozen=True)
class LocalPaperInterruptionEvidence:
    occurred_at: str
    monotonic_seconds: float
    reason_code: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "LocalPaperInterruptionEvidence":
        return cls(**values)


@dataclass(frozen=True)
class LocalPaperEvidenceArtifact:
    schema_version: str
    run_id: str
    commit_sha: str
    config_reference: str
    config_schema_version: str
    runtime_mode: str
    symbol: str
    environment_classification: str
    production_disabled: bool
    start_timestamp: str | None
    end_timestamp: str | None
    start_monotonic_seconds: float
    end_monotonic_seconds: float | None
    elapsed_seconds: float
    minimum_elapsed_seconds: int
    continuity_state: str
    status: str
    stop_reason: str | None
    sanitization_status: str
    evidence_complete: bool
    heartbeat: LocalPaperHeartbeatEvidence
    operator_observations: tuple[LocalPaperOperatorObservation, ...] = field(default_factory=tuple)
    interruptions: tuple[LocalPaperInterruptionEvidence, ...] = field(default_factory=tuple)
    counters: LocalPaperEvidenceCounters = field(default_factory=LocalPaperEvidenceCounters)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "commit_sha": self.commit_sha,
            "config_reference": self.config_reference,
            "config_schema_version": self.config_schema_version,
            "runtime_mode": self.runtime_mode,
            "symbol": self.symbol,
            "environment_classification": self.environment_classification,
            "production_disabled": self.production_disabled,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "start_monotonic_seconds": self.start_monotonic_seconds,
            "end_monotonic_seconds": self.end_monotonic_seconds,
            "elapsed_seconds": self.elapsed_seconds,
            "minimum_elapsed_seconds": self.minimum_elapsed_seconds,
            "continuity_state": self.continuity_state,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "sanitization_status": self.sanitization_status,
            "evidence_complete": self.evidence_complete,
            "heartbeat": self.heartbeat.to_dict(),
            "operator_observations": [observation.to_dict() for observation in self.operator_observations],
            "interruptions": [interruption.to_dict() for interruption in self.interruptions],
            "counters": self.counters.to_dict(),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "LocalPaperEvidenceArtifact":
        payload = dict(values)
        payload["heartbeat"] = LocalPaperHeartbeatEvidence.from_dict(payload.get("heartbeat", {}))
        payload["operator_observations"] = tuple(
            LocalPaperOperatorObservation.from_dict(item) for item in payload.get("operator_observations", [])
        )
        payload["interruptions"] = tuple(
            LocalPaperInterruptionEvidence.from_dict(item) for item in payload.get("interruptions", [])
        )
        payload["counters"] = LocalPaperEvidenceCounters.from_dict(payload.get("counters", {}))
        payload["notes"] = tuple(payload.get("notes", ()))
        return cls(**payload)
