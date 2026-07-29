from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from engine.diagnostics.binance_futures_testnet_order_test_engine import BinanceFuturesTestnetOrderTestEngine
from infrastructure.exchanges.binance_futures_testnet_order_test_client import (
    BinanceFuturesTestnetOrderTestClient,
    BinanceOrderTestHTTPResponse,
)
from infrastructure.persistence.execution_orm import AuditEventORM, ExchangeOrderIdentityORM, ExecutionIntentORM, ProtectivePairORM, RecoveryEventORM, LiveExecutionPermitORM
from infrastructure.persistence.kill_switch_persistence import KillSwitchPersistence
from infrastructure.persistence.live_execution_authorization_policy import LiveExecutionAuthorizationPolicy
from infrastructure.persistence.live_execution_permit_persistence import ISSUE_CONFIRMATION, LiveExecutionPermitPersistence
from infrastructure.security.live_execution_mutation_fingerprint_adapter import build_signed_order_test_create_from_final_request
from infrastructure.security.live_execution_permit_gate import LiveExecutionPermitGate
from models.binance_futures_testnet_order_test import BinanceFuturesTestnetOrderTestConfig
from models.live_execution_authorization import LiveExecutionAuthorizationDecision, LiveExecutionOperation
from models.live_execution_permit import LiveExecutionPermitState
from models.live_execution_permit_enforcement import LiveExecutionPermitReference
from reporting.binance_futures_testnet_order_test_report import format_binance_futures_testnet_order_test_result
from tests.kill_switch_test_support import durable_state_env
from tests.test_binance_futures_testnet_order_test_engine import _engine, _http_get, _write_config

CORRELATION_ID = UUID("11111111-1111-4111-8111-11111111112c")
CLIENT_ORDER_ID = "smcbot-test-matrix-001"
CONFIRMATION = "CONFIRM_TESTNET_ORDER_TEST"


def _sentinel() -> str:
    return " | ".join(
        [
            "unit-test-" + "api-secret",
            "unit-test-full-" + "api-key",
            "signature" + "=abc123",
            "https://" + "authenticated.example.test/fapi/v1/order/test?signature=abc123",
            "signed" + "_query=timestamp&signature=abc123",
            "X-MBX-" + "APIKEY: test-key",
            "raw " + "credential token",
            "SELECT " + "* FROM execution_intents",
            "postgresql://user:" + "database-password@localhost/db",
            "Trace" + "back (most recent call last)",
            "raw exception " + "chain details",
            "internal metadata: signed-url",
        ]
    )


SENSITIVE_MARKERS = tuple(part.lower() for part in [
    "unit-test-api-secret",
    "unit-test-full-api-key",
    "signature=",
    "authenticated.example.test",
    "signed_query",
    "x-mbx-apikey",
    "raw credential",
    "select * from",
    "database-password",
    "traceback",
    "raw exception chain",
    "internal metadata",
    "signed-url",
])


class SentinelBoundaryError(RuntimeError):
    pass


@dataclass
class BoundaryObserver:
    boundary_calls: int = 0
    policy_calls: int = 0
    persistence_factory_calls: int = 0
    ensure_calls: int = 0
    consume_attempts: int = 0
    consume_successes: int = 0
    commit_attempts: int = 0
    commit_successes: int = 0
    close_calls: int = 0
    close_successes: int = 0
    close_failures: int = 0
    correlation_calls: int = 0
    signer_calls: int = 0
    post_calls: int = 0
    delete_calls: int = 0
    post_retry_count: int = 0
    delete_retry_count: int = 0
    events: list[str] = field(default_factory=list)


class _CountingPolicy:
    def __init__(self, delegate: LiveExecutionAuthorizationPolicy, observer: BoundaryObserver, *, fail: bool = False) -> None:
        self._delegate = delegate
        self._observer = observer
        self._fail = fail

    def authorize(self, *args, **kwargs):
        self._observer.policy_calls += 1
        self._observer.events.append("policy")
        if self._fail:
            self._observer.boundary_calls += 1
            raise SentinelBoundaryError(_sentinel())
        return self._delegate.authorize(*args, **kwargs)


