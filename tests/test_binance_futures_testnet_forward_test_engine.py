from __future__ import annotations

import json
from pathlib import Path
from dataclasses import FrozenInstanceError, replace
from types import MappingProxyType
import socket

import pytest

from engine.diagnostics.binance_futures_testnet_forward_test_engine import BinanceFuturesTestnetForwardTestEngine
from models.binance_futures_testnet_forward_test import BinanceFuturesTestnetForwardTestConfig
from models.live_execution_permit_enforcement import LiveExecutionPermitReference
from reporting.binance_futures_testnet_forward_test_report import format_binance_futures_testnet_forward_test_result
from engine.diagnostics.binance_futures_testnet_order_test_engine import BinanceFuturesTestnetOrderTestEngine
from infrastructure.exchanges.binance_futures_testnet_order_test_client import (
    BinanceFuturesTestnetOrderTestClient, BinanceOrderTestHTTPResponse,
)
from infrastructure.persistence.live_execution_permit_persistence import LiveExecutionPermitPersistence, ISSUE_CONFIRMATION
from infrastructure.security.live_execution_permit_gate import LiveExecutionPermitGate
from infrastructure.security.live_execution_mutation_fingerprint_adapter import build_signed_order_test_create_from_final_request
from models.live_execution_permit import LiveExecutionPermitState
from tests.kill_switch_test_support import durable_state_env


