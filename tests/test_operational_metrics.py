from __future__ import annotations

import builtins
import inspect
import os
import socket
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from infrastructure.observability.operational_metrics import OperationalCounterRegistry


VALID_METRIC = "ict_tradingbot_operations_total"


def test_new_registry_starts_empty() -> None:
    registry = OperationalCounterRegistry()

    assert registry.snapshot() == {}


def test_registration_creates_zero_counter_and_is_idempotent() -> None:
    registry = OperationalCounterRegistry()

    registry.register(VALID_METRIC)
    registry.increment(VALID_METRIC, 3)
    registry.register(VALID_METRIC)

    assert registry.get(VALID_METRIC) == 3


def test_default_increment_adds_one_and_returns_current_value() -> None:
    registry = OperationalCounterRegistry()
    registry.register(VALID_METRIC)

    value = registry.increment(VALID_METRIC)

    assert value == 1
    assert registry.get(VALID_METRIC) == 1


def test_positive_int_increments_accumulate_exact_amounts() -> None:
    registry = OperationalCounterRegistry()
    registry.register(VALID_METRIC)

    assert registry.increment(VALID_METRIC, 2) == 2
    assert registry.increment(VALID_METRIC, 5) == 7


@pytest.mark.parametrize("amount", [0, -1, 1.5, "1", True])
def test_invalid_increment_amounts_raise_value_error(amount: object) -> None:
    registry = OperationalCounterRegistry()
    registry.register(VALID_METRIC)

    with pytest.raises(ValueError, match="COUNTER_INCREMENT_INVALID"):
        registry.increment(VALID_METRIC, amount)  # type: ignore[arg-type]


def test_decrement_is_unsupported_and_fails_closed() -> None:
    registry = OperationalCounterRegistry()
    registry.register(VALID_METRIC)

    assert not hasattr(registry, "decrement")
    with pytest.raises(ValueError, match="COUNTER_INCREMENT_INVALID"):
        registry.increment(VALID_METRIC, -1)


@pytest.mark.parametrize("method", ["increment", "get"])
def test_unknown_metric_raises_key_error(method: str) -> None:
    registry = OperationalCounterRegistry()

    with pytest.raises(KeyError, match="METRIC_UNKNOWN"):
        getattr(registry, method)(VALID_METRIC)


@pytest.mark.parametrize(
    "name",
    [
        "ict_tradingbot_operations_total",
        "ict_tradingbot_a_total",
        "ict_tradingbot_" + ("a" * 95) + "_total",
    ],
)
def test_valid_metric_names_are_accepted(name: str) -> None:
    registry = OperationalCounterRegistry()

    registry.register(name)

    assert registry.get(name) == 0


@pytest.mark.parametrize(
    "name",
    [
        "operations_total",
        "ict_tradingbot_operations",
        "ict_tradingbot_Operations_total",
        "ict_tradingbot_operation-count_total",
        "ict_tradingbot_1operations_total",
        "ict_tradingbot__total",
        "ict_tradingbot_" + ("a" * 97) + "_total",
        "ict_tradingbot_" + ("a" * 118) + "_total",
    ],
)
def test_invalid_metric_names_are_rejected(name: str) -> None:
    registry = OperationalCounterRegistry()

    with pytest.raises(ValueError, match="METRIC_NAME_INVALID"):
        registry.register(name)


@pytest.mark.parametrize(
    "name",
    [
        "ict_tradingbot_api_key_total",
        "ict_tradingbot_api_secret_total",
        "ict_tradingbot_signature_total",
        "ict_tradingbot_signed_url_total",
        "ict_tradingbot_authorization_header_total",
        "ict_tradingbot_x_mbx_api_key_total",
        "ict_tradingbot_database_url_total",
        "ict_tradingbot_sql_total",
        "ict_tradingbot_traceback_total",
        "ict_tradingbot_raw_response_total",
        "ict_tradingbot_credential_length_total",
    ],
)
def test_sensitive_marker_names_are_rejected(name: str) -> None:
    registry = OperationalCounterRegistry()

    with pytest.raises(ValueError, match="METRIC_NAME_INVALID"):
        registry.register(name)


@pytest.mark.parametrize("name", ["ict_tradingbot_bad\nname_total", "ict_tradingbot_bad\tname_total", "ict_tradingbot_bad\u007fname_total"])
def test_control_character_names_are_rejected(name: str) -> None:
    registry = OperationalCounterRegistry()

    with pytest.raises(ValueError, match="METRIC_NAME_INVALID"):
        registry.register(name)


