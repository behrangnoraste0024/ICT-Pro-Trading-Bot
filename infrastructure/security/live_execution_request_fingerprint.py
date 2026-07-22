from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Callable

from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit import PERMIT_ENVIRONMENT, PERMIT_SYMBOL, validate_canonical_text

FINGERPRINT_SCHEMA_VERSION = "1.0"
SENSITIVE_KEYS = {
    "apikey",
    "apisecret",
    "signature",
    "signedurl",
    "authorization",
    "headers",
    "requestheaders",
    "responseheaders",
    "authenticatedheaders",
    "rawrequest",
    "rawresponse",
    "rawexchangeresponse",
    "exchangeresponse",
    "metadata",
    "recvwindow",
    "timestamp",
    "xmbxapikey",
}
DECIMAL_PATTERN = re.compile(r"^(-?0|[1-9][0-9]*)(\.[0-9]+)?$")


class RequestFingerprintError(ValueError):
    def __init__(self, code: str = "PERMIT_INVALID") -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class LiveExecutionRequestFingerprint:
    operation: LiveExecutionOperation
    environment: str
    symbol: str
    subject_type: str
    subject_id: str
    request_fingerprint: str
    canonical_payload: dict[str, Any]


def _sanitize_key(key: str) -> str:
    return "".join(ch for ch in key.casefold() if ch.isalnum())


def _reject_sensitive_key(key: str) -> None:
    normalized = _sanitize_key(key)
    if normalized in SENSITIVE_KEYS or "secret" in normalized or "signature" in normalized:
        raise RequestFingerprintError()
    if "api" in normalized and "key" in normalized:
        raise RequestFingerprintError()
    if "signed" in normalized and "url" in normalized:
        raise RequestFingerprintError()
    if "raw" in normalized and ("request" in normalized or "response" in normalized):
        raise RequestFingerprintError()
    if "header" in normalized or "credential" in normalized:
        raise RequestFingerprintError()


def _require_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RequestFingerprintError()
    for key in payload:
        if not isinstance(key, str):
            raise RequestFingerprintError()
        _reject_sensitive_key(key)
    return payload


def _require_exact_keys(payload: dict[str, Any], keys: set[str]) -> None:
    if set(payload) != keys:
        raise RequestFingerprintError()


def _require_str(payload: dict[str, Any], key: str, allowed: set[str] | None = None, max_length: int = 128) -> str:
    value = payload[key]
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise RequestFingerprintError()
    if allowed is not None:
        if value not in allowed:
            raise RequestFingerprintError()
        return value
    try:
        return validate_canonical_text(value, max_length=max_length)
    except Exception as exc:
        raise RequestFingerprintError() from exc


def _require_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload[key]
    if not isinstance(value, bool):
        raise RequestFingerprintError()
    return value


def _require_bool_or_null(payload: dict[str, Any], key: str) -> bool | None:
    value = payload[key]
    if value is None or isinstance(value, bool):
        return value
    raise RequestFingerprintError()


def _require_decimal_or_null(payload: dict[str, Any], key: str) -> str | None:
    value = payload[key]
    if value is None:
        return None
    return _require_decimal(payload, key)


def _require_decimal(payload: dict[str, Any], key: str) -> str:
    value = payload[key]
    if isinstance(value, bool) or isinstance(value, (float, int)) or value is None:
        raise RequestFingerprintError()
    if isinstance(value, Decimal):
        decimal = value
    elif isinstance(value, str):
        if not DECIMAL_PATTERN.fullmatch(value):
            raise RequestFingerprintError()
        try:
            decimal = Decimal(value)
        except InvalidOperation as exc:
            raise RequestFingerprintError() from exc
    else:
        raise RequestFingerprintError()
    if not decimal.is_finite() or decimal < Decimal("0"):
        raise RequestFingerprintError()
    if decimal == 0:
        return "0"
    return format(decimal.normalize(), "f")


def _require_positive_decimal(payload: dict[str, Any], key: str) -> str:
    canonical = _require_decimal(payload, key)
    if Decimal(canonical) <= Decimal("0"):
        raise RequestFingerprintError()
    return canonical


def _operation(payload: dict[str, Any]) -> LiveExecutionOperation:
    value = payload.get("operation")
    if not isinstance(value, str):
        raise RequestFingerprintError()
    try:
        return LiveExecutionOperation(value)
    except ValueError as exc:
        raise RequestFingerprintError() from exc


