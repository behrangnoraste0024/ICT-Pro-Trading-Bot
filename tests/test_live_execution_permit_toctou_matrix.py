from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.diagnostics.binance_futures_testnet_order_lifecycle_engine import BinanceFuturesTestnetOrderLifecycleEngine
from engine.diagnostics.binance_futures_testnet_order_test_engine import BinanceFuturesTestnetOrderTestEngine
from engine.diagnostics.binance_futures_testnet_protective_orders_engine import BinanceFuturesTestnetProtectiveOrdersEngine, ProtectiveAbort
from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import (
    BinanceFuturesTestnetOrderLifecycleClient,
    BinanceLifecycleHTTPResponse,
)
from infrastructure.exchanges.binance_futures_testnet_order_test_client import (
    BinanceFuturesTestnetOrderTestClient,
    BinanceOrderTestHTTPResponse,
)
from infrastructure.exchanges.binance_futures_testnet_protective_orders_client import (
    BinanceFuturesTestnetProtectiveOrdersClient,
)
from infrastructure.persistence.execution_orm import (
    AuditEventORM,
    ExchangeOrderIdentityORM,
    ExecutionIntentORM,
    LiveExecutionPermitORM,
    ProtectivePairORM,
    RecoveryEventORM,
)
from infrastructure.persistence.kill_switch_persistence import KillSwitchPersistence
from infrastructure.persistence.live_execution_authorization_policy import LiveExecutionAuthorizationPolicy
from infrastructure.persistence.live_execution_permit_persistence import (
    ISSUE_CONFIRMATION,
    REVOKE_CONFIRMATION,
    LiveExecutionPermitPersistence,
)
from infrastructure.persistence.protective_lifecycle_persistence import ProtectiveLifecyclePersistence
from infrastructure.security.live_execution_mutation_fingerprint_adapter import (
    build_lifecycle_cancel_from_final_request,
    build_lifecycle_create_from_final_request,
    build_protective_cancel_from_final_request,
    build_protective_create_from_final_request,
    build_signed_order_test_create_from_final_request,
)
from infrastructure.security.live_execution_permit_gate import LiveExecutionPermitGate
from models.binance_futures_testnet_order_lifecycle import BinanceFuturesTestnetOrderLifecycleConfig
from models.binance_futures_testnet_order_test import BinanceFuturesTestnetOrderTestConfig
from models.binance_futures_testnet_protective_orders import (
    BinanceFuturesTestnetProtectiveAlgoSummary,
    BinanceFuturesTestnetProtectiveJournal,
    BinanceFuturesTestnetProtectiveOrdersConfig,
)
from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit import LiveExecutionPermitState
from models.live_execution_permit_enforcement import LiveExecutionPermitReference
from tests.kill_switch_test_support import authorized_runtime_env, durable_state_env
from tests.test_binance_futures_testnet_order_lifecycle_engine import (
    _engine as _lifecycle_engine,
    _http_get as _lifecycle_http_get,
    _write_config as _write_lifecycle_config,
)
from tests.test_binance_futures_testnet_order_test_engine import (
    _engine as _order_test_engine,
    _http_get as _order_test_http_get,
    _write_config as _write_order_test_config,
)
from tests.test_protective_persistence_integration import (
    CONFIRMATION as PROTECTIVE_CONFIRMATION,
    PAIR_ID,
    STOP_ID,
    TP_ID,
    LifecycleTransport,
    _config as _protective_config,
    _database,
    _env as _protective_env,
    _http_get as _protective_http_get,
    _position,
)


class _CountingPermitPersistence:
    def __init__(self, observer: dict[str, int], **kwargs) -> None:
        self._observer = observer
        self._delegate = LiveExecutionPermitPersistence(**kwargs)

    def __getattr__(self, name):
        return getattr(self._delegate, name)

    def ensure_available(self):
        self._observer["ensure_count"] = self._observer.get("ensure_count", 0) + 1
        return self._delegate.ensure_available()

    def consume(self, *args, **kwargs):
        self._observer["consume_attempt_count"] = self._observer.get("consume_attempt_count", 0) + 1
        before_consume = self._observer.get("before_consume")
        if before_consume is not None:
            before_consume()
        result = self._delegate.consume(*args, **kwargs)
        self._observer["successful_consume_count"] = self._observer.get("successful_consume_count", 0) + 1
        self._observer["commit_count"] = self._observer.get("commit_count", 0) + 1
        return result

    def close(self):
        try:
            return self._delegate.close()
        finally:
            self._observer["close_count"] = self._observer.get("close_count", 0) + 1


def _gate(env: dict[str, str], observer: dict[str, int] | None = None) -> LiveExecutionPermitGate:
    if observer is None:
        return LiveExecutionPermitGate(env=env, correlation_id_provider=uuid4)

    def factory(**kwargs):
        return _CountingPermitPersistence(observer, **kwargs)

    return LiveExecutionPermitGate(
        env=env,
        permit_persistence_factory=factory,
        correlation_id_provider=uuid4,
    )


