from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
import logging
import math
import re
from typing import Any

LOGGER_NAME = "ict_tradingbot.observability"

REDACTED = "[REDACTED]"
EXCEPTION = "[EXCEPTION]"
UNSUPPORTED = "[UNSUPPORTED]"

ALLOWED_SEVERITIES = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,79}$")

_SENSITIVE_NORMALIZED_MARKERS = (
    "apikey",
    "apisecret",
    "xmbxapikey",
    "secret",
    "signature",
    "authorization",
    "password",
    "headers",
    "signedurl",
    "databaseurl",
    "connectionstring",
    "postgresql",
    "mysql",
    "sqlite",
    "traceback",
    "rawresponse",
    "rawexchangeresponse",
    "exchangeresponse",
    "metadatajson",
    "credentiallength",
    "selectfrom",
    "sql",
)


def build_structured_record(
    *,
    timestamp: datetime,
    severity: str,
    event_name: str,
    category: str,
    request_fingerprint: str | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "timestamp": _format_timestamp(timestamp),
        "severity": _validate_severity(severity),
        "event_name": _validate_name(event_name, "event_name"),
        "category": _validate_name(category, "category"),
        "request_fingerprint": _sanitize_request_fingerprint(request_fingerprint),
        "context": _sanitize_mapping({} if context is None else context),
    }


def structured_record_to_json(record: Mapping[str, Any]) -> str:
    return json.dumps(dict(record), sort_keys=True, separators=(",", ":"))


def emit_structured_record(record: Mapping[str, Any]) -> None:
    severity = record.get("severity")
    if severity not in ALLOWED_SEVERITIES:
        raise ValueError("severity is invalid")
    sanitized = dict(record)
    logging.getLogger(LOGGER_NAME).log(logging.getLevelName(severity), structured_record_to_json(sanitized))


def _format_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise ValueError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must be UTC")
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_severity(value: str) -> str:
    if not isinstance(value, str) or value not in ALLOWED_SEVERITIES:
        raise ValueError("severity is invalid")
    return value


def _validate_name(value: str, field: str) -> str:
    if not isinstance(value, str) or NAME_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} is invalid")
    return value


def _sanitize_request_fingerprint(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise ValueError("request_fingerprint is invalid")
    sanitized = _sanitize_string(value)
    if sanitized == REDACTED:
        raise ValueError("request_fingerprint is invalid")
    return sanitized


def _sanitize_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("context must be a mapping")
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError("mapping keys must be strings")
        sanitized[key] = REDACTED if _is_sensitive_text(key) else _sanitize_value(item)
    return sanitized


def _sanitize_sequence(value: Sequence[Any]) -> list[Any]:
    return [_sanitize_value(item) for item in value]


def _sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else UNSUPPORTED
    if isinstance(value, str):
        return _sanitize_string(value)
    if isinstance(value, BaseException):
        return EXCEPTION
    if isinstance(value, Mapping):
        return _sanitize_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return _sanitize_sequence(value)
    return UNSUPPORTED


def _sanitize_string(value: str) -> str:
    if _has_control_character(value) or _is_sensitive_text(value):
        return REDACTED
    return value


def _has_control_character(value: str) -> bool:
    return any(character == "\n" or character == "\t" or ord(character) < 32 or ord(character) == 127 for character in value)


def _is_sensitive_text(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "", value.casefold())
    if any(marker in normalized for marker in _SENSITIVE_NORMALIZED_MARKERS):
        return True
    return "http" in normalized and ("signed" in normalized or "signature" in normalized or "auth" in normalized or "apikey" in normalized)
