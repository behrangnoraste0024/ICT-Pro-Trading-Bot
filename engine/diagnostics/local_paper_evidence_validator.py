from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.diagnostics.local_paper_evidence_harness import LocalPaperEvidenceHarness
from models.local_paper_evidence import LocalPaperEvidenceConfig
from reporting.local_paper_evidence_report import SENSITIVE_RE


PASS = "PASS"
FAIL = "FAIL"

SAFE_CODE_RE = re.compile(r"[A-Za-z0-9_.:-]+")
ACCEPTED_STOP_REASONS = {"THRESHOLD_REACHED", "OPERATOR_STOP_AFTER_THRESHOLD"}
REQUIRED_TOP_LEVEL_FIELDS = {
    "schema_version",
    "run_id",
    "commit_sha",
    "config_reference",
    "config_schema_version",
    "runtime_mode",
    "symbol",
    "environment_classification",
    "production_disabled",
    "start_timestamp",
    "end_timestamp",
    "start_monotonic_seconds",
    "end_monotonic_seconds",
    "elapsed_seconds",
    "minimum_elapsed_seconds",
    "continuity_state",
    "status",
    "stop_reason",
    "sanitization_status",
    "evidence_complete",
    "heartbeat",
    "counters",
    "operator_observations",
    "interruptions",
}
ZERO_COUNTER_FIELDS = {
    "external_transport_count",
    "credential_access_count",
    "persistence_write_count",
    "simulated_order_intent_count",
    "simulated_fill_count",
    "market_sample_event_count",
}


@dataclass(frozen=True)
class LocalPaperEvidenceValidationResult:
    status: str
    reason_codes: tuple[str, ...]
    artifact_path: str
    run_id: str | None = None
    evidence_complete: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "artifact_path": self.artifact_path,
            "run_id": self.run_id,
            "evidence_complete": self.evidence_complete,
        }