def _assert_policy_allowed(env: dict[str, str], operation: LiveExecutionOperation, *, current_pair_id: str | None = None) -> None:
    decision = LiveExecutionAuthorizationPolicy(env=env).authorize(
        operation,
        environment="TESTNET",
        symbol="BTCUSDT",
        confirmation_verified=True,
        credentials_configured=True,
        runtime_config_path=env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
        current_pair_id=current_pair_id,
    )
    assert decision.allowed is True
    assert decision.code == "AUTHORIZED"
    assert decision.operation == operation.value


def _assert_boundary_counts(
    observer: dict[str, int],
    *,
    ensure: int,
    consume_attempt: int,
    successful_consume: int,
    commit: int,
    close: int,
) -> None:
    assert observer.get("ensure_count", 0) == ensure
    assert observer.get("consume_attempt_count", 0) == consume_attempt
    assert observer.get("successful_consume_count", 0) == successful_consume
    assert observer.get("commit_count", 0) == commit
    assert observer.get("close_count", 0) == close


def _audit_records(env: dict[str, str]) -> list[tuple[str, str, object]]:
    from sqlalchemy import create_engine

    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine) as session:
            return [(row.action, row.result, row.metadata_json) for row in session.scalars(select(AuditEventORM).order_by(AuditEventORM.id)).all()]
    finally:
        engine.dispose()


def _recovery_records(env: dict[str, str]) -> list[tuple[str, str | None, str | None, object]]:
    from sqlalchemy import create_engine

    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine) as session:
            return [(row.event_type, row.from_state, row.to_state, row.reason_code, row.result) for row in session.scalars(select(RecoveryEventORM).order_by(RecoveryEventORM.id)).all()]
    finally:
        engine.dispose()


def _assert_no_duplicate_audit(env: dict[str, str], action: str) -> None:
    actions = [stored for stored in _audit_actions(env) if stored == action]
    assert len(actions) == len(set(range(len(actions))))


def _assert_sanitized(*items) -> None:
    forbidden = (
        "unit-test-api-secret",
        "unit-test-full-api-key",
        "signature=",
        "https://authenticated.example.test",
        "signed_query",
        "x-mbx-apikey",
        "raw credential",
        "select * from",
        "database-password",
        "traceback",
        "raw exception chain",
    )
    safe_output = json.dumps(items, default=str, sort_keys=True).lower()
    for marker in forbidden:
        assert marker not in safe_output


def _issue(env: dict[str, str], fingerprint) -> LiveExecutionPermitReference:
    persistence = LiveExecutionPermitPersistence(env=env)
    persistence.ensure_available()
    try:
        permit = persistence.issue(fingerprint, issued_by="toctou-test", confirmation=ISSUE_CONFIRMATION)
        return LiveExecutionPermitReference(permit.permit_id, permit.version)
    finally:
        persistence.close()


def _revoke(env: dict[str, str], reference: LiveExecutionPermitReference) -> None:
    persistence = LiveExecutionPermitPersistence(env=env)
    persistence.ensure_available()
    try:
        persistence.revoke(reference.permit_id, expected_version=reference.expected_version, reason_code="OPERATOR_REVOKED", confirmation=REVOKE_CONFIRMATION)
    finally:
        persistence.close()


def _bump_permit_version(env: dict[str, str], reference: LiveExecutionPermitReference) -> None:
    from sqlalchemy import create_engine

    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine) as session:
            permit = session.scalars(select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == reference.permit_id)).first()
            assert permit is not None
            permit.version = reference.expected_version + 1
            session.commit()
    finally:
        engine.dispose()


def _permit_state(env: dict[str, str], permit_id: str) -> tuple[str, int]:
    from sqlalchemy import create_engine

    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine) as session:
            permit = session.scalars(select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == permit_id)).first()
            assert permit is not None
            return permit.state, permit.version
    finally:
        engine.dispose()


def _audit_actions(env: dict[str, str]) -> list[str]:
    from sqlalchemy import create_engine

    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine) as session:
            return list(session.scalars(select(AuditEventORM.action).order_by(AuditEventORM.id)).all())
    finally:
        engine.dispose()


def _permit_consumed_count(env: dict[str, str], permit_id: str | None = None) -> int:
    from sqlalchemy import create_engine

    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine) as session:
            statement = select(AuditEventORM).where(AuditEventORM.action == "PERMIT_CONSUMED")
            if permit_id is not None:
                statement = statement.where(AuditEventORM.metadata_json["permit_id"].as_string() == permit_id)
            return len(session.scalars(statement).all())
    finally:
        engine.dispose()


def _identity_rows(env: dict[str, str]) -> list[tuple[str, str, str]]:
    from sqlalchemy import create_engine

    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine) as session:
            return [
                (row.leg_type, row.client_algo_id, row.status)
                for row in session.scalars(select(ExchangeOrderIdentityORM).order_by(ExchangeOrderIdentityORM.leg_type)).all()
            ]
    finally:
        engine.dispose()


def _identity_snapshot(env: dict[str, str]) -> list[tuple[str, str, str, str, str | None, str, str, str, str]]:
    from sqlalchemy import create_engine

    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine) as session:
            rows = (
                session.query(ExchangeOrderIdentityORM, ProtectivePairORM)
                .join(ProtectivePairORM, ExchangeOrderIdentityORM.protective_pair_id == ProtectivePairORM.id)
                .order_by(ExchangeOrderIdentityORM.client_algo_id, ExchangeOrderIdentityORM.id)
                .all()
            )
            return [
                (
                    str(identity.id),
                    str(identity.protective_pair_id),
                    pair.pair_id,
                    identity.client_algo_id,
                    identity.exchange_order_id,
                    identity.symbol,
                    pair.direction,
                    identity.leg_type,
                    identity.status,
                )
                for identity, pair in rows
            ]
    finally:
        engine.dispose()