class _CountingKillSwitchGate:
    def __init__(self, observer: BoundaryObserver, *, fail: bool = False) -> None:
        self._observer = observer
        self._fail = fail

    def require_released(self) -> None:
        self._observer.boundary_calls += 1
        self._observer.events.append("kill_switch")
        if self._fail:
            raise SentinelBoundaryError(_sentinel())


class _CountingKillSwitchPersistence:
    def __init__(self, observer: BoundaryObserver, *, fail_recovery_query: bool = False, **kwargs) -> None:
        self._delegate = KillSwitchPersistence(**kwargs)
        self._observer = observer
        self._fail_recovery_query = fail_recovery_query

    def ensure_available(self):
        return self._delegate.ensure_available()

    def has_unresolved_recovery(self, *args, **kwargs):
        self._observer.boundary_calls += 1
        self._observer.events.append("recovery_query")
        if self._fail_recovery_query:
            raise SentinelBoundaryError(_sentinel())
        return self._delegate.has_unresolved_recovery(*args, **kwargs)

    def close(self):
        return self._delegate.close()


class _CountingPermitPersistence:
    def __init__(self, observer: BoundaryObserver, *, fail_ensure: bool = False, fail_consume: bool = False, fail_close: bool = False, **kwargs) -> None:
        self._delegate = LiveExecutionPermitPersistence(session_factory=self._session_factory, **kwargs)
        self._observer = observer
        self._fail_ensure = fail_ensure
        self._fail_consume = fail_consume
        self._fail_close = fail_close

    def _session_factory(self, **kwargs):
        session = Session(**kwargs)

        @event.listens_for(session, "before_commit")
        def _before_commit(_session):
            self._observer.commit_attempts += 1
            self._observer.events.append("commit_attempt")

        @event.listens_for(session, "after_flush")
        def _after_flush(_session, _flush_context):
            self._observer.consume_successes += 1
            self._observer.events.append("consume_success")

        @event.listens_for(session, "after_commit")
        def _after_commit(_session):
            self._observer.commit_successes += 1
            self._observer.events.append("commit_success")

        return session

    def ensure_available(self):
        self._observer.ensure_calls += 1
        self._observer.events.append("permit_ensure")
        if self._fail_ensure:
            self._observer.boundary_calls += 1
            raise SentinelBoundaryError(_sentinel())
        return self._delegate.ensure_available()

    def consume(self, *args, **kwargs):
        self._observer.consume_attempts += 1
        self._observer.events.append("permit_consume")
        if self._fail_consume:
            self._observer.boundary_calls += 1
            raise SentinelBoundaryError(_sentinel())
        return self._delegate.consume(*args, **kwargs)

    def close(self):
        self._observer.close_calls += 1
        self._observer.events.append("permit_close")
        self._delegate.close()
        if self._fail_close:
            self._observer.boundary_calls += 1
            self._observer.close_failures += 1
            self._observer.events.append("permit_close_failure")
            raise SentinelBoundaryError(_sentinel())
        self._observer.close_successes += 1
        self._observer.events.append("permit_close_success")


class _CountingOrderTestClient(BinanceFuturesTestnetOrderTestClient):
    observer: BoundaryObserver | None = None
    fail_signer = False
    fail_transport = False

    def _signature(self, canonical_query: str) -> str:
        assert self.observer is not None
        self.observer.signer_calls += 1
        self.observer.events.append("signer")
        if self.fail_signer:
            self.observer.boundary_calls += 1
            raise SentinelBoundaryError(_sentinel())
        return super()._signature(canonical_query)