class LocalPaperEvidenceArtifactValidator:
    def __init__(self, repo_root: str | Path | None = None) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.harness = LocalPaperEvidenceHarness(repo_root=self.repo_root)

    def validate(
        self,
        artifact_path: str | Path,
        *,
        config_path: str | Path = "configs/local_paper_evidence_harness.json",
    ) -> LocalPaperEvidenceValidationResult:
        path = self._resolve(artifact_path)
        reasons: list[str] = []
        before = b""
        payload: dict[str, Any] | None = None
        config: LocalPaperEvidenceConfig | None = None

        if not self._safe_artifact_path(path):
            reasons.append("ARTIFACT_PATH_OUTSIDE_AUTHORIZED_NAMESPACE")
        if not path.exists():
            return self._result(path, None, None, ["ARTIFACT_MISSING", *reasons])

        try:
            before = path.read_bytes()
        except OSError:
            return self._result(path, None, None, ["ARTIFACT_UNREADABLE", *reasons])

        try:
            decoded = before.decode("utf-8")
            loaded = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._append_mutation_check(path, before, reasons)
            return self._result(path, None, None, ["MALFORMED_JSON", *reasons])

        if not isinstance(loaded, dict):
            reasons.append("ARTIFACT_ROOT_NOT_OBJECT")
        else:
            payload = loaded

        try:
            config = self.harness.load_config(config_path)
        except (OSError, ValueError, json.JSONDecodeError):
            reasons.append("CONFIG_UNREADABLE")

        if payload is not None and config is not None:
            reasons.extend(self._validate_payload(path, payload, config))

        self._append_mutation_check(path, before, reasons)
        clean_reasons = tuple(dict.fromkeys(reasons))
        return self._result(
            path,
            self._safe_optional_string(payload, "run_id") if payload else None,
            payload.get("evidence_complete") if payload else None,
            clean_reasons,
        )

    def _validate_payload(self, path: Path, payload: dict[str, Any], config: LocalPaperEvidenceConfig) -> list[str]:
        reasons: list[str] = []
        missing = sorted(REQUIRED_TOP_LEVEL_FIELDS.difference(payload))
        if missing:
            reasons.append("REQUIRED_FIELDS_MISSING")
            return reasons

        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not run_id or len(run_id) > 128 or not SAFE_CODE_RE.fullmatch(run_id) or SENSITIVE_RE.search(run_id):
            reasons.append("RUN_ID_INVALID")
        elif path.stem != run_id:
            reasons.append("RUN_ID_ARTIFACT_MISMATCH")

        if payload.get("schema_version") != config.artifact_schema_version:
            reasons.append("SCHEMA_VERSION_MISMATCH")
        if payload.get("config_schema_version") != config.schema_version:
            reasons.append("CONFIG_SCHEMA_VERSION_MISMATCH")
        if payload.get("runtime_mode") != "local_paper_evidence":
            reasons.append("RUNTIME_MODE_INVALID")
        if payload.get("symbol") != "BTCUSDT":
            reasons.append("SYMBOL_INVALID")
        if payload.get("production_disabled") is not True:
            reasons.append("PRODUCTION_DISABLED_INVALID")
        if payload.get("status") != "COMPLETE":
            reasons.append("STATUS_NOT_COMPLETE")
        if payload.get("stop_reason") not in ACCEPTED_STOP_REASONS:
            reasons.append("STOP_REASON_INVALID")
        if payload.get("sanitization_status") != "SANITIZED":
            reasons.append("SANITIZATION_STATUS_INVALID")
        if payload.get("evidence_complete") is not True:
            reasons.append("EVIDENCE_INCOMPLETE")
        if payload.get("continuity_state") != "CONTINUOUS":
            reasons.append("CONTINUITY_INVALID")

        start = payload.get("start_monotonic_seconds")
        end = payload.get("end_monotonic_seconds")
        elapsed = payload.get("elapsed_seconds")
        minimum = payload.get("minimum_elapsed_seconds")
        if not self._number(start) or not self._number(end) or not self._number(elapsed) or not self._number(minimum):
            reasons.append("TIMING_FIELDS_INVALID")
        else:
            if end < start:
                reasons.append("MONOTONIC_TIMING_INVALID")
            if abs((end - start) - elapsed) > 0.001:
                reasons.append("ELAPSED_MISMATCH")
            if minimum != config.minimum_elapsed_seconds() or elapsed < config.minimum_elapsed_seconds():
                reasons.append("THRESHOLD_NOT_MET")

        interruptions = payload.get("interruptions")
        if not isinstance(interruptions, list) or interruptions:
            reasons.append("INTERRUPTION_PRESENT")

        reasons.extend(self._validate_heartbeat(payload.get("heartbeat"), config))
        reasons.extend(self._validate_observations(payload.get("operator_observations"), config, start, end))
        reasons.extend(self._validate_counters(payload.get("counters")))

        rendered = json.dumps(payload, sort_keys=True)
        if SENSITIVE_RE.search(rendered):
            reasons.append("SANITIZATION_UNSAFE")
        return reasons

    def _validate_heartbeat(self, heartbeat: Any, config: LocalPaperEvidenceConfig) -> list[str]:
        if not isinstance(heartbeat, dict):
            return ["HEARTBEAT_INVALID"]
        reasons: list[str] = []
        if heartbeat.get("liveness_status") != "PASS":
            reasons.append("LIVENESS_INVALID")
        if heartbeat.get("max_allowed_gap_seconds") != config.max_heartbeat_gap_seconds():
            reasons.append("HEARTBEAT_GAP_CONTRACT_INVALID")
        if not self._number(heartbeat.get("last_heartbeat_monotonic_seconds")):
            reasons.append("HEARTBEAT_TIMESTAMP_INVALID")
        return reasons

    def _validate_observations(self, observations: Any, config: LocalPaperEvidenceConfig, start: Any, end: Any) -> list[str]:
        if not isinstance(observations, list):
            return ["OBSERVATIONS_INVALID"]
        if not self._number(start) or not self._number(end):
            return ["OBSERVATION_TIMING_UNCHECKABLE"]
        points = [start]
        for item in observations:
            if not isinstance(item, dict):
                return ["OBSERVATIONS_INVALID"]
            code = item.get("observation_code")
            seconds = item.get("monotonic_seconds")
            if not isinstance(code, str) or not code or not SAFE_CODE_RE.fullmatch(code) or SENSITIVE_RE.search(code):
                return ["OBSERVATION_CODE_INVALID"]
            if not self._number(seconds):
                return ["OBSERVATION_TIMING_INVALID"]
            points.append(seconds)
        points.append(end)
        if any(right < left for left, right in zip(points, points[1:])):
            return ["OBSERVATION_TIMING_INVALID"]
        if any(right - left > config.observation_interval_seconds() for left, right in zip(points, points[1:])):
            return ["OBSERVATION_COVERAGE_GAP"]
        return []

    def _validate_counters(self, counters: Any) -> list[str]:
        if not isinstance(counters, dict):
            return ["COUNTERS_INVALID"]
        for field in ZERO_COUNTER_FIELDS:
            if counters.get(field) != 0:
                return ["COUNTERS_NONZERO"]
        return []

    def _append_mutation_check(self, path: Path, before: bytes, reasons: list[str]) -> None:
        try:
            after = path.read_bytes()
        except OSError:
            reasons.append("ARTIFACT_UNREADABLE_AFTER_VALIDATION")
            return
        if after != before:
            reasons.append("ARTIFACT_MUTATED_BY_VALIDATION")

    def _result(
        self,
        path: Path,
        run_id: str | None,
        evidence_complete: bool | None,
        reasons: list[str] | tuple[str, ...],
    ) -> LocalPaperEvidenceValidationResult:
        reason_tuple = tuple(dict.fromkeys(reasons))
        return LocalPaperEvidenceValidationResult(
            status=PASS if not reason_tuple else FAIL,
            reason_codes=reason_tuple,
            artifact_path=str(path),
            run_id=run_id,
            evidence_complete=evidence_complete,
        )

    def _safe_optional_string(self, payload: dict[str, Any], key: str) -> str | None:
        value = payload.get(key)
        return value if isinstance(value, str) and not SENSITIVE_RE.search(value) else None

    def _number(self, value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _resolve(self, path_text: str | Path) -> Path:
        path = Path(path_text)
        return path if path.is_absolute() else self.repo_root / path

    def _safe_artifact_path(self, path: Path) -> bool:
        try:
            relative = path.relative_to(self.repo_root) if path.is_absolute() else path
        except ValueError:
            return False
        parts = relative.parts
        return len(parts) >= 2 and parts[0] == "reports" and parts[1] == "local_paper_evidence" and ".." not in parts