def _common(payload: dict[str, Any], expected: LiveExecutionOperation) -> LiveExecutionOperation:
    operation = _operation(payload)
    if operation != expected:
        raise RequestFingerprintError()
    _require_str(payload, "schema_version", {FINGERPRINT_SCHEMA_VERSION})
    _require_str(payload, "environment", {PERMIT_ENVIRONMENT})
    _require_str(payload, "symbol", {PERMIT_SYMBOL})
    return operation


def _canonical_hash(canonical_payload: dict[str, Any]) -> str:
    canonical_bytes = json.dumps(
        canonical_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def _result(
    operation: LiveExecutionOperation,
    subject_type: str,
    subject_id: str,
    canonical_payload: dict[str, Any],
) -> LiveExecutionRequestFingerprint:
    return LiveExecutionRequestFingerprint(
        operation=operation,
        environment=PERMIT_ENVIRONMENT,
        symbol=PERMIT_SYMBOL,
        subject_type=subject_type,
        subject_id=subject_id,
        request_fingerprint=_canonical_hash(canonical_payload),
        canonical_payload=dict(canonical_payload),
    )


def build_protective_create_fingerprint(payload: Any) -> LiveExecutionRequestFingerprint:
    payload = _require_payload(payload)
    keys = {
        "schema_version",
        "operation",
        "environment",
        "symbol",
        "pair_id",
        "leg_type",
        "side",
        "position_side",
        "quantity",
        "trigger_price",
        "close_position",
        "reduce_only",
        "client_algo_id",
        "order_type",
        "working_type",
        "price_protect",
    }
    _require_exact_keys(payload, keys)
    operation = _common(payload, LiveExecutionOperation.PROTECTIVE_CREATE)
    pair_id = _require_str(payload, "pair_id", max_length=80)
    leg_type = _require_str(payload, "leg_type", {"STOP", "TAKE_PROFIT"})
    client_algo_id = _require_str(payload, "client_algo_id", max_length=80)
    canonical_payload = {
        "schema_version": FINGERPRINT_SCHEMA_VERSION,
        "operation": operation.value,
        "environment": PERMIT_ENVIRONMENT,
        "symbol": PERMIT_SYMBOL,
        "pair_id": pair_id,
        "leg_type": leg_type,
        "side": _require_str(payload, "side", {"BUY", "SELL"}),
        "position_side": _require_str(payload, "position_side", {"BOTH", "LONG", "SHORT"}),
        "quantity": _require_positive_decimal(payload, "quantity"),
        "trigger_price": _require_positive_decimal(payload, "trigger_price"),
        "close_position": _require_bool(payload, "close_position"),
        "reduce_only": _require_bool_or_null(payload, "reduce_only"),
        "client_algo_id": client_algo_id,
        "order_type": _require_str(payload, "order_type", {"STOP_MARKET", "TAKE_PROFIT_MARKET"}),
        "working_type": _require_str(payload, "working_type", {"MARK_PRICE", "CONTRACT_PRICE"}),
        "price_protect": _require_bool(payload, "price_protect"),
    }
    return _result(operation, "PROTECTIVE_LEG", f"{pair_id}:{leg_type}:{client_algo_id}", canonical_payload)


def build_protective_cancel_fingerprint(payload: Any) -> LiveExecutionRequestFingerprint:
    payload = _require_payload(payload)
    keys = {"schema_version", "operation", "environment", "symbol", "pair_id", "leg_type", "client_algo_id"}
    _require_exact_keys(payload, keys)
    operation = _common(payload, LiveExecutionOperation.PROTECTIVE_CANCEL)
    pair_id = _require_str(payload, "pair_id", max_length=80)
    leg_type = _require_str(payload, "leg_type", {"STOP", "TAKE_PROFIT"})
    client_algo_id = _require_str(payload, "client_algo_id", max_length=80)
    canonical_payload = {
        "schema_version": FINGERPRINT_SCHEMA_VERSION,
        "operation": operation.value,
        "environment": PERMIT_ENVIRONMENT,
        "symbol": PERMIT_SYMBOL,
        "pair_id": pair_id,
        "leg_type": leg_type,
        "client_algo_id": client_algo_id,
    }
    return _result(operation, "PROTECTIVE_LEG", f"{pair_id}:{leg_type}:{client_algo_id}", canonical_payload)


def build_order_lifecycle_create_fingerprint(payload: Any) -> LiveExecutionRequestFingerprint:
    payload = _require_payload(payload)
    keys = {
        "schema_version",
        "operation",
        "environment",
        "symbol",
        "client_order_id",
        "side",
        "position_side",
        "order_type",
        "quantity",
        "price",
        "time_in_force",
        "reduce_only",
    }
    _require_exact_keys(payload, keys)
    operation = _common(payload, LiveExecutionOperation.ORDER_LIFECYCLE_CREATE)
    client_order_id = _require_str(payload, "client_order_id", max_length=80)
    canonical_payload = {
        "schema_version": FINGERPRINT_SCHEMA_VERSION,
        "operation": operation.value,
        "environment": PERMIT_ENVIRONMENT,
        "symbol": PERMIT_SYMBOL,
        "client_order_id": client_order_id,
        "side": _require_str(payload, "side", {"BUY", "SELL"}),
        "position_side": _require_str(payload, "position_side", {"BOTH", "LONG", "SHORT"}),
        "order_type": _require_str(payload, "order_type", {"LIMIT"}),
        "quantity": _require_positive_decimal(payload, "quantity"),
        "price": _require_positive_decimal(payload, "price"),
        "time_in_force": _require_str(payload, "time_in_force", {"GTX", "GTC"}),
        "reduce_only": _require_bool(payload, "reduce_only"),
    }
    return _result(operation, "CLIENT_ORDER", client_order_id, canonical_payload)


def build_order_lifecycle_cancel_fingerprint(payload: Any) -> LiveExecutionRequestFingerprint:
    payload = _require_payload(payload)
    keys = {"schema_version", "operation", "environment", "symbol", "client_order_id"}
    _require_exact_keys(payload, keys)
    operation = _common(payload, LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL)
    client_order_id = _require_str(payload, "client_order_id", max_length=80)
    canonical_payload = {
        "schema_version": FINGERPRINT_SCHEMA_VERSION,
        "operation": operation.value,
        "environment": PERMIT_ENVIRONMENT,
        "symbol": PERMIT_SYMBOL,
        "client_order_id": client_order_id,
    }
    return _result(operation, "CLIENT_ORDER", client_order_id, canonical_payload)


def build_signed_order_test_create_fingerprint(payload: Any) -> LiveExecutionRequestFingerprint:
    payload = _require_payload(payload)
    keys = {
        "schema_version",
        "operation",
        "environment",
        "symbol",
        "client_order_id",
        "side",
        "position_side",
        "order_type",
        "quantity",
        "price",
        "time_in_force",
        "reduce_only",
    }
    _require_exact_keys(payload, keys)
    operation = _common(payload, LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE)
    client_order_id = _require_str(payload, "client_order_id", max_length=80)
    order_type = _require_str(payload, "order_type", {"LIMIT", "MARKET"})
    time_in_force = payload["time_in_force"]
    if order_type == "MARKET":
        price = payload["price"]
        if price is not None or time_in_force is not None:
            raise RequestFingerprintError()
        canonical_time_in_force = None
    else:
        canonical_time_in_force = _require_str(payload, "time_in_force", {"GTX", "GTC"})
        price = _require_positive_decimal(payload, "price")
    canonical_payload = {
        "schema_version": FINGERPRINT_SCHEMA_VERSION,
        "operation": operation.value,
        "environment": PERMIT_ENVIRONMENT,
        "symbol": PERMIT_SYMBOL,
        "client_order_id": client_order_id,
        "side": _require_str(payload, "side", {"BUY", "SELL"}),
        "position_side": _require_str(payload, "position_side", {"BOTH", "LONG", "SHORT"}),
        "order_type": order_type,
        "quantity": _require_positive_decimal(payload, "quantity"),
        "price": price,
        "time_in_force": canonical_time_in_force,
        "reduce_only": _require_bool(payload, "reduce_only"),
    }
    return _result(operation, "CLIENT_ORDER", client_order_id, canonical_payload)


_BUILDERS: dict[LiveExecutionOperation, Callable[[Any], LiveExecutionRequestFingerprint]] = {
    LiveExecutionOperation.PROTECTIVE_CREATE: build_protective_create_fingerprint,
    LiveExecutionOperation.PROTECTIVE_CANCEL: build_protective_cancel_fingerprint,
    LiveExecutionOperation.ORDER_LIFECYCLE_CREATE: build_order_lifecycle_create_fingerprint,
    LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL: build_order_lifecycle_cancel_fingerprint,
    LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE: build_signed_order_test_create_fingerprint,
}


def build_live_execution_request_fingerprint(payload: Any) -> LiveExecutionRequestFingerprint:
    payload = _require_payload(payload)
    operation = _operation(payload)
    builder = _BUILDERS.get(operation)
    if builder is None:
        raise RequestFingerprintError()
    return builder(payload)