def _transport(observer: BoundaryObserver, *, fail: bool = False):
    def authenticated_post(url: str, body: bytes, timeout: int, headers: dict[str, str]) -> BinanceOrderTestHTTPResponse:
        observer.post_calls += 1
        observer.events.append("post_attempt")
        if fail:
            observer.boundary_calls += 1
            raise SentinelBoundaryError(_sentinel())
        return BinanceOrderTestHTTPResponse(200, url, {}, 2)

    return authenticated_post


class _ClientEngine(BinanceFuturesTestnetOrderTestEngine):
    client_cls = _CountingOrderTestClient

    def _client(self, config):
        return self.client_cls(config, http_get=self.http_get, authenticated_post=self.authenticated_post, env=self.env, now_ms_provider=self.now_ms_provider)


def _issue(env: dict[str, str], fingerprint):
    persistence = LiveExecutionPermitPersistence(env=env)
    persistence.ensure_available()
    try:
        return persistence.issue(fingerprint, issued_by="matrix-test", confirmation=ISSUE_CONFIRMATION)
    finally:
        persistence.close()


def _fingerprint(env: dict[str, str]):
    client = BinanceFuturesTestnetOrderTestClient(
        BinanceFuturesTestnetOrderTestConfig(),
        env=env,
        http_get=_http_get,
        authenticated_post=_transport(BoundaryObserver()),
        now_ms_provider=lambda: 123,
    )
    filters = client.fetch_exchange_filters()
    mark_price = client.fetch_mark_price("BTCUSDT")
    preview = client.build_order_test_preview(CLIENT_ORDER_ID, "BUY", "MARKET", 0.001, exchange_filters=filters, mark_price=mark_price)
    unsigned = client.build_unsigned_business_request(preview)
    return build_signed_order_test_create_from_final_request(unsigned)


def _permit_rows(env: dict[str, str]) -> list[tuple[str, str, int]]:
    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine, future=True) as session:
            return [
                (row.permit_id, row.state, row.version)
                for row in session.scalars(select(LiveExecutionPermitORM).order_by(LiveExecutionPermitORM.permit_id)).all()
            ]
    finally:
        engine.dispose()


def _audit_actions(env: dict[str, str]) -> list[str]:
    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine, future=True) as session:
            return [row.action for row in session.scalars(select(AuditEventORM).order_by(AuditEventORM.created_at, AuditEventORM.id)).all()]
    finally:
        engine.dispose()


def _permit_action_counts(env: dict[str, str]) -> dict[str, int]:
    actions = _audit_actions(env)
    return {action: actions.count(action) for action in set(actions)}


def _durable_surface(env: dict[str, str]) -> dict[str, Any]:
    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine, future=True) as session:
            return {
                "permits": [row.__dict__.copy() for row in session.scalars(select(LiveExecutionPermitORM)).all()],
                "audits": [row.__dict__.copy() for row in session.scalars(select(AuditEventORM)).all()],
                "recoveries": [row.__dict__.copy() for row in session.scalars(select(RecoveryEventORM)).all()],
                "intents": [row.__dict__.copy() for row in session.scalars(select(ExecutionIntentORM)).all()],
                "pairs": [row.__dict__.copy() for row in session.scalars(select(ProtectivePairORM)).all()],
                "identities": [row.__dict__.copy() for row in session.scalars(select(ExchangeOrderIdentityORM)).all()],
            }
    finally:
        engine.dispose()


def _assert_sanitized(*surfaces: Any) -> None:
    text = json.dumps(surfaces, default=str, sort_keys=True).lower()
    for marker in SENSITIVE_MARKERS:
        assert marker not in text


def _assert_field_level_sanitized(env: dict[str, str]) -> None:
    durable = _durable_surface(env)
    for rows in durable.values():
        for row in rows:
            for key, value in row.items():
                if key == "_sa_instance_state":
                    continue
                _assert_sanitized({key: value})