@pytest.fixture(autouse=True)
def _no_network_or_real_signing(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network and real signing are forbidden in bridge tests")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(BinanceFuturesTestnetOrderTestClient, "_default_public_get", forbidden)
    monkeypatch.setattr(BinanceFuturesTestnetOrderTestClient, "_default_authenticated_post", forbidden)
    monkeypatch.setattr(BinanceFuturesTestnetOrderTestClient, "_signature", forbidden)


def _local_get(url, timeout):
    if url.endswith("/fapi/v1/time"):
        payload = {"serverTime": 123}
    elif url.endswith("/fapi/v1/exchangeInfo"):
        payload = {"symbols": [{"symbol": "BTCUSDT", "filters": [
            {"filterType": "PRICE_FILTER", "minPrice": "1", "maxPrice": "1000000", "tickSize": "0.10"},
            {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "100", "stepSize": "0.001"},
            {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "maxQty": "100", "stepSize": "0.001"},
            {"filterType": "MIN_NOTIONAL", "notional": "5"},
        ]}]}
    else:
        raise AssertionError("Unexpected public path")
    return BinanceOrderTestHTTPResponse(200, url, payload, 100)


@pytest.fixture
def supervised(tmp_path, monkeypatch):
    env = durable_state_env("RELEASED")
    events = []
    requests = []
    reference = None

    def show():
        persistence = LiveExecutionPermitPersistence(env=env)
        try:
            persistence.ensure_available()
            return persistence.show(reference.permit_id)[0]
        finally:
            persistence.close()

    class ObservedPersistence(LiveExecutionPermitPersistence):
        def consume(self, **kwargs):
            consumed = super().consume(**kwargs)
            events.append("committed")
            return consumed

        def close(self):
            super().close()
            events.append("closed")

    def local_signature(client, canonical):
        assert events[-2:] == ["committed", "closed"]
        assert show().state == LiveExecutionPermitState.CONSUMED
        events.append("simulated-signing")
        return "local-placeholder"

    def local_post(url, body, timeout, headers):
        assert url == "https://demo-fapi.binance.com/fapi/v1/order/test"
        assert events[-1] == "simulated-signing"
        events.append("local-post")
        return BinanceOrderTestHTTPResponse(200, url, {}, 2)

    monkeypatch.setattr(BinanceFuturesTestnetOrderTestClient, "_signature", local_signature)
    gate = LiveExecutionPermitGate(env=env, permit_persistence_factory=ObservedPersistence)
    boundary = BinanceFuturesTestnetOrderTestEngine(
        repo_root=Path.cwd(), env=env, http_get=_local_get,
        authenticated_post=local_post, now_ms_provider=lambda: 123, permit_gate=gate,
    )
    request = MappingProxyType(dict(client_order_id="smcbot-test-bridge", side="BUY", order_type="LIMIT", quantity=0.001, price=50000.0, time_in_force="GTC"))
    client = boundary._client(boundary.load_config("configs/binance_futures_testnet_order_test.json"))
    preview = client.build_order_test_preview(**request, exchange_filters=client.fetch_exchange_filters())
    unsigned = client.build_unsigned_business_request(preview)
    fingerprint = build_signed_order_test_create_from_final_request(unsigned)
    persistence = LiveExecutionPermitPersistence(env=env)
    try:
        persistence.ensure_available()
        issued = persistence.issue(fingerprint, ttl_seconds=300, issued_by="bridge-local-test", confirmation=ISSUE_CONFIRMATION)
    finally:
        persistence.close()
    reference = LiveExecutionPermitReference(issued.permit_id, issued.version)

    original_build = BinanceFuturesTestnetOrderTestClient.build_unsigned_business_request

    def observe_unsigned(client, preview):
        value = original_build(client, preview)
        requests.append(value)
        return value

    monkeypatch.setattr(BinanceFuturesTestnetOrderTestClient, "build_unsigned_business_request", observe_unsigned)

    def no_issue(*args, **kwargs):
        raise AssertionError("Bridge must never issue or replace permits")

    monkeypatch.setattr(LiveExecutionPermitPersistence, "issue", no_issue)
    engine = _engine(tmp_path, order_test_engine=boundary)
    path = _write_config(tmp_path)
    kwargs = dict(execution_mode="SUPERVISED_TESTNET_ORDER_TEST", execution_authorized=True,
                  confirmation="CONFIRM_TESTNET_ORDER_TEST", permit_references=[reference],
                  api_key_identifier="BINANCE_FUTURES_TESTNET_API_KEY",
                  api_secret_identifier="BINANCE_FUTURES_TESTNET_API_SECRET",
                  testnet_order_test_network_enabled=True,
                  runtime_environment=_allowlisted_runtime_env(env),
                  order_test_request=request, local_simulated_transport=True)
    return engine, path, kwargs, boundary, env, events, requests, show


def test_supervised_real_gate_commits_closes_then_simulated_signing_and_order_test(supervised):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    original = dict(kwargs["order_test_request"])
    result = engine.run(path, **kwargs)
    assert result.status == "PASS"
    assert type(boundary.permit_gate) is LiveExecutionPermitGate
    assert events == ["committed", "closed", "simulated-signing", "local-post"]
    assert show().state == LiveExecutionPermitState.CONSUMED
    assert show().version == 2
    assert dict(kwargs["order_test_request"]) == original
    unsigned = requests[0]
    with pytest.raises(FrozenInstanceError):
        unsigned.symbol = "ETHUSDT"
    for mapping in (unsigned.fingerprint_context, unsigned.transport_business_parameters):
        with pytest.raises(TypeError):
            mapping["quantity"] = "999"
        assert not {"timestamp", "recvWindow", "signature"} & mapping.keys()
    evidence = result.evidence
    assert evidence.execution_mode == "SUPERVISED_TESTNET_ORDER_TEST"
    assert evidence.execution_authorized is True
    assert evidence.order_test_requested_count == evidence.permit_reference_count == 1
    assert evidence.permit_consumed_count == evidence.signing_count == evidence.post_count == 1
    assert evidence.accepted_mutation_count == 1
    assert evidence.post_retry_count == evidence.delete_retry_count == evidence.delete_count == 0
    assert evidence.actual_binance_demo_execution is False
    assert evidence.transport_mode == "LOCAL_TEST_SIMULATED_TRANSPORT"
    assert evidence.evidence_complete is True
    rendered = format_binance_futures_testnet_forward_test_result(result)
    serialized = json.dumps(result.to_dict())
    for value in (env["BINANCE_FUTURES_TESTNET_API_KEY"], env["BINANCE_FUTURES_TESTNET_API_SECRET"], "local-placeholder", "X-MBX-APIKEY", "signature=", "https://"):
        assert value not in rendered + serialized


@pytest.mark.parametrize("overrides", [
    {"execution_mode": None}, {"execution_mode": "ORDER_CREATE"},
    {"execution_mode": "ORDER_CANCEL"}, {"execution_mode": "PROTECTIVE_CREATE"},
    {"execution_mode": "PROTECTIVE_CANCEL"}, {"execution_mode": "ACTUAL_BINANCE_DEMO_ORDER_TEST"},
    {"execution_authorized": False}, {"execution_authorized": 1},
    {"confirmation": None}, {"permit_references": []}, {"permit_references": [object()]},
    {"api_key_identifier": None}, {"api_secret_identifier": None},
    {"api_key_identifier": "BINANCE_API_KEY"}, {"api_secret_identifier": "BINANCE_API_SECRET"},
    {"testnet_order_test_network_enabled": False},
    {"runtime_environment": None},
    {"runtime_environment": {}},
    {"runtime_environment": {"BINANCE_FUTURES_TESTNET_API_SECRET": "secret", "ICT_DATABASE_URL": "sqlite:///tmp.db"}},
    {"runtime_environment": {"BINANCE_FUTURES_TESTNET_API_KEY": "key", "ICT_DATABASE_URL": "sqlite:///tmp.db"}},
    {"runtime_environment": {"BINANCE_FUTURES_TESTNET_API_KEY": " ", "BINANCE_FUTURES_TESTNET_API_SECRET": "secret", "ICT_DATABASE_URL": "sqlite:///tmp.db"}},
    {"runtime_environment": {"BINANCE_FUTURES_TESTNET_API_KEY": "key", "BINANCE_FUTURES_TESTNET_API_SECRET": "", "ICT_DATABASE_URL": "sqlite:///tmp.db"}},
    {"runtime_environment": {"BINANCE_FUTURES_TESTNET_API_KEY": "key", "BINANCE_FUTURES_TESTNET_API_SECRET": "secret"}},
    {"runtime_environment": {"BINANCE_FUTURES_TESTNET_API_KEY": "key", "BINANCE_FUTURES_TESTNET_API_SECRET": "secret", "ICT_DATABASE_URL": "sqlite:///tmp.db", "AWS_SECRET_ACCESS_KEY": "not-allowed"}},
    {"order_test_request": None}, {"order_test_request": {"operation": "ORDER_CREATE"}},
    {"local_simulated_transport": False},
])
def test_supervised_prerequisites_block_before_consume(supervised, overrides):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    result = engine.run(path, **{**kwargs, **overrides})
    assert result.status == "FAIL"
    assert result.evidence.post_count == 0
    assert result.evidence.actual_binance_demo_execution is False
    assert events == []
    assert show().state == LiveExecutionPermitState.ISSUED


def test_network_enablement_alone_fails_closed(tmp_path):
    path = _write_config(tmp_path)
    result = _engine(tmp_path).run(
        path,
        testnet_order_test_network_enabled=True,
        runtime_environment={
            "BINANCE_FUTURES_TESTNET_API_KEY": "sentinel-key",
            "BINANCE_FUTURES_TESTNET_API_SECRET": "sentinel-secret",
            "ICT_DATABASE_URL": "sqlite:///sentinel.db",
        },
    )
    assert result.status == "FAIL"
    assert result.decision == "EXECUTION_NOT_AUTHORIZED"
    assert result.evidence.post_count == 0
    assert result.evidence.actual_binance_demo_execution is False


def test_runtime_environment_validation_allows_only_testnet_credentials_and_durable_database(supervised):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    runtime = engine._validated_runtime_environment({**kwargs["runtime_environment"], "DATABASE_URL": "sqlite:///fallback.db"})
    assert set(runtime) <= {
        "BINANCE_FUTURES_TESTNET_API_KEY",
        "BINANCE_FUTURES_TESTNET_API_SECRET",
        "ICT_DATABASE_URL",
        "DATABASE_URL",
    }
    assert runtime["BINANCE_FUTURES_TESTNET_API_KEY"] == env["BINANCE_FUTURES_TESTNET_API_KEY"]
    assert runtime["BINANCE_FUTURES_TESTNET_API_SECRET"] == env["BINANCE_FUTURES_TESTNET_API_SECRET"]
    assert "ICT_LIVE_EXECUTION_RUNTIME_CONFIG" not in runtime


def test_local_supervised_runtime_sentinels_are_sanitized(supervised):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    result = engine.run(path, **kwargs)
    rendered = format_binance_futures_testnet_forward_test_result(result)
    serialized = json.dumps(result.to_dict())
    for value in kwargs["runtime_environment"].values():
        assert value not in rendered
        assert value not in serialized


@pytest.mark.parametrize("override", [
    {"environment": "UNKNOWN"}, {"exchange_symbol": "ETHUSDT"},
    {"rest_base_url": "https://fapi.binance.com"},
    {"rest_base_url": "https://demo-fapi.binance.com:444"},
    {"allowed_hosts": ["binance.com"]}, {"execution_mode": "SUPERVISED_TESTNET_ORDER_TEST"},
])
def test_supervised_scope_rejected_before_transport(supervised, tmp_path, override):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    result = engine.run(_write_config(tmp_path, **override), **kwargs)
    assert result.status == "FAIL"
    assert events == []
    assert show().state == LiveExecutionPermitState.ISSUED


def test_forward_config_default_keeps_network_fail_closed(tmp_path):
    path = _write_config(tmp_path)
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    assert config["feature_enabled"] is False
    assert config["execution_enabled"] is False
    assert config["execution_mode"] == "DISABLED"
    assert config["local_evidence_only"] is True


def test_supervised_real_gate_rejects_reuse_without_refund(supervised):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    assert engine.run(path, **kwargs).status == "PASS"
    second = engine.run(path, **kwargs)
    assert second.decision == "PERMIT_ALREADY_CONSUMED"
    assert events.count("local-post") == 1
    assert second.evidence.post_count == 0
    assert show().state == LiveExecutionPermitState.CONSUMED
    assert show().version == 2


def test_supervised_real_gate_binds_fingerprint(supervised):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    kwargs["order_test_request"] = {**kwargs["order_test_request"], "price": 49999.0}
    result = engine.run(path, **kwargs)
    assert result.decision == "PERMIT_FINGERPRINT_MISMATCH"
    assert "simulated-signing" not in events
    assert show().state == LiveExecutionPermitState.ISSUED


def test_supervised_real_policy_preserves_kill_switch(supervised):
    from infrastructure.persistence.kill_switch_persistence import KillSwitchPersistence
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    persistence = KillSwitchPersistence(env=env)
    try:
        persistence.ensure_available()
        persistence.engage()
    finally:
        persistence.close()
    result = engine.run(path, **kwargs)
    assert result.decision == "KILL_SWITCH_ENGAGED"
    assert result.evidence.kill_switch_denial_count == 1
    assert events == []
    assert show().state == LiveExecutionPermitState.ISSUED


def test_uncertain_local_post_is_not_retried_or_reported_complete(supervised):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    def timeout(*args, **kwargs):
        events.append("timeout")
        raise TimeoutError("signature=private X-MBX-APIKEY SQL traceback")
    boundary.authenticated_post = timeout
    result = engine.run(path, **kwargs)
    assert result.status == "FAIL"
    assert events.count("timeout") == 1
    assert result.evidence.post_count is None
    assert result.evidence.permit_consumed_count is None
    assert result.evidence.evidence_complete is False
    assert result.evidence.actual_binance_demo_execution is False
    assert show().state == LiveExecutionPermitState.CONSUMED
    serialized = json.dumps(result.to_dict())
    for text in ("signature=", "private", "X-MBX-APIKEY", "SQL", "traceback"):
        assert text not in serialized


def test_fake_gate_is_rejected_by_bridge(supervised):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    boundary.permit_gate = object()
    result = engine.run(path, **kwargs)
    assert result.decision == "REAL_ORDER_TEST_BOUNDARY_REQUIRED"
    assert events == []


def test_mixed_transport_callbacks_fail_closed(supervised):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    boundary.http_get = None
    result = engine.run(path, **kwargs)
    assert result.decision == "TRANSPORT_MODE_INVALID"
    assert events == []


@pytest.mark.parametrize("code,body", [(400, {}), (400, {"code": -1, "msg": "private token value"}), (200, {"unexpected": "private"})])
def test_local_exchange_rejection_does_not_fabricate_acceptance(supervised, code, body):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    def rejected(url, *args):
        events.append("rejected-post")
        return BinanceOrderTestHTTPResponse(code, url, body, 20)
    boundary.authenticated_post = rejected
    result = engine.run(path, **kwargs)
    assert result.status == "FAIL"
    assert result.evidence.accepted_mutation_count == 0
    assert result.evidence.rejected_mutation_count == 1
    assert result.evidence.permit_consumed_count == result.evidence.post_count == 1
    assert result.evidence.actual_binance_demo_execution is False
    assert events.count("rejected-post") == 1
    assert "private" not in json.dumps(result.to_dict())


@pytest.mark.parametrize("field,value", [("live_trading_enabled", False), ("dry_run", True)])
def test_supervised_real_policy_preserves_runtime_flags(supervised, field, value):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    runtime = Path(env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"])
    flags = json.loads(runtime.read_text(encoding="utf-8"))
    flags[field] = value
    runtime.write_text(json.dumps(flags), encoding="utf-8")
    result = engine.run(path, **kwargs)
    assert result.decision == ("LIVE_TRADING_DISABLED" if field == "live_trading_enabled" else "DRY_RUN_ACTIVE")
    assert events == []
    assert show().state == LiveExecutionPermitState.ISSUED


@pytest.mark.parametrize("overrides", [
    {"test_order_path": "/fapi/v1/order"},
    {"allowed_authenticated_paths": ["/fapi/v1/algoOrder"]},
    {"api_key_env_var": "BINANCE_API_KEY"},
    {"api_secret_env_var": "BINANCE_API_SECRET"},
])
def test_existing_order_test_config_cannot_widen_bridge(supervised, monkeypatch, overrides):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    original = boundary.load_config
    monkeypatch.setattr(boundary, "load_config", lambda path: replace(original(path), **overrides))
    result = engine.run(path, **kwargs)
    assert result.status == "FAIL"
    assert events == []
    assert show().state == LiveExecutionPermitState.ISSUED


def test_invalid_config_sensitive_values_are_not_reported(tmp_path):
    path = _write_config(tmp_path, rest_base_url="https://private:password@demo-fapi.binance.com?signature=private")
    engine = _engine(tmp_path)
    report = engine.validate(path)
    result = engine.run(path)
    for payload in (report.to_dict(), result.to_dict()):
        serialized = json.dumps(payload)
        assert "private" not in serialized
        assert "signature=" not in serialized


class _Dependency:
    def __init__(self, status: str = "PASS") -> None:
        self.status = status

    def validate(self, *args, **kwargs):
        return type("Report", (), {"status": self.status})()


def _engine(tmp_path: Path, **kwargs) -> BinanceFuturesTestnetForwardTestEngine:
    return BinanceFuturesTestnetForwardTestEngine(
        repo_root=tmp_path,
        forward_loop_engine=kwargs.pop("forward_loop_engine", _Dependency()),
        order_test_engine=kwargs.pop("order_test_engine", _Dependency()),
        order_lifecycle_engine=kwargs.pop("order_lifecycle_engine", _Dependency()),
        protective_orders_engine=kwargs.pop("protective_orders_engine", _Dependency()),
        now_provider=lambda: "2026-08-29T00:00:00+00:00",
        **kwargs,
    )


def _write_config(tmp_path: Path, **overrides) -> str:
    payload = BinanceFuturesTestnetForwardTestConfig().to_dict()
    payload.update(overrides)
    path = tmp_path / "configs" / "binance_futures_testnet_forward_test.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _allowlisted_runtime_env(env: dict[str, str]) -> dict[str, str]:
    return {
        key: env[key]
        for key in (
            "BINANCE_FUTURES_TESTNET_API_KEY",
            "BINANCE_FUTURES_TESTNET_API_SECRET",
            "ICT_DATABASE_URL",
            "DATABASE_URL",
        )
        if key in env
    }


def test_repo_config_validates_disabled_by_default() -> None:
    report = BinanceFuturesTestnetForwardTestEngine().validate()
    runtime = json.loads(Path("configs/binance_futures_testnet_supervised_runtime.json").read_text(encoding="utf-8"))

    assert report.status == "PASS"
    assert report.config is not None
    assert report.config.feature_enabled is False
    assert report.config.execution_enabled is False
    assert report.config.runtime_config_path == "configs/binance_futures_testnet_supervised_runtime.json"
    assert report.config.runtime_config_path != "configs/btc_paper_runtime.json"
    assert runtime["live_trading_enabled"] is True
    assert runtime["dry_run"] is False
    serialized_runtime = json.dumps(runtime).lower()
    for marker in ("api_key", "api secret", "database_url", "permit_id", "signature", "authenticated", "headers"):
        assert marker not in serialized_runtime
    assert report.diagnostics["network_used"] is False
    assert report.diagnostics["actual_demo_execution"] is False


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("environment", "BINANCE_FUTURES_PRODUCTION", "environment"),
        ("exchange_symbol", "ETHUSDT", "exchange_symbol"),
        ("symbol", "ETH/USDT", "symbol"),
        ("rest_base_url", "https://fapi.binance.com", "rest_base_url"),
        ("allowed_hosts", ["demo-fapi.binance.com", "fapi.binance.com"], "allowed_hosts"),
        ("feature_enabled", True, "feature_enabled"),
        ("execution_enabled", True, "execution_enabled"),
        ("allow_production_endpoint", True, "allow_production_endpoint"),
        ("allow_production_credentials", True, "allow_production_credentials"),
        ("allow_real_funds", True, "allow_real_funds"),
        ("allow_network_in_automated_tests", True, "allow_network_in_automated_tests"),
        ("allow_auto_permit_issue", True, "allow_auto_permit_issue"),
        ("allow_permit_reuse", True, "allow_permit_reuse"),
        ("allow_permit_refund", True, "allow_permit_refund"),
        ("post_retry_count", 1, "post_retry_count"),
        ("delete_retry_count", 1, "delete_retry_count"),
        ("report_export_dir", "../reports", "report_export_dir"),
    ],
)
def test_dangerous_config_values_fail_closed(tmp_path: Path, field: str, value, issue: str) -> None:
    path = _write_config(tmp_path, **{field: value})

    report = _engine(tmp_path).validate(path)

    assert report.status == "FAIL"
    assert any(item.name == issue for item in report.issues)