def _seed_lifecycle_cancel_identity(env: dict[str, str], client_order_id: str) -> list[tuple[str, str, str, str, str | None, str, str, str, str]]:
    from sqlalchemy import create_engine

    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    now = datetime.now(UTC)
    intent_id = uuid4()
    pair_pk = uuid4()
    identity_id = uuid4()
    take_profit_identity_id = uuid4()
    correlation_id = uuid4()
    try:
        with Session(engine) as session:
            session.add(
                ExecutionIntentORM(
                    id=intent_id,
                    correlation_id=correlation_id,
                    environment="BINANCE_FUTURES_TESTNET",
                    symbol="BTCUSDT",
                    intent_type="PROTECTIVE_PAIR_CREATE",
                    state="PERSISTED",
                    requested_quantity=Decimal("0.001"),
                    requested_price=Decimal("49500"),
                    failure_code=None,
                    created_at=now,
                    updated_at=now,
                    version=1,
                )
            )
            session.add(
                ProtectivePairORM(
                    id=pair_pk,
                    pair_id=f"lifecycle-{client_order_id}",
                    correlation_id=correlation_id,
                    execution_intent_id=intent_id,
                    environment="BINANCE_FUTURES_TESTNET",
                    symbol="BTCUSDT",
                    position_side="BOTH",
                    direction="BUY",
                    quantity=Decimal("0.001"),
                    state="PAIR_ACTIVE",
                    recovery_required=False,
                    blocking_reason=None,
                    created_at=now,
                    updated_at=now,
                    version=1,
                )
            )
            session.add(
                ExchangeOrderIdentityORM(
                    id=identity_id,
                    protective_pair_id=pair_pk,
                    environment="BINANCE_FUTURES_TESTNET",
                    symbol="BTCUSDT",
                    leg_type="STOP",
                    client_algo_id=client_order_id,
                    exchange_algo_id=None,
                    exchange_order_id="1",
                    status="NEW",
                    trigger_price=Decimal("49400"),
                    created_at=now,
                    updated_at=now,
                    version=1,
                )
            )
            session.add(
                ExchangeOrderIdentityORM(
                    id=take_profit_identity_id,
                    protective_pair_id=pair_pk,
                    environment="BINANCE_FUTURES_TESTNET",
                    symbol="BTCUSDT",
                    leg_type="TAKE_PROFIT",
                    client_algo_id=f"{client_order_id}-tp",
                    exchange_algo_id=None,
                    exchange_order_id="2",
                    status="NEW",
                    trigger_price=Decimal("49700"),
                    created_at=now,
                    updated_at=now,
                    version=1,
                )
            )
            session.commit()
        return _identity_snapshot(env)
    finally:
        engine.dispose()
def _protective_pair_state(env: dict[str, str]) -> tuple[str, bool] | None:
    from sqlalchemy import create_engine

    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine) as session:
            pair = session.scalars(select(ProtectivePairORM)).first()
            if pair is None:
                return None
            return pair.state, bool(pair.recovery_required)
    finally:
        engine.dispose()


def _recovery_reason_codes(env: dict[str, str]) -> list[str | None]:
    from sqlalchemy import create_engine

    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine) as session:
            return list(session.scalars(select(RecoveryEventORM.reason_code).order_by(RecoveryEventORM.id)).all())
    finally:
        engine.dispose()


def _intent_states(env: dict[str, str]) -> list[tuple[str, str]]:
    from sqlalchemy import create_engine

    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine) as session:
            return [(row.intent_type, row.state) for row in session.scalars(select(ExecutionIntentORM).order_by(ExecutionIntentORM.intent_type, ExecutionIntentORM.id)).all()]
    finally:
        engine.dispose()


def _disable_runtime(env: dict[str, str]) -> None:
    path = Path(env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["live_trading_enabled"] = False
    path.write_text(json.dumps(data), encoding="utf-8")


def _engage_kill_switch(env: dict[str, str]) -> None:
    persistence = KillSwitchPersistence(env=env)
    persistence.ensure_available()
    try:
        current = persistence.current()
        if current.state != "ENGAGED":
            persistence.engage()
    finally:
        persistence.close()


def _protective_preview(tmp_path: Path, env: dict[str, str], stop_id: str = STOP_ID, tp_id: str = TP_ID):
    config = BinanceFuturesTestnetProtectiveOrdersConfig().to_dict()
    config_path = _protective_config(tmp_path)
    config.update(json.loads(config_path.read_text(encoding="utf-8")))
    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(**config), env=env)
    position = client.require_protectable_position(_position())
    filters = client.parse_exchange_filters(
        {"symbols": [{"symbol": "BTCUSDT", "filters": [{"filterType": "PRICE_FILTER", "minPrice": "1", "maxPrice": "1000000", "tickSize": "0.10"}]}]}
    )
    return client.build_preview(PAIR_ID, stop_id, tp_id, position, filters, None, None)