def _assert_exact_public_failure(result, *, decision: str, reason: str) -> None:
    assert result.decision == decision
    assert result.reason == reason
    _assert_result_sanitized(result)
    rendered = format_binance_futures_testnet_order_test_result(result)
    assert f"Decision                  : {decision}" in rendered
    assert f"Reason                    : {reason}" in rendered
    _assert_sanitized(rendered)


def _assert_result_sanitized(result) -> None:
    _assert_sanitized(result, result.to_dict())
    assert result.status == "FAIL"
    assert result.reason
    assert len(result.reason) <= 180


def _run_order_test(tmp_path, observer: BoundaryObserver, *, policy=None, permit_gate=None, fail_signer=False, fail_transport=False, permit=None):
    config_path = _write_config(tmp_path)
    _CountingOrderTestClient.observer = observer
    _CountingOrderTestClient.fail_signer = fail_signer
    _CountingOrderTestClient.fail_transport = fail_transport
    engine = _engine(
        tmp_path,
        env=observer.env,  # type: ignore[attr-defined]
        http_get=_http_get,
        authenticated_post=_transport(observer, fail=fail_transport),
        now_ms_provider=lambda: 123,
        authorization_policy=policy,
        permit_gate=permit_gate,
    )
    engine.__class__ = type("_MatrixOrderTestEngine", (_ClientEngine, engine.__class__), {})
    return engine.submit_test_order(
        CLIENT_ORDER_ID,
        "BUY",
        "MARKET",
        0.001,
        confirmation=CONFIRMATION,
        config_path=str(config_path),
        permit=permit,
    )


def _setup(tmp_path, observer: BoundaryObserver):
    env = durable_state_env("RELEASED")
    observer.env = env  # type: ignore[attr-defined]
    fingerprint = _fingerprint(env)
    permit = _issue(env, fingerprint)
    reference = LiveExecutionPermitReference(permit.permit_id, permit.version)
    return env, fingerprint, permit, reference


def _assert_pre_consume(env, observer, permit):
    rows = _permit_rows(env)
    assert rows == [(permit.permit_id, LiveExecutionPermitState.ISSUED.value, permit.version)]
    assert observer.consume_successes == 0
    assert observer.commit_attempts == 0
    assert observer.commit_successes == 0
    assert observer.close_failures == 0
    assert observer.signer_calls == 0
    assert observer.post_calls == 0
    assert observer.delete_calls == 0
    assert observer.post_retry_count == 0
    assert observer.delete_retry_count == 0
    actions = _permit_action_counts(env)
    assert actions.get("PERMIT_ISSUED", 0) == 1
    assert actions.get("PERMIT_CONSUMED", 0) == 0
    assert actions.get("PERMIT_REFUNDED", 0) == 0
    assert actions.get("PERMIT_REISSUED", 0) == 0
    assert actions.get("PERMIT_REPLACED", 0) == 0
    durable = _durable_surface(env)
    assert durable["recoveries"] == []
    assert durable["identities"] == []
    _assert_sanitized(durable)
    _assert_field_level_sanitized(env)


def _assert_post_consume(env, observer, permit):
    rows = _permit_rows(env)
    assert rows == [(permit.permit_id, LiveExecutionPermitState.CONSUMED.value, permit.version + 1)]
    assert observer.consume_successes == 1
    assert observer.commit_attempts == 1
    assert observer.commit_successes == 1
    actions = _permit_action_counts(env)
    assert actions.get("PERMIT_ISSUED", 0) == 1
    assert actions.get("PERMIT_CONSUMED", 0) == 1
    assert actions.get("PERMIT_REFUNDED", 0) == 0
    assert actions.get("PERMIT_REISSUED", 0) == 0
    assert actions.get("PERMIT_REPLACED", 0) == 0
    durable = _durable_surface(env)
    assert durable["recoveries"] == []
    assert durable["identities"] == []
    _assert_sanitized(durable)
    _assert_field_level_sanitized(env)


