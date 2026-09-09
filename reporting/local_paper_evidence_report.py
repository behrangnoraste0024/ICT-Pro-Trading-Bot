from __future__ import annotations

import json
import re
from typing import Any

from models.local_paper_evidence import LocalPaperEvidenceArtifact


SENSITIVE_RE = re.compile(
    r"(api[_-]?key|secret|password|token|signature|authorization|bearer|authenticated url|signed url|traceback|select\s+|insert\s+|update\s+|delete\s+|postgresql://|mysql://)",
    re.IGNORECASE,
)


def artifact_to_sanitized_dict(artifact: LocalPaperEvidenceArtifact) -> dict[str, Any]:
    payload = artifact.to_dict()
    rendered = json.dumps(payload, sort_keys=True)
    if SENSITIVE_RE.search(rendered):
        safe_payload = {
            **payload,
            "operator_observations": [],
            "interruptions": [],
            "notes": [],
            "sanitization_status": "SANITIZATION_FAILED",
            "status": "FAILED",
            "stop_reason": "SANITIZATION_FAILURE",
            "evidence_complete": False,
        }
        return safe_payload
    return payload


def artifact_to_json(artifact: LocalPaperEvidenceArtifact) -> str:
    return json.dumps(artifact_to_sanitized_dict(artifact), indent=2, sort_keys=True)


def format_local_paper_evidence_report(artifact: LocalPaperEvidenceArtifact) -> str:
    payload = artifact_to_sanitized_dict(artifact)
    lines = [
        "===== LOCAL PAPER EVIDENCE HARNESS =====",
        f"Run ID             : {payload['run_id']}",
        f"Status             : {payload['status']}",
        f"Evidence Complete  : {payload['evidence_complete']}",
        f"Stop Reason        : {payload['stop_reason'] or 'N/A'}",
        f"Symbol             : {payload['symbol']}",
        f"Production Disabled: {payload['production_disabled']}",
        f"Elapsed Seconds    : {payload['elapsed_seconds']}",
        f"Heartbeat Count    : {payload['counters']['heartbeat_count']}",
        f"Observation Count  : {payload['counters']['operator_observation_count']}",
        f"External Transport : {payload['counters']['external_transport_count']}",
        f"Credential Access  : {payload['counters']['credential_access_count']}",
        "========================================",
    ]
    return "\n".join(lines)
