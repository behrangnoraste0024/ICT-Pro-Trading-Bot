from __future__ import annotations

from datetime import UTC, datetime, timezone, timedelta
import json
import logging
import os
import socket
import sqlite3

import pytest

from infrastructure.observability.structured_logging import (
    LOGGER_NAME,
    build_structured_record,
    emit_structured_record,
    structured_record_to_json,
)


UTC_TIME = datetime(2026, 8, 16, 0, 0, 0, 123456, tzinfo=UTC)
EXPECTED_KEYS = {"timestamp", "severity", "event_name", "category", "request_fingerprint", "context"}


def _record(**overrides):
    payload = {
        "timestamp": UTC_TIME,
        "severity": "INFO",
        "event_name": "permit_denied",
        "category": "safety",
        "request_fingerprint": None,
        "context": {},
    }
    payload.update(overrides)
    return build_structured_record(**payload)


@pytest.mark.parametrize("severity", ["DEBUG", "INFO", "WARNING", "ERROR"])
def test_records_accept_all_required_severities(severity: str) -> None:
    record = _record(severity=severity)

    assert record["severity"] == severity


def test_record_has_exact_schema_and_utc_timestamp_format() -> None:
    record = _record()

    assert set(record) == EXPECTED_KEYS
    assert record["timestamp"] == "2026-08-16T00:00:00Z"


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError):
        _record(timestamp=datetime(2026, 8, 16, 0, 0, 0))


def test_non_utc_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError):
        _record(timestamp=datetime(2026, 8, 16, 0, 0, 0, tzinfo=timezone(timedelta(hours=1))))


def test_invalid_severity_is_rejected() -> None:
    with pytest.raises(ValueError):
        _record(severity="WARN")


def test_valid_event_name_and_category_are_accepted() -> None:
    record = _record(event_name="api_status_1", category="live_ops")

    assert record["event_name"] == "api_status_1"
    assert record["category"] == "live_ops"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_name", "Event"),
        ("event_name", "1event"),
        ("event_name", "event-name"),
        ("event_name", "a" * 81),
        ("category", "Category"),
        ("category", "1category"),
        ("category", "category-name"),
        ("category", "a" * 81),
    ],
)
def test_invalid_event_name_or_category_is_rejected(field: str, value: str) -> None:
    with pytest.raises(ValueError):
        _record(**{field: value})


def test_request_fingerprint_accepts_safe_text() -> None:
    record = _record(request_fingerprint="abc_123.fingerprint-xyz")

    assert record["request_fingerprint"] == "abc_123.fingerprint-xyz"


@pytest.mark.parametrize("value", ["", "a" * 129, "signature=abc", "line\nbreak"])
def test_invalid_or_oversized_request_fingerprint_is_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        _record(request_fingerprint=value)


def test_empty_and_ordinary_safe_contexts_are_supported() -> None:
    assert _record()["context"] == {}
    assert _record(context={"ok": True, "count": 3, "ratio": 1.5, "note": "safe"})["context"] == {
        "ok": True,
        "count": 3,
        "ratio": 1.5,
        "note": "safe",
    }


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("api_key", "abc123"),
        ("api_secret", "secret123"),
        ("signature", "deadbeef"),
        ("url", "https://example.test/path?signature=deadbeef"),
        ("Authorization", "Bearer abc123"),
        ("X-MBX-APIKEY", "abc123"),
        ("database_url", "postgresql://user:password@host/db"),
        ("query", "SELECT * FROM accounts"),
        ("error", "Traceback (most recent call last)"),
        ("rawResponse", '{"secret":"value"}'),
    ],
)
def test_sensitive_values_are_redacted_without_raw_fragments(key: str, value: str) -> None:
    record = _record(context={key: value})

    text = json.dumps(record)
    assert record["context"][key] == "[REDACTED]"
    assert value not in text


def test_exception_object_becomes_exception_placeholder_without_stringification() -> None:
    record = _record(context={"error": RuntimeError("signature=raw-secret")})

    assert record["context"]["error"] == "[EXCEPTION]"
    assert "raw-secret" not in json.dumps(record)


@pytest.mark.parametrize("value", ["line\nbreak", "tab\tbreak", "bad\u0001value", "bad\u007fvalue"])
def test_control_characters_are_redacted(value: str) -> None:
    record = _record(context={"message": value})

    assert record["context"]["message"] == "[REDACTED]"


def test_nested_mapping_sequence_and_sensitive_nested_key_are_sanitized() -> None:
    original = {"outer": {"safe": "ok", "api_key": "secret"}, "items": ["ok", {"signature": "abc"}]}

    record = _record(context=original)

    assert record["context"] == {
        "outer": {"safe": "ok", "api_key": "[REDACTED]"},
        "items": ["ok", {"signature": "[REDACTED]"}],
    }
    assert original["outer"]["api_key"] == "secret"


def test_unsupported_object_becomes_placeholder() -> None:
    class Unsupported:
        pass

    record = _record(context={"object": Unsupported()})

    assert record["context"]["object"] == "[UNSUPPORTED]"


def test_non_string_mapping_key_raises_value_error() -> None:
    with pytest.raises(ValueError):
        _record(context={1: "bad"})


def test_deterministic_dict_output_does_not_share_mutable_context() -> None:
    context = {"nested": {"value": "safe"}, "items": ["safe"]}

    record = _record(context=context)
    context["nested"]["value"] = "changed"
    context["items"].append("changed")

    assert record["context"] == {"nested": {"value": "safe"}, "items": ["safe"]}


def test_deterministic_json_output_uses_sorted_compact_sanitized_values() -> None:
    record = _record(context={"z": "safe", "api_key": "secret"})

    assert structured_record_to_json(record) == (
        '{"category":"safety","context":{"api_key":"[REDACTED]","z":"safe"},'
        '"event_name":"permit_denied","request_fingerprint":null,"severity":"INFO",'
        '"timestamp":"2026-08-16T00:00:00Z"}'
    )


def test_exact_logger_name_and_safe_stdlib_logging_emission(caplog: pytest.LogCaptureFixture) -> None:
    record = _record(context={"api_key": "secret"})

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        emit_structured_record(record)

    assert LOGGER_NAME == "ict_tradingbot.observability"
    assert caplog.records[0].name == LOGGER_NAME
    assert '"api_key":"[REDACTED]"' in caplog.records[0].message
    assert "secret" not in caplog.records[0].message


def test_zero_authority_no_environment_network_database_or_mutation_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("forbidden authority used")

    monkeypatch.setattr(os.environ, "get", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(sqlite3, "connect", fail)

    record = _record(
        context={
            "permit_consumed": False,
            "order_mutated": False,
            "protective_pair_mutated": False,
            "recovery_mutated": False,
            "kill_switch_mutated": False,
            "execution_authorized": False,
        }
    )

    assert record["context"]["permit_consumed"] is False
    assert record["context"]["order_mutated"] is False
    assert record["context"]["protective_pair_mutated"] is False
    assert record["context"]["recovery_mutated"] is False
    assert record["context"]["kill_switch_mutated"] is False
    assert record["context"]["execution_authorized"] is False