def _assert_no_refund_replacement_or_reuse(env, permit, *, expected_version: int) -> None:
    rows = _permit_rows(env)
    assert rows == [(permit.permit_id, LiveExecutionPermitState.CONSUMED.value, expected_version)]
    actions = _permit_action_counts(env)
    assert actions.get("PERMIT_ISSUED", 0) == 1
    assert actions.get("PERMIT_CONSUMED", 0) == 1
    assert actions.get("PERMIT_REFUNDED", 0) == 0
    assert actions.get("PERMIT_REISSUED", 0) == 0
    assert actions.get("PERMIT_REPLACED", 0) == 0


def _assert_reuse_denied(tmp_path, env, permit, reference, observer, *, signer_before: int, post_before: int, delete_before: int, consume_before: int) -> None:
    result = _run_order_test(
        tmp_path,
        observer,
        permit_gate=LiveExecutionPermitGate(env=env, correlation_id_provider=lambda: CORRELATION_ID),
        fail_transport=True,
        permit=reference,
    )
    assert result.status == "FAIL"
    assert result.decision == "PERMIT_ALREADY_CONSUMED"
    assert result.reason == "Permit is already consumed."
    assert observer.consume_successes == consume_before
    assert observer.signer_calls == signer_before
    assert observer.post_calls == post_before
    assert observer.delete_calls == delete_before
    _assert_no_refund_replacement_or_reuse(env, permit, expected_version=permit.version + 1)
    _assert_result_sanitized(result)


def _assert_events_order(observer: BoundaryObserver, *ordered: str) -> None:
    positions = [observer.events.index(event) for event in ordered]
    assert positions == sorted(positions)


def test_policy_failure_is_sanitized_and_blocks_all_downstream_activity(tmp_path):
    observer = BoundaryObserver()
    env, _fp, permit, reference = _setup(tmp_path, observer)
    policy = _CountingPolicy(LiveExecutionAuthorizationPolicy(env=env), observer, fail=True)

    result = _run_order_test(tmp_path, observer, policy=policy, permit=reference)

    assert observer.boundary_calls == 1
    assert observer.policy_calls == 1
    assert observer.persistence_factory_calls == 0
    _assert_pre_consume(env, observer, permit)
    _assert_exact_public_failure(result, decision="ORDER_TEST_REJECTED", reason="Test Order request failed safely.")


def test_persistence_factory_failure_is_sanitized_and_blocks_mutation(tmp_path):
    observer = BoundaryObserver()
    env, _fp, permit, reference = _setup(tmp_path, observer)

    def factory(**kwargs):
        observer.persistence_factory_calls += 1
        observer.boundary_calls += 1
        raise SentinelBoundaryError(_sentinel())

    gate = LiveExecutionPermitGate(env=env, permit_persistence_factory=factory)

    result = _run_order_test(tmp_path, observer, permit_gate=gate, permit=reference)

    assert observer.boundary_calls == 1
    assert observer.persistence_factory_calls == 1
    _assert_pre_consume(env, observer, permit)
    _assert_exact_public_failure(result, decision="PERMIT_GATE_UNAVAILABLE", reason="Live execution permit gate is unavailable.")


def test_permit_ensure_failure_is_sanitized_and_blocks_mutation(tmp_path):
    observer = BoundaryObserver()
    env, _fp, permit, reference = _setup(tmp_path, observer)

    def factory(**kwargs):
        observer.persistence_factory_calls += 1
        return _CountingPermitPersistence(observer, fail_ensure=True, **kwargs)

    gate = LiveExecutionPermitGate(env=env, permit_persistence_factory=factory)

    result = _run_order_test(tmp_path, observer, permit_gate=gate, permit=reference)

    assert observer.boundary_calls == 1
    assert observer.ensure_calls == 1
    _assert_pre_consume(env, observer, permit)
    _assert_exact_public_failure(result, decision="PERMIT_GATE_UNAVAILABLE", reason="Live execution permit gate is unavailable.")


