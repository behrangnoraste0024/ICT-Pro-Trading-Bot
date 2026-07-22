from __future__ import annotations

from decimal import Decimal

import pytest

from infrastructure.security.live_execution_request_fingerprint import RequestFingerprintError, _require_decimal, build_live_execution_request_fingerprint

PROTECTIVE_CREATE = {
    "schema_version": "1.0",
    "operation": "PROTECTIVE_CREATE",
    "environment": "TESTNET",
    "symbol": "BTCUSDT",
    "pair_id": "pair-abc",
    "leg_type": "STOP",
    "side": "SELL",
    "position_side": "LONG",
    "quantity": "0.001600",
    "trigger_price": "62000.00",
    "close_position": True,
    "reduce_only": None,
    "client_algo_id": "smcbot-protect-sl-001",
    "order_type": "STOP_MARKET",
    "working_type": "MARK_PRICE",
    "price_protect": True,
}

OPERATION_VECTORS = [
    (PROTECTIVE_CREATE, "55e5fc8c1f1c89c5790886789923fc4ad8d89a4de439309108f76642b1e8cd36", "PROTECTIVE_LEG", "pair-abc:STOP:smcbot-protect-sl-001"),
    ({"schema_version": "1.0", "operation": "PROTECTIVE_CANCEL", "environment": "TESTNET", "symbol": "BTCUSDT", "pair_id": "pair-abc", "leg_type": "STOP", "client_algo_id": "smcbot-protect-sl-001"}, "fff99d430414468b3e4b9e4a108557721407250d13edde61da53a86e1e1783d7", "PROTECTIVE_LEG", "pair-abc:STOP:smcbot-protect-sl-001"),
    ({"schema_version": "1.0", "operation": "ORDER_LIFECYCLE_CREATE", "environment": "TESTNET", "symbol": "BTCUSDT", "client_order_id": "smcbot-limit-001", "side": "BUY", "position_side": "BOTH", "order_type": "LIMIT", "quantity": "0.0020", "price": "63000.00", "time_in_force": "GTX", "reduce_only": False}, "c00b9bc5929cfa40b7a1ef834775938433019524624c7527ae32e44c49898d51", "CLIENT_ORDER", "smcbot-limit-001"),
    ({"schema_version": "1.0", "operation": "ORDER_LIFECYCLE_CANCEL", "environment": "TESTNET", "symbol": "BTCUSDT", "client_order_id": "smcbot-limit-001"}, "d3d8ec2fe1209c13aa7b55e014a5b77a06132266533a0f00cbba084b6b875be3", "CLIENT_ORDER", "smcbot-limit-001"),
    ({"schema_version": "1.0", "operation": "SIGNED_ORDER_TEST_CREATE", "environment": "TESTNET", "symbol": "BTCUSDT", "client_order_id": "smcbot-test-001", "side": "BUY", "position_side": "BOTH", "order_type": "LIMIT", "quantity": "0.0020", "price": "63000.00", "time_in_force": "GTX", "reduce_only": False}, "6fa9268e85cf0759753a838b512bd1233c70dbf2b99e1f5a9d69610a1ee9564e", "CLIENT_ORDER", "smcbot-test-001"),
]


@pytest.mark.parametrize("payload,expected_hash,subject_type,subject_id", OPERATION_VECTORS)
def test_supported_operations_have_fixed_fingerprint_vectors(payload: dict, expected_hash: str, subject_type: str, subject_id: str) -> None:
    result = build_live_execution_request_fingerprint(payload)
    assert result.request_fingerprint == expected_hash
    assert result.subject_type == subject_type
    assert result.subject_id == subject_id
    assert "request_fingerprint" not in result.canonical_payload


@pytest.mark.parametrize("payload,expected_hash,_,__", OPERATION_VECTORS)
def test_fingerprints_are_deterministic_and_key_order_independent(payload: dict, expected_hash: str, _: str, __: str) -> None:
    reordered = dict(reversed(list(payload.items())))
    assert build_live_execution_request_fingerprint(payload).request_fingerprint == expected_hash
    assert build_live_execution_request_fingerprint(reordered).request_fingerprint == expected_hash


def test_decimal_equivalent_inputs_produce_same_canonical_hash_without_scientific_notation() -> None:
    first = dict(PROTECTIVE_CREATE, quantity=Decimal("1"), trigger_price=Decimal("62000.0"))
    second = dict(PROTECTIVE_CREATE, quantity="1.00", trigger_price="62000.00")
    a = build_live_execution_request_fingerprint(first)
    b = build_live_execution_request_fingerprint(second)
    assert a.request_fingerprint == b.request_fingerprint
    assert a.canonical_payload["quantity"] == "1"
    assert a.canonical_payload["trigger_price"] == "62000"
    assert "E" not in a.canonical_payload["quantity"]
    assert "E" not in a.canonical_payload["trigger_price"]


@pytest.mark.parametrize("value", ["-0", "-0.0", "-0.000", Decimal("-0"), Decimal("-0.000")])
def test_negative_zero_decimal_inputs_canonicalize_to_zero(value: object) -> None:
    assert _require_decimal({"value": value}, "value") == "0"
    assert _require_decimal({"value": "0"}, "value") == "0"