def _active_protective_order(label: str, preview) -> BinanceFuturesTestnetProtectiveAlgoSummary:
    return BinanceFuturesTestnetProtectiveAlgoSummary(
        symbol="BTCUSDT",
        client_algo_id=preview.stop_client_algo_id if label == "STOP" else preview.take_profit_client_algo_id,
        algo_id=f"algo-{label.lower()}",
        algo_type="CONDITIONAL",
        side=preview.protective_side,
        position_side="BOTH",
        order_type="STOP_MARKET" if label == "STOP" else "TAKE_PROFIT_MARKET",
        trigger_price=preview.stop_trigger if label == "STOP" else preview.take_profit_trigger,
        algo_status="NEW",
        actual_order_id=f"order-{label.lower()}",
        close_position=True,
        working_type="MARK_PRICE",
        price_protect=True,
    )


def _seed_active_protective_pair(tmp_path: Path, env: dict[str, str]):
    preview = _protective_preview(tmp_path, env)
    position = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), env=env).require_protectable_position(_position())
    persistence = ProtectiveLifecyclePersistence(env=env)
    persistence.ensure_available()
    try:
        state = persistence.prepare_lifecycle(PAIR_ID, STOP_ID, TP_ID, position, preview)
        persistence.mark_create_transmitted(state)
        persistence.confirm_create(state, "STOP", _active_protective_order("STOP", preview))
        persistence.confirm_create(state, "TAKE_PROFIT", _active_protective_order("TAKE_PROFIT", preview))
        return preview, state
    finally:
        persistence.close()


def _protective_permits(tmp_path: Path, env: dict[str, str], stop_id: str = STOP_ID, tp_id: str = TP_ID) -> tuple[LiveExecutionPermitReference, LiveExecutionPermitReference, LiveExecutionPermitReference, LiveExecutionPermitReference]:
    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), env=env)
    preview = _protective_preview(tmp_path, env, stop_id, tp_id)
    return (
        _issue(env, build_protective_create_from_final_request(client.build_create_unsigned_business_request(preview, "STOP"))),
        _issue(env, build_protective_create_from_final_request(client.build_create_unsigned_business_request(preview, "TAKE_PROFIT"))),
        _issue(env, build_protective_cancel_from_final_request(client.build_cancel_unsigned_business_request(preview, "TAKE_PROFIT"))),
        _issue(env, build_protective_cancel_from_final_request(client.build_cancel_unsigned_business_request(preview, "STOP"))),
    )


class _ProtectiveRecorder(LifecycleTransport):
    def __init__(self, env: dict[str, str] | None = None, transition_after_posts: int | None = None) -> None:
        super().__init__()
        self.env = env
        self.transition_after_posts = transition_after_posts
        self.post_count = 0
        self.delete_count = 0
        self.post_retry_count = 0
        self.delete_retry_count = 0
        self.signature_count = 0
        self.transition_observed = False

    def sign(self, canonical: str) -> str:
        self.signature_count += 1
        raise AssertionError("signing must be blocked before transport")

    def __call__(self, method, url, body, timeout, headers):
        if method == "POST":
            self.post_count += 1
        if method == "DELETE":
            self.delete_count += 1
        if self.env is not None and self.transition_after_posts is not None and method == "POST" and self.post_count == self.transition_after_posts:
            response = super().__call__(method, url, body, timeout, headers)
            _assert_policy_allowed(self.env, LiveExecutionOperation.PROTECTIVE_CANCEL, current_pair_id=PAIR_ID)
            _engage_kill_switch(self.env)
            self.transition_observed = True
            return response
        if method == "DELETE":
            raise AssertionError("DELETE must be blocked before transport")
        return super().__call__(method, url, body, timeout, headers)


def _protective_engine(tmp_path: Path, env: dict[str, str], transport, observer: dict[str, int] | None = None) -> BinanceFuturesTestnetProtectiveOrdersEngine:
    return BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=env,
        http_get=_protective_http_get,
        authenticated_request=transport,
        now_ms_provider=lambda: 1000,
        permit_gate=_gate(env, observer),
        persistence_factory=ProtectiveLifecyclePersistence,
    )


def _lifecycle_unsigned(tmp_path: Path, env: dict[str, str]):
    client = BinanceFuturesTestnetOrderLifecycleClient(BinanceFuturesTestnetOrderLifecycleConfig(), env=env)
    filters = client.parse_exchange_filters(
        {"symbols": [{"symbol": "BTCUSDT", "filters": [
            {"filterType": "PRICE_FILTER", "minPrice": "1", "maxPrice": "1000000", "tickSize": "0.10"},
            {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "100", "stepSize": "0.001"},
            {"filterType": "MIN_NOTIONAL", "notional": "5"},
        ]}]}
    )
    ticker = client.parse_book_ticker({"symbol": "BTCUSDT", "bidPrice": "50000", "askPrice": "50001", "bidQty": "1", "askQty": "1"})
    preview = client.build_lifecycle_preview("lifecycle-toctou-001", "smcbot-lifecycle-001", "BUY", 0.001, None, filters, ticker)
    return preview, client.build_create_unsigned_business_request(preview), client.build_cancel_unsigned_business_request("smcbot-lifecycle-001")