def test_kill_switch_read_failure_is_sanitized_and_blocks_mutation(tmp_path):
    observer = BoundaryObserver()
    env, _fp, permit, reference = _setup(tmp_path, observer)
    policy = _CountingPolicy(
        LiveExecutionAuthorizationPolicy(env=env, kill_switch_gate=_CountingKillSwitchGate(observer, fail=True)),
        observer,
    )

    result = _run_order_test(tmp_path, observer, policy=policy, permit=reference)

    assert observer.boundary_calls == 1
    assert observer.policy_calls == 1
    _assert_pre_consume(env, observer, permit)
    _assert_exact_public_failure(result, decision="KILL_SWITCH_STATE_UNAVAILABLE", reason="Durable kill-switch state is unavailable.")


def test_recovery_query_failure_is_sanitized_and_blocks_mutation(tmp_path):
    observer = BoundaryObserver()
    env, _fp, permit, reference = _setup(tmp_path, observer)

    def persistence_factory(**kwargs):
        return _CountingKillSwitchPersistence(observer, fail_recovery_query=True, **kwargs)

    policy = _CountingPolicy(LiveExecutionAuthorizationPolicy(env=env, persistence_factory=persistence_factory), observer)

    result = _run_order_test(tmp_path, observer, policy=policy, permit=reference)

    assert observer.boundary_calls == 1
    assert observer.policy_calls == 1
    _assert_pre_consume(env, observer, permit)
    _assert_exact_public_failure(result, decision="PERSISTENCE_UNAVAILABLE", reason="Execution persistence is unavailable.")


def test_permit_consume_failure_is_sanitized_without_signing_or_transport(tmp_path):
    observer = BoundaryObserver()
    env, _fp, permit, reference = _setup(tmp_path, observer)

    def factory(**kwargs):
        observer.persistence_factory_calls += 1
        return _CountingPermitPersistence(observer, fail_consume=True, **kwargs)

    gate = LiveExecutionPermitGate(env=env, permit_persistence_factory=factory)

    result = _run_order_test(tmp_path, observer, permit_gate=gate, permit=reference)

    assert observer.boundary_calls == 1
    assert observer.consume_attempts == 1
    _assert_pre_consume(env, observer, permit)
    _assert_exact_public_failure(result, decision="PERMIT_GATE_UNAVAILABLE", reason="Live execution permit gate is unavailable.")


def test_correlation_provider_failure_is_sanitized_and_blocks_mutation(tmp_path):
    observer = BoundaryObserver()
    env, _fp, permit, reference = _setup(tmp_path, observer)

    def correlation_provider():
        observer.correlation_calls += 1
        observer.boundary_calls += 1
        raise SentinelBoundaryError(_sentinel())

    gate = LiveExecutionPermitGate(env=env, correlation_id_provider=correlation_provider)

    result = _run_order_test(tmp_path, observer, permit_gate=gate, permit=reference)

    assert observer.boundary_calls == 1
    assert observer.correlation_calls == 1
    _assert_pre_consume(env, observer, permit)
    _assert_exact_public_failure(result, decision="PERMIT_GATE_UNAVAILABLE", reason="Live execution permit gate is unavailable.")


def test_persistence_close_failure_is_sanitized_after_durable_consume(tmp_path):
    observer = BoundaryObserver()
    env, _fp, permit, reference = _setup(tmp_path, observer)

    def factory(**kwargs):
        observer.persistence_factory_calls += 1
        return _CountingPermitPersistence(observer, fail_close=True, **kwargs)

    gate = LiveExecutionPermitGate(env=env, correlation_id_provider=lambda: CORRELATION_ID, permit_persistence_factory=factory)

    result = _run_order_test(tmp_path, observer, permit_gate=gate, permit=reference)

    assert observer.boundary_calls == 1
    assert observer.consume_successes == 1
    assert observer.commit_attempts == 1
    assert observer.commit_successes == 1
    assert observer.close_calls == 1
    assert observer.close_successes == 0
    assert observer.close_failures == 1
    assert observer.signer_calls == 0
    assert observer.post_calls == 0
    assert observer.delete_calls == 0
    _assert_events_order(observer, "consume_success", "commit_success", "permit_close_failure")
    _assert_post_consume(env, observer, permit)
    _assert_no_refund_replacement_or_reuse(env, permit, expected_version=permit.version + 1)
    _assert_reuse_denied(
        tmp_path,
        env,
        permit,
        reference,
        observer,
        signer_before=observer.signer_calls,
        post_before=observer.post_calls,
        delete_before=observer.delete_calls,
        consume_before=observer.consume_successes,
    )
    _assert_exact_public_failure(result, decision="PERMIT_CONSUMED_NO_TRANSPORT", reason="Permit was consumed but mutation transport was blocked.")