def test_dependency_failure_blocks_validation(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    report = _engine(tmp_path, order_lifecycle_engine=_Dependency("FAIL")).validate(path)

    assert report.status == "FAIL"
    assert any(issue.name == "order_lifecycle_status" for issue in report.issues)


def test_default_run_fails_closed_without_consuming_or_signing(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    permit = LiveExecutionPermitReference("permit-77777777777777777777777777777777", 3)

    result = _engine(tmp_path).run(path, permit_references=[permit], strategy_decision_count=2)

    assert result.status == "FAIL"
    assert result.decision == "EXECUTION_NOT_AUTHORIZED"
    assert result.evidence is not None
    assert result.evidence.permit_reference_count == 1
    assert result.evidence.permit_consumed_count == 0
    assert result.evidence.signing_count == 0
    assert result.evidence.post_count == 0
    assert result.evidence.delete_count == 0
    assert result.evidence.actual_binance_demo_execution is False
    assert result.diagnostics["network_used"] is False
    assert result.diagnostics["permit_auto_issued"] is False


def test_local_simulated_transport_is_labeled_not_demo_execution(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    result = _engine(tmp_path).run(path, local_simulated_transport=True, strategy_decision_count=4, risk_denial_count=1)

    assert result.status == "PASS"
    assert result.decision == "LOCAL_SIMULATION_EVIDENCE"
    assert result.evidence is not None
    assert result.evidence.strategy_decision_count == 4
    assert result.evidence.risk_denial_count == 1
    assert result.evidence.evidence_complete is True
    rendered = format_binance_futures_testnet_forward_test_result(result)
    assert "LOCAL TEST / SIMULATED TRANSPORT" in rendered
    assert "ACTUAL BINANCE DEMO EXECUTION: false" in rendered


def test_report_sanitizes_sensitive_issue_text(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    result = _engine(tmp_path).run(path)
    rendered = format_binance_futures_testnet_forward_test_result(result)

    forbidden = ("signature=", "X-MBX-APIKEY", "api_secret", "traceback", "SELECT *")
    for marker in forbidden:
        assert marker not in rendered