def _lifecycle_permits(tmp_path: Path, env: dict[str, str]) -> tuple[LiveExecutionPermitReference, LiveExecutionPermitReference]:
    _preview, create_unsigned, cancel_unsigned = _lifecycle_unsigned(tmp_path, env)
    return (
        _issue(env, build_lifecycle_create_from_final_request(create_unsigned)),
        _issue(env, build_lifecycle_cancel_from_final_request(cancel_unsigned)),
    )


class _LifecycleRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.statuses = ["NEW", "NEW", "CANCELED", "CANCELED"]
        self.post_count = 0
        self.delete_count = 0
        self.post_retry_count = 0
        self.delete_retry_count = 0
        self.signature_count = 0

    def __call__(self, method, url, body, timeout, headers):
        body_text = body.decode("utf-8")
        self.calls.append((method, url, body_text))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, [{"symbol": "BTCUSDT", "positionAmt": "0"}], 10)
        if method == "POST":
            self.post_count += 1
            return BinanceLifecycleHTTPResponse(200, url, {"symbol": "BTCUSDT", "clientOrderId": "smcbot-lifecycle-001", "orderId": 1, "side": "BUY", "type": "LIMIT", "timeInForce": "GTX", "price": "49500", "origQty": "0.001", "executedQty": "0", "status": self.statuses.pop(0)}, 10)
        if method == "DELETE":
            self.delete_count += 1
            raise AssertionError("DELETE must be blocked before transport")
        status = self.statuses.pop(0)
        return BinanceLifecycleHTTPResponse(200, url, {"symbol": "BTCUSDT", "clientOrderId": "smcbot-lifecycle-001", "orderId": 1, "side": "BUY", "type": "LIMIT", "timeInForce": "GTX", "price": "49500", "origQty": "0.001", "executedQty": "0", "status": status}, 10)

    def sign(self, canonical: str) -> str:
        self.signature_count += 1
        raise AssertionError("signing must be blocked before transport")


def _lifecycle_test_engine(tmp_path: Path, env: dict[str, str], transport, observer: dict[str, int] | None = None) -> BinanceFuturesTestnetOrderLifecycleEngine:
    return _lifecycle_engine(
        tmp_path,
        env=env,
        http_get=_lifecycle_http_get,
        authenticated_request=transport,
        now_ms_provider=lambda: 1000,
        permit_gate=_gate(env, observer),
    )


def _order_test_preview_and_request(env: dict[str, str]):
    client = BinanceFuturesTestnetOrderTestClient(BinanceFuturesTestnetOrderTestConfig(), env=env)
    filters = client.parse_exchange_filters(
        {"symbols": [{"symbol": "BTCUSDT", "filters": [
            {"filterType": "PRICE_FILTER", "minPrice": "1", "maxPrice": "1000000", "tickSize": "0.10"},
            {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "100", "stepSize": "0.001"},
            {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "maxQty": "100", "stepSize": "0.001"},
            {"filterType": "MIN_NOTIONAL", "notional": "5"},
        ]}]}
    )
    preview = client.build_order_test_preview("smcbot-test-toctou", "BUY", "LIMIT", 0.001, 50000.0, "GTC", False, exchange_filters=filters)
    return preview, client.build_unsigned_business_request(preview)


class _OrderTestRecorder:
    def __init__(self) -> None:
        self.post_count = 0
        self.post_retry_count = 0
        self.signature_count = 0
        self.unsigned_requests = []

    def post(self, url, body, timeout, headers):
        self.post_count += 1
        raise AssertionError("POST must be blocked before transport")

    def sign(self, canonical: str) -> str:
        self.signature_count += 1
        raise AssertionError("signing must be blocked before transport")


def _order_test_real_client(env: dict[str, str], recorder: _OrderTestRecorder) -> BinanceFuturesTestnetOrderTestClient:
    client = BinanceFuturesTestnetOrderTestClient(
        BinanceFuturesTestnetOrderTestConfig(),
        env=env,
        http_get=_order_test_http_get,
        authenticated_post=recorder.post,
        now_ms_provider=lambda: 1000,
    )
    original = client.build_unsigned_business_request

    def recording_build(preview):
        request = original(preview)
        recorder.unsigned_requests.append(request)
        return request

    client.build_unsigned_business_request = recording_build
    client._signature = recorder.sign
    return client


def _order_test_real_engine(tmp_path: Path, env: dict[str, str], client: BinanceFuturesTestnetOrderTestClient, observer: dict[str, int] | None = None) -> BinanceFuturesTestnetOrderTestEngine:
    engine = _order_test_engine(
        tmp_path,
        env=env,
        http_get=_order_test_http_get,
        authenticated_post=client.authenticated_post,
        now_ms_provider=lambda: 1000,
        permit_gate=_gate(env, observer),
    )
    engine._client = lambda config: client
    return engine