def test_signer_failure_is_sanitized_after_durable_consume(tmp_path):
    observer = BoundaryObserver()
    env, _fp, permit, reference = _setup(tmp_path, observer)

    def factory(**kwargs):
        observer.persistence_factory_calls += 1
        return _CountingPermitPersistence(observer, **kwargs)

    gate = LiveExecutionPermitGate(
        env=env,
        correlation_id_provider=lambda: CORRELATION_ID,
        permit_persistence_factory=factory,
    )

    result = _run_order_test(tmp_path, observer, permit_gate=gate, fail_signer=True, permit=reference)

    assert observer.boundary_calls == 1
    assert observer.consume_successes == 1
    assert observer.commit_successes == 1
    assert observer.close_successes == 1
    assert observer.signer_calls == 1
    assert observer.post_calls == 0
    assert observer.delete_calls == 0
    assert observer.post_retry_count == 0
    assert observer.delete_retry_count == 0
    _assert_events_order(observer, "consume_success", "commit_success", "permit_close_success", "signer")
    _assert_post_consume(env, observer, permit)
    _assert_no_refund_replacement_or_reuse(env, permit, expected_version=permit.version + 1)
    _assert_reuse_denied(
        tmp_path,
        env,
        permit,
        reference,
        observer,
        signer_before=observer.signer_calls,
        post_before=observer.post_calls,
        delete_before=observer.delete_calls,
        consume_before=observer.consume_successes,
    )
    _assert_exact_public_failure(result, decision="ORDER_TEST_REJECTED", reason="Test Order request failed safely.")


def test_transport_failure_is_sanitized_after_durable_consume(tmp_path):
    observer = BoundaryObserver()
    env, _fp, permit, reference = _setup(tmp_path, observer)

    def factory(**kwargs):
        observer.persistence_factory_calls += 1
        return _CountingPermitPersistence(observer, **kwargs)

    gate = LiveExecutionPermitGate(
        env=env,
        correlation_id_provider=lambda: CORRELATION_ID,
        permit_persistence_factory=factory,
    )

    result = _run_order_test(tmp_path, observer, permit_gate=gate, fail_transport=True, permit=reference)

    assert observer.boundary_calls == 1
    assert observer.consume_successes == 1
    assert observer.commit_successes == 1
    assert observer.close_successes == 1
    assert observer.signer_calls == 1
    assert observer.post_calls == 1
    assert observer.delete_calls == 0
    assert observer.post_retry_count == 0
    assert observer.delete_retry_count == 0
    _assert_events_order(observer, "consume_success", "commit_success", "permit_close_success", "signer", "post_attempt")
    _assert_post_consume(env, observer, permit)
    _assert_no_refund_replacement_or_reuse(env, permit, expected_version=permit.version + 1)
    _assert_reuse_denied(
        tmp_path,
        env,
        permit,
        reference,
        observer,
        signer_before=observer.signer_calls,
        post_before=observer.post_calls,
        delete_before=observer.delete_calls,
        consume_before=observer.consume_successes,
    )
    _assert_exact_public_failure(result, decision="ORDER_TEST_REJECTED", reason="Test Order request failed safely.")