@pytest.mark.parametrize("value", ["-0.001", "-1", Decimal("-0.001")])
def test_negative_nonzero_decimal_inputs_are_rejected(value: object) -> None:
    with pytest.raises(RequestFingerprintError):
        build_live_execution_request_fingerprint(dict(PROTECTIVE_CREATE, quantity=value))


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", "0"),
        ("quantity", "-0"),
        ("quantity", Decimal("-0.000")),
        ("quantity", "-0.001"),
        ("trigger_price", "0"),
        ("trigger_price", "-0.0"),
        ("trigger_price", "-0.001"),
    ],
)
def test_protective_create_positive_numeric_fields_reject_zero_and_negative_values(field: str, value: object) -> None:
    with pytest.raises(RequestFingerprintError):
        build_live_execution_request_fingerprint(dict(PROTECTIVE_CREATE, **{field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", "0"),
        ("quantity", "-0.0"),
        ("quantity", "-0.001"),
        ("price", "0"),
        ("price", "-0"),
        ("price", "-0.001"),
    ],
)
def test_lifecycle_create_positive_numeric_fields_reject_zero_and_negative_values(field: str, value: object) -> None:
    payload = {
        "schema_version": "1.0",
        "operation": "ORDER_LIFECYCLE_CREATE",
        "environment": "TESTNET",
        "symbol": "BTCUSDT",
        "client_order_id": "smcbot-limit-001",
        "side": "BUY",
        "position_side": "BOTH",
        "order_type": "LIMIT",
        "quantity": "0.0020",
        "price": "63000.00",
        "time_in_force": "GTX",
        "reduce_only": False,
    }
    with pytest.raises(RequestFingerprintError):
        build_live_execution_request_fingerprint(dict(payload, **{field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", "0"),
        ("quantity", "-0.0"),
        ("quantity", "-0.001"),
        ("price", "0"),
        ("price", "-0"),
        ("price", "-0.001"),
    ],
)
def test_signed_order_test_create_positive_numeric_fields_reject_zero_and_negative_values(field: str, value: object) -> None:
    payload = {
        "schema_version": "1.0",
        "operation": "SIGNED_ORDER_TEST_CREATE",
        "environment": "TESTNET",
        "symbol": "BTCUSDT",
        "client_order_id": "smcbot-test-001",
        "side": "BUY",
        "position_side": "BOTH",
        "order_type": "LIMIT",
        "quantity": "0.0020",
        "price": "63000.00",
        "time_in_force": "GTX",
        "reduce_only": False,
    }
    with pytest.raises(RequestFingerprintError):
        build_live_execution_request_fingerprint(dict(payload, **{field: value}))


@pytest.mark.parametrize("field,value", [("quantity", 1), ("quantity", 1.0), ("quantity", True), ("trigger_price", "1E+5")])
def test_numeric_fields_reject_float_int_bool_and_scientific_notation(field: str, value: object) -> None:
    with pytest.raises(RequestFingerprintError):
        build_live_execution_request_fingerprint(dict(PROTECTIVE_CREATE, **{field: value}))


@pytest.mark.parametrize("field,value", [("quantity", None), ("reduce_only", False), ("side", "BUY"), ("trigger_price", "62000.01"), ("client_algo_id", "smcbot-protect-sl-002"), ("pair_id", "pair-other"), ("operation", "PROTECTIVE_CANCEL")])
def test_business_field_changes_change_or_reject_fingerprint(field: str, value: object) -> None:
    baseline = build_live_execution_request_fingerprint(PROTECTIVE_CREATE).request_fingerprint
    payload = dict(PROTECTIVE_CREATE, **{field: value})
    if field in {"operation", "quantity"}:
        with pytest.raises(RequestFingerprintError):
            build_live_execution_request_fingerprint(payload)
    else:
        assert build_live_execution_request_fingerprint(payload).request_fingerprint != baseline


def test_missing_null_and_false_are_distinct() -> None:
    null_payload = dict(PROTECTIVE_CREATE, reduce_only=None)
    false_payload = dict(PROTECTIVE_CREATE, reduce_only=False)
    missing_payload = dict(PROTECTIVE_CREATE)
    missing_payload.pop("reduce_only")
    assert build_live_execution_request_fingerprint(null_payload).request_fingerprint != build_live_execution_request_fingerprint(false_payload).request_fingerprint
    with pytest.raises(RequestFingerprintError):
        build_live_execution_request_fingerprint(missing_payload)


@pytest.mark.parametrize("extra_key", ["timestamp", "recvWindow", "signature", "X-MBX-APIKEY", "signed-url", "rawResponse", "metadata", "headers"])
def test_unknown_and_sensitive_keys_are_rejected(extra_key: str) -> None:
    with pytest.raises(RequestFingerprintError):
        build_live_execution_request_fingerprint(dict(PROTECTIVE_CREATE, **{extra_key: "secret-token"}))


@pytest.mark.parametrize("field,value", [("environment", "PRODUCTION"), ("symbol", "ETHUSDT"), ("symbol", "*"), ("client_algo_id", "*")])
def test_scope_substitution_and_wildcards_are_rejected(field: str, value: str) -> None:
    with pytest.raises(RequestFingerprintError):
        build_live_execution_request_fingerprint(dict(PROTECTIVE_CREATE, **{field: value}))