def test_protective_create_rechecks_runtime_disable_before_post(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path / "protective-create")
    env = _protective_env(database_url)
    stop_create, take_create, take_cancel, stop_cancel = _protective_permits(tmp_path, env)
    observer: dict[str, int] = {}
    calls = {"time": 0}

    def http_get(url, timeout):
        if url.endswith("/fapi/v1/time"):
            calls["time"] += 1
            if calls["time"] == 1:
                _assert_policy_allowed(env, LiveExecutionOperation.PROTECTIVE_CREATE, current_pair_id=PAIR_ID)
                _disable_runtime(env)
        return _protective_http_get(url, timeout)

    transport = _ProtectiveRecorder()
    engine = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=env,
        http_get=http_get,
        authenticated_request=transport,
        now_ms_provider=lambda: 1000,
        permit_gate=_gate(env, observer),
        persistence_factory=ProtectiveLifecyclePersistence,
    )

    result = engine.run_protective_lifecycle(
        PAIR_ID,
        STOP_ID,
        TP_ID,
        confirmation=PROTECTIVE_CONFIRMATION,
        config_path=str(_protective_config(tmp_path)),
        stop_create_permit=stop_create,
        take_profit_create_permit=take_create,
        take_profit_cancel_permit=take_cancel,
        stop_cancel_permit=stop_cancel,
    )

    assert result.decision == "LIVE_TRADING_DISABLED"
    assert result.create_request_transmitted is False
    assert result.cancel_request_transmitted is False
    assert result.recovery_required is False
    assert result.create_requests == []
    assert result.cancel_requests == []
    assert transport.post_count == 0
    assert transport.delete_count == 0
    assert transport.post_retry_count == 0
    assert transport.delete_retry_count == 0
    assert transport.signature_count == 0
    _assert_boundary_counts(observer, ensure=0, consume_attempt=0, successful_consume=0, commit=0, close=0)
    assert _identity_rows(env) == []
    assert _recovery_records(env) == []
    assert _permit_consumed_count(env) == 0
    assert "PERMIT_CONSUMED" not in _audit_actions(env)
    assert _permit_state(env, stop_create.permit_id) == (LiveExecutionPermitState.ISSUED.value, stop_create.expected_version)
    assert _protective_pair_state(env) == ("FAILED_SAFE", False)
    _assert_sanitized(result.to_dict(), _audit_records(env), _recovery_records(env))
    database_engine.dispose()


def test_protective_cancel_rechecks_kill_switch_before_delete(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path / "protective-cancel")
    env = _protective_env(database_url)
    stop_create, take_create, take_cancel, stop_cancel = _protective_permits(tmp_path, env)
    preview, state = _seed_active_protective_pair(tmp_path, env)
    observer: dict[str, int] = {}
    transport = _ProtectiveRecorder()
    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), env=env)
    client._signature = transport.sign
    persistence = ProtectiveLifecyclePersistence(env=env)
    persistence.ensure_available()

    _assert_policy_allowed(env, LiveExecutionOperation.PROTECTIVE_CANCEL, current_pair_id=PAIR_ID)
    assert _identity_rows(env) == [("STOP", STOP_ID, "NEW"), ("TAKE_PROFIT", TP_ID, "NEW")]
    assert _protective_pair_state(env) == ("PAIR_ACTIVE", False)
    _engage_kill_switch(env)

    try:
        unsigned = client.build_cancel_unsigned_business_request(preview, "TAKE_PROFIT")
        fingerprint = build_protective_cancel_from_final_request(unsigned)
        try:
            _gate(env, observer).authorize_and_consume(
                operation=LiveExecutionOperation.PROTECTIVE_CANCEL,
                fingerprint=fingerprint,
                permit_reference=take_cancel,
                confirmation_verified=True,
                credentials_configured=True,
                runtime_config_path=str(_protective_config(tmp_path)),
                current_pair_id=PAIR_ID,
            )
        except Exception as exc:
            assert getattr(exc, "code", None) == "KILL_SWITCH_ENGAGED"
            assert getattr(exc, "permit_consumed", False) is False
        else:
            raise AssertionError("cancel boundary must fail closed before DELETE")
    finally:
        persistence.close()

    assert transport.post_count == 0
    assert transport.delete_count == 0
    assert transport.post_retry_count == 0
    assert transport.delete_retry_count == 0
    assert transport.signature_count == 0
    _assert_boundary_counts(observer, ensure=0, consume_attempt=0, successful_consume=0, commit=0, close=0)
    assert _permit_consumed_count(env, take_cancel.permit_id) == 0
    assert _identity_rows(env) == [("STOP", STOP_ID, "NEW"), ("TAKE_PROFIT", TP_ID, "NEW")]
    assert len(_identity_rows(env)) == 2
    assert _protective_pair_state(env) == ("PAIR_ACTIVE", False)
    assert _recovery_records(env) == []
    assert "PERMIT_CONSUMED" not in _audit_actions(env)
    _assert_sanitized({"decision": "KILL_SWITCH_ENGAGED"}, _audit_records(env), _recovery_records(env))
    database_engine.dispose()


