from __future__ import annotations

import json
import socket
from contextlib import contextmanager
from pathlib import Path
from types import MappingProxyType

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from engine.diagnostics.binance_futures_testnet_forward_test_engine import BinanceFuturesTestnetForwardTestEngine
from engine.diagnostics.binance_futures_testnet_order_test_engine import BinanceFuturesTestnetOrderTestEngine
from infrastructure.exchanges.binance_futures_testnet_order_test_client import (
    BinanceFuturesTestnetOrderTestClient,
    BinanceOrderTestHTTPResponse,
)
from infrastructure.persistence.execution_orm import AuditEventORM
from infrastructure.persistence.live_execution_authorization_policy import LiveExecutionAuthorizationPolicy
from infrastructure.persistence.live_execution_permit_persistence import (
    ISSUE_CONFIRMATION,
    LiveExecutionPermitPersistence,
    get_order_test_runtime_evidence,
)
from infrastructure.security.live_execution_mutation_fingerprint_adapter import build_signed_order_test_create_from_final_request
from infrastructure.security.live_execution_permit_gate import LiveExecutionPermitGate
from models.binance_futures_testnet_forward_test import BinanceFuturesTestnetForwardTestConfig
from models.live_execution_authorization import LiveExecutionAuthorizationDecision
from models.live_execution_permit import LiveExecutionPermitState
from models.live_execution_permit_enforcement import LiveExecutionPermitReference
from tests.kill_switch_test_support import durable_state_env


EXPECTED_SUCCESS_EVENTS = [
    "POLICY_EVALUATED",
    "PERSISTENCE_OPENED",
    "PERMIT_CONSUMED",
    "PERSISTENCE_COMMITTED",
    "PERSISTENCE_CLOSED",
    "SIGNED",
    "POST_ATTEMPTED",
    "POST_COMPLETED",
]