@pytest.mark.parametrize(
    "name",
    [
        "ict_tradingbot_request_fingerprint_total",
        "ict_tradingbot_permit_id_total",
        "ict_tradingbot_order_id_total",
        "ict_tradingbot_pair_id_total",
        "ict_tradingbot_client_order_id_total",
        "ict_tradingbot_correlation_id_total",
    ],
)
def test_identifier_derived_metric_names_are_prohibited(name: str) -> None:
    registry = OperationalCounterRegistry()

    with pytest.raises(ValueError, match="METRIC_NAME_INVALID"):
        registry.register(name)


def test_labels_and_tags_api_does_not_exist() -> None:
    registry = OperationalCounterRegistry()

    assert not hasattr(registry, "labels")
    assert not hasattr(registry, "tags")
    for method_name in ("register", "increment", "get", "snapshot", "reset"):
        assert "labels" not in inspect.signature(getattr(registry, method_name)).parameters
        assert "tags" not in inspect.signature(getattr(registry, method_name)).parameters


def test_snapshot_returns_exact_fresh_deterministic_values() -> None:
    registry = OperationalCounterRegistry()
    first = "ict_tradingbot_first_total"
    second = "ict_tradingbot_second_total"
    registry.register(second)
    registry.register(first)
    registry.increment(second, 2)
    registry.increment(first, 1)

    snapshot = registry.snapshot()
    snapshot["ict_tradingbot_first_total"] = 999

    assert list(registry.snapshot().items()) == [(first, 1), (second, 2)]
    assert registry.get(first) == 1
    assert registry.snapshot() == registry.snapshot()


def test_reset_clears_state_and_registry_remains_reusable() -> None:
    registry = OperationalCounterRegistry()
    registry.register(VALID_METRIC)
    registry.increment(VALID_METRIC)

    registry.reset()
    registry.register(VALID_METRIC)

    assert registry.get(VALID_METRIC) == 0


def test_concurrent_increments_are_lossless_and_reads_are_safe() -> None:
    registry = OperationalCounterRegistry()
    registry.register(VALID_METRIC)

    def increment_many() -> None:
        for _ in range(1000):
            registry.increment(VALID_METRIC)
            assert registry.get(VALID_METRIC) >= 1

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: increment_many(), range(8)))

    assert registry.get(VALID_METRIC) == 8000


def test_concurrent_snapshots_are_internally_consistent() -> None:
    registry = OperationalCounterRegistry()
    registry.register(VALID_METRIC)

    def increment_many() -> None:
        for _ in range(500):
            registry.increment(VALID_METRIC)

    def snapshot_many() -> list[int]:
        return [registry.snapshot()[VALID_METRIC] for _ in range(500)]

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(increment_many), executor.submit(increment_many), executor.submit(snapshot_many), executor.submit(snapshot_many)]
        observed = [value for future in futures if isinstance((result := future.result()), list) for value in result]

    assert registry.get(VALID_METRIC) == 1000
    assert all(isinstance(value, int) and 0 <= value <= 1000 for value in observed)


def test_registry_is_process_local_only() -> None:
    first = OperationalCounterRegistry()
    second = OperationalCounterRegistry()

    first.register(VALID_METRIC)
    first.increment(VALID_METRIC)

    assert second.snapshot() == {}


def test_no_persistence_export_network_credentials_or_execution_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("forbidden authority used")

    monkeypatch.setattr(os.environ, "get", fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(sqlite3, "connect", fail)
    monkeypatch.setattr(builtins, "open", fail)

    registry = OperationalCounterRegistry()
    registry.register(VALID_METRIC)

    assert registry.increment(VALID_METRIC) == 1
    assert registry.snapshot() == {VALID_METRIC: 1}


def test_no_exporter_route_or_integration_methods_exist() -> None:
    registry = OperationalCounterRegistry()

    for name in (
        "export",
        "persist",
        "to_prometheus",
        "to_opentelemetry",
        "route",
        "authorize_execution",
        "create_permit",
        "consume_permit",
        "refund_permit",
        "reuse_permit",
        "mutate_order",
        "mutate_protective_pair",
        "mutate_recovery",
        "engage_kill_switch",
        "release_kill_switch",
    ):
        assert not hasattr(registry, name)