def test_lifecycle_create_rechecks_revoked_permit_before_post(tmp_path: Path) -> None:
    env = durable_state_env("RELEASED")
    create_permit, cancel_permit = _lifecycle_permits(tmp_path, env)
    _assert_policy_allowed(env, LiveExecutionOperation.ORDER_LIFECYCLE_CREATE)
    assert _permit_state(env, create_permit.permit_id) == (LiveExecutionPermitState.ISSUED.value, create_permit.expected_version)
    _revoke(env, create_permit)
    observer: dict[str, int] = {}
    transport = _LifecycleRecorder()
    engine = _lifecycle_test_engine(tmp_path, env, transport, observer)

    result = engine.run_lifecycle(
        "lifecycle-toctou-001",
        "smcbot-lifecycle-001",
        "BUY",
        0.001,
        confirmation=BinanceFuturesTestnetOrderLifecycleConfig().lifecycle_confirmation_phrase,
        config_path=str(_write_lifecycle_config(tmp_path)),
        create_permit=create_permit,
        cancel_permit=cancel_permit,
    )

    assert result.decision == "PERMIT_ALREADY_REVOKED"
    assert result.create_request_transmitted is False
    assert result.cancel_request_transmitted is False
    assert result.signature_generated is False
    assert result.recovery_required is False
    assert result.phase == "FAILED"
    assert transport.post_count == 0
    assert transport.delete_count == 0
    assert transport.post_retry_count == 0
    assert transport.delete_retry_count == 0
    assert transport.signature_count == 0
    _assert_boundary_counts(observer, ensure=1, consume_attempt=1, successful_consume=0, commit=0, close=1)
    assert _permit_consumed_count(env, create_permit.permit_id) == 0
    assert _permit_state(env, create_permit.permit_id) == (LiveExecutionPermitState.REVOKED.value, create_permit.expected_version + 1)
    assert _identity_rows(env) == []
    assert _recovery_records(env) == []
    assert "PERMIT_CONSUMED" not in _audit_actions(env)
    _assert_sanitized(result.to_dict(), _audit_records(env), _recovery_records(env))


def test_lifecycle_cancel_rechecks_permit_version_before_delete(tmp_path: Path) -> None:
    env = durable_state_env("RELEASED")
    client_order_id = "smcbot-lifecycle-001"
    _preview, _create_unsigned, cancel_unsigned = _lifecycle_unsigned(tmp_path, env)
    cancel_permit = _issue(env, build_lifecycle_cancel_from_final_request(cancel_unsigned))
    _assert_policy_allowed(env, LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL)
    assert _permit_state(env, cancel_permit.permit_id) == (LiveExecutionPermitState.ISSUED.value, cancel_permit.expected_version)
    assert _permit_consumed_count(env, cancel_permit.permit_id) == 0
    _bump_permit_version(env, cancel_permit)
    identity_before: list[tuple[str, str, str, str, str | None, str, str, str, str]] = []

    def seed_identity_before_consume() -> None:
        nonlocal identity_before
        if not identity_before:
            identity_before = _seed_lifecycle_cancel_identity(env, client_order_id)
            matching_before = [row for row in identity_before if row[3] == client_order_id]
            assert len(matching_before) == 1
            assert matching_before[0][4] == "1"
            assert matching_before[0][5] == "BTCUSDT"
            assert matching_before[0][7] == "STOP"
            assert matching_before[0][8] == "NEW"

    observer = {"before_consume": seed_identity_before_consume}
    transport = _LifecycleRecorder()
    engine = _lifecycle_test_engine(tmp_path, env, transport, observer)

    result = engine.recovery_cancel(
        client_order_id,
        confirmation=BinanceFuturesTestnetOrderLifecycleConfig().cancel_confirmation_phrase,
        config_path=str(_write_lifecycle_config(tmp_path)),
        cancel_permit=cancel_permit,
    )

    identity_after = _identity_snapshot(env)
    assert identity_before
    assert result.decision == "PERMIT_VERSION_CONFLICT"
    assert result.create_request_transmitted is False
    assert result.cancel_request_transmitted is False
    assert result.signature_generated is False
    assert result.recovery_required is False
    assert transport.post_count == 0
    assert transport.delete_count == 0
    assert transport.post_retry_count == 0
    assert transport.delete_retry_count == 0
    assert transport.signature_count == 0
    _assert_boundary_counts(observer, ensure=1, consume_attempt=1, successful_consume=0, commit=0, close=1)
    assert _permit_consumed_count(env, cancel_permit.permit_id) == 0
    assert _permit_state(env, cancel_permit.permit_id) == (LiveExecutionPermitState.ISSUED.value, cancel_permit.expected_version + 1)
    assert identity_after == identity_before
    matching_after = [row for row in identity_after if row[3] == client_order_id]
    assert len(matching_after) == 1
    assert matching_after[0][4] == "1"
    assert matching_after[0][8] == "NEW"
    assert _recovery_records(env) == []
    assert "PERMIT_CONSUMED" not in _audit_actions(env)
    _assert_sanitized(result.to_dict(), identity_before, identity_after, _audit_records(env), _recovery_records(env))