@pytest.fixture(autouse=True)
def _block_network_and_default_signing(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network and default signing are forbidden in runtime evidence tests")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(BinanceFuturesTestnetOrderTestClient, "_default_public_get", forbidden)
    monkeypatch.setattr(BinanceFuturesTestnetOrderTestClient, "_default_authenticated_post", forbidden)
    monkeypatch.setattr(BinanceFuturesTestnetOrderTestClient, "_signature", forbidden)


def test_success_runtime_evidence_ordering_sanitization_and_forward_report(monkeypatch, tmp_path):
    events: list[str] = []

    class CloseProbePersistence(LiveExecutionPermitPersistence):
        def close(self):
            evidence = get_order_test_runtime_evidence()
            if evidence is not None:
                assert "PERSISTENCE_CLOSED" not in evidence["mutation_boundary_events"]
            super().close()
            events.append("closed")
            evidence = get_order_test_runtime_evidence()
            if evidence is not None:
                assert "PERSISTENCE_CLOSED" in evidence["mutation_boundary_events"]

    def signature_spy(client, canonical):
        evidence = get_order_test_runtime_evidence()
        assert evidence is not None
        assert "SIGNED" not in evidence["mutation_boundary_events"]
        assert "POST_ATTEMPTED" not in evidence["mutation_boundary_events"]
        events.append("signed")
        return "local-placeholder"

    def post_spy(url, body, timeout, headers):
        evidence = get_order_test_runtime_evidence()
        assert evidence is not None
        assert evidence["mutation_boundary_events"][-2:] == ["SIGNED", "POST_ATTEMPTED"]
        assert headers["X-MBX-APIKEY"] == "unit-test-key"
        events.append("post")
        return BinanceOrderTestHTTPResponse(200, url, {}, 2)

    monkeypatch.setattr(BinanceFuturesTestnetOrderTestClient, "_signature", signature_spy)
    engine, path, kwargs, env, reference = _forward_engine(tmp_path, CloseProbePersistence, post_spy)
    original_request = dict(kwargs["order_test_request"])

    result = engine.run(path, **kwargs)

    assert result.status == "PASS"
    assert result.evidence.production_disabled is True
    assert result.evidence.permit_consumed_count == 1
    assert result.evidence.signing_count == 1
    assert result.evidence.post_count == 1
    assert result.evidence.post_retry_count == 0
    assert result.evidence.delete_retry_count == 0
    assert result.evidence.delete_count == 0
    assert result.evidence.actual_binance_demo_execution is False
    assert result.evidence.transport_mode == "LOCAL_TEST_SIMULATED_TRANSPORT"
    assert result.evidence.symbol == "BTCUSDT"
    assert kwargs["order_test_request"] == MappingProxyType(original_request)
    assert _permit_state(env, reference).state == LiveExecutionPermitState.CONSUMED
    assert _audit_count(env, "PERMIT_CONSUMED") == 1
    assert events == ["closed", "signed", "post"]

    diagnostics = result.diagnostics
    assert diagnostics["policy_evaluation_count"] == 1
    assert diagnostics["audit_record_count"] == 1
    assert diagnostics["recovery_required"] is False
    assert diagnostics["mutation_boundary_events"] == EXPECTED_SUCCESS_EVENTS

    serialized = json.dumps(result.to_dict(), sort_keys=True)
    for forbidden in (
        env["BINANCE_FUTURES_TESTNET_API_KEY"],
        env["BINANCE_FUTURES_TESTNET_API_SECRET"],
        "local-placeholder",
        "X-MBX-APIKEY",
        "signature=",
        "https://",
    ):
        assert forbidden not in serialized


def test_policy_never_completes_has_no_policy_evidence(monkeypatch, tmp_path):
    class FailingFinalPolicy:
        def __init__(self):
            self.calls = 0

        def authorize(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return LiveExecutionAuthorizationDecision(True, "AUTHORIZED", "SIGNED_ORDER_TEST_CREATE")
            raise RuntimeError("policy unavailable")

    policy = FailingFinalPolicy()
    result = _run_order_test(monkeypatch, tmp_path, authorization_policy=policy)

    evidence = result.payload["runtime_evidence"]
    assert policy.calls == 2
    assert evidence["policy_evaluation_count"] == 0
    assert "POLICY_EVALUATED" not in evidence["mutation_boundary_events"]
    assert result.decision == "PERMIT_GATE_UNAVAILABLE"


def test_commit_failure_does_not_claim_commit_or_transport(monkeypatch, tmp_path):
    class CommitFailurePersistence(LiveExecutionPermitPersistence):
        @contextmanager
        def _transaction(self, *, record_runtime_boundary: bool = False):
            with self._session() as session:
                try:
                    with session.begin():
                        yield session
                    if record_runtime_boundary:
                        raise RuntimeError("commit failed")
                except Exception:
                    session.rollback()
                    raise

    result = _run_order_test(monkeypatch, tmp_path, persistence_factory=CommitFailurePersistence)

    evidence = result.payload["runtime_evidence"]
    assert "PERMIT_CONSUMED" in evidence["mutation_boundary_events"]
    assert "PERSISTENCE_COMMITTED" not in evidence["mutation_boundary_events"]
    assert "SIGNED" not in evidence["mutation_boundary_events"]
    assert "POST_ATTEMPTED" not in evidence["mutation_boundary_events"]


def test_signer_failure_does_not_claim_signed_or_post(monkeypatch, tmp_path):
    def signer_failure(client, canonical):
        raise RuntimeError("signing failed")

    result = _run_order_test(monkeypatch, tmp_path, signature=signer_failure)

    evidence = result.payload["runtime_evidence"]
    assert evidence["mutation_boundary_events"][:5] == EXPECTED_SUCCESS_EVENTS[:5]
    assert "SIGNED" not in evidence["mutation_boundary_events"]
    assert "POST_ATTEMPTED" not in evidence["mutation_boundary_events"]
    assert result.request_metadata is None


def test_uncertain_transport_does_not_claim_post_completed(monkeypatch, tmp_path):
    def transport_failure(url, body, timeout, headers):
        raise TimeoutError("transport uncertain")

    result = _run_order_test(monkeypatch, tmp_path, authenticated_post=transport_failure)

    evidence = result.payload["runtime_evidence"]
    assert evidence["mutation_boundary_events"][-2:] == ["SIGNED", "POST_ATTEMPTED"]
    assert "POST_COMPLETED" not in evidence["mutation_boundary_events"]
    assert result.request_metadata is None


def test_recovery_required_uses_policy_result_without_permit_consume(monkeypatch, tmp_path):
    class RecoveryPolicy(LiveExecutionAuthorizationPolicy):
        def __init__(self):
            super().__init__(repo_root=Path.cwd(), env=durable_state_env("RELEASED"))
            self.calls = 0

        def authorize(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return LiveExecutionAuthorizationDecision(True, "AUTHORIZED", "SIGNED_ORDER_TEST_CREATE")
            return self._record_order_test_authorization_evidence(
                LiveExecutionAuthorizationDecision(False, "RECOVERY_REQUIRED", "SIGNED_ORDER_TEST_CREATE"),
                recovery_required=True,
            )

    policy = RecoveryPolicy()
    result = _run_order_test(monkeypatch, tmp_path, authorization_policy=policy)

    evidence = result.payload["runtime_evidence"]
    assert policy.calls == 2
    assert evidence["policy_evaluation_count"] == 1
    assert evidence["recovery_required"] is True
    assert evidence["audit_record_count"] == 0
    assert evidence["mutation_boundary_events"] == ["POLICY_EVALUATED"]
    assert result.decision == "RECOVERY_REQUIRED"


def _run_order_test(
    monkeypatch,
    tmp_path,
    *,
    persistence_factory=LiveExecutionPermitPersistence,
    authorization_policy=None,
    signature=None,
    authenticated_post=None,
):
    if signature is None:
        signature = lambda client, canonical: "local-placeholder"
    if authenticated_post is None:
        authenticated_post = lambda url, body, timeout, headers: BinanceOrderTestHTTPResponse(200, url, {}, 2)
    monkeypatch.setattr(BinanceFuturesTestnetOrderTestClient, "_signature", signature)
    env = durable_state_env("RELEASED")
    boundary = _boundary(env, persistence_factory, authenticated_post, authorization_policy=authorization_policy)
    reference = _issue_reference(boundary, env)
    return boundary.submit_test_order(
        client_order_id="smcbot-test-runtime",
        side="BUY",
        order_type="LIMIT",
        quantity=0.001,
        price=50000.0,
        time_in_force="GTC",
        confirmation="CONFIRM_TESTNET_ORDER_TEST",
        permit=reference,
    )


def _forward_engine(tmp_path, persistence_factory, authenticated_post):
    env = durable_state_env("RELEASED")
    boundary = _boundary(env, persistence_factory, authenticated_post)
    reference = _issue_reference(boundary, env)
    engine = BinanceFuturesTestnetForwardTestEngine(
        repo_root=tmp_path,
        forward_loop_engine=_Dependency(),
        order_test_engine=boundary,
        order_lifecycle_engine=_Dependency(),
        protective_orders_engine=_Dependency(),
        now_provider=lambda: "2026-08-29T00:00:00+00:00",
    )
    path = _write_forward_config(tmp_path)
    request = MappingProxyType(
        {
            "client_order_id": "smcbot-test-runtime",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.001,
            "price": 50000.0,
            "time_in_force": "GTC",
        }
    )
    kwargs = {
        "execution_mode": "SUPERVISED_TESTNET_ORDER_TEST",
        "execution_authorized": True,
        "confirmation": "CONFIRM_TESTNET_ORDER_TEST",
        "permit_references": [reference],
        "api_key_identifier": "BINANCE_FUTURES_TESTNET_API_KEY",
        "api_secret_identifier": "BINANCE_FUTURES_TESTNET_API_SECRET",
        "testnet_order_test_network_enabled": True,
        "runtime_environment": _forward_runtime_env(env),
        "order_test_request": request,
        "local_simulated_transport": True,
    }
    return engine, path, kwargs, env, reference


def _boundary(env, persistence_factory, authenticated_post, *, authorization_policy=None):
    policy = authorization_policy or LiveExecutionAuthorizationPolicy(repo_root=Path.cwd(), env=env)
    gate = LiveExecutionPermitGate(
        authorization_policy=policy,
        env=env,
        permit_persistence_factory=persistence_factory,
    )
    return BinanceFuturesTestnetOrderTestEngine(
        repo_root=Path.cwd(),
        env=env,
        http_get=_local_get,
        authenticated_post=authenticated_post,
        permit_gate=gate,
        authorization_policy=policy,
        now_ms_provider=lambda: 123,
    )


def _issue_reference(boundary, env):
    request = {
        "client_order_id": "smcbot-test-runtime",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": 0.001,
        "price": 50000.0,
        "time_in_force": "GTC",
    }
    client = boundary._client(boundary.load_config("configs/binance_futures_testnet_order_test.json"))
    preview = client.build_order_test_preview(**request, exchange_filters=client.fetch_exchange_filters())
    unsigned = client.build_unsigned_business_request(preview)
    fingerprint = build_signed_order_test_create_from_final_request(unsigned)
    persistence = LiveExecutionPermitPersistence(env=env)
    try:
        persistence.ensure_available()
        permit = persistence.issue(
            fingerprint,
            ttl_seconds=300,
            issued_by="runtime-evidence-test",
            confirmation=ISSUE_CONFIRMATION,
        )
    finally:
        persistence.close()
    return LiveExecutionPermitReference(permit.permit_id, permit.version)


def _permit_state(env, reference):
    persistence = LiveExecutionPermitPersistence(env=env)
    try:
        persistence.ensure_available()
        permit, _ = persistence.show(reference.permit_id)
        return permit
    finally:
        persistence.close()


def _audit_count(env, action: str) -> int:
    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(bind=engine, future=True) as session:
            return len(list(session.scalars(select(AuditEventORM).where(AuditEventORM.action == action)).all()))
    finally:
        engine.dispose()


def _local_get(url, timeout):
    if url.endswith("/fapi/v1/time"):
        payload = {"serverTime": 123}
    elif url.endswith("/fapi/v1/exchangeInfo"):
        payload = {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "filters": [
                        {"filterType": "PRICE_FILTER", "minPrice": "1", "maxPrice": "1000000", "tickSize": "0.10"},
                        {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "100", "stepSize": "0.001"},
                        {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "maxQty": "100", "stepSize": "0.001"},
                        {"filterType": "MIN_NOTIONAL", "notional": "5"},
                    ],
                }
            ]
        }
    else:
        raise AssertionError("unexpected public path")
    return BinanceOrderTestHTTPResponse(200, url, payload, 100)


def _write_forward_config(tmp_path: Path) -> str:
    payload = BinanceFuturesTestnetForwardTestConfig().to_dict()
    path = tmp_path / "configs" / "binance_futures_testnet_forward_test.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _forward_runtime_env(env: dict[str, str]) -> dict[str, str]:
    return {
        "BINANCE_FUTURES_TESTNET_API_KEY": env["BINANCE_FUTURES_TESTNET_API_KEY"],
        "BINANCE_FUTURES_TESTNET_API_SECRET": env["BINANCE_FUTURES_TESTNET_API_SECRET"],
        "ICT_DATABASE_URL": env["ICT_DATABASE_URL"],
    }


class _Dependency:
    status = "PASS"

    def validate(self, *args, **kwargs):
        return self