def test_protective_create_rechecks_new_recovery_evidence_before_post(tmp_path: Path) -> None:
    database_url, database_engine = _database(tmp_path / "protective-recovery-evidence")
    env = _protective_env(database_url)
    stop_create, take_create, take_cancel, stop_cancel = _protective_permits(tmp_path, env)
    observer: dict[str, int] = {}
    calls = {"time": 0}

    def http_get(url, timeout):
        if url.endswith("/fapi/v1/time"):
            calls["time"] += 1
            if calls["time"] == 1:
                _assert_policy_allowed(env, LiveExecutionOperation.PROTECTIVE_CREATE, current_pair_id=PAIR_ID)
                persistence = ProtectiveLifecyclePersistence(env=env)
                persistence.ensure_available()
                try:
                    preview = _protective_preview(tmp_path, env, "smcbot-protect-sl-new", "smcbot-protect-tp-new")
                    position = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), env=env).require_protectable_position(_position())
                    state = persistence.prepare_lifecycle("other-pair", "smcbot-protect-sl-new", "smcbot-protect-tp-new", position, preview)
                    persistence.mark_recovery_required(state, "CREATE", "TOCTOU_RECOVERY_EVIDENCE")
                finally:
                    persistence.close()
        return _protective_http_get(url, timeout)

    transport = _ProtectiveRecorder()
    engine = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=env,
        http_get=http_get,
        authenticated_request=transport,
        now_ms_provider=lambda: 1000,
        permit_gate=_gate(env, observer),
        persistence_factory=ProtectiveLifecyclePersistence,
    )

    result = engine.run_protective_lifecycle(
        PAIR_ID,
        STOP_ID,
        TP_ID,
        confirmation=PROTECTIVE_CONFIRMATION,
        config_path=str(_protective_config(tmp_path)),
        stop_create_permit=stop_create,
        take_profit_create_permit=take_create,
        take_profit_cancel_permit=take_cancel,
        stop_cancel_permit=stop_cancel,
    )

    assert result.decision == "RECOVERY_REQUIRED"
    assert result.create_request_transmitted is False
    assert result.cancel_request_transmitted is False
    assert result.recovery_required is False
    assert transport.post_count == 0
    assert transport.delete_count == 0
    assert transport.post_retry_count == 0
    assert transport.delete_retry_count == 0
    assert transport.signature_count == 0
    _assert_boundary_counts(observer, ensure=0, consume_attempt=0, successful_consume=0, commit=0, close=0)
    assert _permit_consumed_count(env, stop_create.permit_id) == 0
    assert _identity_rows(env) == []
    with Session(database_engine) as session:
        pairs = list(session.scalars(select(ProtectivePairORM).order_by(ProtectivePairORM.pair_id)).all())
        assert [(pair.pair_id, pair.state, pair.recovery_required) for pair in pairs] == [
            ("other-pair", "RECOVERY_REQUIRED", True),
            (PAIR_ID, "FAILED_SAFE", False),
        ]
    assert _recovery_reason_codes(env) == ["TOCTOU_RECOVERY_EVIDENCE"]
    assert "PERMIT_CONSUMED" not in _audit_actions(env)
    _assert_sanitized(result.to_dict(), _audit_records(env), _recovery_records(env))
    database_engine.dispose()


def test_order_test_rechecks_final_policy_before_signing_and_post(tmp_path: Path) -> None:
    env = durable_state_env("RELEASED")
    preview, unsigned = _order_test_preview_and_request(env)
    permit = _issue(env, build_signed_order_test_create_from_final_request(unsigned))
    observer: dict[str, int] = {}
    recorder = _OrderTestRecorder()
    client = _order_test_real_client(env, recorder)
    calls = {"time": 0}

    def http_get(url, timeout):
        if url.endswith("/fapi/v1/time"):
            calls["time"] += 1
            if calls["time"] == 1:
                _assert_policy_allowed(env, LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE)
                _disable_runtime(env)
        return _order_test_http_get(url, timeout)

    client.http_get = http_get
    engine = _order_test_real_engine(tmp_path, env, client, observer)

    result = engine.submit_test_order(
        preview.client_order_id,
        preview.side,
        preview.order_type,
        float(preview.quantity),
        float(preview.price),
        preview.time_in_force,
        preview.reduce_only,
        confirmation=BinanceFuturesTestnetOrderTestConfig().network_confirmation_phrase,
        config_path=str(_write_order_test_config(tmp_path)),
        permit=permit,
    )

    assert result.decision == "LIVE_TRADING_DISABLED"
    assert result.signature_generated is False
    assert result.test_order_request_transmitted is False
    assert recorder.signature_count == 0
    assert recorder.post_count == 0
    assert recorder.post_retry_count == 0
    _assert_boundary_counts(observer, ensure=0, consume_attempt=0, successful_consume=0, commit=0, close=0)
    assert _permit_consumed_count(env, permit.permit_id) == 0
    assert _permit_state(env, permit.permit_id) == (LiveExecutionPermitState.ISSUED.value, permit.expected_version)
    assert _recovery_records(env) == []
    assert _identity_rows(env) == []
    assert recorder.unsigned_requests
    captured = build_signed_order_test_create_from_final_request(recorder.unsigned_requests[-1])
    assert captured.operation == LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE
    transport_params = dict(recorder.unsigned_requests[-1])
    assert transport_params["symbol"] == "BTCUSDT"
    assert "timestamp" not in transport_params
    assert "recvWindow" not in transport_params
    assert "signature" not in transport_params
    assert "PERMIT_CONSUMED" not in _audit_actions(env)
    _assert_sanitized(result.to_dict(), _audit_records(env), _recovery_records(env), getattr(captured, "fingerprint_context", {}), transport_params)