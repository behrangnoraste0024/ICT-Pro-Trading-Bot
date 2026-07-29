from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID
from urllib.parse import parse_qs

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from infrastructure.persistence.execution_orm import AuditEventORM, LiveExecutionPermitORM
from infrastructure.persistence.live_execution_permit_persistence import ISSUE_CONFIRMATION, LiveExecutionPermitPersistence
from infrastructure.persistence.protective_lifecycle_persistence import ProtectiveLifecyclePersistence
from engine.diagnostics.binance_futures_testnet_order_lifecycle_engine import BinanceFuturesTestnetOrderLifecycleEngine
from engine.diagnostics.binance_futures_testnet_order_test_engine import BinanceFuturesTestnetOrderTestEngine
from engine.diagnostics.binance_futures_testnet_protective_orders_engine import BinanceFuturesTestnetProtectiveOrdersEngine
from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import (
    BinanceFuturesTestnetOrderLifecycleClient,
    BinanceLifecycleHTTPResponse,
)
from infrastructure.exchanges.binance_futures_testnet_order_test_client import (
    BinanceFuturesTestnetOrderTestClient,
    BinanceOrderTestHTTPResponse,
)
from infrastructure.exchanges.binance_futures_testnet_protective_orders_client import (
    BinanceFuturesTestnetProtectiveAPIError,
    BinanceFuturesTestnetProtectiveOrdersClient,
)
from infrastructure.security.live_execution_mutation_fingerprint_adapter import (
    build_lifecycle_cancel_from_final_request,
    build_lifecycle_create_from_final_request,
    build_protective_cancel_from_final_request,
    build_protective_create_from_final_request,
    build_signed_order_test_create_from_final_request,
)
from infrastructure.security.live_execution_permit_gate import LiveExecutionPermitGate
from infrastructure.security.live_execution_request_fingerprint import build_live_execution_request_fingerprint
from models.live_execution_authorization import LiveExecutionOperation
from models.binance_futures_testnet_order_lifecycle import (
    BinanceFuturesTestnetOrderLifecycleConfig,
    LifecyclePhase,
)
from models.binance_futures_testnet_order_test import BinanceFuturesTestnetOrderTestConfig
from models.binance_futures_testnet_protective_orders import (
    BinanceFuturesTestnetProtectiveAlgoSummary,
    BinanceFuturesTestnetProtectiveJournal,
    BinanceFuturesTestnetProtectiveOrdersConfig,
    ProtectiveMutationKind,
    ProtectiveReconciliationState,
)
from models.live_execution_permit import LiveExecutionPermitState
from models.live_execution_permit_enforcement import LiveExecutionPermitReference, LiveExecutionUnsignedMutationRequest
from tests.kill_switch_test_support import durable_state_env
from tests.test_binance_futures_testnet_order_lifecycle_engine import (
    _engine as _lifecycle_engine,
    _exchange_info as _lifecycle_exchange_info,
    _http_get as _lifecycle_http_get,
    _write_config as _write_lifecycle_config,
)
from tests.test_binance_futures_testnet_order_test_engine import (
    _engine as _order_test_engine,
    _http_get as _order_test_http_get,
    _write_config as _write_order_test_config,
)
from tests.test_binance_futures_testnet_protective_orders import (
    _LegacyProtectivePersistence,
    _algo_response,
    _exchange_info,
    _http_get,
    _position,
    _write_config,
)


CORRELATION = UUID("11111111-1111-4111-8111-111111111112")


def _fingerprint():
    return build_live_execution_request_fingerprint(
        {
            "schema_version": "1.0", "operation": "ORDER_LIFECYCLE_CREATE",
            "environment": "TESTNET", "symbol": "BTCUSDT", "client_order_id": "smcbot-durable-001",
            "side": "BUY", "position_side": "BOTH", "order_type": "LIMIT", "quantity": "0.001",
            "price": "50000", "time_in_force": "GTX", "reduce_only": False,
        }
    )


def _issue(env, fingerprint):
    persistence = LiveExecutionPermitPersistence(env=env)
    persistence.ensure_available()
    try:
        return persistence.issue(fingerprint, issued_by="durable-test", confirmation=ISSUE_CONFIRMATION)
    finally:
        persistence.close()


class _ClosingPermitPersistence:
    def __init__(self, observer: dict[str, object], **kwargs) -> None:
        self._delegate = LiveExecutionPermitPersistence(**kwargs)
        self._observer = observer

    def __getattr__(self, name):
        return getattr(self._delegate, name)

    def close(self) -> None:
        self._delegate.close()
        self._observer["close_count"] = int(self._observer["close_count"]) + 1
        self._observer["close_completed"] = True


def _assert_consumed_at_transport(env, issued, fingerprint, observer, operation=LiveExecutionOperation.PROTECTIVE_CREATE) -> None:
    assert observer == {"close_count": 1, "close_completed": True}
    independent_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(independent_engine, future=True) as session:
            permit = session.scalar(
                select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == issued.permit_id)
            )
            audits = list(
                session.scalars(
                    select(AuditEventORM).where(
                        AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                        AuditEventORM.action == "PERMIT_CONSUMED",
                    )
                ).all()
            )
        assert permit is not None
        assert permit.state == LiveExecutionPermitState.CONSUMED.value
        assert permit.version == issued.version + 1
        assert permit.consumed_at is not None
        assert permit.consumption_correlation_id is not None
        assert permit.operation == operation.value
        assert permit.environment == "TESTNET"
        assert permit.symbol == "BTCUSDT"
        assert permit.request_fingerprint == fingerprint.request_fingerprint
        matching = [event for event in audits if event.metadata_json.get("permit_id") == issued.permit_id]
        assert len(matching) == 1
        metadata = matching[0].metadata_json
        assert matching[0].result == "PASS"
        assert metadata["operation"] == operation.value
        assert metadata["environment"] == "TESTNET"
        assert metadata["symbol"] == "BTCUSDT"
        assert metadata["request_fingerprint"] == fingerprint.request_fingerprint
        assert metadata["consumption_correlation_id"] == str(permit.consumption_correlation_id)
    finally:
        independent_engine.dispose()


def test_real_durable_gate_consumption_is_committed_before_caller_continues() -> None:
    """The gate owns and closes its transaction before the mutation boundary."""
    env = durable_state_env("RELEASED")
    fingerprint = _fingerprint()
    issued = _issue(env, fingerprint)
    gate = LiveExecutionPermitGate(env=env, correlation_id_provider=lambda: CORRELATION)

    receipt = gate.authorize_and_consume(
        operation=LiveExecutionOperation.ORDER_LIFECYCLE_CREATE,
        fingerprint=fingerprint,
        permit_reference=LiveExecutionPermitReference(issued.permit_id, issued.version),
        confirmation_verified=True,
        credentials_configured=True,
        runtime_config_path=env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
    )

    # This independent engine/session intentionally shares no object with the
    # gate. Seeing both rows proves the consumption transaction committed.
    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine, future=True) as session:
            permit = session.scalar(select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == issued.permit_id))
            audit = session.scalar(
                select(AuditEventORM).where(
                    AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                    AuditEventORM.action == "PERMIT_CONSUMED",
                )
            )
        assert permit is not None
        assert permit.state == LiveExecutionPermitState.CONSUMED.value
        assert permit.version == issued.version + 1
        assert permit.consumed_at is not None
        assert str(permit.consumption_correlation_id) == str(CORRELATION)
        assert audit is not None
        assert audit.result == "PASS"
        assert audit.metadata_json["permit_id"] == issued.permit_id
        assert audit.metadata_json["request_fingerprint"] == fingerprint.request_fingerprint
        assert audit.metadata_json["consumption_correlation_id"] == str(CORRELATION)
        assert receipt.consumed_version == permit.version
    finally:
        engine.dispose()


def test_durable_enforcement_uses_actual_live_execution_permit_gate() -> None:
    gate = LiveExecutionPermitGate(env=durable_state_env("RELEASED"))
    assert type(gate) is LiveExecutionPermitGate
    assert gate.authorize_and_consume.__module__ == "infrastructure.security.live_execution_permit_gate"


def test_protective_create_permit_is_committed_and_closed_before_post(tmp_path) -> None:
    env = durable_state_env("RELEASED")
    config_path = _write_config(tmp_path)
    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), env=env)
    preview = client.build_preview(
        "pair-001",
        "smcbot-protect-sl-001",
        "smcbot-protect-tp-001",
        client.require_protectable_position(_position()),
        client.parse_exchange_filters(_exchange_info()),
        1000,
        1000,
    )
    unsigned_request = client.build_create_unsigned_business_request(preview, "STOP")
    fingerprint = build_protective_create_from_final_request(unsigned_request)
    issued = _issue(env, fingerprint)
    observer = {"close_count": 0, "close_completed": False}
    gate = LiveExecutionPermitGate(
        env=env,
        correlation_id_provider=lambda: CORRELATION,
        permit_persistence_factory=lambda **kwargs: _ClosingPermitPersistence(observer, **kwargs),
    )
    post_calls = []
    created = False

    def transport(method, url, body, timeout, headers):
        nonlocal created
        params = parse_qs(body.decode("utf-8"))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        if method == "POST":
            assert client_id == preview.stop_client_algo_id
            _assert_consumed_at_transport(env, issued, fingerprint, observer)
            post_calls.append(client_id)
            created = True
            return BinanceLifecycleHTTPResponse(
                200,
                url,
                _algo_response(client_id, "STOP_MARKET", status="NEW", trigger=str(preview.stop_trigger)),
                10,
            )
        if method == "GET" and created and client_id == preview.stop_client_algo_id:
            return BinanceLifecycleHTTPResponse(
                200,
                url,
                _algo_response(client_id, "STOP_MARKET", status="TRIGGERED", trigger=str(preview.stop_trigger)),
                10,
            )
        if method == "GET":
            raise BinanceFuturesTestnetProtectiveAPIError(
                "NO_SUCH_ORDER",
                http_status=400,
                binance_code=-2013,
                method="GET",
                path="/fapi/v1/algoOrder",
                request_transmitted=True,
                response_received=True,
            )
        raise AssertionError("unexpected mutation transport")

    engine = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=env,
        http_get=_http_get,
        authenticated_request=transport,
        permit_gate=gate,
        now_ms_provider=lambda: 1000,
    )
    assert isinstance(engine.permit_gate, LiveExecutionPermitGate)
    result = engine.run_protective_lifecycle(
        preview.pair_id,
        preview.stop_client_algo_id,
        preview.take_profit_client_algo_id,
        confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE",
        config_path=str(config_path),
        stop_create_permit=LiveExecutionPermitReference(issued.permit_id, issued.version),
        take_profit_create_permit=LiveExecutionPermitReference("permit-" + "b" * 32, 1),
        take_profit_cancel_permit=LiveExecutionPermitReference("permit-" + "c" * 32, 1),
        stop_cancel_permit=LiveExecutionPermitReference("permit-" + "d" * 32, 1),
    )

    assert result.stop_order is not None
    assert result.stop_order.client_algo_id == preview.stop_client_algo_id
    assert post_calls == [preview.stop_client_algo_id]
    assert observer == {"close_count": 1, "close_completed": True}
    stored_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(stored_engine, future=True) as session:
            stored = session.scalar(select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == issued.permit_id))
            audits = list(session.scalars(select(AuditEventORM).where(AuditEventORM.action == "PERMIT_CONSUMED")).all())
        assert stored is not None and stored.state == LiveExecutionPermitState.CONSUMED.value
        assert stored.version == issued.version + 1
        assert len([event for event in audits if event.metadata_json.get("permit_id") == issued.permit_id]) == 1
        assert result.create_requests[0].retry_count == 0
    finally:
        stored_engine.dispose()




def test_protective_stop_create_fingerprint_equals_transmitted_business_request(tmp_path) -> None:
    env = durable_state_env("RELEASED")
    config_path = _write_config(tmp_path)
    config = BinanceFuturesTestnetProtectiveOrdersConfig()
    client = BinanceFuturesTestnetProtectiveOrdersClient(
        config,
        http_get=_http_get,
        env=env,
        now_ms_provider=lambda: 1000,
    )
    preview = client.build_preview(
        "pair-001",
        "smcbot-protect-sl-001",
        "smcbot-protect-tp-001",
        client.require_protectable_position(_position()),
        client.parse_exchange_filters(_exchange_info()),
        1000,
        1000,
    )
    unsigned_request = client.build_create_unsigned_business_request(preview, "STOP")
    shared_before = {
        "operation": unsigned_request.operation,
        "environment": unsigned_request.environment,
        "symbol": unsigned_request.symbol,
        "subject_type": unsigned_request.subject_type,
        "subject_id": unsigned_request.subject_id,
        "fingerprint_context": dict(unsigned_request.fingerprint_context),
        "transport_business_parameters": dict(unsigned_request.transport_business_parameters),
    }
    expected_business = shared_before["transport_business_parameters"]
    expected_business_keys = {
        "algoType",
        "symbol",
        "side",
        "type",
        "triggerPrice",
        "workingType",
        "closePosition",
        "priceProtect",
        "positionSide",
        "clientAlgoId",
        "newOrderRespType",
    }
    expected_field_classification = {
        "pair_id": "FINGERPRINT_CONTEXT",
        "leg": "FINGERPRINT_CONTEXT",
        "symbol": "TRANSPORT_BUSINESS",
        "algoType": "TRANSPORT_BUSINESS",
        "clientAlgoId": "TRANSPORT_BUSINESS",
        "side": "TRANSPORT_BUSINESS",
        "positionSide": "TRANSPORT_BUSINESS",
        "type": "TRANSPORT_BUSINESS",
        "quantity": "FINGERPRINT_CONTEXT",
        "triggerPrice": "TRANSPORT_BUSINESS",
        "closePosition": "TRANSPORT_BUSINESS",
        "reduceOnly": "FINGERPRINT_CONTEXT",
        "workingType": "TRANSPORT_BUSINESS",
        "priceProtect": "TRANSPORT_BUSINESS",
        "newOrderRespType": "TRANSPORT_BUSINESS",
        "timestamp": "AUTH_TRANSPORT",
        "recvWindow": "AUTH_TRANSPORT",
        "signature": "AUTH_TRANSPORT",
    }

    assert unsigned_request.operation == LiveExecutionOperation.PROTECTIVE_CREATE
    assert unsigned_request.environment == "TESTNET"
    assert unsigned_request.symbol == "BTCUSDT"
    assert unsigned_request.subject_type == "PROTECTIVE_PAIR"
    assert unsigned_request.subject_id == preview.pair_id
    assert shared_before["fingerprint_context"]["pair_id"] == preview.pair_id
    assert shared_before["fingerprint_context"]["leg_type"] == "STOP"
    assert shared_before["fingerprint_context"]["quantity"] == "0.001"
    assert shared_before["fingerprint_context"]["reduce_only"] is None
    assert "pair_id" not in expected_business
    assert "leg" not in expected_business
    assert "quantity" not in expected_business
    assert "reduceOnly" not in expected_business
    assert set(expected_business) == expected_business_keys
    assert expected_business == {
        "algoType": config.allowed_algo_type,
        "symbol": "BTCUSDT",
        "side": preview.protective_side,
        "type": "STOP_MARKET",
        "triggerPrice": "45000",
        "workingType": "MARK_PRICE",
        "closePosition": "true",
        "priceProtect": "true",
        "positionSide": "BOTH",
        "clientAlgoId": preview.stop_client_algo_id,
        "newOrderRespType": config.new_order_response_type,
    }
    assert expected_field_classification == {
        "pair_id": "FINGERPRINT_CONTEXT",
        "leg": "FINGERPRINT_CONTEXT",
        "symbol": "TRANSPORT_BUSINESS",
        "algoType": "TRANSPORT_BUSINESS",
        "clientAlgoId": "TRANSPORT_BUSINESS",
        "side": "TRANSPORT_BUSINESS",
        "positionSide": "TRANSPORT_BUSINESS",
        "type": "TRANSPORT_BUSINESS",
        "quantity": "FINGERPRINT_CONTEXT",
        "triggerPrice": "TRANSPORT_BUSINESS",
        "closePosition": "TRANSPORT_BUSINESS",
        "reduceOnly": "FINGERPRINT_CONTEXT",
        "workingType": "TRANSPORT_BUSINESS",
        "priceProtect": "TRANSPORT_BUSINESS",
        "newOrderRespType": "TRANSPORT_BUSINESS",
        "timestamp": "AUTH_TRANSPORT",
        "recvWindow": "AUTH_TRANSPORT",
        "signature": "AUTH_TRANSPORT",
    }
    for auth_field in ("timestamp", "recvWindow", "signature"):
        assert auth_field not in shared_before["fingerprint_context"]
        assert auth_field not in expected_business

    fingerprint = build_protective_create_from_final_request(unsigned_request)
    assert len(fingerprint.request_fingerprint) == 64
    assert fingerprint.request_fingerprint == fingerprint.request_fingerprint.lower()
    assert set(fingerprint.request_fingerprint) <= set("0123456789abcdef")
    assert fingerprint.operation == LiveExecutionOperation.PROTECTIVE_CREATE.value
    assert fingerprint.environment == "TESTNET"
    assert fingerprint.symbol == "BTCUSDT"
    assert fingerprint.canonical_payload["pair_id"] == preview.pair_id
    assert fingerprint.canonical_payload["leg_type"] == "STOP"
    assert fingerprint.canonical_payload["client_algo_id"] == preview.stop_client_algo_id
    assert fingerprint.canonical_payload["side"] == expected_business["side"]
    assert fingerprint.canonical_payload["position_side"] == expected_business["positionSide"]
    assert fingerprint.canonical_payload["quantity"] == "0.001"
    assert fingerprint.canonical_payload["trigger_price"] == expected_business["triggerPrice"]
    assert fingerprint.canonical_payload["close_position"] is True
    assert fingerprint.canonical_payload["reduce_only"] is None
    assert fingerprint.canonical_payload["order_type"] == expected_business["type"]
    assert fingerprint.canonical_payload["working_type"] == expected_business["workingType"]
    assert fingerprint.canonical_payload["price_protect"] is True
    issued = _issue(env, fingerprint)
    observer = {"close_count": 0, "close_completed": False}
    gate = LiveExecutionPermitGate(
        env=env,
        correlation_id_provider=lambda: CORRELATION,
        permit_persistence_factory=lambda **kwargs: _ClosingPermitPersistence(observer, **kwargs),
    )
    captured = {"fingerprint": fingerprint, "transmitted": None}
    post_calls = []
    created = False
    original_class_unsigned_builder = BinanceFuturesTestnetProtectiveOrdersClient.build_create_unsigned_business_request
    original_class_create_stop_order = BinanceFuturesTestnetProtectiveOrdersClient.create_stop_order

    try:
        def captured_unsigned_builder(actual_client, actual_preview, label):
            rebuilt = original_class_unsigned_builder(actual_client, actual_preview, label)
            if label == "STOP":
                assert dict(rebuilt.fingerprint_context) == shared_before["fingerprint_context"]
                assert dict(rebuilt.transport_business_parameters) == expected_business
                return unsigned_request
            return rebuilt

        def captured_create_stop_order(actual_client, actual_preview, unsigned_business_request=None):
            assert unsigned_business_request is unsigned_request
            assert dict(unsigned_business_request.transport_business_parameters) == expected_business
            return original_class_create_stop_order(
                actual_client,
                actual_preview,
                unsigned_business_request=unsigned_business_request,
            )

        BinanceFuturesTestnetProtectiveOrdersClient.build_create_unsigned_business_request = captured_unsigned_builder
        BinanceFuturesTestnetProtectiveOrdersClient.create_stop_order = captured_create_stop_order

        def transport(method, url, body, timeout, headers):
            nonlocal created
            body_text = body.decode("utf-8")
            params = {key: values[0] for key, values in parse_qs(body_text).items()}
            if "positionSide/dual" in url:
                return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
            if "positionRisk" in url:
                return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
            client_id = params["clientAlgoId"]
            if method == "POST":
                assert url == "https://demo-fapi.binance.com/fapi/v1/algoOrder"
                assert client_id == preview.stop_client_algo_id
                assert observer == {"close_count": 1, "close_completed": True}
                _assert_consumed_at_transport(env, issued, fingerprint, observer)
                assert env[config.api_key_env_var] not in body_text
                assert env[config.api_secret_env_var] not in body_text
                transmitted_before_auth_removal = dict(params)
                auth_only = {"timestamp", "recvWindow", "signature"}
                assert auth_only <= set(transmitted_before_auth_removal)
                assert len(transmitted_before_auth_removal["signature"]) == 64
                actual_unsigned_transmitted = {
                    key: value for key, value in transmitted_before_auth_removal.items() if key not in auth_only
                }
                assert set(actual_unsigned_transmitted) == set(expected_business)
                assert actual_unsigned_transmitted == expected_business
                assert "pair_id" not in actual_unsigned_transmitted
                assert "leg" not in actual_unsigned_transmitted
                assert "quantity" not in actual_unsigned_transmitted
                assert "reduceOnly" not in actual_unsigned_transmitted
                assert actual_unsigned_transmitted["triggerPrice"] == "45000"
                assert actual_unsigned_transmitted["closePosition"] == "true"
                assert actual_unsigned_transmitted["priceProtect"] == "true"
                assert actual_unsigned_transmitted["type"] == "STOP_MARKET"
                assert actual_unsigned_transmitted["workingType"] == "MARK_PRICE"
                assert actual_unsigned_transmitted["clientAlgoId"] == preview.stop_client_algo_id
                assert actual_unsigned_transmitted["positionSide"] == "BOTH"
                assert actual_unsigned_transmitted["side"] == preview.protective_side
                assert actual_unsigned_transmitted["symbol"] == "BTCUSDT"
                captured["transmitted"] = transmitted_before_auth_removal
                post_calls.append(client_id)
                created = True
                return BinanceLifecycleHTTPResponse(
                    200,
                    url,
                    _algo_response(client_id, "STOP_MARKET", status="NEW", trigger=str(preview.stop_trigger)),
                    10,
                )
            if method == "GET" and created and client_id == preview.stop_client_algo_id:
                return BinanceLifecycleHTTPResponse(
                    200,
                    url,
                    _algo_response(client_id, "STOP_MARKET", status="TRIGGERED", trigger=str(preview.stop_trigger)),
                    10,
                )
            if method == "GET":
                raise BinanceFuturesTestnetProtectiveAPIError(
                    "NO_SUCH_ORDER",
                    http_status=400,
                    binance_code=-2013,
                    method="GET",
                    path="/fapi/v1/algoOrder",
                    request_transmitted=True,
                    response_received=True,
                )
            raise AssertionError("unexpected mutation transport")

        client.authenticated_request = transport
        engine = BinanceFuturesTestnetProtectiveOrdersEngine(
            repo_root=tmp_path,
            env=env,
            http_get=_http_get,
            authenticated_request=transport,
            permit_gate=gate,
            now_ms_provider=lambda: 1000,
        )
        engine._client = lambda loaded_config: client
        assert isinstance(engine, BinanceFuturesTestnetProtectiveOrdersEngine)
        assert isinstance(engine.permit_gate, LiveExecutionPermitGate)
        assert isinstance(client, BinanceFuturesTestnetProtectiveOrdersClient)

        modified_request = LiveExecutionUnsignedMutationRequest(
            operation=unsigned_request.operation,
            environment=unsigned_request.environment,
            symbol=unsigned_request.symbol,
            subject_type=unsigned_request.subject_type,
            subject_id=unsigned_request.subject_id,
            fingerprint_context={**dict(unsigned_request.fingerprint_context), "leg_type": "TAKE_PROFIT"},
            transport_business_parameters=dict(unsigned_request.transport_business_parameters),
        )
        modified_fingerprint = build_protective_create_from_final_request(modified_request)
        assert modified_fingerprint.canonical_payload != fingerprint.canonical_payload
        assert modified_fingerprint.request_fingerprint != fingerprint.request_fingerprint

        result = engine.run_protective_lifecycle(
            preview.pair_id,
            preview.stop_client_algo_id,
            preview.take_profit_client_algo_id,
            confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE",
            config_path=str(config_path),
            stop_create_permit=LiveExecutionPermitReference(issued.permit_id, issued.version),
            take_profit_create_permit=LiveExecutionPermitReference("permit-" + "b" * 32, 1),
            take_profit_cancel_permit=LiveExecutionPermitReference("permit-" + "c" * 32, 1),
            stop_cancel_permit=LiveExecutionPermitReference("permit-" + "d" * 32, 1),
        )

        shared_after = {
            "operation": unsigned_request.operation,
            "environment": unsigned_request.environment,
            "symbol": unsigned_request.symbol,
            "subject_type": unsigned_request.subject_type,
            "subject_id": unsigned_request.subject_id,
            "fingerprint_context": dict(unsigned_request.fingerprint_context),
            "transport_business_parameters": dict(unsigned_request.transport_business_parameters),
        }
        assert shared_after == shared_before
        for auth_field in ("timestamp", "recvWindow", "signature"):
            assert auth_field not in shared_after["fingerprint_context"]
            assert auth_field not in shared_after["transport_business_parameters"]
        assert captured["fingerprint"].request_fingerprint == fingerprint.request_fingerprint
        assert captured["transmitted"] is not None
        assert result.stop_order is not None
        assert result.stop_order.client_algo_id == preview.stop_client_algo_id
        assert post_calls == [preview.stop_client_algo_id]
        assert result.create_requests[0].retry_count == 0
        assert observer == {"close_count": 1, "close_completed": True}
        stored_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
        try:
            with Session(stored_engine, future=True) as session:
                stored = session.scalar(
                    select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == issued.permit_id)
                )
                audits = list(
                    session.scalars(
                        select(AuditEventORM).where(
                            AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                            AuditEventORM.action == "PERMIT_CONSUMED",
                        )
                    ).all()
                )
            assert stored is not None
            assert stored.state == LiveExecutionPermitState.CONSUMED.value
            assert stored.version == issued.version + 1 == 2
            assert stored.consumed_at is not None
            assert stored.consumption_correlation_id is not None
            assert stored.operation == LiveExecutionOperation.PROTECTIVE_CREATE.value
            assert stored.environment == "TESTNET"
            assert stored.symbol == "BTCUSDT"
            assert stored.request_fingerprint == fingerprint.request_fingerprint
            matching = [event for event in audits if event.metadata_json.get("permit_id") == issued.permit_id]
            assert len(matching) == 1
            assert matching[0].metadata_json["request_fingerprint"] == fingerprint.request_fingerprint
        finally:
            stored_engine.dispose()
    finally:
        BinanceFuturesTestnetProtectiveOrdersClient.build_create_unsigned_business_request = original_class_unsigned_builder
        BinanceFuturesTestnetProtectiveOrdersClient.create_stop_order = original_class_create_stop_order


def test_protective_take_profit_create_fingerprint_equals_transmitted_business_request(tmp_path) -> None:
    env = durable_state_env("RELEASED")
    config_path = _write_config(tmp_path)
    config = BinanceFuturesTestnetProtectiveOrdersConfig()
    client = BinanceFuturesTestnetProtectiveOrdersClient(
        config,
        http_get=_http_get,
        env=env,
        now_ms_provider=lambda: 1000,
    )
    preview = client.build_preview(
        "pair-001",
        "smcbot-protect-sl-001",
        "smcbot-protect-tp-001",
        client.require_protectable_position(_position()),
        client.parse_exchange_filters(_exchange_info()),
        1000,
        1000,
    )
    stop_request = client.build_create_unsigned_business_request(preview, "STOP")
    stop_fingerprint = build_protective_create_from_final_request(stop_request)
    stop_permit = _issue(env, stop_fingerprint)
    take_profit_request = client.build_create_unsigned_business_request(preview, "TAKE_PROFIT")
    shared_before = {
        "operation": take_profit_request.operation,
        "environment": take_profit_request.environment,
        "symbol": take_profit_request.symbol,
        "subject_type": take_profit_request.subject_type,
        "subject_id": take_profit_request.subject_id,
        "fingerprint_context": dict(take_profit_request.fingerprint_context),
        "transport_business_parameters": dict(take_profit_request.transport_business_parameters),
    }
    expected_business = shared_before["transport_business_parameters"]
    expected_business_keys = {
        "algoType",
        "symbol",
        "side",
        "type",
        "triggerPrice",
        "workingType",
        "closePosition",
        "priceProtect",
        "positionSide",
        "clientAlgoId",
        "newOrderRespType",
    }
    field_classification = {
        "pair_id": "FINGERPRINT_CONTEXT",
        "leg": "FINGERPRINT_CONTEXT",
        "symbol": "TRANSPORT_BUSINESS",
        "algoType": "TRANSPORT_BUSINESS",
        "clientAlgoId": "TRANSPORT_BUSINESS",
        "side": "TRANSPORT_BUSINESS",
        "positionSide": "TRANSPORT_BUSINESS",
        "type": "TRANSPORT_BUSINESS",
        "quantity": "FINGERPRINT_CONTEXT",
        "triggerPrice": "TRANSPORT_BUSINESS",
        "closePosition": "TRANSPORT_BUSINESS",
        "reduceOnly": "FINGERPRINT_CONTEXT",
        "workingType": "TRANSPORT_BUSINESS",
        "priceProtect": "TRANSPORT_BUSINESS",
        "newOrderRespType": "TRANSPORT_BUSINESS",
        "timestamp": "AUTH_TRANSPORT",
        "recvWindow": "AUTH_TRANSPORT",
        "signature": "AUTH_TRANSPORT",
    }

    assert take_profit_request.operation == LiveExecutionOperation.PROTECTIVE_CREATE
    assert take_profit_request.environment == "TESTNET"
    assert take_profit_request.symbol == "BTCUSDT"
    assert take_profit_request.subject_type == "PROTECTIVE_PAIR"
    assert take_profit_request.subject_id == preview.pair_id
    assert shared_before["fingerprint_context"]["pair_id"] == preview.pair_id
    assert shared_before["fingerprint_context"]["leg_type"] == "TAKE_PROFIT"
    assert shared_before["fingerprint_context"]["quantity"] == "0.001"
    assert shared_before["fingerprint_context"]["reduce_only"] is None
    assert set(expected_business) == expected_business_keys
    assert "pair_id" not in expected_business
    assert "leg" not in expected_business
    assert "quantity" not in expected_business
    assert "reduceOnly" not in expected_business
    assert expected_business["algoType"] == config.allowed_algo_type
    assert expected_business["symbol"] == "BTCUSDT"
    assert expected_business["side"] == preview.protective_side
    assert expected_business["type"] == "TAKE_PROFIT_MARKET"
    assert expected_business["triggerPrice"] == "55000"
    assert expected_business["workingType"] == "MARK_PRICE"
    assert expected_business["closePosition"] == "true"
    assert expected_business["priceProtect"] == "true"
    assert expected_business["positionSide"] == "BOTH"
    assert expected_business["clientAlgoId"] == preview.take_profit_client_algo_id
    assert expected_business["newOrderRespType"] == config.new_order_response_type
    assert field_classification["quantity"] == "FINGERPRINT_CONTEXT"
    assert field_classification["reduceOnly"] == "FINGERPRINT_CONTEXT"
    for auth_field in ("timestamp", "recvWindow", "signature"):
        assert auth_field not in shared_before["fingerprint_context"]
        assert auth_field not in expected_business

    take_profit_fingerprint = build_protective_create_from_final_request(take_profit_request)
    assert len(take_profit_fingerprint.request_fingerprint) == 64
    assert take_profit_fingerprint.request_fingerprint == take_profit_fingerprint.request_fingerprint.lower()
    assert set(take_profit_fingerprint.request_fingerprint) <= set("0123456789abcdef")
    assert take_profit_fingerprint.operation == LiveExecutionOperation.PROTECTIVE_CREATE.value
    assert take_profit_fingerprint.environment == "TESTNET"
    assert take_profit_fingerprint.symbol == "BTCUSDT"
    assert take_profit_fingerprint.canonical_payload["pair_id"] == preview.pair_id
    assert take_profit_fingerprint.canonical_payload["leg_type"] == "TAKE_PROFIT"
    assert take_profit_fingerprint.canonical_payload["client_algo_id"] == preview.take_profit_client_algo_id
    assert take_profit_fingerprint.canonical_payload["side"] == expected_business["side"]
    assert take_profit_fingerprint.canonical_payload["position_side"] == expected_business["positionSide"]
    assert take_profit_fingerprint.canonical_payload["quantity"] == "0.001"
    assert take_profit_fingerprint.canonical_payload["trigger_price"] == expected_business["triggerPrice"]
    assert take_profit_fingerprint.canonical_payload["close_position"] is True
    assert take_profit_fingerprint.canonical_payload["reduce_only"] is None
    assert take_profit_fingerprint.canonical_payload["order_type"] == "TAKE_PROFIT_MARKET"
    assert take_profit_fingerprint.canonical_payload["working_type"] == "MARK_PRICE"
    assert take_profit_fingerprint.canonical_payload["price_protect"] is True
    assert take_profit_fingerprint.request_fingerprint != stop_fingerprint.request_fingerprint
    assert take_profit_fingerprint.canonical_payload["client_algo_id"] != stop_fingerprint.canonical_payload["client_algo_id"]
    assert take_profit_fingerprint.canonical_payload["trigger_price"] != stop_fingerprint.canonical_payload["trigger_price"]
    assert take_profit_fingerprint.canonical_payload["order_type"] != stop_fingerprint.canonical_payload["order_type"]
    take_profit_permit = _issue(env, take_profit_fingerprint)
    assert stop_permit.permit_id != take_profit_permit.permit_id
    observer = {"close_count": 0, "close_completed": False}
    gate = LiveExecutionPermitGate(
        env=env,
        correlation_id_provider=lambda: CORRELATION,
        permit_persistence_factory=lambda **kwargs: _ClosingPermitPersistence(observer, **kwargs),
    )
    captured = {"fingerprint": take_profit_fingerprint, "transmitted": None}
    calls: list[tuple[str, str]] = []
    stop_post_calls: list[str] = []
    take_profit_post_calls: list[str] = []
    created_take_profit = False
    queried_take_profit = False
    original_class_unsigned_builder = BinanceFuturesTestnetProtectiveOrdersClient.build_create_unsigned_business_request
    original_class_create_stop_order = BinanceFuturesTestnetProtectiveOrdersClient.create_stop_order
    original_class_create_take_profit_order = BinanceFuturesTestnetProtectiveOrdersClient.create_take_profit_order

    try:
        def captured_unsigned_builder(actual_client, actual_preview, label):
            rebuilt = original_class_unsigned_builder(actual_client, actual_preview, label)
            if label == "STOP":
                raise AssertionError("STOP create builder should not run when STOP is already present")
            assert label == "TAKE_PROFIT"
            assert dict(rebuilt.fingerprint_context) == shared_before["fingerprint_context"]
            assert dict(rebuilt.transport_business_parameters) == expected_business
            return take_profit_request

        def blocked_create_stop_order(actual_client, actual_preview, unsigned_business_request=None):
            raise AssertionError("STOP create POST should not run when STOP is already present")

        def captured_create_take_profit_order(actual_client, actual_preview, unsigned_business_request=None):
            assert unsigned_business_request is take_profit_request
            assert dict(unsigned_business_request.transport_business_parameters) == expected_business
            return original_class_create_take_profit_order(
                actual_client,
                actual_preview,
                unsigned_business_request=unsigned_business_request,
            )

        BinanceFuturesTestnetProtectiveOrdersClient.build_create_unsigned_business_request = captured_unsigned_builder
        BinanceFuturesTestnetProtectiveOrdersClient.create_stop_order = blocked_create_stop_order
        BinanceFuturesTestnetProtectiveOrdersClient.create_take_profit_order = captured_create_take_profit_order

        def transport(method, url, body, timeout, headers):
            nonlocal created_take_profit, queried_take_profit
            calls.append((method, url))
            body_text = body.decode("utf-8")
            params = {key: values[0] for key, values in parse_qs(body_text).items()}
            if "positionSide/dual" in url:
                return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
            if "positionRisk" in url:
                if queried_take_profit:
                    raise TimeoutError("stop after TAKE_PROFIT create proof before delete")
                return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
            assert "/fapi/v1/algoOrder" in url
            client_id = params["clientAlgoId"]
            if method == "POST":
                assert url == "https://demo-fapi.binance.com/fapi/v1/algoOrder"
                assert client_id == preview.take_profit_client_algo_id
                assert observer == {"close_count": 1, "close_completed": True}
                _assert_consumed_at_transport(env, take_profit_permit, take_profit_fingerprint, observer)
                assert env[config.api_key_env_var] not in body_text
                assert env[config.api_secret_env_var] not in body_text
                transmitted_before_auth_removal = dict(params)
                auth_only = {"timestamp", "recvWindow", "signature"}
                assert auth_only <= set(transmitted_before_auth_removal)
                assert len(transmitted_before_auth_removal["signature"]) == 64
                actual_unsigned_transmitted = {
                    key: value for key, value in transmitted_before_auth_removal.items() if key not in auth_only
                }
                assert set(actual_unsigned_transmitted) == set(expected_business)
                assert actual_unsigned_transmitted == expected_business
                assert "pair_id" not in actual_unsigned_transmitted
                assert "leg" not in actual_unsigned_transmitted
                assert "quantity" not in actual_unsigned_transmitted
                assert "reduceOnly" not in actual_unsigned_transmitted
                assert actual_unsigned_transmitted["symbol"] == "BTCUSDT"
                assert actual_unsigned_transmitted["algoType"] == config.allowed_algo_type
                assert actual_unsigned_transmitted["clientAlgoId"] == preview.take_profit_client_algo_id
                assert actual_unsigned_transmitted["side"] == preview.protective_side
                assert actual_unsigned_transmitted["positionSide"] == "BOTH"
                assert actual_unsigned_transmitted["type"] == "TAKE_PROFIT_MARKET"
                assert actual_unsigned_transmitted["triggerPrice"] == "55000"
                assert actual_unsigned_transmitted["closePosition"] == "true"
                assert actual_unsigned_transmitted["workingType"] == "MARK_PRICE"
                assert actual_unsigned_transmitted["priceProtect"] == "true"
                assert actual_unsigned_transmitted["newOrderRespType"] == config.new_order_response_type
                captured["transmitted"] = transmitted_before_auth_removal
                take_profit_post_calls.append(client_id)
                created_take_profit = True
                return BinanceLifecycleHTTPResponse(
                    200,
                    url,
                    _algo_response(client_id, "TAKE_PROFIT_MARKET", status="NEW", trigger=str(preview.take_profit_trigger)),
                    10,
                )
            if method == "DELETE":
                raise AssertionError("DELETE must not run in this TAKE_PROFIT create contract test")
            if method != "GET":
                raise AssertionError("unexpected authenticated method")
            if client_id == preview.stop_client_algo_id:
                return BinanceLifecycleHTTPResponse(
                    200,
                    url,
                    _algo_response(client_id, "STOP_MARKET", status="NEW", trigger=str(preview.stop_trigger)),
                    10,
                )
            if client_id == preview.take_profit_client_algo_id and created_take_profit:
                queried_take_profit = True
                return BinanceLifecycleHTTPResponse(
                    200,
                    url,
                    _algo_response(client_id, "TAKE_PROFIT_MARKET", status="NEW", trigger=str(preview.take_profit_trigger)),
                    10,
                )
            if client_id == preview.take_profit_client_algo_id:
                raise BinanceFuturesTestnetProtectiveAPIError(
                    "NO_SUCH_ORDER",
                    http_status=400,
                    binance_code=-2013,
                    method="GET",
                    path="/fapi/v1/algoOrder",
                    request_transmitted=True,
                    response_received=True,
                )
            raise AssertionError("unexpected clientAlgoId")

        client.authenticated_request = transport
        engine = BinanceFuturesTestnetProtectiveOrdersEngine(
            repo_root=tmp_path,
            env=env,
            http_get=_http_get,
            authenticated_request=transport,
            permit_gate=gate,
            now_ms_provider=lambda: 1000,
        )
        engine._client = lambda loaded_config: client
        assert isinstance(engine, BinanceFuturesTestnetProtectiveOrdersEngine)
        assert isinstance(engine.permit_gate, LiveExecutionPermitGate)
        assert isinstance(client, BinanceFuturesTestnetProtectiveOrdersClient)

        modified_request = LiveExecutionUnsignedMutationRequest(
            operation=take_profit_request.operation,
            environment=take_profit_request.environment,
            symbol=take_profit_request.symbol,
            subject_type=take_profit_request.subject_type,
            subject_id=take_profit_request.subject_id,
            fingerprint_context={**dict(take_profit_request.fingerprint_context), "leg_type": "STOP"},
            transport_business_parameters=dict(take_profit_request.transport_business_parameters),
        )
        modified_fingerprint = build_protective_create_from_final_request(modified_request)
        assert modified_fingerprint.canonical_payload != take_profit_fingerprint.canonical_payload
        assert modified_fingerprint.request_fingerprint != take_profit_fingerprint.request_fingerprint

        result = engine.run_protective_lifecycle(
            preview.pair_id,
            preview.stop_client_algo_id,
            preview.take_profit_client_algo_id,
            confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE",
            config_path=str(config_path),
            stop_create_permit=LiveExecutionPermitReference(stop_permit.permit_id, stop_permit.version),
            take_profit_create_permit=LiveExecutionPermitReference(take_profit_permit.permit_id, take_profit_permit.version),
            take_profit_cancel_permit=LiveExecutionPermitReference("permit-" + "c" * 32, 1),
            stop_cancel_permit=LiveExecutionPermitReference("permit-" + "d" * 32, 1),
        )

        shared_after = {
            "operation": take_profit_request.operation,
            "environment": take_profit_request.environment,
            "symbol": take_profit_request.symbol,
            "subject_type": take_profit_request.subject_type,
            "subject_id": take_profit_request.subject_id,
            "fingerprint_context": dict(take_profit_request.fingerprint_context),
            "transport_business_parameters": dict(take_profit_request.transport_business_parameters),
        }
        assert shared_after == shared_before
        for auth_field in ("timestamp", "recvWindow", "signature"):
            assert auth_field not in shared_after["fingerprint_context"]
            assert auth_field not in shared_after["transport_business_parameters"]
        assert captured["fingerprint"].request_fingerprint == take_profit_fingerprint.request_fingerprint
        assert captured["transmitted"] is not None
        assert result.take_profit_order is not None
        assert result.take_profit_order.client_algo_id == preview.take_profit_client_algo_id
        assert result.stop_order is not None
        assert result.stop_order.client_algo_id == preview.stop_client_algo_id
        assert result.unexpected_trigger is False
        assert result.unexpected_position_change is False
        assert take_profit_post_calls == [preview.take_profit_client_algo_id]
        assert stop_post_calls == []
        assert [call for call in calls if call[0] == "POST"] == [("POST", "https://demo-fapi.binance.com/fapi/v1/algoOrder")]
        assert [call for call in calls if call[0] == "DELETE"] == []
        assert result.create_requests and result.create_requests[0].retry_count == 0
        assert result.cancel_requests == []
        assert observer == {"close_count": 1, "close_completed": True}
        stored_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
        try:
            with Session(stored_engine, future=True) as session:
                permits = list(
                    session.scalars(
                        select(LiveExecutionPermitORM).where(
                            LiveExecutionPermitORM.permit_id.in_([stop_permit.permit_id, take_profit_permit.permit_id])
                        )
                    ).all()
                )
                audits = list(
                    session.scalars(
                        select(AuditEventORM).where(
                            AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                            AuditEventORM.action == "PERMIT_CONSUMED",
                        )
                    ).all()
                )
            by_id = {permit.permit_id: permit for permit in permits}
            assert by_id[stop_permit.permit_id].state == LiveExecutionPermitState.ISSUED.value
            assert by_id[stop_permit.permit_id].version == 1
            assert by_id[stop_permit.permit_id].consumption_correlation_id is None
            assert by_id[take_profit_permit.permit_id].state == LiveExecutionPermitState.CONSUMED.value
            assert by_id[take_profit_permit.permit_id].version == take_profit_permit.version + 1 == 2
            assert by_id[take_profit_permit.permit_id].consumed_at is not None
            assert by_id[take_profit_permit.permit_id].consumption_correlation_id is not None
            assert by_id[take_profit_permit.permit_id].operation == LiveExecutionOperation.PROTECTIVE_CREATE.value
            assert by_id[take_profit_permit.permit_id].environment == "TESTNET"
            assert by_id[take_profit_permit.permit_id].symbol == "BTCUSDT"
            assert by_id[take_profit_permit.permit_id].request_fingerprint == take_profit_fingerprint.request_fingerprint
            stop_audits = [event for event in audits if event.metadata_json.get("permit_id") == stop_permit.permit_id]
            take_profit_audits = [event for event in audits if event.metadata_json.get("permit_id") == take_profit_permit.permit_id]
            assert stop_audits == []
            assert len(take_profit_audits) == 1
            assert take_profit_audits[0].result == "PASS"
            assert take_profit_audits[0].metadata_json["operation"] == LiveExecutionOperation.PROTECTIVE_CREATE.value
            assert take_profit_audits[0].metadata_json["environment"] == "TESTNET"
            assert take_profit_audits[0].metadata_json["symbol"] == "BTCUSDT"
            assert take_profit_audits[0].metadata_json["request_fingerprint"] == take_profit_fingerprint.request_fingerprint
            assert take_profit_audits[0].metadata_json["consumption_correlation_id"] == str(
                by_id[take_profit_permit.permit_id].consumption_correlation_id
            )
        finally:
            stored_engine.dispose()
    finally:
        BinanceFuturesTestnetProtectiveOrdersClient.build_create_unsigned_business_request = original_class_unsigned_builder
        BinanceFuturesTestnetProtectiveOrdersClient.create_stop_order = original_class_create_stop_order
        BinanceFuturesTestnetProtectiveOrdersClient.create_take_profit_order = original_class_create_take_profit_order

def test_protective_stop_cancel_fingerprint_equals_transmitted_business_request(tmp_path) -> None:
    import engine.diagnostics.binance_futures_testnet_protective_orders_engine as protective_engine_module

    env = durable_state_env("RELEASED")
    config_path = _write_config(tmp_path)
    config = BinanceFuturesTestnetProtectiveOrdersConfig()
    client = BinanceFuturesTestnetProtectiveOrdersClient(
        config,
        http_get=_http_get,
        env=env,
        now_ms_provider=lambda: 1000,
    )
    position = client.require_protectable_position(_position())
    preview = client.build_preview(
        "pair-001",
        "smcbot-protect-sl-001",
        "smcbot-protect-tp-001",
        position,
        client.parse_exchange_filters(_exchange_info()),
        1000,
        1000,
    )
    stop_order = BinanceFuturesTestnetProtectiveAlgoSummary(
        symbol="BTCUSDT",
        client_algo_id=preview.stop_client_algo_id,
        algo_id="42",
        algo_type="CONDITIONAL",
        side="SELL",
        position_side="BOTH",
        order_type="STOP_MARKET",
        trigger_price=preview.stop_trigger,
        algo_status="NEW",
        actual_order_id="4200",
        close_position=True,
        working_type="MARK_PRICE",
        price_protect=True,
    )

    persistence = ProtectiveLifecyclePersistence(env=env)
    persistence.ensure_available()
    try:
        state = persistence.prepare_lifecycle(
            preview.pair_id,
            preview.stop_client_algo_id,
            preview.take_profit_client_algo_id,
            position,
            preview,
        )
        persistence.mark_create_transmitted(state)
        persistence.confirm_create(state, "STOP", stop_order)
    finally:
        persistence.close()

    journal_engine = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=env,
        http_get=_http_get,
        authenticated_request=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("journal setup must not transport")),
        persistence_factory=ProtectiveLifecyclePersistence,
        now_ms_provider=lambda: 1000,
    )
    journal = BinanceFuturesTestnetProtectiveJournal(
        pair_id=preview.pair_id,
        stop_client_algo_id=preview.stop_client_algo_id,
        take_profit_client_algo_id=preview.take_profit_client_algo_id,
    )
    journal_engine._attach_journal_baseline(journal, position, preview)
    create_intent = journal_engine._mutation_intent(
        journal,
        preview,
        "STOP",
        ProtectiveMutationKind.CREATE.value,
        "STOP_CREATE_STARTED",
    )
    create_intent.resolved = True
    create_intent.reconciliation_state = ProtectiveReconciliationState.PRESENT.value
    create_intent.reconciliation_reason = "Exact clientAlgoId lookup found a matching order."
    journal.mutation_intents.append(create_intent)
    journal_engine._write_journal(
        config,
        journal,
        "STOP_CREATED",
        {"client_algo_id": preview.stop_client_algo_id},
    )

    stop_cancel_request = client.build_cancel_unsigned_business_request(preview, "STOP")
    take_profit_cancel_request = client.build_cancel_unsigned_business_request(preview, "TAKE_PROFIT")
    shared_before = {
        "operation": stop_cancel_request.operation,
        "environment": stop_cancel_request.environment,
        "symbol": stop_cancel_request.symbol,
        "subject_type": stop_cancel_request.subject_type,
        "subject_id": stop_cancel_request.subject_id,
        "fingerprint_context": dict(stop_cancel_request.fingerprint_context),
        "transport_business_parameters": dict(stop_cancel_request.transport_business_parameters),
    }
    expected_business = shared_before["transport_business_parameters"]
    assert stop_cancel_request.operation == LiveExecutionOperation.PROTECTIVE_CANCEL
    assert stop_cancel_request.environment == "TESTNET"
    assert stop_cancel_request.symbol == "BTCUSDT"
    assert stop_cancel_request.subject_type == "PROTECTIVE_PAIR"
    assert stop_cancel_request.subject_id == preview.pair_id
    assert shared_before["fingerprint_context"]["pair_id"] == preview.pair_id
    assert shared_before["fingerprint_context"]["leg_type"] == "STOP"
    assert shared_before["fingerprint_context"]["client_algo_id"] == preview.stop_client_algo_id
    assert expected_business == {"symbol": "BTCUSDT", "clientAlgoId": preview.stop_client_algo_id}
    assert set(expected_business) == {"symbol", "clientAlgoId"}
    for forbidden in ("leg", "timestamp", "recvWindow", "signature", "headers", "credentials"):
        assert forbidden not in expected_business
        assert forbidden not in shared_before["fingerprint_context"]
    assert "pair_id" not in expected_business
    assert "pair_id" in shared_before["fingerprint_context"]

    stop_fingerprint = build_protective_cancel_from_final_request(stop_cancel_request)
    take_profit_fingerprint = build_protective_cancel_from_final_request(take_profit_cancel_request)
    assert len(stop_fingerprint.request_fingerprint) == 64
    assert stop_fingerprint.request_fingerprint == stop_fingerprint.request_fingerprint.lower()
    assert set(stop_fingerprint.request_fingerprint) <= set("0123456789abcdef")
    assert stop_fingerprint.operation == LiveExecutionOperation.PROTECTIVE_CANCEL.value
    assert stop_fingerprint.environment == "TESTNET"
    assert stop_fingerprint.symbol == "BTCUSDT"
    assert stop_fingerprint.subject_type == "PROTECTIVE_LEG"
    assert stop_fingerprint.subject_id == f"{preview.pair_id}:STOP:{preview.stop_client_algo_id}"
    assert stop_fingerprint.canonical_payload["pair_id"] == preview.pair_id
    assert stop_fingerprint.canonical_payload["leg_type"] == "STOP"
    assert stop_fingerprint.canonical_payload["client_algo_id"] == preview.stop_client_algo_id
    assert "timestamp" not in stop_fingerprint.canonical_payload
    assert "recvWindow" not in stop_fingerprint.canonical_payload
    assert "signature" not in stop_fingerprint.canonical_payload
    assert take_profit_fingerprint.canonical_payload != stop_fingerprint.canonical_payload
    assert take_profit_fingerprint.request_fingerprint != stop_fingerprint.request_fingerprint
    assert take_profit_fingerprint.canonical_payload["leg_type"] == "TAKE_PROFIT"
    assert take_profit_fingerprint.canonical_payload["client_algo_id"] == preview.take_profit_client_algo_id

    take_profit_leg_variant = LiveExecutionUnsignedMutationRequest(
        operation=stop_cancel_request.operation,
        environment=stop_cancel_request.environment,
        symbol=stop_cancel_request.symbol,
        subject_type=stop_cancel_request.subject_type,
        subject_id=stop_cancel_request.subject_id,
        fingerprint_context={**dict(stop_cancel_request.fingerprint_context), "leg_type": "TAKE_PROFIT"},
        transport_business_parameters=dict(stop_cancel_request.transport_business_parameters),
    )
    take_profit_leg_fingerprint = build_protective_cancel_from_final_request(take_profit_leg_variant)
    assert take_profit_leg_fingerprint.canonical_payload != stop_fingerprint.canonical_payload
    assert take_profit_leg_fingerprint.request_fingerprint != stop_fingerprint.request_fingerprint
    take_profit_client_variant = LiveExecutionUnsignedMutationRequest(
        operation=stop_cancel_request.operation,
        environment=stop_cancel_request.environment,
        symbol=stop_cancel_request.symbol,
        subject_type=stop_cancel_request.subject_type,
        subject_id=stop_cancel_request.subject_id,
        fingerprint_context={
            **dict(stop_cancel_request.fingerprint_context),
            "client_algo_id": preview.take_profit_client_algo_id,
        },
        transport_business_parameters={
            **dict(stop_cancel_request.transport_business_parameters),
            "clientAlgoId": preview.take_profit_client_algo_id,
        },
    )
    take_profit_client_fingerprint = build_protective_cancel_from_final_request(take_profit_client_variant)
    assert take_profit_client_fingerprint.canonical_payload != stop_fingerprint.canonical_payload
    assert take_profit_client_fingerprint.request_fingerprint != stop_fingerprint.request_fingerprint

    stop_cancel_permit = _issue(env, stop_fingerprint)
    take_profit_cancel_permit = _issue(env, take_profit_fingerprint)
    assert stop_cancel_permit.request_fingerprint == stop_fingerprint.request_fingerprint
    assert stop_cancel_permit.request_fingerprint != take_profit_fingerprint.request_fingerprint
    assert stop_cancel_permit.version == take_profit_cancel_permit.version == 1
    observer = {"close_count": 0, "close_completed": False}
    gate = LiveExecutionPermitGate(
        env=env,
        correlation_id_provider=lambda: CORRELATION,
        permit_persistence_factory=lambda **kwargs: _ClosingPermitPersistence(observer, **kwargs),
    )
    captured = {"request": None, "fingerprint": None, "transmitted": None}
    calls: list[tuple[str, str, str | None]] = []
    stop_delete_calls: list[str] = []
    post_calls: list[str | None] = []
    stop_deleted = False
    original_class_unsigned_builder = BinanceFuturesTestnetProtectiveOrdersClient.build_cancel_unsigned_business_request
    original_class_cancel_exact = BinanceFuturesTestnetProtectiveOrdersClient.cancel_algo_order_exact
    original_engine_fingerprint_builder = protective_engine_module.build_protective_cancel_from_final_request

    try:
        def captured_cancel_builder(actual_client, actual_preview, label):
            rebuilt = original_class_unsigned_builder(actual_client, actual_preview, label)
            if label == "TAKE_PROFIT":
                raise AssertionError("TAKE_PROFIT cancel builder must not run when TAKE_PROFIT is absent")
            assert label == "STOP"
            assert dict(rebuilt.fingerprint_context) == shared_before["fingerprint_context"]
            assert dict(rebuilt.transport_business_parameters) == expected_business
            captured["request"] = stop_cancel_request
            return stop_cancel_request

        def captured_fingerprint_builder(unsigned_request):
            assert unsigned_request is stop_cancel_request
            fingerprint = original_engine_fingerprint_builder(unsigned_request)
            assert fingerprint.request_fingerprint == stop_fingerprint.request_fingerprint
            captured["fingerprint"] = fingerprint
            return fingerprint

        def captured_cancel_exact(actual_client, client_algo_id, unsigned_business_request=None):
            assert client_algo_id == preview.stop_client_algo_id
            assert unsigned_business_request is stop_cancel_request
            assert dict(unsigned_business_request.transport_business_parameters) == expected_business
            return original_class_cancel_exact(actual_client, client_algo_id, unsigned_business_request=unsigned_business_request)

        BinanceFuturesTestnetProtectiveOrdersClient.build_cancel_unsigned_business_request = captured_cancel_builder
        BinanceFuturesTestnetProtectiveOrdersClient.cancel_algo_order_exact = captured_cancel_exact
        protective_engine_module.build_protective_cancel_from_final_request = captured_fingerprint_builder

        def transport(method, url, body, timeout, headers):
            nonlocal stop_deleted
            body_text = body.decode("utf-8")
            params = {key: values[0] for key, values in parse_qs(body_text).items()}
            calls.append((method, url, params.get("clientAlgoId")))
            if "positionSide/dual" in url:
                return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
            if "positionRisk" in url:
                return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
            assert "/fapi/v1/algoOrder" in url
            assert "openOrders" not in url
            assert "allOpenOrders" not in url
            client_id = params["clientAlgoId"]
            if method == "POST":
                post_calls.append(client_id)
                raise AssertionError("protective recovery must not create an order")
            if method == "DELETE":
                assert url == "https://demo-fapi.binance.com/fapi/v1/algoOrder"
                assert client_id == preview.stop_client_algo_id
                assert client_id != preview.take_profit_client_algo_id
                assert "algoId" not in params
                assert observer == {"close_count": 1, "close_completed": True}
                independent_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
                try:
                    with Session(independent_engine, future=True) as session:
                        permits = list(
                            session.scalars(
                                select(LiveExecutionPermitORM).where(
                                    LiveExecutionPermitORM.permit_id.in_([
                                        stop_cancel_permit.permit_id,
                                        take_profit_cancel_permit.permit_id,
                                    ])
                                )
                            ).all()
                        )
                        audits = list(
                            session.scalars(
                                select(AuditEventORM).where(
                                    AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                                    AuditEventORM.action == "PERMIT_CONSUMED",
                                )
                            ).all()
                        )
                    by_id = {permit.permit_id: permit for permit in permits}
                    assert by_id[stop_cancel_permit.permit_id].state == LiveExecutionPermitState.CONSUMED.value
                    assert by_id[stop_cancel_permit.permit_id].version == 2
                    assert by_id[stop_cancel_permit.permit_id].consumed_at is not None
                    assert by_id[stop_cancel_permit.permit_id].consumption_correlation_id == CORRELATION
                    assert by_id[stop_cancel_permit.permit_id].request_fingerprint == stop_fingerprint.request_fingerprint
                    assert by_id[stop_cancel_permit.permit_id].operation == LiveExecutionOperation.PROTECTIVE_CANCEL.value
                    assert by_id[stop_cancel_permit.permit_id].environment == "TESTNET"
                    assert by_id[stop_cancel_permit.permit_id].symbol == "BTCUSDT"
                    assert by_id[take_profit_cancel_permit.permit_id].state == LiveExecutionPermitState.ISSUED.value
                    assert by_id[take_profit_cancel_permit.permit_id].version == 1
                    assert by_id[take_profit_cancel_permit.permit_id].consumed_at is None
                    assert by_id[take_profit_cancel_permit.permit_id].consumption_correlation_id is None
                    stop_audits = [event for event in audits if event.metadata_json.get("permit_id") == stop_cancel_permit.permit_id]
                    take_profit_audits = [event for event in audits if event.metadata_json.get("permit_id") == take_profit_cancel_permit.permit_id]
                    assert len(stop_audits) == 1
                    assert stop_audits[0].result == "PASS"
                    assert stop_audits[0].metadata_json["operation"] == LiveExecutionOperation.PROTECTIVE_CANCEL.value
                    assert stop_audits[0].metadata_json["environment"] == "TESTNET"
                    assert stop_audits[0].metadata_json["symbol"] == "BTCUSDT"
                    assert stop_audits[0].metadata_json["request_fingerprint"] == stop_fingerprint.request_fingerprint
                    assert stop_audits[0].metadata_json["consumption_correlation_id"] == str(CORRELATION)
                    assert take_profit_audits == []
                finally:
                    independent_engine.dispose()
                transmitted_before_auth_removal = dict(params)
                auth_only = {"timestamp", "recvWindow", "signature"}
                assert auth_only <= set(transmitted_before_auth_removal)
                assert len(transmitted_before_auth_removal["signature"]) == 64
                actual_unsigned_transmitted = {
                    key: value for key, value in transmitted_before_auth_removal.items() if key not in auth_only
                }
                assert set(actual_unsigned_transmitted) == {"symbol", "clientAlgoId"}
                assert actual_unsigned_transmitted == expected_business
                assert actual_unsigned_transmitted == stop_cancel_request.transport_business_parameters
                assert "pair_id" not in actual_unsigned_transmitted
                assert "leg" not in actual_unsigned_transmitted
                assert "algoId" not in actual_unsigned_transmitted
                assert actual_unsigned_transmitted["symbol"] == "BTCUSDT"
                assert actual_unsigned_transmitted["clientAlgoId"] == preview.stop_client_algo_id
                captured["transmitted"] = transmitted_before_auth_removal
                stop_delete_calls.append(client_id)
                stop_deleted = True
                return BinanceLifecycleHTTPResponse(
                    200,
                    url,
                    {"clientAlgoId": preview.stop_client_algo_id, "algoId": "42", "code": 200, "msg": "success"},
                    10,
                )
            if method != "GET":
                raise AssertionError("unexpected authenticated method")
            if client_id == preview.stop_client_algo_id and not stop_deleted:
                return BinanceLifecycleHTTPResponse(
                    200,
                    url,
                    _algo_response(
                        preview.stop_client_algo_id,
                        "STOP_MARKET",
                        status="NEW",
                        trigger=str(preview.stop_trigger),
                    ),
                    10,
                )
            if client_id == preview.stop_client_algo_id and stop_deleted:
                raise BinanceFuturesTestnetProtectiveAPIError(
                    "NO_SUCH_ORDER",
                    http_status=400,
                    binance_code=-2013,
                    method="GET",
                    path="/fapi/v1/algoOrder",
                    request_transmitted=True,
                    response_received=True,
                )
            if client_id == preview.take_profit_client_algo_id:
                raise BinanceFuturesTestnetProtectiveAPIError(
                    "NO_SUCH_ORDER",
                    http_status=400,
                    binance_code=-2013,
                    method="GET",
                    path="/fapi/v1/algoOrder",
                    request_transmitted=True,
                    response_received=True,
                )
            raise AssertionError("unexpected clientAlgoId")

        client.authenticated_request = transport
        engine = BinanceFuturesTestnetProtectiveOrdersEngine(
            repo_root=tmp_path,
            env=env,
            http_get=_http_get,
            authenticated_request=transport,
            persistence_factory=ProtectiveLifecyclePersistence,
            permit_gate=gate,
            now_ms_provider=lambda: 1000,
        )
        engine._client = lambda loaded_config: client
        assert isinstance(engine, BinanceFuturesTestnetProtectiveOrdersEngine)
        assert isinstance(engine.permit_gate, LiveExecutionPermitGate)
        assert isinstance(client, BinanceFuturesTestnetProtectiveOrdersClient)

        result = engine.recover_protective_pair(
            preview.stop_client_algo_id,
            preview.take_profit_client_algo_id,
            confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY",
            config_path=str(config_path),
            stop_cancel_permit=LiveExecutionPermitReference(stop_cancel_permit.permit_id, stop_cancel_permit.version),
            take_profit_cancel_permit=LiveExecutionPermitReference(take_profit_cancel_permit.permit_id, take_profit_cancel_permit.version),
        )

        shared_after = {
            "operation": stop_cancel_request.operation,
            "environment": stop_cancel_request.environment,
            "symbol": stop_cancel_request.symbol,
            "subject_type": stop_cancel_request.subject_type,
            "subject_id": stop_cancel_request.subject_id,
            "fingerprint_context": dict(stop_cancel_request.fingerprint_context),
            "transport_business_parameters": dict(stop_cancel_request.transport_business_parameters),
        }
        assert shared_after == shared_before
        for auth_field in ("timestamp", "recvWindow", "signature", "headers", "credentials"):
            assert auth_field not in shared_after["fingerprint_context"]
            assert auth_field not in shared_after["transport_business_parameters"]
        assert captured["request"] is stop_cancel_request
        assert captured["fingerprint"] is not None
        assert captured["fingerprint"].request_fingerprint == stop_fingerprint.request_fingerprint
        assert captured["transmitted"] is not None
        assert result.status == "PASS", (result.decision, result.reason, [issue.to_dict() for issue in result.issues])
        assert result.decision == "RECOVERY_COMPLETE"
        assert result.stop_order is not None
        assert result.stop_order.client_algo_id == preview.stop_client_algo_id
        assert result.take_profit_order is None
        assert result.final_stop_order is None
        assert result.final_take_profit_order is None
        assert result.unexpected_trigger is False
        assert result.unexpected_position_change is False
        assert stop_delete_calls == [preview.stop_client_algo_id]
        assert post_calls == []
        assert [call for call in calls if call[0] == "DELETE"] == [
            ("DELETE", "https://demo-fapi.binance.com/fapi/v1/algoOrder", preview.stop_client_algo_id)
        ]
        assert [call for call in calls if call[0] == "POST"] == []
        assert all("allOpenOrders" not in url and "openOrders" not in url for _, url, _ in calls)
        assert len(result.cancel_requests) == 1
        assert result.cancel_requests[0].retry_count == 0
        assert result.create_requests == []
        assert observer == {"close_count": 1, "close_completed": True}

        stored_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
        try:
            with Session(stored_engine, future=True) as session:
                permits = list(
                    session.scalars(
                        select(LiveExecutionPermitORM).where(
                            LiveExecutionPermitORM.permit_id.in_([
                                stop_cancel_permit.permit_id,
                                take_profit_cancel_permit.permit_id,
                            ])
                        )
                    ).all()
                )
                audits = list(
                    session.scalars(
                        select(AuditEventORM).where(
                            AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                            AuditEventORM.action == "PERMIT_CONSUMED",
                        )
                    ).all()
                )
            by_id = {permit.permit_id: permit for permit in permits}
            assert by_id[stop_cancel_permit.permit_id].state == LiveExecutionPermitState.CONSUMED.value
            assert by_id[stop_cancel_permit.permit_id].version == stop_cancel_permit.version + 1 == 2
            assert by_id[stop_cancel_permit.permit_id].consumed_at is not None
            assert by_id[stop_cancel_permit.permit_id].consumption_correlation_id == CORRELATION
            assert by_id[stop_cancel_permit.permit_id].operation == LiveExecutionOperation.PROTECTIVE_CANCEL.value
            assert by_id[stop_cancel_permit.permit_id].environment == "TESTNET"
            assert by_id[stop_cancel_permit.permit_id].symbol == "BTCUSDT"
            assert by_id[stop_cancel_permit.permit_id].request_fingerprint == stop_fingerprint.request_fingerprint
            assert by_id[take_profit_cancel_permit.permit_id].state == LiveExecutionPermitState.ISSUED.value
            assert by_id[take_profit_cancel_permit.permit_id].version == 1
            assert by_id[take_profit_cancel_permit.permit_id].consumed_at is None
            assert by_id[take_profit_cancel_permit.permit_id].consumption_correlation_id is None
            stop_audits = [event for event in audits if event.metadata_json.get("permit_id") == stop_cancel_permit.permit_id]
            take_profit_audits = [event for event in audits if event.metadata_json.get("permit_id") == take_profit_cancel_permit.permit_id]
            assert len(stop_audits) == 1
            assert stop_audits[0].result == "PASS"
            assert stop_audits[0].metadata_json["operation"] == LiveExecutionOperation.PROTECTIVE_CANCEL.value
            assert stop_audits[0].metadata_json["environment"] == "TESTNET"
            assert stop_audits[0].metadata_json["symbol"] == "BTCUSDT"
            assert stop_audits[0].metadata_json["request_fingerprint"] == stop_fingerprint.request_fingerprint
            assert stop_audits[0].metadata_json["consumption_correlation_id"] == str(CORRELATION)
            assert take_profit_audits == []
        finally:
            stored_engine.dispose()
    finally:
        BinanceFuturesTestnetProtectiveOrdersClient.build_cancel_unsigned_business_request = original_class_unsigned_builder
        BinanceFuturesTestnetProtectiveOrdersClient.cancel_algo_order_exact = original_class_cancel_exact
        protective_engine_module.build_protective_cancel_from_final_request = original_engine_fingerprint_builder

def test_protective_take_profit_cancel_fingerprint_equals_transmitted_business_request(tmp_path) -> None:
    import engine.diagnostics.binance_futures_testnet_protective_orders_engine as protective_engine_module

    env = durable_state_env("RELEASED")
    config_path = _write_config(tmp_path)
    config = BinanceFuturesTestnetProtectiveOrdersConfig()
    client = BinanceFuturesTestnetProtectiveOrdersClient(
        config,
        http_get=_http_get,
        env=env,
        now_ms_provider=lambda: 1000,
    )
    position = client.require_protectable_position(_position())
    preview = client.build_preview(
        "pair-001",
        "smcbot-protect-sl-001",
        "smcbot-protect-tp-001",
        position,
        client.parse_exchange_filters(_exchange_info()),
        1000,
        1000,
    )
    stop_order = BinanceFuturesTestnetProtectiveAlgoSummary(
        symbol="BTCUSDT",
        client_algo_id=preview.stop_client_algo_id,
        algo_id="42",
        algo_type="CONDITIONAL",
        side="SELL",
        position_side="BOTH",
        order_type="STOP_MARKET",
        trigger_price=preview.stop_trigger,
        algo_status="NEW",
        actual_order_id="4200",
        close_position=True,
        working_type="MARK_PRICE",
        price_protect=True,
    )
    take_profit_order = BinanceFuturesTestnetProtectiveAlgoSummary(
        symbol="BTCUSDT",
        client_algo_id=preview.take_profit_client_algo_id,
        algo_id="43",
        algo_type="CONDITIONAL",
        side="SELL",
        position_side="BOTH",
        order_type="TAKE_PROFIT_MARKET",
        trigger_price=preview.take_profit_trigger,
        algo_status="NEW",
        actual_order_id="4300",
        close_position=True,
        working_type="MARK_PRICE",
        price_protect=True,
    )

    persistence = ProtectiveLifecyclePersistence(env=env)
    persistence.ensure_available()
    try:
        state = persistence.prepare_lifecycle(
            preview.pair_id,
            preview.stop_client_algo_id,
            preview.take_profit_client_algo_id,
            position,
            preview,
        )
        persistence.mark_create_transmitted(state)
        persistence.confirm_create(state, "STOP", stop_order)
        persistence.confirm_create(state, "TAKE_PROFIT", take_profit_order)
    finally:
        persistence.close()

    journal_engine = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=env,
        http_get=_http_get,
        authenticated_request=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("journal setup must not transport")),
        persistence_factory=_LegacyProtectivePersistence,
        now_ms_provider=lambda: 1000,
    )
    journal = BinanceFuturesTestnetProtectiveJournal(
        pair_id=preview.pair_id,
        stop_client_algo_id=preview.stop_client_algo_id,
        take_profit_client_algo_id=preview.take_profit_client_algo_id,
    )
    journal_engine._attach_journal_baseline(journal, position, preview)
    create_intent = journal_engine._mutation_intent(
        journal,
        preview,
        "TAKE_PROFIT",
        ProtectiveMutationKind.CREATE.value,
        "TAKE_PROFIT_CREATE_STARTED",
    )
    create_intent.resolved = True
    create_intent.reconciliation_state = ProtectiveReconciliationState.PRESENT.value
    create_intent.reconciliation_reason = "Exact clientAlgoId lookup found a matching order."
    journal.mutation_intents.append(create_intent)
    journal_engine._write_journal(
        config,
        journal,
        "TAKE_PROFIT_CREATED",
        {"client_algo_id": preview.take_profit_client_algo_id},
    )

    take_profit_cancel_request = client.build_cancel_unsigned_business_request(preview, "TAKE_PROFIT")
    stop_cancel_request = client.build_cancel_unsigned_business_request(preview, "STOP")
    shared_before = {
        "operation": take_profit_cancel_request.operation,
        "environment": take_profit_cancel_request.environment,
        "symbol": take_profit_cancel_request.symbol,
        "subject_type": take_profit_cancel_request.subject_type,
        "subject_id": take_profit_cancel_request.subject_id,
        "fingerprint_context": dict(take_profit_cancel_request.fingerprint_context),
        "transport_business_parameters": dict(take_profit_cancel_request.transport_business_parameters),
    }
    expected_business = shared_before["transport_business_parameters"]
    assert take_profit_cancel_request.operation == LiveExecutionOperation.PROTECTIVE_CANCEL
    assert take_profit_cancel_request.environment == "TESTNET"
    assert take_profit_cancel_request.symbol == "BTCUSDT"
    assert take_profit_cancel_request.subject_type == "PROTECTIVE_PAIR"
    assert take_profit_cancel_request.subject_id == preview.pair_id
    assert shared_before["fingerprint_context"]["pair_id"] == preview.pair_id
    assert shared_before["fingerprint_context"]["leg_type"] == "TAKE_PROFIT"
    assert shared_before["fingerprint_context"]["client_algo_id"] == preview.take_profit_client_algo_id
    assert expected_business == {"symbol": "BTCUSDT", "clientAlgoId": preview.take_profit_client_algo_id}
    assert set(expected_business) == {"symbol", "clientAlgoId"}
    for forbidden in ("leg", "timestamp", "recvWindow", "signature", "headers", "credentials"):
        assert forbidden not in expected_business
        assert forbidden not in shared_before["fingerprint_context"]
    assert "pair_id" not in expected_business
    assert "pair_id" in shared_before["fingerprint_context"]

    take_profit_fingerprint = build_protective_cancel_from_final_request(take_profit_cancel_request)
    stop_fingerprint = build_protective_cancel_from_final_request(stop_cancel_request)
    assert len(take_profit_fingerprint.request_fingerprint) == 64
    assert take_profit_fingerprint.request_fingerprint == take_profit_fingerprint.request_fingerprint.lower()
    assert set(take_profit_fingerprint.request_fingerprint) <= set("0123456789abcdef")
    assert take_profit_fingerprint.operation == LiveExecutionOperation.PROTECTIVE_CANCEL.value
    assert take_profit_fingerprint.environment == "TESTNET"
    assert take_profit_fingerprint.symbol == "BTCUSDT"
    assert take_profit_fingerprint.subject_type == "PROTECTIVE_LEG"
    assert take_profit_fingerprint.subject_id == f"{preview.pair_id}:TAKE_PROFIT:{preview.take_profit_client_algo_id}"
    assert take_profit_fingerprint.canonical_payload["pair_id"] == preview.pair_id
    assert take_profit_fingerprint.canonical_payload["leg_type"] == "TAKE_PROFIT"
    assert take_profit_fingerprint.canonical_payload["client_algo_id"] == preview.take_profit_client_algo_id
    assert "timestamp" not in take_profit_fingerprint.canonical_payload
    assert "recvWindow" not in take_profit_fingerprint.canonical_payload
    assert "signature" not in take_profit_fingerprint.canonical_payload
    assert stop_fingerprint.canonical_payload != take_profit_fingerprint.canonical_payload
    assert stop_fingerprint.request_fingerprint != take_profit_fingerprint.request_fingerprint
    assert stop_fingerprint.canonical_payload["leg_type"] == "STOP"
    assert stop_fingerprint.canonical_payload["client_algo_id"] == preview.stop_client_algo_id

    stop_leg_variant = LiveExecutionUnsignedMutationRequest(
        operation=take_profit_cancel_request.operation,
        environment=take_profit_cancel_request.environment,
        symbol=take_profit_cancel_request.symbol,
        subject_type=take_profit_cancel_request.subject_type,
        subject_id=take_profit_cancel_request.subject_id,
        fingerprint_context={**dict(take_profit_cancel_request.fingerprint_context), "leg_type": "STOP"},
        transport_business_parameters=dict(take_profit_cancel_request.transport_business_parameters),
    )
    stop_leg_fingerprint = build_protective_cancel_from_final_request(stop_leg_variant)
    assert stop_leg_fingerprint.canonical_payload != take_profit_fingerprint.canonical_payload
    assert stop_leg_fingerprint.request_fingerprint != take_profit_fingerprint.request_fingerprint
    stop_client_variant = LiveExecutionUnsignedMutationRequest(
        operation=take_profit_cancel_request.operation,
        environment=take_profit_cancel_request.environment,
        symbol=take_profit_cancel_request.symbol,
        subject_type=take_profit_cancel_request.subject_type,
        subject_id=take_profit_cancel_request.subject_id,
        fingerprint_context={
            **dict(take_profit_cancel_request.fingerprint_context),
            "client_algo_id": preview.stop_client_algo_id,
        },
        transport_business_parameters={
            **dict(take_profit_cancel_request.transport_business_parameters),
            "clientAlgoId": preview.stop_client_algo_id,
        },
    )
    stop_client_fingerprint = build_protective_cancel_from_final_request(stop_client_variant)
    assert stop_client_fingerprint.canonical_payload != take_profit_fingerprint.canonical_payload
    assert stop_client_fingerprint.request_fingerprint != take_profit_fingerprint.request_fingerprint

    take_profit_cancel_permit = _issue(env, take_profit_fingerprint)
    stop_cancel_permit = _issue(env, stop_fingerprint)
    assert take_profit_cancel_permit.request_fingerprint == take_profit_fingerprint.request_fingerprint
    assert take_profit_cancel_permit.request_fingerprint != stop_fingerprint.request_fingerprint
    assert take_profit_cancel_permit.version == stop_cancel_permit.version == 1
    observer = {"close_count": 0, "close_completed": False}
    gate = LiveExecutionPermitGate(
        env=env,
        correlation_id_provider=lambda: CORRELATION,
        permit_persistence_factory=lambda **kwargs: _ClosingPermitPersistence(observer, **kwargs),
    )
    captured = {"request": None, "fingerprint": None, "transmitted": None}
    calls: list[tuple[str, str, str | None]] = []
    take_profit_delete_calls: list[str] = []
    post_calls: list[str | None] = []
    take_profit_deleted = False
    original_class_unsigned_builder = BinanceFuturesTestnetProtectiveOrdersClient.build_cancel_unsigned_business_request
    original_class_cancel_exact = BinanceFuturesTestnetProtectiveOrdersClient.cancel_algo_order_exact
    original_engine_fingerprint_builder = protective_engine_module.build_protective_cancel_from_final_request

    try:
        def captured_cancel_builder(actual_client, actual_preview, label):
            rebuilt = original_class_unsigned_builder(actual_client, actual_preview, label)
            if label == "STOP":
                raise AssertionError("STOP cancel builder must not run when STOP is absent")
            assert label == "TAKE_PROFIT"
            assert dict(rebuilt.fingerprint_context) == shared_before["fingerprint_context"]
            assert dict(rebuilt.transport_business_parameters) == expected_business
            captured["request"] = take_profit_cancel_request
            return take_profit_cancel_request

        def captured_fingerprint_builder(unsigned_request):
            assert unsigned_request is take_profit_cancel_request
            fingerprint = original_engine_fingerprint_builder(unsigned_request)
            assert fingerprint.request_fingerprint == take_profit_fingerprint.request_fingerprint
            captured["fingerprint"] = fingerprint
            return fingerprint

        def captured_cancel_exact(actual_client, client_algo_id, unsigned_business_request=None):
            assert client_algo_id == preview.take_profit_client_algo_id
            assert unsigned_business_request is take_profit_cancel_request
            assert dict(unsigned_business_request.transport_business_parameters) == expected_business
            return original_class_cancel_exact(actual_client, client_algo_id, unsigned_business_request=unsigned_business_request)

        BinanceFuturesTestnetProtectiveOrdersClient.build_cancel_unsigned_business_request = captured_cancel_builder
        BinanceFuturesTestnetProtectiveOrdersClient.cancel_algo_order_exact = captured_cancel_exact
        protective_engine_module.build_protective_cancel_from_final_request = captured_fingerprint_builder

        def transport(method, url, body, timeout, headers):
            nonlocal take_profit_deleted
            body_text = body.decode("utf-8")
            params = {key: values[0] for key, values in parse_qs(body_text).items()}
            calls.append((method, url, params.get("clientAlgoId")))
            if "positionSide/dual" in url:
                return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
            if "positionRisk" in url:
                return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
            assert "/fapi/v1/algoOrder" in url
            assert "openOrders" not in url
            assert "allOpenOrders" not in url
            client_id = params["clientAlgoId"]
            if method == "POST":
                post_calls.append(client_id)
                raise AssertionError("protective recovery must not create an order")
            if method == "DELETE":
                assert url == "https://demo-fapi.binance.com/fapi/v1/algoOrder"
                assert client_id == preview.take_profit_client_algo_id
                assert client_id != preview.stop_client_algo_id
                assert "algoId" not in params
                assert observer == {"close_count": 1, "close_completed": True}
                independent_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
                try:
                    with Session(independent_engine, future=True) as session:
                        permits = list(
                            session.scalars(
                                select(LiveExecutionPermitORM).where(
                                    LiveExecutionPermitORM.permit_id.in_([
                                        take_profit_cancel_permit.permit_id,
                                        stop_cancel_permit.permit_id,
                                    ])
                                )
                            ).all()
                        )
                        audits = list(
                            session.scalars(
                                select(AuditEventORM).where(
                                    AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                                    AuditEventORM.action == "PERMIT_CONSUMED",
                                )
                            ).all()
                        )
                    by_id = {permit.permit_id: permit for permit in permits}
                    assert by_id[take_profit_cancel_permit.permit_id].state == LiveExecutionPermitState.CONSUMED.value
                    assert by_id[take_profit_cancel_permit.permit_id].version == 2
                    assert by_id[take_profit_cancel_permit.permit_id].consumed_at is not None
                    assert by_id[take_profit_cancel_permit.permit_id].consumption_correlation_id == CORRELATION
                    assert by_id[take_profit_cancel_permit.permit_id].request_fingerprint == take_profit_fingerprint.request_fingerprint
                    assert by_id[take_profit_cancel_permit.permit_id].operation == LiveExecutionOperation.PROTECTIVE_CANCEL.value
                    assert by_id[take_profit_cancel_permit.permit_id].environment == "TESTNET"
                    assert by_id[take_profit_cancel_permit.permit_id].symbol == "BTCUSDT"
                    assert by_id[stop_cancel_permit.permit_id].state == LiveExecutionPermitState.ISSUED.value
                    assert by_id[stop_cancel_permit.permit_id].version == 1
                    assert by_id[stop_cancel_permit.permit_id].consumed_at is None
                    assert by_id[stop_cancel_permit.permit_id].consumption_correlation_id is None
                    take_profit_audits = [event for event in audits if event.metadata_json.get("permit_id") == take_profit_cancel_permit.permit_id]
                    stop_audits = [event for event in audits if event.metadata_json.get("permit_id") == stop_cancel_permit.permit_id]
                    assert len(take_profit_audits) == 1
                    assert take_profit_audits[0].result == "PASS"
                    assert take_profit_audits[0].metadata_json["operation"] == LiveExecutionOperation.PROTECTIVE_CANCEL.value
                    assert take_profit_audits[0].metadata_json["environment"] == "TESTNET"
                    assert take_profit_audits[0].metadata_json["symbol"] == "BTCUSDT"
                    assert take_profit_audits[0].metadata_json["request_fingerprint"] == take_profit_fingerprint.request_fingerprint
                    assert take_profit_audits[0].metadata_json["consumption_correlation_id"] == str(CORRELATION)
                    assert stop_audits == []
                finally:
                    independent_engine.dispose()
                transmitted_before_auth_removal = dict(params)
                auth_only = {"timestamp", "recvWindow", "signature"}
                assert auth_only <= set(transmitted_before_auth_removal)
                assert len(transmitted_before_auth_removal["signature"]) == 64
                actual_unsigned_transmitted = {
                    key: value for key, value in transmitted_before_auth_removal.items() if key not in auth_only
                }
                assert set(actual_unsigned_transmitted) == {"symbol", "clientAlgoId"}
                assert actual_unsigned_transmitted == expected_business
                assert actual_unsigned_transmitted == take_profit_cancel_request.transport_business_parameters
                assert "pair_id" not in actual_unsigned_transmitted
                assert "leg" not in actual_unsigned_transmitted
                assert "algoId" not in actual_unsigned_transmitted
                assert actual_unsigned_transmitted["symbol"] == "BTCUSDT"
                assert actual_unsigned_transmitted["clientAlgoId"] == preview.take_profit_client_algo_id
                captured["transmitted"] = transmitted_before_auth_removal
                take_profit_delete_calls.append(client_id)
                take_profit_deleted = True
                return BinanceLifecycleHTTPResponse(
                    200,
                    url,
                    {"clientAlgoId": preview.take_profit_client_algo_id, "algoId": "43", "code": 200, "msg": "success"},
                    10,
                )
            if method != "GET":
                raise AssertionError("unexpected authenticated method")
            if client_id == preview.stop_client_algo_id:
                raise BinanceFuturesTestnetProtectiveAPIError(
                    "NO_SUCH_ORDER",
                    http_status=400,
                    binance_code=-2013,
                    method="GET",
                    path="/fapi/v1/algoOrder",
                    request_transmitted=True,
                    response_received=True,
                )
            if client_id == preview.take_profit_client_algo_id and not take_profit_deleted:
                return BinanceLifecycleHTTPResponse(
                    200,
                    url,
                    _algo_response(
                        preview.take_profit_client_algo_id,
                        "TAKE_PROFIT_MARKET",
                        status="NEW",
                        trigger=str(preview.take_profit_trigger),
                    ),
                    10,
                )
            if client_id == preview.take_profit_client_algo_id and take_profit_deleted:
                raise BinanceFuturesTestnetProtectiveAPIError(
                    "NO_SUCH_ORDER",
                    http_status=400,
                    binance_code=-2013,
                    method="GET",
                    path="/fapi/v1/algoOrder",
                    request_transmitted=True,
                    response_received=True,
                )
            raise AssertionError("unexpected clientAlgoId")

        client.authenticated_request = transport
        engine = BinanceFuturesTestnetProtectiveOrdersEngine(
            repo_root=tmp_path,
            env=env,
            http_get=_http_get,
            authenticated_request=transport,
            persistence_factory=_LegacyProtectivePersistence,
            permit_gate=gate,
            now_ms_provider=lambda: 1000,
        )
        engine._client = lambda loaded_config: client
        assert isinstance(engine, BinanceFuturesTestnetProtectiveOrdersEngine)
        assert isinstance(engine.permit_gate, LiveExecutionPermitGate)
        assert isinstance(client, BinanceFuturesTestnetProtectiveOrdersClient)

        result = engine.recover_protective_pair(
            preview.stop_client_algo_id,
            preview.take_profit_client_algo_id,
            confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY",
            config_path=str(config_path),
            stop_cancel_permit=LiveExecutionPermitReference(stop_cancel_permit.permit_id, stop_cancel_permit.version),
            take_profit_cancel_permit=LiveExecutionPermitReference(take_profit_cancel_permit.permit_id, take_profit_cancel_permit.version),
        )

        shared_after = {
            "operation": take_profit_cancel_request.operation,
            "environment": take_profit_cancel_request.environment,
            "symbol": take_profit_cancel_request.symbol,
            "subject_type": take_profit_cancel_request.subject_type,
            "subject_id": take_profit_cancel_request.subject_id,
            "fingerprint_context": dict(take_profit_cancel_request.fingerprint_context),
            "transport_business_parameters": dict(take_profit_cancel_request.transport_business_parameters),
        }
        assert shared_after == shared_before
        for auth_field in ("timestamp", "recvWindow", "signature", "headers", "credentials", "apiKey"):
            assert auth_field not in shared_after["fingerprint_context"]
            assert auth_field not in shared_after["transport_business_parameters"]
        assert captured["request"] is take_profit_cancel_request
        assert captured["fingerprint"] is not None
        assert captured["fingerprint"].request_fingerprint == take_profit_fingerprint.request_fingerprint
        assert captured["transmitted"] is not None
        assert result.status == "PASS", (result.decision, result.reason, [issue.to_dict() for issue in result.issues])
        assert result.decision == "RECOVERY_COMPLETE"
        assert result.stop_order is None
        assert result.take_profit_order is not None
        assert result.take_profit_order.client_algo_id == preview.take_profit_client_algo_id
        assert result.final_stop_order is None
        assert result.final_take_profit_order is None
        assert result.recovery_required is False
        assert result.unexpected_trigger is False
        assert result.unexpected_position_change is False
        assert take_profit_delete_calls == [preview.take_profit_client_algo_id]
        assert post_calls == []
        assert [call for call in calls if call[0] == "DELETE"] == [
            ("DELETE", "https://demo-fapi.binance.com/fapi/v1/algoOrder", preview.take_profit_client_algo_id)
        ]
        assert [call for call in calls if call[0] == "POST"] == []
        assert all("allOpenOrders" not in url and "openOrders" not in url for _, url, _ in calls)
        assert len(result.cancel_requests) == 1
        assert result.cancel_requests[0].retry_count == 0
        assert result.create_requests == []
        assert observer == {"close_count": 1, "close_completed": True}

        stored_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
        try:
            with Session(stored_engine, future=True) as session:
                permits = list(
                    session.scalars(
                        select(LiveExecutionPermitORM).where(
                            LiveExecutionPermitORM.permit_id.in_([
                                take_profit_cancel_permit.permit_id,
                                stop_cancel_permit.permit_id,
                            ])
                        )
                    ).all()
                )
                audits = list(
                    session.scalars(
                        select(AuditEventORM).where(
                            AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                            AuditEventORM.action == "PERMIT_CONSUMED",
                        )
                    ).all()
                )
            by_id = {permit.permit_id: permit for permit in permits}
            assert by_id[take_profit_cancel_permit.permit_id].state == LiveExecutionPermitState.CONSUMED.value
            assert by_id[take_profit_cancel_permit.permit_id].version == take_profit_cancel_permit.version + 1 == 2
            assert by_id[take_profit_cancel_permit.permit_id].consumed_at is not None
            assert by_id[take_profit_cancel_permit.permit_id].consumption_correlation_id == CORRELATION
            assert by_id[take_profit_cancel_permit.permit_id].operation == LiveExecutionOperation.PROTECTIVE_CANCEL.value
            assert by_id[take_profit_cancel_permit.permit_id].environment == "TESTNET"
            assert by_id[take_profit_cancel_permit.permit_id].symbol == "BTCUSDT"
            assert by_id[take_profit_cancel_permit.permit_id].request_fingerprint == take_profit_fingerprint.request_fingerprint
            assert by_id[stop_cancel_permit.permit_id].state == LiveExecutionPermitState.ISSUED.value
            assert by_id[stop_cancel_permit.permit_id].version == 1
            assert by_id[stop_cancel_permit.permit_id].consumed_at is None
            assert by_id[stop_cancel_permit.permit_id].consumption_correlation_id is None
            take_profit_audits = [event for event in audits if event.metadata_json.get("permit_id") == take_profit_cancel_permit.permit_id]
            stop_audits = [event for event in audits if event.metadata_json.get("permit_id") == stop_cancel_permit.permit_id]
            assert len(take_profit_audits) == 1
            assert take_profit_audits[0].result == "PASS"
            assert take_profit_audits[0].metadata_json["operation"] == LiveExecutionOperation.PROTECTIVE_CANCEL.value
            assert take_profit_audits[0].metadata_json["environment"] == "TESTNET"
            assert take_profit_audits[0].metadata_json["symbol"] == "BTCUSDT"
            assert take_profit_audits[0].metadata_json["request_fingerprint"] == take_profit_fingerprint.request_fingerprint
            assert take_profit_audits[0].metadata_json["consumption_correlation_id"] == str(CORRELATION)
            assert stop_audits == []
        finally:
            stored_engine.dispose()
    finally:
        BinanceFuturesTestnetProtectiveOrdersClient.build_cancel_unsigned_business_request = original_class_unsigned_builder
        BinanceFuturesTestnetProtectiveOrdersClient.cancel_algo_order_exact = original_class_cancel_exact
        protective_engine_module.build_protective_cancel_from_final_request = original_engine_fingerprint_builder
def test_protective_cancel_permit_is_committed_and_closed_before_delete(tmp_path) -> None:
    env = durable_state_env("RELEASED")
    config_path = _write_config(tmp_path)
    config = BinanceFuturesTestnetProtectiveOrdersConfig()
    client = BinanceFuturesTestnetProtectiveOrdersClient(config, env=env)
    position = client.require_protectable_position(_position())
    preview = client.build_preview(
        "pair-001",
        "smcbot-protect-sl-001",
        "smcbot-protect-tp-001",
        position,
        client.parse_exchange_filters(_exchange_info()),
        1000,
        1000,
    )
    stop_order = BinanceFuturesTestnetProtectiveAlgoSummary(
        symbol="BTCUSDT",
        client_algo_id=preview.stop_client_algo_id,
        algo_id="42",
        algo_type="CONDITIONAL",
        side="SELL",
        position_side="BOTH",
        order_type="STOP_MARKET",
        trigger_price=preview.stop_trigger,
        algo_status="NEW",
        actual_order_id="4200",
        close_position=True,
        working_type="MARK_PRICE",
        price_protect=True,
    )

    persistence = ProtectiveLifecyclePersistence(env=env)
    persistence.ensure_available()
    try:
        state = persistence.prepare_lifecycle(
            preview.pair_id,
            preview.stop_client_algo_id,
            preview.take_profit_client_algo_id,
            position,
            preview,
        )
        persistence.mark_create_transmitted(state)
        persistence.confirm_create(state, "STOP", stop_order)
    finally:
        persistence.close()

    observer = {"close_count": 0, "close_completed": False}
    unsigned_request = client.build_cancel_unsigned_business_request(preview, "STOP")
    fingerprint = build_protective_cancel_from_final_request(unsigned_request)
    assert unsigned_request.environment == "TESTNET"
    assert unsigned_request.symbol == "BTCUSDT"
    assert unsigned_request.subject_id == preview.pair_id
    assert unsigned_request.fingerprint_context["leg_type"] == "STOP"
    assert unsigned_request.fingerprint_context["client_algo_id"] == preview.stop_client_algo_id
    issued = _issue(env, fingerprint)
    gate = LiveExecutionPermitGate(
        env=env,
        correlation_id_provider=lambda: CORRELATION,
        permit_persistence_factory=lambda **kwargs: _ClosingPermitPersistence(observer, **kwargs),
    )
    calls: list[tuple[str, str]] = []
    deleted = False

    def transport(method, url, body, timeout, headers):
        nonlocal deleted
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url))
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        if method == "POST":
            raise AssertionError("protective recovery must not create an order")
        assert url.startswith("https://demo-fapi.binance.com/")
        assert "/fapi/v1/algoOrder" in url
        client_id = params["clientAlgoId"][0]
        if method == "DELETE":
            assert client_id == preview.stop_client_algo_id
            assert "algoId" not in params
            _assert_consumed_at_transport(
                env,
                issued,
                fingerprint,
                observer,
                LiveExecutionOperation.PROTECTIVE_CANCEL,
            )
            deleted = True
            return BinanceLifecycleHTTPResponse(
                200,
                url,
                {
                    "clientAlgoId": preview.stop_client_algo_id,
                    "algoId": "42",
                    "code": 200,
                    "msg": "success",
                },
                10,
            )
        if method != "GET":
            raise AssertionError("unexpected authenticated method")
        if client_id == preview.stop_client_algo_id and not deleted:
            return BinanceLifecycleHTTPResponse(
                200,
                url,
                _algo_response(
                    preview.stop_client_algo_id,
                    "STOP_MARKET",
                    status="NEW",
                    trigger=str(preview.stop_trigger),
                ),
                10,
            )
        raise BinanceFuturesTestnetProtectiveAPIError(
            "NO_SUCH_ORDER",
            http_status=400,
            binance_code=-2013,
            method="GET",
            path="/fapi/v1/algoOrder",
            request_transmitted=True,
            response_received=True,
        )

    engine = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=env,
        http_get=_http_get,
        authenticated_request=transport,
        persistence_factory=ProtectiveLifecyclePersistence,
        permit_gate=gate,
        now_ms_provider=lambda: 1000,
    )
    journal = BinanceFuturesTestnetProtectiveJournal(
        pair_id=preview.pair_id,
        stop_client_algo_id=preview.stop_client_algo_id,
        take_profit_client_algo_id=preview.take_profit_client_algo_id,
    )
    engine._attach_journal_baseline(journal, position, preview)
    create_intent = engine._mutation_intent(
        journal,
        preview,
        "STOP",
        ProtectiveMutationKind.CREATE.value,
        "STOP_CREATE_STARTED",
    )
    create_intent.resolved = True
    create_intent.reconciliation_state = ProtectiveReconciliationState.PRESENT.value
    create_intent.reconciliation_reason = "Exact clientAlgoId lookup found a matching order."
    journal.mutation_intents.append(create_intent)
    engine._write_journal(
        config,
        journal,
        "STOP_CREATED",
        {"client_algo_id": preview.stop_client_algo_id},
    )

    assert isinstance(engine.permit_gate, LiveExecutionPermitGate)
    result = engine.recover_protective_pair(
        preview.stop_client_algo_id,
        preview.take_profit_client_algo_id,
        confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY",
        config_path=str(config_path),
        stop_cancel_permit=LiveExecutionPermitReference(issued.permit_id, issued.version),
    )

    delete_calls = [(method, url) for method, url in calls if method == "DELETE"]
    post_calls = [(method, url) for method, url in calls if method == "POST"]
    assert result.status == "PASS", (result.decision, result.reason, [issue.to_dict() for issue in result.issues])
    assert result.decision == "RECOVERY_COMPLETE"
    assert result.stop_order is not None
    assert result.stop_order.client_algo_id == preview.stop_client_algo_id
    assert result.take_profit_order is None
    assert result.final_stop_order is None
    assert len(delete_calls) == 1
    assert all("/fapi/v1/algoOrder" in url for _, url in delete_calls)
    assert post_calls == []
    assert len(result.cancel_requests) == 1
    assert result.cancel_requests[0].retry_count == 0
    assert observer == {"close_count": 1, "close_completed": True}

    stored_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(stored_engine, future=True) as session:
            stored = session.scalar(
                select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == issued.permit_id)
            )
            audits = list(
                session.scalars(
                    select(AuditEventORM).where(
                        AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                        AuditEventORM.action == "PERMIT_CONSUMED",
                    )
                ).all()
            )
        assert stored is not None
        assert stored.state == LiveExecutionPermitState.CONSUMED.value
        assert stored.version == issued.version + 1 == 2
        assert stored.consumption_correlation_id is not None
        assert stored.operation == LiveExecutionOperation.PROTECTIVE_CANCEL.value
        matching = [event for event in audits if event.metadata_json.get("permit_id") == issued.permit_id]
        assert len(matching) == 1
    finally:
        stored_engine.dispose()



def test_lifecycle_create_fingerprint_equals_transmitted_business_request(tmp_path) -> None:
    import engine.diagnostics.binance_futures_testnet_order_lifecycle_engine as lifecycle_engine_module

    env = durable_state_env("RELEASED")
    config_path = _write_lifecycle_config(tmp_path)
    config = BinanceFuturesTestnetOrderLifecycleConfig()
    lifecycle_id = "lifecycle-fingerprint-create-001"
    client_order_id = "smcbot-lifecycle-fp-create-001"
    client = BinanceFuturesTestnetOrderLifecycleClient(
        config,
        http_get=_lifecycle_http_get,
        env=env,
        now_ms_provider=lambda: 123,
    )
    filters = client.parse_exchange_filters(_lifecycle_exchange_info())
    ticker = client.parse_book_ticker(
        {
            "symbol": "BTCUSDT",
            "bidPrice": "50000",
            "askPrice": "50001",
            "bidQty": "1",
            "askQty": "1",
        }
    )
    preview = client.build_lifecycle_preview(
        lifecycle_id,
        client_order_id,
        "BUY",
        Decimal("0.001"),
        config.default_price_offset_bps,
        filters,
        ticker,
    )
    create_request_for_permit = client.build_create_unsigned_business_request(preview)
    create_fingerprint_for_permit = build_lifecycle_create_from_final_request(create_request_for_permit)
    cancel_request_for_permit = client.build_cancel_unsigned_business_request(client_order_id)
    cancel_fingerprint = build_lifecycle_cancel_from_final_request(cancel_request_for_permit)
    create_permit = _issue(env, create_fingerprint_for_permit)
    cancel_permit = _issue(env, cancel_fingerprint)
    assert create_permit.permit_id != cancel_permit.permit_id
    assert create_permit.version == cancel_permit.version == 1

    expected_business = dict(create_request_for_permit.transport_business_parameters)
    expected_business_keys = {
        "symbol",
        "newClientOrderId",
        "side",
        "positionSide",
        "type",
        "quantity",
        "price",
        "timeInForce",
        "newOrderRespType",
    }
    field_classification = {
        "client_order_id": "FINGERPRINT_AND_TRANSPORT",
        "symbol": "FINGERPRINT_AND_TRANSPORT",
        "side": "FINGERPRINT_AND_TRANSPORT",
        "positionSide": "FINGERPRINT_AND_TRANSPORT",
        "type": "FINGERPRINT_AND_TRANSPORT",
        "quantity": "FINGERPRINT_AND_TRANSPORT",
        "price": "FINGERPRINT_AND_TRANSPORT",
        "timeInForce": "FINGERPRINT_AND_TRANSPORT",
        "reduceOnly": "FINGERPRINT_BOUND_DEFAULTED_FIELD",
        "newOrderRespType": "FIXED_TRANSPORT_CONTROL",
        "timestamp": "AUTH_TRANSPORT",
        "recvWindow": "AUTH_TRANSPORT",
        "signature": "AUTH_TRANSPORT",
    }
    assert set(field_classification) == {
        "client_order_id",
        "symbol",
        "side",
        "positionSide",
        "type",
        "quantity",
        "price",
        "timeInForce",
        "reduceOnly",
        "newOrderRespType",
        "timestamp",
        "recvWindow",
        "signature",
    }
    assert create_request_for_permit.operation == LiveExecutionOperation.ORDER_LIFECYCLE_CREATE
    assert create_request_for_permit.environment == "TESTNET"
    assert create_request_for_permit.symbol == "BTCUSDT"
    assert create_request_for_permit.subject_type == "ORDER_LIFECYCLE"
    assert create_request_for_permit.subject_id == client_order_id
    assert set(expected_business) == expected_business_keys
    assert expected_business["symbol"] == "BTCUSDT"
    assert expected_business["newClientOrderId"] == client_order_id
    assert expected_business["side"] == "BUY"
    assert expected_business["positionSide"] == "BOTH"
    assert expected_business["type"] == "LIMIT"
    assert expected_business["quantity"] == "0.001"
    assert expected_business["price"] == format(preview.derived_price.normalize(), "f")
    assert expected_business["timeInForce"] == "GTX"
    assert expected_business["newOrderRespType"] == config.new_order_response_type
    assert field_classification["newOrderRespType"] == "FIXED_TRANSPORT_CONTROL"
    assert field_classification["reduceOnly"] == "FINGERPRINT_BOUND_DEFAULTED_FIELD"
    assert "reduceOnly" not in expected_business
    assert create_request_for_permit.fingerprint_context["reduce_only"] is False
    assert "reduceOnly" not in create_request_for_permit.transport_business_parameters
    for forbidden in ("timestamp", "recvWindow", "signature", "apiKey", "headers", "credentials", "lifecycle_id"):
        assert forbidden not in expected_business
        assert forbidden not in create_request_for_permit.fingerprint_context
    assert "newOrderRespType" not in create_request_for_permit.fingerprint_context
    assert create_request_for_permit.fingerprint_context["client_order_id"] == expected_business["newClientOrderId"]
    assert create_request_for_permit.fingerprint_context["side"] == expected_business["side"]
    assert create_request_for_permit.fingerprint_context["position_side"] == expected_business["positionSide"]
    assert create_request_for_permit.fingerprint_context["order_type"] == expected_business["type"]
    assert create_request_for_permit.fingerprint_context["quantity"] == expected_business["quantity"]
    assert create_request_for_permit.fingerprint_context["price"] == expected_business["price"]
    assert create_request_for_permit.fingerprint_context["time_in_force"] == expected_business["timeInForce"]
    assert create_request_for_permit.fingerprint_context["reduce_only"] is False

    assert len(create_fingerprint_for_permit.request_fingerprint) == 64
    assert create_fingerprint_for_permit.request_fingerprint == create_fingerprint_for_permit.request_fingerprint.lower()
    assert set(create_fingerprint_for_permit.request_fingerprint) <= set("0123456789abcdef")
    assert create_fingerprint_for_permit.operation == LiveExecutionOperation.ORDER_LIFECYCLE_CREATE.value
    assert create_fingerprint_for_permit.environment == "TESTNET"
    assert create_fingerprint_for_permit.symbol == "BTCUSDT"
    assert create_fingerprint_for_permit.subject_type == "CLIENT_ORDER"
    assert create_fingerprint_for_permit.subject_id == client_order_id
    assert create_fingerprint_for_permit.canonical_payload["client_order_id"] == client_order_id
    assert create_fingerprint_for_permit.canonical_payload["side"] == "BUY"
    assert create_fingerprint_for_permit.canonical_payload["position_side"] == "BOTH"
    assert create_fingerprint_for_permit.canonical_payload["order_type"] == "LIMIT"
    assert create_fingerprint_for_permit.canonical_payload["quantity"] == "0.001"
    assert create_fingerprint_for_permit.canonical_payload["price"] == expected_business["price"]
    assert create_fingerprint_for_permit.canonical_payload["time_in_force"] == "GTX"
    assert create_fingerprint_for_permit.canonical_payload["reduce_only"] is False
    assert field_classification["reduceOnly"] == "FINGERPRINT_BOUND_DEFAULTED_FIELD"
    assert "reduceOnly" not in create_request_for_permit.transport_business_parameters
    assert "timestamp" not in create_fingerprint_for_permit.canonical_payload
    assert "recvWindow" not in create_fingerprint_for_permit.canonical_payload
    assert "signature" not in create_fingerprint_for_permit.canonical_payload

    reduce_only_true_context = {
        **dict(create_request_for_permit.fingerprint_context),
        "reduce_only": True,
    }
    reduce_only_true_fingerprint = build_live_execution_request_fingerprint(reduce_only_true_context)
    assert reduce_only_true_fingerprint.canonical_payload["reduce_only"] is True
    assert reduce_only_true_fingerprint.canonical_payload != create_fingerprint_for_permit.canonical_payload
    assert reduce_only_true_fingerprint.request_fingerprint != create_fingerprint_for_permit.request_fingerprint
    with pytest.raises(ValueError, match="PERMIT_REQUEST_INVALID"):
        LiveExecutionUnsignedMutationRequest(
            operation=create_request_for_permit.operation,
            environment=create_request_for_permit.environment,
            symbol=create_request_for_permit.symbol,
            subject_type=create_request_for_permit.subject_type,
            subject_id=create_request_for_permit.subject_id,
            fingerprint_context=reduce_only_true_context,
            transport_business_parameters=dict(create_request_for_permit.transport_business_parameters),
        )
    reduce_only_true_transmitted_request = LiveExecutionUnsignedMutationRequest(
        operation=create_request_for_permit.operation,
        environment=create_request_for_permit.environment,
        symbol=create_request_for_permit.symbol,
        subject_type=create_request_for_permit.subject_type,
        subject_id=create_request_for_permit.subject_id,
        fingerprint_context=reduce_only_true_context,
        transport_business_parameters={
            **dict(create_request_for_permit.transport_business_parameters),
            "reduceOnly": "true",
        },
    )
    assert reduce_only_true_transmitted_request.transport_business_parameters["reduceOnly"] == "true"

    client_id_variant = LiveExecutionUnsignedMutationRequest(
        operation=create_request_for_permit.operation,
        environment=create_request_for_permit.environment,
        symbol=create_request_for_permit.symbol,
        subject_type=create_request_for_permit.subject_type,
        subject_id="smcbot-lifecycle-fp-create-002",
        fingerprint_context={
            **dict(create_request_for_permit.fingerprint_context),
            "client_order_id": "smcbot-lifecycle-fp-create-002",
        },
        transport_business_parameters={
            **dict(create_request_for_permit.transport_business_parameters),
            "newClientOrderId": "smcbot-lifecycle-fp-create-002",
        },
    )
    client_id_variant_fingerprint = build_lifecycle_create_from_final_request(client_id_variant)
    assert client_id_variant_fingerprint.canonical_payload != create_fingerprint_for_permit.canonical_payload
    assert client_id_variant_fingerprint.request_fingerprint != create_fingerprint_for_permit.request_fingerprint
    price_variant = LiveExecutionUnsignedMutationRequest(
        operation=create_request_for_permit.operation,
        environment=create_request_for_permit.environment,
        symbol=create_request_for_permit.symbol,
        subject_type=create_request_for_permit.subject_type,
        subject_id=create_request_for_permit.subject_id,
        fingerprint_context={
            **dict(create_request_for_permit.fingerprint_context),
            "price": "49900.0",
        },
        transport_business_parameters={
            **dict(create_request_for_permit.transport_business_parameters),
            "price": "49900.0",
        },
    )
    price_variant_fingerprint = build_lifecycle_create_from_final_request(price_variant)
    assert price_variant_fingerprint.canonical_payload != create_fingerprint_for_permit.canonical_payload
    assert price_variant_fingerprint.request_fingerprint != create_fingerprint_for_permit.request_fingerprint

    observer = {"close_count": 0, "close_completed": False}
    gate = LiveExecutionPermitGate(
        env=env,
        correlation_id_provider=lambda: CORRELATION,
        permit_persistence_factory=lambda **kwargs: _ClosingPermitPersistence(observer, **kwargs),
    )
    captured = {"request": None, "fingerprint": None, "transmitted": None}
    calls: list[tuple[str, str, str | None]] = []
    journal_at_post: list[dict[str, object]] = []
    original_class_create_builder = BinanceFuturesTestnetOrderLifecycleClient.build_create_unsigned_business_request
    original_class_cancel_builder = BinanceFuturesTestnetOrderLifecycleClient.build_cancel_unsigned_business_request
    original_class_create_order = BinanceFuturesTestnetOrderLifecycleClient.create_order
    original_engine_fingerprint_builder = lifecycle_engine_module.build_lifecycle_create_from_final_request

    try:
        def captured_create_builder(actual_client, actual_preview):
            rebuilt = original_class_create_builder(actual_client, actual_preview)
            assert rebuilt.operation == create_request_for_permit.operation
            assert rebuilt.environment == create_request_for_permit.environment
            assert rebuilt.symbol == create_request_for_permit.symbol
            assert rebuilt.subject_type == create_request_for_permit.subject_type
            assert rebuilt.subject_id == create_request_for_permit.subject_id
            assert dict(rebuilt.fingerprint_context) == dict(create_request_for_permit.fingerprint_context)
            assert dict(rebuilt.transport_business_parameters) == expected_business
            captured["request"] = rebuilt
            return rebuilt

        def blocked_cancel_builder(actual_client, actual_client_order_id):
            raise AssertionError("cancel shared request must not be built when created order expires")

        def captured_fingerprint_builder(unsigned_request):
            assert unsigned_request is captured["request"]
            fingerprint = original_engine_fingerprint_builder(unsigned_request)
            assert fingerprint.request_fingerprint == create_fingerprint_for_permit.request_fingerprint
            captured["fingerprint"] = fingerprint
            return fingerprint

        def captured_create_order(actual_client, actual_preview, server_time=None, unsigned_business_request=None):
            assert unsigned_business_request is captured["request"]
            assert dict(unsigned_business_request.transport_business_parameters) == expected_business
            return original_class_create_order(
                actual_client,
                actual_preview,
                server_time=server_time,
                unsigned_business_request=unsigned_business_request,
            )

        BinanceFuturesTestnetOrderLifecycleClient.build_create_unsigned_business_request = captured_create_builder
        BinanceFuturesTestnetOrderLifecycleClient.build_cancel_unsigned_business_request = blocked_cancel_builder
        BinanceFuturesTestnetOrderLifecycleClient.create_order = captured_create_order
        lifecycle_engine_module.build_lifecycle_create_from_final_request = captured_fingerprint_builder

        def transport(method, url, body, timeout, headers):
            body_text = body.decode("utf-8")
            params = {key: values[0] for key, values in parse_qs(body_text).items()}
            identity = params.get("newClientOrderId") or params.get("origClientOrderId")
            calls.append((method, url, identity))
            if "positionSide/dual" in url:
                return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
            if "positionRisk" in url:
                return BinanceLifecycleHTTPResponse(
                    200,
                    url,
                    [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": "0"}],
                    10,
                )
            assert url == "https://demo-fapi.binance.com/fapi/v1/order"
            if method == "DELETE":
                raise AssertionError("terminal-safe lifecycle order must not be cancelled")
            if method == "POST":
                assert identity == client_order_id
                assert observer == {"close_count": 1, "close_completed": True}
                _assert_consumed_at_transport(
                    env,
                    create_permit,
                    create_fingerprint_for_permit,
                    observer,
                    LiveExecutionOperation.ORDER_LIFECYCLE_CREATE,
                )
                assert env[config.api_key_env_var] not in body_text
                assert env[config.api_secret_env_var] not in body_text
                journal_path = (
                    tmp_path
                    / "data"
                    / "runtime"
                    / "binance_futures_testnet_order_lifecycle"
                    / "lifecycle.json"
                )
                persisted_journal = json.loads(journal_path.read_text(encoding="utf-8"))
                create_markers = [
                    entry
                    for entry in persisted_journal["entries"]
                    if entry["phase"] == LifecyclePhase.CREATE_REQUEST_STARTED.value
                ]
                assert persisted_journal["phase"] == LifecyclePhase.CREATE_REQUEST_STARTED.value
                assert persisted_journal["entries"][-1]["phase"] == LifecyclePhase.CREATE_REQUEST_STARTED.value
                assert persisted_journal["entries"][-1]["details"]["client_order_id"] == client_order_id
                assert len(create_markers) == 1
                journal_at_post.append(persisted_journal)

                independent_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
                try:
                    with Session(independent_engine, future=True) as session:
                        permits = list(
                            session.scalars(
                                select(LiveExecutionPermitORM).where(
                                    LiveExecutionPermitORM.permit_id.in_([create_permit.permit_id, cancel_permit.permit_id])
                                )
                            ).all()
                        )
                        audits = list(
                            session.scalars(
                                select(AuditEventORM).where(
                                    AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                                    AuditEventORM.action == "PERMIT_CONSUMED",
                                )
                            ).all()
                        )
                    by_id = {permit.permit_id: permit for permit in permits}
                    assert by_id[create_permit.permit_id].state == LiveExecutionPermitState.CONSUMED.value
                    assert by_id[create_permit.permit_id].version == 2
                    assert by_id[create_permit.permit_id].consumed_at is not None
                    assert by_id[create_permit.permit_id].consumption_correlation_id == CORRELATION
                    assert by_id[create_permit.permit_id].operation == LiveExecutionOperation.ORDER_LIFECYCLE_CREATE.value
                    assert by_id[create_permit.permit_id].environment == "TESTNET"
                    assert by_id[create_permit.permit_id].symbol == "BTCUSDT"
                    assert by_id[create_permit.permit_id].request_fingerprint == create_fingerprint_for_permit.request_fingerprint
                    assert by_id[cancel_permit.permit_id].state == LiveExecutionPermitState.ISSUED.value
                    assert by_id[cancel_permit.permit_id].version == 1
                    assert by_id[cancel_permit.permit_id].consumed_at is None
                    assert by_id[cancel_permit.permit_id].consumption_correlation_id is None
                    create_audits = [event for event in audits if event.metadata_json.get("permit_id") == create_permit.permit_id]
                    cancel_audits = [event for event in audits if event.metadata_json.get("permit_id") == cancel_permit.permit_id]
                    assert len(create_audits) == 1
                    assert create_audits[0].result == "PASS"
                    assert create_audits[0].metadata_json["operation"] == LiveExecutionOperation.ORDER_LIFECYCLE_CREATE.value
                    assert create_audits[0].metadata_json["environment"] == "TESTNET"
                    assert create_audits[0].metadata_json["symbol"] == "BTCUSDT"
                    assert create_audits[0].metadata_json["request_fingerprint"] == create_fingerprint_for_permit.request_fingerprint
                    assert create_audits[0].metadata_json["consumption_correlation_id"] == str(CORRELATION)
                    assert cancel_audits == []
                finally:
                    independent_engine.dispose()

                transmitted_before_auth_removal = dict(params)
                auth_only = {"timestamp", "recvWindow", "signature"}
                assert auth_only <= set(transmitted_before_auth_removal)
                assert len(transmitted_before_auth_removal["signature"]) == 64
                actual_unsigned_transmitted = {
                    key: value for key, value in transmitted_before_auth_removal.items() if key not in auth_only
                }
                assert set(actual_unsigned_transmitted) == set(expected_business)
                assert actual_unsigned_transmitted == expected_business
                assert actual_unsigned_transmitted == captured["request"].transport_business_parameters
                assert actual_unsigned_transmitted["newClientOrderId"] == create_fingerprint_for_permit.canonical_payload["client_order_id"]
                assert actual_unsigned_transmitted["price"] == create_fingerprint_for_permit.canonical_payload["price"]
                assert actual_unsigned_transmitted["quantity"] == create_fingerprint_for_permit.canonical_payload["quantity"]
                assert actual_unsigned_transmitted["newOrderRespType"] == config.new_order_response_type
                assert "timestamp" not in actual_unsigned_transmitted
                assert "recvWindow" not in actual_unsigned_transmitted
                assert "signature" not in actual_unsigned_transmitted
                assert "apiKey" not in actual_unsigned_transmitted
                assert "headers" not in actual_unsigned_transmitted
                captured["transmitted"] = transmitted_before_auth_removal
                return BinanceLifecycleHTTPResponse(
                    200,
                    url,
                    {
                        "symbol": "BTCUSDT",
                        "clientOrderId": client_order_id,
                        "orderId": "101",
                        "side": "BUY",
                        "positionSide": "BOTH",
                        "type": "LIMIT",
                        "timeInForce": "GTX",
                        "price": expected_business["price"],
                        "origQty": "0.001",
                        "executedQty": "0",
                        "status": "NEW",
                    },
                    10,
                )
            if method == "GET":
                assert params["symbol"] == "BTCUSDT"
                assert params["origClientOrderId"] == client_order_id
                return BinanceLifecycleHTTPResponse(
                    200,
                    url,
                    {
                        "symbol": "BTCUSDT",
                        "clientOrderId": client_order_id,
                        "orderId": "101",
                        "side": "BUY",
                        "positionSide": "BOTH",
                        "type": "LIMIT",
                        "timeInForce": "GTX",
                        "price": expected_business["price"],
                        "origQty": "0.001",
                        "executedQty": "0",
                        "status": "EXPIRED",
                    },
                    10,
                )
            raise AssertionError("unexpected lifecycle transport")

        client.authenticated_request = transport
        engine = _lifecycle_engine(
            tmp_path,
            env=env,
            http_get=_lifecycle_http_get,
            authenticated_request=transport,
            permit_gate=gate,
            now_ms_provider=lambda: 123,
        )
        engine._client = lambda loaded_config: client
        assert isinstance(engine, BinanceFuturesTestnetOrderLifecycleEngine)
        assert isinstance(engine.permit_gate, LiveExecutionPermitGate)
        assert isinstance(client, BinanceFuturesTestnetOrderLifecycleClient)

        result = engine.run_lifecycle(
            lifecycle_id,
            client_order_id,
            "BUY",
            Decimal("0.001"),
            price_offset_bps=config.default_price_offset_bps,
            confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE",
            config_path=str(config_path),
            create_permit=LiveExecutionPermitReference(create_permit.permit_id, create_permit.version),
            cancel_permit=LiveExecutionPermitReference(cancel_permit.permit_id, cancel_permit.version),
        )

        shared_after = {
            "operation": captured["request"].operation,
            "environment": captured["request"].environment,
            "symbol": captured["request"].symbol,
            "subject_type": captured["request"].subject_type,
            "subject_id": captured["request"].subject_id,
            "fingerprint_context": dict(captured["request"].fingerprint_context),
            "transport_business_parameters": dict(captured["request"].transport_business_parameters),
        }
        assert shared_after == {
            "operation": create_request_for_permit.operation,
            "environment": create_request_for_permit.environment,
            "symbol": create_request_for_permit.symbol,
            "subject_type": create_request_for_permit.subject_type,
            "subject_id": create_request_for_permit.subject_id,
            "fingerprint_context": dict(create_request_for_permit.fingerprint_context),
            "transport_business_parameters": expected_business,
        }
        for auth_field in ("timestamp", "recvWindow", "signature", "headers", "credentials", "apiKey"):
            assert auth_field not in shared_after["fingerprint_context"]
            assert auth_field not in shared_after["transport_business_parameters"]
        assert captured["fingerprint"] is not None
        assert captured["fingerprint"].request_fingerprint == create_fingerprint_for_permit.request_fingerprint
        assert captured["transmitted"] is not None
        post_calls = [call for call in calls if call[0] == "POST"]
        delete_calls = [call for call in calls if call[0] == "DELETE"]
        assert post_calls == [("POST", "https://demo-fapi.binance.com/fapi/v1/order", client_order_id)]
        assert delete_calls == []
        assert result.status == "PASS", (result.decision, result.reason, [issue.to_dict() for issue in result.issues])
        assert result.decision == "LIFECYCLE_COMPLETE"
        assert result.lifecycle_complete is True
        assert result.recovery_required is False
        assert result.created_order is not None and result.created_order.client_order_id == client_order_id
        assert result.queried_order is not None and result.queried_order.status == "EXPIRED"
        assert result.final_order is not None and result.final_order.status == "EXPIRED"
        assert result.cancel_order is None
        assert result.unexpected_fill_detected is False
        assert result.unexpected_position_detected is False
        assert result.create_request is not None and result.create_request.retry_count == 0
        assert result.cancel_request is None
        assert journal_at_post and journal_at_post[0]["phase"] == LifecyclePhase.CREATE_REQUEST_STARTED.value
        assert observer == {"close_count": 1, "close_completed": True}

        stored_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
        try:
            with Session(stored_engine, future=True) as session:
                permits = list(
                    session.scalars(
                        select(LiveExecutionPermitORM).where(
                            LiveExecutionPermitORM.permit_id.in_([create_permit.permit_id, cancel_permit.permit_id])
                        )
                    ).all()
                )
                audits = list(
                    session.scalars(
                        select(AuditEventORM).where(
                            AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                            AuditEventORM.action == "PERMIT_CONSUMED",
                        )
                    ).all()
                )
            by_id = {permit.permit_id: permit for permit in permits}
            assert by_id[create_permit.permit_id].state == LiveExecutionPermitState.CONSUMED.value
            assert by_id[create_permit.permit_id].version == create_permit.version + 1 == 2
            assert by_id[create_permit.permit_id].consumed_at is not None
            assert by_id[create_permit.permit_id].consumption_correlation_id == CORRELATION
            assert by_id[create_permit.permit_id].operation == LiveExecutionOperation.ORDER_LIFECYCLE_CREATE.value
            assert by_id[create_permit.permit_id].environment == "TESTNET"
            assert by_id[create_permit.permit_id].symbol == "BTCUSDT"
            assert by_id[create_permit.permit_id].request_fingerprint == create_fingerprint_for_permit.request_fingerprint
            assert by_id[cancel_permit.permit_id].state == LiveExecutionPermitState.ISSUED.value
            assert by_id[cancel_permit.permit_id].version == 1
            assert by_id[cancel_permit.permit_id].consumed_at is None
            assert by_id[cancel_permit.permit_id].consumption_correlation_id is None
            create_audits = [event for event in audits if event.metadata_json.get("permit_id") == create_permit.permit_id]
            cancel_audits = [event for event in audits if event.metadata_json.get("permit_id") == cancel_permit.permit_id]
            assert len(create_audits) == 1
            assert create_audits[0].result == "PASS"
            assert create_audits[0].metadata_json["operation"] == LiveExecutionOperation.ORDER_LIFECYCLE_CREATE.value
            assert create_audits[0].metadata_json["environment"] == "TESTNET"
            assert create_audits[0].metadata_json["symbol"] == "BTCUSDT"
            assert create_audits[0].metadata_json["request_fingerprint"] == create_fingerprint_for_permit.request_fingerprint
            assert create_audits[0].metadata_json["consumption_correlation_id"] == str(CORRELATION)
            assert cancel_audits == []
        finally:
            stored_engine.dispose()
    finally:
        BinanceFuturesTestnetOrderLifecycleClient.build_create_unsigned_business_request = original_class_create_builder
        BinanceFuturesTestnetOrderLifecycleClient.build_cancel_unsigned_business_request = original_class_cancel_builder
        BinanceFuturesTestnetOrderLifecycleClient.create_order = original_class_create_order
        lifecycle_engine_module.build_lifecycle_create_from_final_request = original_engine_fingerprint_builder
def test_lifecycle_create_permit_is_committed_and_closed_before_post(tmp_path) -> None:
    env = durable_state_env("RELEASED")
    config_path = _write_lifecycle_config(tmp_path)
    config = BinanceFuturesTestnetOrderLifecycleConfig()
    lifecycle_id = "lifecycle-durable-001"
    client_order_id = "smcbot-lifecycle-durable-001"
    client = BinanceFuturesTestnetOrderLifecycleClient(config, env=env)
    filters = client.parse_exchange_filters(_lifecycle_exchange_info())
    ticker = client.parse_book_ticker(
        {
            "symbol": "BTCUSDT",
            "bidPrice": "50000",
            "askPrice": "50001",
            "bidQty": "1",
            "askQty": "1",
        }
    )
    preview = client.build_lifecycle_preview(
        lifecycle_id,
        client_order_id,
        "BUY",
        Decimal("0.001"),
        config.default_price_offset_bps,
        filters,
        ticker,
    )
    create_unsigned_request = client.build_create_unsigned_business_request(preview)
    cancel_unsigned_request = client.build_cancel_unsigned_business_request(client_order_id)
    create_fingerprint = build_lifecycle_create_from_final_request(create_unsigned_request)
    cancel_fingerprint = build_lifecycle_cancel_from_final_request(cancel_unsigned_request)
    create_permit = _issue(env, create_fingerprint)
    cancel_permit = _issue(env, cancel_fingerprint)
    assert create_permit.permit_id != cancel_permit.permit_id
    assert create_permit.version == cancel_permit.version == 1

    observer = {"close_count": 0, "close_completed": False}
    gate = LiveExecutionPermitGate(
        env=env,
        correlation_id_provider=lambda: CORRELATION,
        permit_persistence_factory=lambda **kwargs: _ClosingPermitPersistence(observer, **kwargs),
    )
    calls: list[tuple[str, str, str | None]] = []
    journal_at_post: list[dict[str, object]] = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        identity = (params.get("newClientOrderId") or params.get("origClientOrderId") or [None])[0]
        calls.append((method, url, identity))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(
                200,
                url,
                [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": "0"}],
                10,
            )
        assert url == "https://demo-fapi.binance.com/fapi/v1/order"
        if method == "DELETE":
            raise AssertionError("terminal-safe lifecycle order must not be cancelled")
        if method == "POST":
            assert params["symbol"] == ["BTCUSDT"]
            assert params["newClientOrderId"] == [client_order_id]
            assert params["side"] == ["BUY"]
            assert params["positionSide"] == ["BOTH"]
            assert params["type"] == ["LIMIT"]
            assert params["quantity"] == ["0.001"]
            assert params["price"] == [format(preview.derived_price.normalize(), "f")]
            assert params["timeInForce"] == ["GTX"]
            assert "reduceOnly" not in params
            assert create_fingerprint.canonical_payload["reduce_only"] is False
            assert params["newOrderRespType"] == ["ACK"]

            _assert_consumed_at_transport(
                env,
                create_permit,
                create_fingerprint,
                observer,
                LiveExecutionOperation.ORDER_LIFECYCLE_CREATE,
            )
            journal_path = (
                tmp_path
                / "data"
                / "runtime"
                / "binance_futures_testnet_order_lifecycle"
                / "lifecycle.json"
            )
            persisted_journal = json.loads(journal_path.read_text(encoding="utf-8"))
            assert persisted_journal["phase"] == LifecyclePhase.CREATE_REQUEST_STARTED.value
            assert persisted_journal["entries"][-1]["phase"] == LifecyclePhase.CREATE_REQUEST_STARTED.value
            assert persisted_journal["entries"][-1]["details"]["client_order_id"] == client_order_id
            journal_at_post.append(persisted_journal)

            independent_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
            try:
                with Session(independent_engine, future=True) as session:
                    untouched = session.scalar(
                        select(LiveExecutionPermitORM).where(
                            LiveExecutionPermitORM.permit_id == cancel_permit.permit_id
                        )
                    )
                    cancel_audits = list(
                        session.scalars(
                            select(AuditEventORM).where(
                                AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                                AuditEventORM.action == "PERMIT_CONSUMED",
                            )
                        ).all()
                    )
                assert untouched is not None
                assert untouched.state == LiveExecutionPermitState.ISSUED.value
                assert untouched.version == cancel_permit.version
                assert untouched.consumed_at is None
                assert untouched.consumption_correlation_id is None
                assert untouched.operation == LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL.value
                assert untouched.request_fingerprint == cancel_fingerprint.request_fingerprint
                assert not [
                    event
                    for event in cancel_audits
                    if event.metadata_json.get("permit_id") == cancel_permit.permit_id
                ]
            finally:
                independent_engine.dispose()

            return BinanceLifecycleHTTPResponse(
                200,
                url,
                {
                    "symbol": "BTCUSDT",
                    "clientOrderId": client_order_id,
                    "orderId": "101",
                    "side": "BUY",
                    "positionSide": "BOTH",
                    "type": "LIMIT",
                    "timeInForce": "GTX",
                    "price": format(preview.derived_price.normalize(), "f"),
                    "origQty": "0.001",
                    "executedQty": "0",
                    "status": "NEW",
                },
                10,
            )
        if method == "GET":
            assert params["symbol"] == ["BTCUSDT"]
            assert params["origClientOrderId"] == [client_order_id]
            return BinanceLifecycleHTTPResponse(
                200,
                url,
                {
                    "symbol": "BTCUSDT",
                    "clientOrderId": client_order_id,
                    "orderId": "101",
                    "side": "BUY",
                    "positionSide": "BOTH",
                    "type": "LIMIT",
                    "timeInForce": "GTX",
                    "price": format(preview.derived_price.normalize(), "f"),
                    "origQty": "0.001",
                    "executedQty": "0",
                    "status": "EXPIRED",
                },
                10,
            )
        raise AssertionError("unexpected lifecycle transport")

    engine = _lifecycle_engine(
        tmp_path,
        env=env,
        http_get=_lifecycle_http_get,
        authenticated_request=transport,
        permit_gate=gate,
        now_ms_provider=lambda: 123,
    )
    assert isinstance(engine, BinanceFuturesTestnetOrderLifecycleEngine)
    assert isinstance(engine.permit_gate, LiveExecutionPermitGate)
    result = engine.run_lifecycle(
        lifecycle_id,
        client_order_id,
        "BUY",
        Decimal("0.001"),
        price_offset_bps=config.default_price_offset_bps,
        confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE",
        config_path=str(config_path),
        create_permit=LiveExecutionPermitReference(create_permit.permit_id, create_permit.version),
        cancel_permit=LiveExecutionPermitReference(cancel_permit.permit_id, cancel_permit.version),
    )

    post_calls = [call for call in calls if call[0] == "POST"]
    delete_calls = [call for call in calls if call[0] == "DELETE"]
    assert result.status == "PASS", (result.decision, result.reason, [issue.to_dict() for issue in result.issues])
    assert result.decision == "LIFECYCLE_COMPLETE"
    assert result.lifecycle_complete is True
    assert result.created_order is not None and result.created_order.client_order_id == client_order_id
    assert result.queried_order is not None and result.queried_order.status == "EXPIRED"
    assert result.final_order is not None and result.final_order.status == "EXPIRED"
    assert result.cancel_order is None
    assert result.unexpected_fill_detected is False
    assert len(post_calls) == 1
    assert post_calls[0] == ("POST", "https://demo-fapi.binance.com/fapi/v1/order", client_order_id)
    assert delete_calls == []
    assert result.create_request is not None and result.create_request.retry_count == 0
    assert result.cancel_request is None
    assert journal_at_post and journal_at_post[0]["phase"] == LifecyclePhase.CREATE_REQUEST_STARTED.value
    assert observer == {"close_count": 1, "close_completed": True}

    stored_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(stored_engine, future=True) as session:
            permits = list(
                session.scalars(
                    select(LiveExecutionPermitORM).where(
                        LiveExecutionPermitORM.permit_id.in_([create_permit.permit_id, cancel_permit.permit_id])
                    )
                ).all()
            )
            audits = list(
                session.scalars(
                    select(AuditEventORM).where(
                        AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                        AuditEventORM.action == "PERMIT_CONSUMED",
                    )
                ).all()
            )
        by_id = {permit.permit_id: permit for permit in permits}
        stored_create = by_id[create_permit.permit_id]
        stored_cancel = by_id[cancel_permit.permit_id]
        assert len(permits) == 2
        assert stored_create.state == LiveExecutionPermitState.CONSUMED.value
        assert stored_create.version == create_permit.version + 1 == 2
        assert stored_create.consumption_correlation_id is not None
        assert stored_create.operation == LiveExecutionOperation.ORDER_LIFECYCLE_CREATE.value
        assert stored_create.request_fingerprint == create_fingerprint.request_fingerprint
        assert stored_cancel.state == LiveExecutionPermitState.ISSUED.value
        assert stored_cancel.version == cancel_permit.version == 1
        assert stored_cancel.consumption_correlation_id is None
        assert stored_cancel.operation == LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL.value
        assert stored_cancel.request_fingerprint == cancel_fingerprint.request_fingerprint
        assert len([event for event in audits if event.metadata_json.get("permit_id") == create_permit.permit_id]) == 1
        assert not [event for event in audits if event.metadata_json.get("permit_id") == cancel_permit.permit_id]
    finally:
        stored_engine.dispose()


def test_lifecycle_cancel_permit_is_committed_and_closed_before_delete(tmp_path) -> None:
    env = durable_state_env("RELEASED")
    config_path = _write_lifecycle_config(tmp_path)
    config = BinanceFuturesTestnetOrderLifecycleConfig()
    lifecycle_id = "lifecycle-durable-cancel-001"
    client_order_id = "smcbot-lifecycle-cancel-001"
    client = BinanceFuturesTestnetOrderLifecycleClient(config, env=env)
    filters = client.parse_exchange_filters(_lifecycle_exchange_info())
    ticker = client.parse_book_ticker(
        {
            "symbol": "BTCUSDT",
            "bidPrice": "50000",
            "askPrice": "50001",
            "bidQty": "1",
            "askQty": "1",
        }
    )
    preview = client.build_lifecycle_preview(
        lifecycle_id,
        client_order_id,
        "BUY",
        Decimal("0.001"),
        config.default_price_offset_bps,
        filters,
        ticker,
    )
    create_fingerprint = build_lifecycle_create_from_final_request(
        client.build_create_unsigned_business_request(preview)
    )
    cancel_fingerprint = build_lifecycle_cancel_from_final_request(
        client.build_cancel_unsigned_business_request(client_order_id)
    )
    create_permit = _issue(env, create_fingerprint)
    cancel_permit = _issue(env, cancel_fingerprint)
    assert create_permit.permit_id != cancel_permit.permit_id
    assert create_permit.version == cancel_permit.version == 1

    observers: list[dict[str, object]] = []

    def persistence_factory(**kwargs):
        observer = {"close_count": 0, "close_completed": False}
        observers.append(observer)
        return _ClosingPermitPersistence(observer, **kwargs)

    correlations = iter(
        [
            UUID("11111111-1111-4111-8111-111111111121"),
            UUID("11111111-1111-4111-8111-111111111122"),
        ]
    )
    gate = LiveExecutionPermitGate(
        env=env,
        correlation_id_provider=lambda: next(correlations),
        permit_persistence_factory=persistence_factory,
    )
    calls: list[tuple[str, str, str | None]] = []
    order_query_count = 0
    journal_at_delete: list[dict[str, object]] = []

    def order_payload(status: str) -> dict[str, object]:
        return {
            "symbol": "BTCUSDT",
            "clientOrderId": client_order_id,
            "orderId": "202",
            "side": "BUY",
            "positionSide": "BOTH",
            "type": "LIMIT",
            "timeInForce": "GTX",
            "price": format(preview.derived_price.normalize(), "f"),
            "origQty": "0.001",
            "executedQty": "0",
            "status": status,
        }

    def transport(method, url, body, timeout, headers):
        nonlocal order_query_count
        params = parse_qs(body.decode("utf-8"))
        identity = (params.get("newClientOrderId") or params.get("origClientOrderId") or [None])[0]
        calls.append((method, url, identity))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(
                200,
                url,
                [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": "0"}],
                10,
            )
        assert url == "https://demo-fapi.binance.com/fapi/v1/order"
        if method == "POST":
            assert params["symbol"] == ["BTCUSDT"]
            assert params["newClientOrderId"] == [client_order_id]
            assert len(observers) == 1
            _assert_consumed_at_transport(
                env,
                create_permit,
                create_fingerprint,
                observers[0],
                LiveExecutionOperation.ORDER_LIFECYCLE_CREATE,
            )
            return BinanceLifecycleHTTPResponse(200, url, order_payload("NEW"), 10)
        if method == "GET":
            assert params["symbol"] == ["BTCUSDT"]
            assert params["origClientOrderId"] == [client_order_id]
            order_query_count += 1
            return BinanceLifecycleHTTPResponse(
                200,
                url,
                order_payload("NEW" if order_query_count == 1 else "CANCELED"),
                10,
            )
        if method == "DELETE":
            assert params["symbol"] == ["BTCUSDT"]
            assert params["origClientOrderId"] == [client_order_id]
            assert "orderId" not in params
            assert len([call for call in calls if call[0] == "POST"]) == 1
            assert len([call for call in calls if call[0] == "DELETE"]) == 1
            assert len(observers) == 2
            assert observers[0] == {"close_count": 1, "close_completed": True}
            assert observers[1] == {"close_count": 1, "close_completed": True}

            journal_path = (
                tmp_path
                / "data"
                / "runtime"
                / "binance_futures_testnet_order_lifecycle"
                / "lifecycle.json"
            )
            persisted_journal = json.loads(journal_path.read_text(encoding="utf-8"))
            phases = [entry["phase"] for entry in persisted_journal["entries"]]
            assert persisted_journal["phase"] == LifecyclePhase.CANCEL_REQUEST_STARTED.value
            assert phases.count(LifecyclePhase.CREATE_REQUEST_STARTED.value) == 1
            assert phases.count(LifecyclePhase.CANCEL_REQUEST_STARTED.value) == 1
            assert phases.index(LifecyclePhase.CREATE_REQUEST_STARTED.value) < phases.index(
                LifecyclePhase.CANCEL_REQUEST_STARTED.value
            )
            journal_at_delete.append(persisted_journal)

            independent_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
            try:
                with Session(independent_engine, future=True) as session:
                    permits = list(
                        session.scalars(
                            select(LiveExecutionPermitORM).where(
                                LiveExecutionPermitORM.permit_id.in_(
                                    [create_permit.permit_id, cancel_permit.permit_id]
                                )
                            )
                        ).all()
                    )
                    audits = list(
                        session.scalars(
                            select(AuditEventORM).where(
                                AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                                AuditEventORM.action == "PERMIT_CONSUMED",
                            )
                        ).all()
                    )
                by_id = {permit.permit_id: permit for permit in permits}
                stored_create = by_id[create_permit.permit_id]
                stored_cancel = by_id[cancel_permit.permit_id]
                assert stored_create.state == LiveExecutionPermitState.CONSUMED.value
                assert stored_create.version == create_permit.version + 1 == 2
                assert stored_create.consumption_correlation_id is not None
                assert stored_cancel.state == LiveExecutionPermitState.CONSUMED.value
                assert stored_cancel.version == cancel_permit.version + 1 == 2
                assert stored_cancel.consumed_at is not None
                assert stored_cancel.consumption_correlation_id is not None
                assert stored_cancel.consumption_correlation_id != stored_create.consumption_correlation_id
                assert stored_cancel.operation == LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL.value
                assert stored_cancel.environment == "TESTNET"
                assert stored_cancel.symbol == "BTCUSDT"
                assert stored_cancel.request_fingerprint == cancel_fingerprint.request_fingerprint
                create_audits = [
                    event for event in audits if event.metadata_json.get("permit_id") == create_permit.permit_id
                ]
                cancel_audits = [
                    event for event in audits if event.metadata_json.get("permit_id") == cancel_permit.permit_id
                ]
                assert len(create_audits) == 1
                assert len(cancel_audits) == 1
                assert create_audits[0].id != cancel_audits[0].id
                assert cancel_audits[0].result == "PASS"
                cancel_metadata = cancel_audits[0].metadata_json
                assert cancel_metadata["operation"] == LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL.value
                assert cancel_metadata["environment"] == "TESTNET"
                assert cancel_metadata["symbol"] == "BTCUSDT"
                assert cancel_metadata["request_fingerprint"] == cancel_fingerprint.request_fingerprint
                assert cancel_metadata["consumption_correlation_id"] == str(
                    stored_cancel.consumption_correlation_id
                )
            finally:
                independent_engine.dispose()

            return BinanceLifecycleHTTPResponse(200, url, order_payload("CANCELED"), 10)
        raise AssertionError("unexpected lifecycle transport")

    engine = _lifecycle_engine(
        tmp_path,
        env=env,
        http_get=_lifecycle_http_get,
        authenticated_request=transport,
        permit_gate=gate,
        now_ms_provider=lambda: 123,
    )
    assert isinstance(engine, BinanceFuturesTestnetOrderLifecycleEngine)
    assert isinstance(engine.permit_gate, LiveExecutionPermitGate)
    result = engine.run_lifecycle(
        lifecycle_id,
        client_order_id,
        "BUY",
        Decimal("0.001"),
        price_offset_bps=config.default_price_offset_bps,
        confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE",
        config_path=str(config_path),
        create_permit=LiveExecutionPermitReference(create_permit.permit_id, create_permit.version),
        cancel_permit=LiveExecutionPermitReference(cancel_permit.permit_id, cancel_permit.version),
    )

    post_calls = [call for call in calls if call[0] == "POST"]
    delete_calls = [call for call in calls if call[0] == "DELETE"]
    position_calls = [call for call in calls if "positionRisk" in call[1]]
    assert result.status == "PASS", (result.decision, result.reason, [issue.to_dict() for issue in result.issues])
    assert result.decision == "LIFECYCLE_COMPLETE"
    assert result.lifecycle_complete is True
    assert result.recovery_required is False
    assert result.unexpected_fill_detected is False
    assert result.created_order is not None and result.created_order.status == "NEW"
    assert result.queried_order is not None and result.queried_order.status == "NEW"
    assert result.cancel_order is not None and result.cancel_order.status == "CANCELED"
    assert result.final_order is not None and result.final_order.status == "CANCELED"
    assert post_calls == [("POST", "https://demo-fapi.binance.com/fapi/v1/order", client_order_id)]
    assert delete_calls == [("DELETE", "https://demo-fapi.binance.com/fapi/v1/order", client_order_id)]
    assert len(position_calls) == 2
    assert result.create_request is not None and result.create_request.retry_count == 0
    assert result.cancel_request is not None and result.cancel_request.retry_count == 0
    assert len(observers) == 2
    assert observers[0] == {"close_count": 1, "close_completed": True}
    assert observers[1] == {"close_count": 1, "close_completed": True}
    assert journal_at_delete and journal_at_delete[0]["phase"] == LifecyclePhase.CANCEL_REQUEST_STARTED.value

    stored_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(stored_engine, future=True) as session:
            permits = list(
                session.scalars(
                    select(LiveExecutionPermitORM).where(
                        LiveExecutionPermitORM.permit_id.in_([create_permit.permit_id, cancel_permit.permit_id])
                    )
                ).all()
            )
            audits = list(
                session.scalars(
                    select(AuditEventORM).where(
                        AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                        AuditEventORM.action == "PERMIT_CONSUMED",
                    )
                ).all()
            )
        by_id = {permit.permit_id: permit for permit in permits}
        assert len(permits) == 2
        assert by_id[create_permit.permit_id].state == LiveExecutionPermitState.CONSUMED.value
        assert by_id[create_permit.permit_id].version == 2
        assert by_id[cancel_permit.permit_id].state == LiveExecutionPermitState.CONSUMED.value
        assert by_id[cancel_permit.permit_id].version == 2
        assert by_id[cancel_permit.permit_id].consumption_correlation_id is not None
        assert len([event for event in audits if event.metadata_json.get("permit_id") == create_permit.permit_id]) == 1
        assert len([event for event in audits if event.metadata_json.get("permit_id") == cancel_permit.permit_id]) == 1
    finally:
        stored_engine.dispose()


def test_order_test_permit_is_committed_and_closed_before_post(tmp_path) -> None:
    env = durable_state_env("RELEASED")
    config_path = _write_order_test_config(tmp_path)
    config = BinanceFuturesTestnetOrderTestConfig()
    client_order_id = "smcbot-test-durable-001"
    observer = {"close_count": 0, "close_completed": False}
    calls: list[tuple[str, str, str]] = []
    signing_events: list[str] = []
    unsigned_request = None
    issued = None
    fingerprint = None

    def authenticated_post(url, body, timeout, headers):
        body_text = body.decode("utf-8")
        params = parse_qs(body_text)
        calls.append(("POST", url, params["newClientOrderId"][0]))
        assert url == "https://demo-fapi.binance.com/fapi/v1/order/test"
        assert params["symbol"] == ["BTCUSDT"]
        assert params["newClientOrderId"] == [client_order_id]
        assert params["side"] == ["BUY"]
        assert params["positionSide"] == ["BOTH"]
        assert params["type"] == ["LIMIT"]
        assert params["quantity"] == ["0.001"]
        assert params["price"] == ["50000"]
        assert params["timeInForce"] == ["GTC"]
        assert "reduceOnly" not in params
        assert fingerprint.canonical_payload["reduce_only"] is False
        assert params["timestamp"] == ["123"]
        assert params["recvWindow"] == [str(config.recv_window_ms)]
        assert len(params["signature"]) == 1
        assert len(params["signature"][0]) == 64
        assert signing_events == ["signed_after_permit_close"]
        assert observer == {"close_count": 1, "close_completed": True}
        assert env[config.api_key_env_var] not in body_text
        assert env[config.api_secret_env_var] not in body_text
        assert unsigned_request is not None
        assert issued is not None
        assert fingerprint is not None
        _assert_consumed_at_transport(
            env,
            issued,
            fingerprint,
            observer,
            LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE,
        )
        return BinanceOrderTestHTTPResponse(200, url, {}, 2)

    client = BinanceFuturesTestnetOrderTestClient(
        config,
        http_get=_order_test_http_get,
        authenticated_post=authenticated_post,
        env=env,
        now_ms_provider=lambda: 123,
    )
    filters = client.parse_exchange_filters(_order_test_http_get("https://demo-fapi.binance.com/fapi/v1/exchangeInfo", 30).payload)
    preview = client.build_order_test_preview(
        client_order_id,
        "BUY",
        "LIMIT",
        Decimal("0.001"),
        Decimal("50000"),
        "GTC",
        False,
        exchange_filters=filters,
    )
    unsigned_request = client.build_unsigned_business_request(preview)
    unsigned_before = {
        "operation": unsigned_request.operation,
        "environment": unsigned_request.environment,
        "symbol": unsigned_request.symbol,
        "subject_type": unsigned_request.subject_type,
        "subject_id": unsigned_request.subject_id,
        "fingerprint_context": dict(unsigned_request.fingerprint_context),
        "transport_business_parameters": dict(unsigned_request.transport_business_parameters),
    }
    for auth_field in ("timestamp", "recvWindow", "signature"):
        assert auth_field not in unsigned_before["fingerprint_context"]
        assert auth_field not in unsigned_before["transport_business_parameters"]
    assert unsigned_before["transport_business_parameters"]["quantity"] == "0.001"
    assert unsigned_before["transport_business_parameters"]["price"] == "50000"
    assert unsigned_before["transport_business_parameters"]["positionSide"] == "BOTH"
    assert unsigned_before["transport_business_parameters"]["timeInForce"] == "GTC"
    assert "reduceOnly" not in unsigned_before["transport_business_parameters"]
    assert unsigned_before["fingerprint_context"]["reduce_only"] is False

    fingerprint = build_signed_order_test_create_from_final_request(unsigned_request)
    issued = _issue(env, fingerprint)
    gate = LiveExecutionPermitGate(
        env=env,
        correlation_id_provider=lambda: CORRELATION,
        permit_persistence_factory=lambda **kwargs: _ClosingPermitPersistence(observer, **kwargs),
    )
    real_signature = client._signature

    def observed_signature(canonical_query: str) -> str:
        assert observer == {"close_count": 1, "close_completed": True}
        assert signing_events == []
        signing_events.append("signed_after_permit_close")
        return real_signature(canonical_query)

    client._signature = observed_signature
    real_unsigned_builder = client.build_unsigned_business_request

    def captured_unsigned_builder(actual_preview):
        rebuilt = real_unsigned_builder(actual_preview)
        assert dict(rebuilt.fingerprint_context) == dict(unsigned_request.fingerprint_context)
        assert dict(rebuilt.transport_business_parameters) == dict(unsigned_request.transport_business_parameters)
        return unsigned_request

    client.build_unsigned_business_request = captured_unsigned_builder
    engine = _order_test_engine(
        tmp_path,
        env=env,
        http_get=_order_test_http_get,
        authenticated_post=authenticated_post,
        permit_gate=gate,
        now_ms_provider=lambda: 123,
    )
    engine._client = lambda loaded_config: client
    assert isinstance(engine, BinanceFuturesTestnetOrderTestEngine)
    assert isinstance(engine.permit_gate, LiveExecutionPermitGate)

    result = engine.submit_test_order(
        client_order_id,
        "BUY",
        "LIMIT",
        Decimal("0.001"),
        price=Decimal("50000"),
        time_in_force="GTC",
        reduce_only=False,
        confirmation="CONFIRM_TESTNET_ORDER_TEST",
        config_path=str(config_path),
        permit=LiveExecutionPermitReference(issued.permit_id, issued.version),
    )

    unsigned_after = {
        "operation": unsigned_request.operation,
        "environment": unsigned_request.environment,
        "symbol": unsigned_request.symbol,
        "subject_type": unsigned_request.subject_type,
        "subject_id": unsigned_request.subject_id,
        "fingerprint_context": dict(unsigned_request.fingerprint_context),
        "transport_business_parameters": dict(unsigned_request.transport_business_parameters),
    }
    assert unsigned_after == unsigned_before
    for auth_field in ("timestamp", "recvWindow", "signature"):
        assert auth_field not in unsigned_after["fingerprint_context"]
        assert auth_field not in unsigned_after["transport_business_parameters"]
    assert result.status == "PASS", (result.decision, result.reason, [issue.to_dict() for issue in result.issues])
    assert result.decision == "ORDER_TEST_ACCEPTED"
    assert result.test_order_request_transmitted is True
    assert result.authenticated_transport_invoked is True
    assert result.signature_generated is True
    assert result.request_metadata is not None
    assert result.request_metadata.retry_count == 0
    assert result.request_metadata.request_transmitted is True
    assert result.request_metadata.signature_generated is True
    assert calls == [("POST", "https://demo-fapi.binance.com/fapi/v1/order/test", client_order_id)]
    assert signing_events == ["signed_after_permit_close"]
    assert observer == {"close_count": 1, "close_completed": True}

    stored_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(stored_engine, future=True) as session:
            stored = session.scalar(
                select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == issued.permit_id)
            )
            audits = list(
                session.scalars(
                    select(AuditEventORM).where(
                        AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                        AuditEventORM.action == "PERMIT_CONSUMED",
                    )
                ).all()
            )
        assert stored is not None
        assert stored.state == LiveExecutionPermitState.CONSUMED.value
        assert stored.version == issued.version + 1 == 2
        assert stored.consumed_at is not None
        assert stored.consumption_correlation_id is not None
        assert stored.operation == LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value
        assert stored.environment == "TESTNET"
        assert stored.symbol == "BTCUSDT"
        assert stored.request_fingerprint == fingerprint.request_fingerprint
        matching = [event for event in audits if event.metadata_json.get("permit_id") == issued.permit_id]
        assert len(matching) == 1
    finally:
        stored_engine.dispose()











def test_lifecycle_cancel_fingerprint_equals_transmitted_business_request(tmp_path) -> None:
    import engine.diagnostics.binance_futures_testnet_order_lifecycle_engine as lifecycle_engine_module

    env = durable_state_env("RELEASED")
    config_path = _write_lifecycle_config(tmp_path)
    config = BinanceFuturesTestnetOrderLifecycleConfig()
    lifecycle_id = "lifecycle-fingerprint-cancel-001"
    client_order_id = "smcbot-lifecycle-fp-cancel-001"
    client = BinanceFuturesTestnetOrderLifecycleClient(
        config,
        http_get=_lifecycle_http_get,
        env=env,
        now_ms_provider=lambda: 123,
    )
    filters = client.parse_exchange_filters(_lifecycle_exchange_info())
    ticker = client.parse_book_ticker(
        {
            "symbol": "BTCUSDT",
            "bidPrice": "50000",
            "askPrice": "50001",
            "bidQty": "1",
            "askQty": "1",
        }
    )
    preview = client.build_lifecycle_preview(
        lifecycle_id,
        client_order_id,
        "BUY",
        Decimal("0.001"),
        config.default_price_offset_bps,
        filters,
        ticker,
    )
    create_request_for_permit = client.build_create_unsigned_business_request(preview)
    cancel_request_for_permit = client.build_cancel_unsigned_business_request(client_order_id)
    create_fingerprint_for_permit = build_lifecycle_create_from_final_request(create_request_for_permit)
    cancel_fingerprint_for_permit = build_lifecycle_cancel_from_final_request(cancel_request_for_permit)
    create_permit = _issue(env, create_fingerprint_for_permit)
    cancel_permit = _issue(env, cancel_fingerprint_for_permit)
    assert create_permit.permit_id != cancel_permit.permit_id
    assert create_permit.version == cancel_permit.version == 1

    expected_cancel_business = dict(cancel_request_for_permit.transport_business_parameters)
    cancel_field_classification = {
        "client_order_id": "FINGERPRINT_AND_TRANSPORT",
        "symbol": "FINGERPRINT_AND_TRANSPORT",
        "origClientOrderId": "FINGERPRINT_AND_TRANSPORT",
        "timestamp": "AUTH_TRANSPORT",
        "recvWindow": "AUTH_TRANSPORT",
        "signature": "AUTH_TRANSPORT",
    }
    assert set(cancel_field_classification) == {
        "client_order_id",
        "symbol",
        "origClientOrderId",
        "timestamp",
        "recvWindow",
        "signature",
    }
    assert cancel_request_for_permit.operation == LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL
    assert cancel_request_for_permit.environment == "TESTNET"
    assert cancel_request_for_permit.symbol == "BTCUSDT"
    assert cancel_request_for_permit.subject_type == "ORDER_LIFECYCLE"
    assert cancel_request_for_permit.subject_id == client_order_id
    assert set(expected_cancel_business) == {"symbol", "origClientOrderId"}
    assert expected_cancel_business["symbol"] == "BTCUSDT"
    assert expected_cancel_business["origClientOrderId"] == client_order_id
    assert cancel_request_for_permit.fingerprint_context == {
        "schema_version": "1.0",
        "operation": "ORDER_LIFECYCLE_CANCEL",
        "environment": "TESTNET",
        "symbol": "BTCUSDT",
        "client_order_id": client_order_id,
    }
    assert cancel_fingerprint_for_permit.operation == LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL.value
    assert cancel_fingerprint_for_permit.environment == "TESTNET"
    assert cancel_fingerprint_for_permit.symbol == "BTCUSDT"
    assert cancel_fingerprint_for_permit.subject_type == "CLIENT_ORDER"
    assert cancel_fingerprint_for_permit.subject_id == client_order_id
    assert cancel_fingerprint_for_permit.canonical_payload["client_order_id"] == client_order_id
    assert cancel_fingerprint_for_permit.canonical_payload["schema_version"] == "1.0"
    assert "timestamp" not in cancel_fingerprint_for_permit.canonical_payload
    assert "recvWindow" not in cancel_fingerprint_for_permit.canonical_payload
    assert "signature" not in cancel_fingerprint_for_permit.canonical_payload
    assert len(cancel_fingerprint_for_permit.request_fingerprint) == 64
    assert cancel_fingerprint_for_permit.request_fingerprint == cancel_fingerprint_for_permit.request_fingerprint.lower()
    assert set(cancel_fingerprint_for_permit.request_fingerprint) <= set("0123456789abcdef")

    changed_client_id = "smcbot-lifecycle-fp-cancel-002"
    changed_client_request = LiveExecutionUnsignedMutationRequest(
        operation=cancel_request_for_permit.operation,
        environment=cancel_request_for_permit.environment,
        symbol=cancel_request_for_permit.symbol,
        subject_type=cancel_request_for_permit.subject_type,
        subject_id=changed_client_id,
        fingerprint_context={
            **dict(cancel_request_for_permit.fingerprint_context),
            "client_order_id": changed_client_id,
        },
        transport_business_parameters={
            **dict(cancel_request_for_permit.transport_business_parameters),
            "origClientOrderId": changed_client_id,
        },
    )
    changed_client_fingerprint = build_lifecycle_cancel_from_final_request(changed_client_request)
    assert changed_client_fingerprint.canonical_payload != cancel_fingerprint_for_permit.canonical_payload
    assert changed_client_fingerprint.request_fingerprint != cancel_fingerprint_for_permit.request_fingerprint
    assert cancel_permit.request_fingerprint != changed_client_fingerprint.request_fingerprint

    observers: list[dict[str, object]] = []

    def persistence_factory(**kwargs):
        observer = {"close_count": 0, "close_completed": False}
        observers.append(observer)
        return _ClosingPermitPersistence(observer, **kwargs)

    correlations = iter(
        [
            UUID("11111111-1111-4111-8111-111111111131"),
            UUID("11111111-1111-4111-8111-111111111132"),
        ]
    )
    gate = LiveExecutionPermitGate(
        env=env,
        correlation_id_provider=lambda: next(correlations),
        permit_persistence_factory=persistence_factory,
    )
    captured = {"request": None, "fingerprint": None, "transmitted": None}
    cancel_request_snapshot: dict[str, object] = {}
    calls: list[tuple[str, str, str | None]] = []
    query_payloads: list[dict[str, object]] = []
    journal_before_cancel_consume: list[str] = []
    journal_at_delete: list[dict[str, object]] = []
    order_query_count = 0
    journal_path = tmp_path / "data" / "runtime" / "binance_futures_testnet_order_lifecycle" / "lifecycle.json"
    lock_path = tmp_path / "data" / "runtime" / "binance_futures_testnet_order_lifecycle" / "lifecycle.lock"
    original_class_cancel_builder = BinanceFuturesTestnetOrderLifecycleClient.build_cancel_unsigned_business_request
    original_class_cancel_order = BinanceFuturesTestnetOrderLifecycleClient.cancel_order_exact
    original_engine_cancel_fingerprint_builder = lifecycle_engine_module.build_lifecycle_cancel_from_final_request

    def order_payload(status: str) -> dict[str, object]:
        return {
            "symbol": "BTCUSDT",
            "clientOrderId": client_order_id,
            "orderId": "303",
            "side": "BUY",
            "positionSide": "BOTH",
            "type": "LIMIT",
            "timeInForce": "GTX",
            "price": format(preview.derived_price.normalize(), "f"),
            "origQty": "0.001",
            "executedQty": "0",
            "status": status,
        }

    try:
        def captured_cancel_builder(actual_client, actual_client_order_id):
            assert actual_client_order_id == client_order_id
            rebuilt = original_class_cancel_builder(actual_client, actual_client_order_id)
            assert rebuilt.operation == cancel_request_for_permit.operation
            assert rebuilt.environment == cancel_request_for_permit.environment
            assert rebuilt.symbol == cancel_request_for_permit.symbol
            assert rebuilt.subject_type == cancel_request_for_permit.subject_type
            assert rebuilt.subject_id == cancel_request_for_permit.subject_id
            assert dict(rebuilt.fingerprint_context) == dict(cancel_request_for_permit.fingerprint_context)
            assert dict(rebuilt.transport_business_parameters) == expected_cancel_business
            captured["request"] = rebuilt
            return rebuilt

        def captured_cancel_fingerprint_builder(unsigned_request):
            assert unsigned_request is captured["request"]
            assert journal_path.exists()
            persisted_journal = json.loads(journal_path.read_text(encoding="utf-8"))
            phases = [entry["phase"] for entry in persisted_journal["entries"]]
            assert persisted_journal["phase"] == LifecyclePhase.CANCEL_REQUEST_STARTED.value
            assert phases.count(LifecyclePhase.CREATE_REQUEST_STARTED.value) == 1
            assert phases.count(LifecyclePhase.CANCEL_REQUEST_STARTED.value) == 1
            assert phases.index(LifecyclePhase.CREATE_REQUEST_STARTED.value) < phases.index(
                LifecyclePhase.CANCEL_REQUEST_STARTED.value
            )
            journal_before_cancel_consume.append(journal_path.read_text(encoding="utf-8"))
            fingerprint = original_engine_cancel_fingerprint_builder(unsigned_request)
            assert fingerprint.request_fingerprint == cancel_fingerprint_for_permit.request_fingerprint
            captured["fingerprint"] = fingerprint
            cancel_request_snapshot.update(
                {
                    "operation": unsigned_request.operation,
                    "environment": unsigned_request.environment,
                    "symbol": unsigned_request.symbol,
                    "subject_type": unsigned_request.subject_type,
                    "subject_id": unsigned_request.subject_id,
                    "fingerprint_context": dict(unsigned_request.fingerprint_context),
                    "transport_business_parameters": dict(unsigned_request.transport_business_parameters),
                }
            )
            return fingerprint

        def captured_cancel_order(actual_client, actual_client_order_id, server_time=None, unsigned_business_request=None):
            assert actual_client_order_id == client_order_id
            assert unsigned_business_request is captured["request"]
            assert dict(unsigned_business_request.transport_business_parameters) == expected_cancel_business
            return original_class_cancel_order(
                actual_client,
                actual_client_order_id,
                server_time=server_time,
                unsigned_business_request=unsigned_business_request,
            )

        BinanceFuturesTestnetOrderLifecycleClient.build_cancel_unsigned_business_request = captured_cancel_builder
        BinanceFuturesTestnetOrderLifecycleClient.cancel_order_exact = captured_cancel_order
        lifecycle_engine_module.build_lifecycle_cancel_from_final_request = captured_cancel_fingerprint_builder

        def transport(method, url, body, timeout, headers):
            nonlocal order_query_count
            body_text = body.decode("utf-8")
            params = {key: values[0] for key, values in parse_qs(body_text).items()}
            identity = params.get("newClientOrderId") or params.get("origClientOrderId")
            calls.append((method, url, identity))
            if "positionSide/dual" in url:
                return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
            if "positionRisk" in url:
                return BinanceLifecycleHTTPResponse(
                    200,
                    url,
                    [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": "0"}],
                    10,
                )
            assert url == "https://demo-fapi.binance.com/fapi/v1/order"
            if method == "POST":
                assert identity == client_order_id
                assert params["symbol"] == "BTCUSDT"
                assert params["newClientOrderId"] == client_order_id
                assert params["side"] == "BUY"
                assert params["positionSide"] == "BOTH"
                assert params["type"] == "LIMIT"
                assert params["quantity"] == "0.001"
                assert params["price"] == format(preview.derived_price.normalize(), "f")
                assert params["timeInForce"] == "GTX"
                assert "reduceOnly" not in params
                assert params["newOrderRespType"] == config.new_order_response_type
                assert len(observers) == 1
                _assert_consumed_at_transport(
                    env,
                    create_permit,
                    create_fingerprint_for_permit,
                    observers[0],
                    LiveExecutionOperation.ORDER_LIFECYCLE_CREATE,
                )
                return BinanceLifecycleHTTPResponse(200, url, order_payload("NEW"), 10)
            if method == "GET":
                assert params["symbol"] == "BTCUSDT"
                assert params["origClientOrderId"] == client_order_id
                assert "orderId" not in params
                order_query_count += 1
                payload = order_payload("NEW" if order_query_count == 1 else "CANCELED")
                query_payloads.append(payload)
                return BinanceLifecycleHTTPResponse(200, url, payload, 10)
            if method == "DELETE":
                assert identity == client_order_id
                assert params["symbol"] == "BTCUSDT"
                assert params["origClientOrderId"] == client_order_id
                assert "orderId" not in params
                assert "newClientOrderId" not in params
                assert len([call for call in calls if call[0] == "POST"]) == 1
                assert len([call for call in calls if call[0] == "DELETE"]) == 1
                assert len(observers) == 2
                assert observers[0] == {"close_count": 1, "close_completed": True}
                assert observers[1] == {"close_count": 1, "close_completed": True}
                assert journal_before_cancel_consume
                assert journal_path.read_text(encoding="utf-8") == journal_before_cancel_consume[0]

                persisted_journal = json.loads(journal_path.read_text(encoding="utf-8"))
                phases = [entry["phase"] for entry in persisted_journal["entries"]]
                assert persisted_journal["phase"] == LifecyclePhase.CANCEL_REQUEST_STARTED.value
                assert phases.count(LifecyclePhase.CREATE_REQUEST_STARTED.value) == 1
                assert phases.count(LifecyclePhase.CANCEL_REQUEST_STARTED.value) == 1
                assert phases.index(LifecyclePhase.CREATE_REQUEST_STARTED.value) < phases.index(
                    LifecyclePhase.CANCEL_REQUEST_STARTED.value
                )
                journal_at_delete.append(persisted_journal)

                independent_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
                try:
                    with Session(independent_engine, future=True) as session:
                        permits = list(
                            session.scalars(
                                select(LiveExecutionPermitORM).where(
                                    LiveExecutionPermitORM.permit_id.in_(
                                        [create_permit.permit_id, cancel_permit.permit_id]
                                    )
                                )
                            ).all()
                        )
                        audits = list(
                            session.scalars(
                                select(AuditEventORM).where(
                                    AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                                    AuditEventORM.action == "PERMIT_CONSUMED",
                                )
                            ).all()
                        )
                    by_id = {permit.permit_id: permit for permit in permits}
                    stored_create = by_id[create_permit.permit_id]
                    stored_cancel = by_id[cancel_permit.permit_id]
                    assert stored_create.state == LiveExecutionPermitState.CONSUMED.value
                    assert stored_create.version == create_permit.version + 1 == 2
                    assert stored_create.consumption_correlation_id is not None
                    assert stored_create.operation == LiveExecutionOperation.ORDER_LIFECYCLE_CREATE.value
                    assert stored_create.request_fingerprint == create_fingerprint_for_permit.request_fingerprint
                    assert stored_cancel.state == LiveExecutionPermitState.CONSUMED.value
                    assert stored_cancel.version == cancel_permit.version + 1 == 2
                    assert stored_cancel.consumed_at is not None
                    assert stored_cancel.consumption_correlation_id is not None
                    assert stored_cancel.consumption_correlation_id != stored_create.consumption_correlation_id
                    assert stored_cancel.operation == LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL.value
                    assert stored_cancel.environment == "TESTNET"
                    assert stored_cancel.symbol == "BTCUSDT"
                    assert stored_cancel.request_fingerprint == captured["fingerprint"].request_fingerprint
                    create_audits = [
                        event for event in audits if event.metadata_json.get("permit_id") == create_permit.permit_id
                    ]
                    cancel_audits = [
                        event for event in audits if event.metadata_json.get("permit_id") == cancel_permit.permit_id
                    ]
                    assert len(create_audits) == 1
                    assert len(cancel_audits) == 1
                    assert create_audits[0].id != cancel_audits[0].id
                    assert create_audits[0].result == "PASS"
                    assert cancel_audits[0].result == "PASS"
                    assert create_audits[0].metadata_json["operation"] == LiveExecutionOperation.ORDER_LIFECYCLE_CREATE.value
                    assert cancel_audits[0].metadata_json["operation"] == LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL.value
                    assert cancel_audits[0].metadata_json["request_fingerprint"] == captured["fingerprint"].request_fingerprint
                    assert cancel_audits[0].metadata_json["environment"] == "TESTNET"
                    assert cancel_audits[0].metadata_json["symbol"] == "BTCUSDT"
                    assert cancel_audits[0].metadata_json["consumption_correlation_id"] == str(
                        stored_cancel.consumption_correlation_id
                    )
                finally:
                    independent_engine.dispose()

                transmitted_before_auth_removal = dict(params)
                auth_only = {"timestamp", "recvWindow", "signature"}
                assert auth_only <= set(transmitted_before_auth_removal)
                assert len(transmitted_before_auth_removal["signature"]) == 64
                actual_unsigned_transmitted = {
                    key: value for key, value in transmitted_before_auth_removal.items() if key not in auth_only
                }
                assert set(actual_unsigned_transmitted) == set(captured["request"].transport_business_parameters)
                assert actual_unsigned_transmitted == captured["request"].transport_business_parameters
                assert actual_unsigned_transmitted["symbol"] == "BTCUSDT"
                assert (
                    actual_unsigned_transmitted["origClientOrderId"]
                    == captured["fingerprint"].canonical_payload["client_order_id"]
                    == client_order_id
                )
                for forbidden in (
                    "timestamp",
                    "recvWindow",
                    "signature",
                    "apiKey",
                    "headers",
                    "credentials",
                    "exchange_order_id",
                    "orderId",
                ):
                    assert forbidden not in actual_unsigned_transmitted
                    assert forbidden not in captured["request"].fingerprint_context
                    assert forbidden not in captured["request"].transport_business_parameters
                captured["transmitted"] = transmitted_before_auth_removal
                return BinanceLifecycleHTTPResponse(200, url, order_payload("CANCELED"), 10)
            raise AssertionError("unexpected lifecycle transport")

        client.authenticated_request = transport
        engine = _lifecycle_engine(
            tmp_path,
            env=env,
            http_get=_lifecycle_http_get,
            authenticated_request=transport,
            permit_gate=gate,
            now_ms_provider=lambda: 123,
        )
        engine._client = lambda loaded_config: client
        assert isinstance(engine, BinanceFuturesTestnetOrderLifecycleEngine)
        assert isinstance(engine.permit_gate, LiveExecutionPermitGate)
        assert isinstance(client, BinanceFuturesTestnetOrderLifecycleClient)

        result = engine.run_lifecycle(
            lifecycle_id,
            client_order_id,
            "BUY",
            Decimal("0.001"),
            price_offset_bps=config.default_price_offset_bps,
            confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE",
            config_path=str(config_path),
            create_permit=LiveExecutionPermitReference(create_permit.permit_id, create_permit.version),
            cancel_permit=LiveExecutionPermitReference(cancel_permit.permit_id, cancel_permit.version),
        )

        assert captured["request"] is not None
        assert captured["fingerprint"] is not None
        assert captured["transmitted"] is not None
        assert cancel_request_snapshot == {
            "operation": cancel_request_for_permit.operation,
            "environment": cancel_request_for_permit.environment,
            "symbol": cancel_request_for_permit.symbol,
            "subject_type": cancel_request_for_permit.subject_type,
            "subject_id": cancel_request_for_permit.subject_id,
            "fingerprint_context": dict(cancel_request_for_permit.fingerprint_context),
            "transport_business_parameters": expected_cancel_business,
        }
        assert {
            "operation": captured["request"].operation,
            "environment": captured["request"].environment,
            "symbol": captured["request"].symbol,
            "subject_type": captured["request"].subject_type,
            "subject_id": captured["request"].subject_id,
            "fingerprint_context": dict(captured["request"].fingerprint_context),
            "transport_business_parameters": dict(captured["request"].transport_business_parameters),
        } == cancel_request_snapshot
        assert captured["fingerprint"].request_fingerprint == cancel_fingerprint_for_permit.request_fingerprint
        assert captured["fingerprint"].canonical_payload["client_order_id"] == client_order_id
        assert captured["fingerprint"].subject_id == client_order_id
        assert captured["fingerprint"].request_fingerprint != changed_client_fingerprint.request_fingerprint

        post_calls = [call for call in calls if call[0] == "POST"]
        delete_calls = [call for call in calls if call[0] == "DELETE"]
        query_calls = [call for call in calls if call[0] == "GET" and call[1] == "https://demo-fapi.binance.com/fapi/v1/order"]
        position_calls = [call for call in calls if "positionRisk" in call[1]]
        assert post_calls == [("POST", "https://demo-fapi.binance.com/fapi/v1/order", client_order_id)]
        assert delete_calls == [("DELETE", "https://demo-fapi.binance.com/fapi/v1/order", client_order_id)]
        assert len(query_calls) == 2
        assert len(position_calls) == 2
        assert query_payloads[0]["status"] == "NEW"
        assert query_payloads[0]["symbol"] == "BTCUSDT"
        assert query_payloads[0]["clientOrderId"] == client_order_id
        assert query_payloads[0]["side"] == "BUY"
        assert query_payloads[0]["type"] == "LIMIT"
        assert query_payloads[0]["executedQty"] == "0"

        assert result.status == "PASS", (result.decision, result.reason, [issue.to_dict() for issue in result.issues])
        assert result.decision == "LIFECYCLE_COMPLETE"
        assert result.lifecycle_complete is True
        assert result.recovery_required is False
        assert result.created_order is not None and result.created_order.status == "NEW"
        assert result.queried_order is not None and result.queried_order.status == "NEW"
        assert result.cancel_order is not None and result.cancel_order.status == "CANCELED"
        assert result.cancel_order.executed_quantity == Decimal("0")
        assert result.final_order is not None and result.final_order.status == "CANCELED"
        assert result.final_order.executed_quantity == Decimal("0")
        assert result.unexpected_fill_detected is False
        assert result.unexpected_position_detected is False
        assert result.create_request is not None and result.create_request.retry_count == 0
        assert result.cancel_request is not None and result.cancel_request.retry_count == 0
        assert journal_at_delete and journal_at_delete[0]["phase"] == LifecyclePhase.CANCEL_REQUEST_STARTED.value
        assert not lock_path.exists()
        assert len(observers) == 2
        assert observers[0] == {"close_count": 1, "close_completed": True}
        assert observers[1] == {"close_count": 1, "close_completed": True}

        stored_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
        try:
            with Session(stored_engine, future=True) as session:
                permits = list(
                    session.scalars(
                        select(LiveExecutionPermitORM).where(
                            LiveExecutionPermitORM.permit_id.in_([create_permit.permit_id, cancel_permit.permit_id])
                        )
                    ).all()
                )
                audits = list(
                    session.scalars(
                        select(AuditEventORM).where(
                            AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                            AuditEventORM.action == "PERMIT_CONSUMED",
                        )
                    ).all()
                )
            by_id = {permit.permit_id: permit for permit in permits}
            stored_create = by_id[create_permit.permit_id]
            stored_cancel = by_id[cancel_permit.permit_id]
            assert len(permits) == 2
            assert stored_create.state == LiveExecutionPermitState.CONSUMED.value
            assert stored_create.version == 2
            assert stored_create.consumption_correlation_id is not None
            assert stored_create.operation == LiveExecutionOperation.ORDER_LIFECYCLE_CREATE.value
            assert stored_create.request_fingerprint == create_fingerprint_for_permit.request_fingerprint
            assert stored_cancel.state == LiveExecutionPermitState.CONSUMED.value
            assert stored_cancel.version == 2
            assert stored_cancel.consumption_correlation_id is not None
            assert stored_cancel.consumption_correlation_id != stored_create.consumption_correlation_id
            assert stored_cancel.operation == LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL.value
            assert stored_cancel.environment == "TESTNET"
            assert stored_cancel.symbol == "BTCUSDT"
            assert stored_cancel.request_fingerprint == captured["fingerprint"].request_fingerprint
            create_audits = [event for event in audits if event.metadata_json.get("permit_id") == create_permit.permit_id]
            cancel_audits = [event for event in audits if event.metadata_json.get("permit_id") == cancel_permit.permit_id]
            assert len(create_audits) == 1
            assert len(cancel_audits) == 1
            assert create_audits[0].metadata_json["request_fingerprint"] == create_fingerprint_for_permit.request_fingerprint
            assert cancel_audits[0].metadata_json["request_fingerprint"] == captured["fingerprint"].request_fingerprint
        finally:
            stored_engine.dispose()
    finally:
        BinanceFuturesTestnetOrderLifecycleClient.build_cancel_unsigned_business_request = original_class_cancel_builder
        BinanceFuturesTestnetOrderLifecycleClient.cancel_order_exact = original_class_cancel_order
        lifecycle_engine_module.build_lifecycle_cancel_from_final_request = original_engine_cancel_fingerprint_builder

def test_order_test_limit_fingerprint_equals_transmitted_business_request(tmp_path) -> None:
    import engine.diagnostics.binance_futures_testnet_order_test_engine as order_test_engine_module

    env = durable_state_env("RELEASED")
    config_path = _write_order_test_config(tmp_path)
    config = BinanceFuturesTestnetOrderTestConfig()
    client_order_id = "smcbot-test-fp-limit-001"
    observer = {"close_count": 0, "close_completed": False}
    calls: list[tuple[str, str, str | None]] = []
    signing_events: list[str] = []
    captured = {"request": None, "fingerprint": None, "transmitted": None}
    request_snapshot: dict[str, object] = {}

    client = BinanceFuturesTestnetOrderTestClient(
        config,
        http_get=_order_test_http_get,
        authenticated_post=lambda url, body, timeout, headers: BinanceOrderTestHTTPResponse(500, url, {}, 0),
        env=env,
        now_ms_provider=lambda: 123,
    )
    filters = client.parse_exchange_filters(
        _order_test_http_get("https://demo-fapi.binance.com/fapi/v1/exchangeInfo", 30).payload
    )
    preview = client.build_order_test_preview(
        client_order_id,
        "BUY",
        "LIMIT",
        Decimal("0.001"),
        Decimal("50000"),
        "GTC",
        False,
        exchange_filters=filters,
    )
    unsigned_request = client.build_unsigned_business_request(preview)
    fingerprint = build_signed_order_test_create_from_final_request(unsigned_request)
    issued = _issue(env, fingerprint)
    assert issued.version == 1
    assert issued.operation == LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value
    assert issued.environment == "TESTNET"
    assert issued.symbol == "BTCUSDT"
    assert issued.request_fingerprint == fingerprint.request_fingerprint

    expected_business = dict(unsigned_request.transport_business_parameters)
    field_classification = {
        "symbol": "FINGERPRINT_AND_TRANSPORT",
        "client_order_id": "FINGERPRINT_AND_TRANSPORT",
        "newClientOrderId": "FINGERPRINT_AND_TRANSPORT",
        "side": "FINGERPRINT_AND_TRANSPORT",
        "positionSide": "FINGERPRINT_AND_TRANSPORT",
        "type": "FINGERPRINT_AND_TRANSPORT",
        "quantity": "FINGERPRINT_AND_TRANSPORT",
        "price": "FINGERPRINT_AND_TRANSPORT",
        "timeInForce": "FINGERPRINT_AND_TRANSPORT",
        "reduceOnly": "FINGERPRINT_BOUND_DEFAULTED_FIELD",
        "timestamp": "AUTH_TRANSPORT",
        "recvWindow": "AUTH_TRANSPORT",
        "signature": "AUTH_TRANSPORT",
    }
    assert set(field_classification) == {
        "symbol",
        "client_order_id",
        "newClientOrderId",
        "side",
        "positionSide",
        "type",
        "quantity",
        "price",
        "timeInForce",
        "reduceOnly",
        "timestamp",
        "recvWindow",
        "signature",
    }
    assert unsigned_request.operation == LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE
    assert unsigned_request.environment == "TESTNET"
    assert unsigned_request.symbol == "BTCUSDT"
    assert unsigned_request.subject_type == "ORDER_TEST"
    assert unsigned_request.subject_id == client_order_id
    assert set(expected_business) == {
        "symbol",
        "side",
        "type",
        "quantity",
        "price",
        "newClientOrderId",
        "timeInForce",
        "positionSide",
    }
    assert expected_business == {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "quantity": "0.001",
        "price": "50000",
        "newClientOrderId": client_order_id,
        "timeInForce": "GTC",
        "positionSide": "BOTH",
    }
    assert "reduceOnly" not in expected_business
    assert unsigned_request.fingerprint_context == {
        "schema_version": "1.0",
        "operation": "SIGNED_ORDER_TEST_CREATE",
        "environment": "TESTNET",
        "symbol": "BTCUSDT",
        "client_order_id": client_order_id,
        "side": "BUY",
        "position_side": "BOTH",
        "order_type": "LIMIT",
        "quantity": "0.001",
        "price": "50000",
        "time_in_force": "GTC",
        "reduce_only": False,
    }
    for forbidden in (
        "timestamp",
        "recvWindow",
        "signature",
        "apiKey",
        "headers",
        "credentials",
        "raw_preview",
        "filter_metadata",
        "mark_price",
        "permit_id",
        "correlation_id",
    ):
        assert forbidden not in unsigned_request.fingerprint_context
        assert forbidden not in unsigned_request.transport_business_parameters

    assert fingerprint.operation == LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value
    assert fingerprint.environment == "TESTNET"
    assert fingerprint.symbol == "BTCUSDT"
    assert fingerprint.subject_type == "CLIENT_ORDER"
    assert fingerprint.subject_id == client_order_id
    assert fingerprint.canonical_payload["client_order_id"] == client_order_id
    assert fingerprint.canonical_payload["side"] == "BUY"
    assert fingerprint.canonical_payload["position_side"] == "BOTH"
    assert fingerprint.canonical_payload["order_type"] == "LIMIT"
    assert fingerprint.canonical_payload["quantity"] == "0.001"
    assert fingerprint.canonical_payload["price"] == "50000"
    assert fingerprint.canonical_payload["time_in_force"] == "GTC"
    assert fingerprint.canonical_payload["reduce_only"] is False
    assert "timestamp" not in fingerprint.canonical_payload
    assert "recvWindow" not in fingerprint.canonical_payload
    assert "signature" not in fingerprint.canonical_payload
    assert len(fingerprint.request_fingerprint) == 64
    assert fingerprint.request_fingerprint == fingerprint.request_fingerprint.lower()
    assert set(fingerprint.request_fingerprint) <= set("0123456789abcdef")

    reduce_only_true_preview = client.build_order_test_preview(
        client_order_id,
        "BUY",
        "LIMIT",
        Decimal("0.001"),
        Decimal("50000"),
        "GTC",
        True,
        exchange_filters=filters,
    )
    reduce_only_true_request = client.build_unsigned_business_request(reduce_only_true_preview)
    reduce_only_true_fingerprint = build_signed_order_test_create_from_final_request(reduce_only_true_request)
    assert reduce_only_true_request.fingerprint_context["reduce_only"] is True
    assert reduce_only_true_request.transport_business_parameters["reduceOnly"] == "true"
    assert reduce_only_true_fingerprint.canonical_payload != fingerprint.canonical_payload
    assert reduce_only_true_fingerprint.request_fingerprint != fingerprint.request_fingerprint

    price_variant = LiveExecutionUnsignedMutationRequest(
        operation=unsigned_request.operation,
        environment=unsigned_request.environment,
        symbol=unsigned_request.symbol,
        subject_type=unsigned_request.subject_type,
        subject_id=unsigned_request.subject_id,
        fingerprint_context={**dict(unsigned_request.fingerprint_context), "price": "50001"},
        transport_business_parameters={**dict(unsigned_request.transport_business_parameters), "price": "50001"},
    )
    time_in_force_variant = LiveExecutionUnsignedMutationRequest(
        operation=unsigned_request.operation,
        environment=unsigned_request.environment,
        symbol=unsigned_request.symbol,
        subject_type=unsigned_request.subject_type,
        subject_id=unsigned_request.subject_id,
        fingerprint_context={**dict(unsigned_request.fingerprint_context), "time_in_force": "GTX"},
        transport_business_parameters={**dict(unsigned_request.transport_business_parameters), "timeInForce": "GTX"},
    )
    position_side_variant = LiveExecutionUnsignedMutationRequest(
        operation=unsigned_request.operation,
        environment=unsigned_request.environment,
        symbol=unsigned_request.symbol,
        subject_type=unsigned_request.subject_type,
        subject_id=unsigned_request.subject_id,
        fingerprint_context={**dict(unsigned_request.fingerprint_context), "position_side": "LONG"},
        transport_business_parameters={**dict(unsigned_request.transport_business_parameters), "positionSide": "LONG"},
    )
    client_id_variant_id = "smcbot-test-fp-limit-002"
    client_id_variant = LiveExecutionUnsignedMutationRequest(
        operation=unsigned_request.operation,
        environment=unsigned_request.environment,
        symbol=unsigned_request.symbol,
        subject_type=unsigned_request.subject_type,
        subject_id=client_id_variant_id,
        fingerprint_context={**dict(unsigned_request.fingerprint_context), "client_order_id": client_id_variant_id},
        transport_business_parameters={**dict(unsigned_request.transport_business_parameters), "newClientOrderId": client_id_variant_id},
    )
    for variant in (price_variant, time_in_force_variant, position_side_variant, client_id_variant):
        variant_fingerprint = build_signed_order_test_create_from_final_request(variant)
        assert variant_fingerprint.canonical_payload != fingerprint.canonical_payload
        assert variant_fingerprint.request_fingerprint != fingerprint.request_fingerprint
        assert issued.request_fingerprint != variant_fingerprint.request_fingerprint

    gate = LiveExecutionPermitGate(
        env=env,
        correlation_id_provider=lambda: CORRELATION,
        permit_persistence_factory=lambda **kwargs: _ClosingPermitPersistence(observer, **kwargs),
    )
    real_unsigned_builder = client.build_unsigned_business_request
    real_submit_test_order = client.submit_test_order
    real_signature = client._signature
    original_engine_fingerprint_builder = order_test_engine_module.build_signed_order_test_create_from_final_request

    try:
        def captured_unsigned_builder(actual_preview):
            rebuilt = real_unsigned_builder(actual_preview)
            assert dict(rebuilt.fingerprint_context) == dict(unsigned_request.fingerprint_context)
            assert dict(rebuilt.transport_business_parameters) == expected_business
            captured["request"] = rebuilt
            return rebuilt

        def captured_fingerprint_builder(actual_unsigned_request):
            assert actual_unsigned_request is captured["request"]
            produced = original_engine_fingerprint_builder(actual_unsigned_request)
            assert produced.request_fingerprint == fingerprint.request_fingerprint
            captured["fingerprint"] = produced
            request_snapshot.update(
                {
                    "operation": actual_unsigned_request.operation,
                    "environment": actual_unsigned_request.environment,
                    "symbol": actual_unsigned_request.symbol,
                    "subject_type": actual_unsigned_request.subject_type,
                    "subject_id": actual_unsigned_request.subject_id,
                    "fingerprint_context": dict(actual_unsigned_request.fingerprint_context),
                    "transport_business_parameters": dict(actual_unsigned_request.transport_business_parameters),
                }
            )
            return produced

        def captured_submit_test_order(actual_preview, server_time=None, unsigned_business_request=None):
            assert unsigned_business_request is captured["request"]
            assert dict(unsigned_business_request.transport_business_parameters) == expected_business
            return real_submit_test_order(actual_preview, server_time, unsigned_business_request=unsigned_business_request)

        def observed_signature(canonical_query: str) -> str:
            assert observer == {"close_count": 1, "close_completed": True}
            assert signing_events == []
            assert "signature=" not in canonical_query
            assert "timestamp=123" in canonical_query
            assert f"recvWindow={config.recv_window_ms}" in canonical_query
            signing_events.append("signed_after_permit_close")
            return real_signature(canonical_query)

        def authenticated_post(url, body, timeout, headers):
            body_text = body.decode("utf-8")
            params = {key: values[0] for key, values in parse_qs(body_text).items()}
            calls.append(("POST", url, params.get("newClientOrderId")))
            assert url == "https://demo-fapi.binance.com/fapi/v1/order/test"
            assert headers["Content-Type"] == "application/x-www-form-urlencoded"
            assert "X-MBX-APIKEY" in headers
            assert env[config.api_key_env_var] not in body_text
            assert env[config.api_secret_env_var] not in body_text
            assert observer == {"close_count": 1, "close_completed": True}
            assert signing_events == ["signed_after_permit_close"]
            _assert_consumed_at_transport(
                env,
                issued,
                fingerprint,
                observer,
                LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE,
            )

            transmitted_before_auth_removal = dict(params)
            auth_only = {"timestamp", "recvWindow", "signature"}
            assert auth_only <= set(transmitted_before_auth_removal)
            assert len(transmitted_before_auth_removal["signature"]) == 64
            actual_unsigned_transmitted = {
                key: value for key, value in transmitted_before_auth_removal.items() if key not in auth_only
            }
            assert set(actual_unsigned_transmitted) == set(captured["request"].transport_business_parameters)
            assert actual_unsigned_transmitted == captured["request"].transport_business_parameters
            assert actual_unsigned_transmitted["newClientOrderId"] == captured["fingerprint"].canonical_payload["client_order_id"] == client_order_id
            assert actual_unsigned_transmitted["positionSide"] == captured["fingerprint"].canonical_payload["position_side"] == "BOTH"
            assert actual_unsigned_transmitted["price"] == captured["fingerprint"].canonical_payload["price"] == "50000"
            assert actual_unsigned_transmitted["quantity"] == captured["fingerprint"].canonical_payload["quantity"] == "0.001"
            assert actual_unsigned_transmitted["timeInForce"] == captured["fingerprint"].canonical_payload["time_in_force"] == "GTC"
            assert "reduceOnly" not in actual_unsigned_transmitted
            assert captured["fingerprint"].canonical_payload["reduce_only"] is False
            for forbidden in (
                "timestamp",
                "recvWindow",
                "signature",
                "apiKey",
                "headers",
                "credentials",
                "raw_preview",
                "filter_metadata",
                "mark_price",
                "permit_id",
                "correlation_id",
            ):
                assert forbidden not in actual_unsigned_transmitted
                assert forbidden not in captured["request"].fingerprint_context
                assert forbidden not in captured["request"].transport_business_parameters
            captured["transmitted"] = transmitted_before_auth_removal

            independent_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
            try:
                with Session(independent_engine, future=True) as session:
                    stored = session.scalar(
                        select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == issued.permit_id)
                    )
                    audits = list(
                        session.scalars(
                            select(AuditEventORM).where(
                                AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                                AuditEventORM.action == "PERMIT_CONSUMED",
                            )
                        ).all()
                    )
                assert stored is not None
                assert stored.state == LiveExecutionPermitState.CONSUMED.value
                assert stored.version == issued.version + 1 == 2
                assert stored.consumed_at is not None
                assert stored.consumption_correlation_id is not None
                assert stored.operation == LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value
                assert stored.environment == "TESTNET"
                assert stored.symbol == "BTCUSDT"
                assert stored.request_fingerprint == captured["fingerprint"].request_fingerprint
                matching = [event for event in audits if event.metadata_json.get("permit_id") == issued.permit_id]
                assert len(matching) == 1
                assert matching[0].result == "PASS"
                assert matching[0].metadata_json["operation"] == LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value
                assert matching[0].metadata_json["environment"] == "TESTNET"
                assert matching[0].metadata_json["symbol"] == "BTCUSDT"
                assert matching[0].metadata_json["request_fingerprint"] == captured["fingerprint"].request_fingerprint
                assert matching[0].metadata_json["consumption_correlation_id"] == str(stored.consumption_correlation_id)
            finally:
                independent_engine.dispose()
            return BinanceOrderTestHTTPResponse(200, url, {}, 2)

        client.build_unsigned_business_request = captured_unsigned_builder
        client.submit_test_order = captured_submit_test_order
        client._signature = observed_signature
        client.authenticated_post = authenticated_post
        order_test_engine_module.build_signed_order_test_create_from_final_request = captured_fingerprint_builder

        engine = _order_test_engine(
            tmp_path,
            env=env,
            http_get=_order_test_http_get,
            authenticated_post=authenticated_post,
            permit_gate=gate,
            now_ms_provider=lambda: 123,
        )
        engine._client = lambda loaded_config: client
        assert isinstance(engine, BinanceFuturesTestnetOrderTestEngine)
        assert isinstance(engine.permit_gate, LiveExecutionPermitGate)
        assert isinstance(client, BinanceFuturesTestnetOrderTestClient)

        result = engine.submit_test_order(
            client_order_id,
            "BUY",
            "LIMIT",
            Decimal("0.001"),
            price=Decimal("50000"),
            time_in_force="GTC",
            reduce_only=False,
            confirmation="CONFIRM_TESTNET_ORDER_TEST",
            config_path=str(config_path),
            permit=LiveExecutionPermitReference(issued.permit_id, issued.version),
        )

        assert captured["request"] is not None
        assert captured["fingerprint"] is not None
        assert captured["transmitted"] is not None
        assert request_snapshot == {
            "operation": unsigned_request.operation,
            "environment": unsigned_request.environment,
            "symbol": unsigned_request.symbol,
            "subject_type": unsigned_request.subject_type,
            "subject_id": unsigned_request.subject_id,
            "fingerprint_context": dict(unsigned_request.fingerprint_context),
            "transport_business_parameters": expected_business,
        }
        assert {
            "operation": captured["request"].operation,
            "environment": captured["request"].environment,
            "symbol": captured["request"].symbol,
            "subject_type": captured["request"].subject_type,
            "subject_id": captured["request"].subject_id,
            "fingerprint_context": dict(captured["request"].fingerprint_context),
            "transport_business_parameters": dict(captured["request"].transport_business_parameters),
        } == request_snapshot
        assert captured["fingerprint"].request_fingerprint == fingerprint.request_fingerprint
        assert captured["fingerprint"].canonical_payload == fingerprint.canonical_payload
        assert captured["fingerprint"].request_fingerprint != reduce_only_true_fingerprint.request_fingerprint
        assert result.status == "PASS", (result.decision, result.reason, [issue.to_dict() for issue in result.issues])
        assert result.decision == "ORDER_TEST_ACCEPTED"
        assert result.test_order_request_transmitted is True
        assert result.authenticated_transport_invoked is True
        assert result.signature_generated is True
        assert result.request_metadata is not None
        assert result.request_metadata.retry_count == 0
        assert result.request_metadata.request_transmitted is True
        assert result.request_metadata.signature_generated is True
        assert calls == [("POST", "https://demo-fapi.binance.com/fapi/v1/order/test", client_order_id)]
        assert signing_events == ["signed_after_permit_close"]
        assert observer == {"close_count": 1, "close_completed": True}

        stored_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
        try:
            with Session(stored_engine, future=True) as session:
                stored = session.scalar(
                    select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == issued.permit_id)
                )
                audits = list(
                    session.scalars(
                        select(AuditEventORM).where(
                            AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                            AuditEventORM.action == "PERMIT_CONSUMED",
                        )
                    ).all()
                )
            assert stored is not None
            assert stored.state == LiveExecutionPermitState.CONSUMED.value
            assert stored.version == 2
            assert stored.operation == LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value
            assert stored.environment == "TESTNET"
            assert stored.symbol == "BTCUSDT"
            assert stored.request_fingerprint == captured["fingerprint"].request_fingerprint
            assert len([event for event in audits if event.metadata_json.get("permit_id") == issued.permit_id]) == 1
        finally:
            stored_engine.dispose()
    finally:
        order_test_engine_module.build_signed_order_test_create_from_final_request = original_engine_fingerprint_builder

def test_order_test_market_fingerprint_equals_transmitted_business_request(tmp_path) -> None:
    import engine.diagnostics.binance_futures_testnet_order_test_engine as order_test_engine_module

    env = durable_state_env("RELEASED")
    config_path = _write_order_test_config(tmp_path)
    config = BinanceFuturesTestnetOrderTestConfig()
    client_order_id = "smcbot-test-fp-market-001"
    observer = {"close_count": 0, "close_completed": False}
    calls: list[tuple[str, str, str | None]] = []
    signing_events: list[str] = []
    http_get_calls: list[str] = []
    captured = {"request": None, "fingerprint": None, "transmitted": None}
    request_snapshot: dict[str, object] = {}

    def order_test_http_get(url, timeout):
        http_get_calls.append(url)
        if url.endswith("/fapi/v1/time"):
            return BinanceOrderTestHTTPResponse(200, url, {"serverTime": 123}, 18)
        if "/fapi/v1/premiumIndex" in url:
            return BinanceOrderTestHTTPResponse(200, url, {"symbol": "BTCUSDT", "markPrice": "50000"}, 40)
        return _order_test_http_get(url, timeout)

    client = BinanceFuturesTestnetOrderTestClient(
        config,
        http_get=order_test_http_get,
        authenticated_post=lambda url, body, timeout, headers: BinanceOrderTestHTTPResponse(500, url, {}, 0),
        env=env,
        now_ms_provider=lambda: 123,
    )
    filters = client.parse_exchange_filters(
        _order_test_http_get("https://demo-fapi.binance.com/fapi/v1/exchangeInfo", 30).payload
    )
    preview = client.build_order_test_preview(
        client_order_id,
        "SELL",
        "MARKET",
        Decimal("0.001"),
        price=None,
        time_in_force=None,
        reduce_only=False,
        exchange_filters=filters,
        mark_price=Decimal("50000"),
    )
    unsigned_request = client.build_unsigned_business_request(preview)
    fingerprint = build_signed_order_test_create_from_final_request(unsigned_request)
    issued = _issue(env, fingerprint)
    assert issued.version == 1
    assert issued.operation == LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value
    assert issued.environment == "TESTNET"
    assert issued.symbol == "BTCUSDT"
    assert issued.request_fingerprint == fingerprint.request_fingerprint

    expected_business = dict(unsigned_request.transport_business_parameters)
    field_classification = {
        "symbol": "FINGERPRINT_AND_TRANSPORT",
        "client_order_id": "FINGERPRINT_AND_TRANSPORT",
        "newClientOrderId": "FINGERPRINT_AND_TRANSPORT",
        "side": "FINGERPRINT_AND_TRANSPORT",
        "positionSide": "FINGERPRINT_AND_TRANSPORT",
        "type": "FINGERPRINT_AND_TRANSPORT",
        "quantity": "FINGERPRINT_AND_TRANSPORT",
        "price": "FINGERPRINT_BOUND_NULL_FIELD",
        "timeInForce": "FINGERPRINT_BOUND_NULL_FIELD",
        "reduceOnly": "FINGERPRINT_BOUND_DEFAULTED_FIELD",
        "mark price": "READ_ONLY_VALIDATION_INPUT",
        "timestamp": "AUTH_TRANSPORT",
        "recvWindow": "AUTH_TRANSPORT",
        "signature": "AUTH_TRANSPORT",
    }
    assert set(field_classification) == {
        "symbol",
        "client_order_id",
        "newClientOrderId",
        "side",
        "positionSide",
        "type",
        "quantity",
        "price",
        "timeInForce",
        "reduceOnly",
        "mark price",
        "timestamp",
        "recvWindow",
        "signature",
    }
    assert unsigned_request.operation == LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE
    assert unsigned_request.environment == "TESTNET"
    assert unsigned_request.symbol == "BTCUSDT"
    assert unsigned_request.subject_type == "ORDER_TEST"
    assert unsigned_request.subject_id == client_order_id
    assert set(expected_business) == {"symbol", "side", "type", "quantity", "newClientOrderId", "positionSide"}
    assert expected_business == {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "MARKET",
        "quantity": "0.001",
        "newClientOrderId": client_order_id,
        "positionSide": "BOTH",
    }
    assert "price" not in expected_business
    assert "timeInForce" not in expected_business
    assert "markPrice" not in expected_business
    assert "reduceOnly" not in expected_business
    assert unsigned_request.fingerprint_context == {
        "schema_version": "1.0",
        "operation": "SIGNED_ORDER_TEST_CREATE",
        "environment": "TESTNET",
        "symbol": "BTCUSDT",
        "client_order_id": client_order_id,
        "side": "SELL",
        "position_side": "BOTH",
        "order_type": "MARKET",
        "quantity": "0.001",
        "price": None,
        "time_in_force": None,
        "reduce_only": False,
    }
    for forbidden in (
        "timestamp",
        "recvWindow",
        "signature",
        "apiKey",
        "headers",
        "credentials",
        "markPrice",
        "estimated_notional",
        "filter_metadata",
        "preview_metadata",
        "permit_id",
        "correlation_id",
    ):
        assert forbidden not in unsigned_request.fingerprint_context
        assert forbidden not in unsigned_request.transport_business_parameters

    assert fingerprint.operation == LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value
    assert fingerprint.environment == "TESTNET"
    assert fingerprint.symbol == "BTCUSDT"
    assert fingerprint.subject_type == "CLIENT_ORDER"
    assert fingerprint.subject_id == client_order_id
    assert fingerprint.canonical_payload["client_order_id"] == client_order_id
    assert fingerprint.canonical_payload["side"] == "SELL"
    assert fingerprint.canonical_payload["position_side"] == "BOTH"
    assert fingerprint.canonical_payload["order_type"] == "MARKET"
    assert fingerprint.canonical_payload["quantity"] == "0.001"
    assert fingerprint.canonical_payload["price"] is None
    assert fingerprint.canonical_payload["time_in_force"] is None
    assert fingerprint.canonical_payload["reduce_only"] is False
    assert "markPrice" not in fingerprint.canonical_payload
    assert "timestamp" not in fingerprint.canonical_payload
    assert "recvWindow" not in fingerprint.canonical_payload
    assert "signature" not in fingerprint.canonical_payload
    assert len(fingerprint.request_fingerprint) == 64
    assert fingerprint.request_fingerprint == fingerprint.request_fingerprint.lower()
    assert set(fingerprint.request_fingerprint) <= set("0123456789abcdef")

    alternate_mark_preview = client.build_order_test_preview(
        client_order_id,
        "SELL",
        "MARKET",
        Decimal("0.001"),
        price=None,
        time_in_force=None,
        reduce_only=False,
        exchange_filters=filters,
        mark_price=Decimal("60000"),
    )
    alternate_mark_request = client.build_unsigned_business_request(alternate_mark_preview)
    alternate_mark_fingerprint = build_signed_order_test_create_from_final_request(alternate_mark_request)
    assert alternate_mark_preview.estimated_notional == Decimal("60.000")
    assert dict(alternate_mark_request.fingerprint_context) == dict(unsigned_request.fingerprint_context)
    assert dict(alternate_mark_request.transport_business_parameters) == expected_business
    assert alternate_mark_fingerprint.request_fingerprint == fingerprint.request_fingerprint

    reduce_only_true_preview = client.build_order_test_preview(
        client_order_id,
        "SELL",
        "MARKET",
        Decimal("0.001"),
        price=None,
        time_in_force=None,
        reduce_only=True,
        exchange_filters=filters,
        mark_price=Decimal("50000"),
    )
    reduce_only_true_request = client.build_unsigned_business_request(reduce_only_true_preview)
    reduce_only_true_fingerprint = build_signed_order_test_create_from_final_request(reduce_only_true_request)
    assert reduce_only_true_request.fingerprint_context["reduce_only"] is True
    assert reduce_only_true_request.transport_business_parameters["reduceOnly"] == "true"
    assert reduce_only_true_fingerprint.canonical_payload != fingerprint.canonical_payload
    assert reduce_only_true_fingerprint.request_fingerprint != fingerprint.request_fingerprint

    limit_variant = LiveExecutionUnsignedMutationRequest(
        operation=unsigned_request.operation,
        environment=unsigned_request.environment,
        symbol=unsigned_request.symbol,
        subject_type=unsigned_request.subject_type,
        subject_id=unsigned_request.subject_id,
        fingerprint_context={
            **dict(unsigned_request.fingerprint_context),
            "order_type": "LIMIT",
            "price": "50000",
            "time_in_force": "GTC",
        },
        transport_business_parameters={
            **dict(unsigned_request.transport_business_parameters),
            "type": "LIMIT",
            "price": "50000",
            "timeInForce": "GTC",
        },
    )
    invalid_market_price = LiveExecutionUnsignedMutationRequest(
        operation=unsigned_request.operation,
        environment=unsigned_request.environment,
        symbol=unsigned_request.symbol,
        subject_type=unsigned_request.subject_type,
        subject_id=unsigned_request.subject_id,
        fingerprint_context={**dict(unsigned_request.fingerprint_context), "price": "50000"},
        transport_business_parameters={**dict(unsigned_request.transport_business_parameters), "price": "50000"},
    )
    invalid_market_time_in_force = LiveExecutionUnsignedMutationRequest(
        operation=unsigned_request.operation,
        environment=unsigned_request.environment,
        symbol=unsigned_request.symbol,
        subject_type=unsigned_request.subject_type,
        subject_id=unsigned_request.subject_id,
        fingerprint_context={**dict(unsigned_request.fingerprint_context), "time_in_force": "GTC"},
        transport_business_parameters={**dict(unsigned_request.transport_business_parameters), "timeInForce": "GTC"},
    )
    quantity_variant = LiveExecutionUnsignedMutationRequest(
        operation=unsigned_request.operation,
        environment=unsigned_request.environment,
        symbol=unsigned_request.symbol,
        subject_type=unsigned_request.subject_type,
        subject_id=unsigned_request.subject_id,
        fingerprint_context={**dict(unsigned_request.fingerprint_context), "quantity": "0.002"},
        transport_business_parameters={**dict(unsigned_request.transport_business_parameters), "quantity": "0.002"},
    )
    position_side_variant = LiveExecutionUnsignedMutationRequest(
        operation=unsigned_request.operation,
        environment=unsigned_request.environment,
        symbol=unsigned_request.symbol,
        subject_type=unsigned_request.subject_type,
        subject_id=unsigned_request.subject_id,
        fingerprint_context={**dict(unsigned_request.fingerprint_context), "position_side": "LONG"},
        transport_business_parameters={**dict(unsigned_request.transport_business_parameters), "positionSide": "LONG"},
    )
    client_id_variant_id = "smcbot-test-fp-market-002"
    client_id_variant = LiveExecutionUnsignedMutationRequest(
        operation=unsigned_request.operation,
        environment=unsigned_request.environment,
        symbol=unsigned_request.symbol,
        subject_type=unsigned_request.subject_type,
        subject_id=client_id_variant_id,
        fingerprint_context={**dict(unsigned_request.fingerprint_context), "client_order_id": client_id_variant_id},
        transport_business_parameters={**dict(unsigned_request.transport_business_parameters), "newClientOrderId": client_id_variant_id},
    )
    for variant in (limit_variant, quantity_variant, position_side_variant, client_id_variant):
        variant_fingerprint = build_signed_order_test_create_from_final_request(variant)
        assert variant_fingerprint.canonical_payload != fingerprint.canonical_payload
        assert variant_fingerprint.request_fingerprint != fingerprint.request_fingerprint
        assert issued.request_fingerprint != variant_fingerprint.request_fingerprint
    for variant in (invalid_market_price, invalid_market_time_in_force):
        with pytest.raises(Exception):
            build_signed_order_test_create_from_final_request(variant)

    gate = LiveExecutionPermitGate(
        env=env,
        correlation_id_provider=lambda: CORRELATION,
        permit_persistence_factory=lambda **kwargs: _ClosingPermitPersistence(observer, **kwargs),
    )
    real_unsigned_builder = client.build_unsigned_business_request
    real_submit_test_order = client.submit_test_order
    real_signature = client._signature
    original_engine_fingerprint_builder = order_test_engine_module.build_signed_order_test_create_from_final_request

    try:
        def captured_unsigned_builder(actual_preview):
            rebuilt = real_unsigned_builder(actual_preview)
            assert actual_preview.order_type == "MARKET"
            assert actual_preview.price is None
            assert actual_preview.time_in_force is None
            assert actual_preview.reference_price == Decimal("50000")
            assert actual_preview.estimated_notional == Decimal("50.000")
            assert dict(rebuilt.fingerprint_context) == dict(unsigned_request.fingerprint_context)
            assert dict(rebuilt.transport_business_parameters) == expected_business
            captured["request"] = rebuilt
            return rebuilt

        def captured_fingerprint_builder(actual_unsigned_request):
            assert actual_unsigned_request is captured["request"]
            produced = original_engine_fingerprint_builder(actual_unsigned_request)
            assert produced.request_fingerprint == fingerprint.request_fingerprint
            captured["fingerprint"] = produced
            request_snapshot.update(
                {
                    "operation": actual_unsigned_request.operation,
                    "environment": actual_unsigned_request.environment,
                    "symbol": actual_unsigned_request.symbol,
                    "subject_type": actual_unsigned_request.subject_type,
                    "subject_id": actual_unsigned_request.subject_id,
                    "fingerprint_context": dict(actual_unsigned_request.fingerprint_context),
                    "transport_business_parameters": dict(actual_unsigned_request.transport_business_parameters),
                }
            )
            return produced

        def captured_submit_test_order(actual_preview, server_time=None, unsigned_business_request=None):
            assert unsigned_business_request is captured["request"]
            assert dict(unsigned_business_request.transport_business_parameters) == expected_business
            return real_submit_test_order(actual_preview, server_time, unsigned_business_request=unsigned_business_request)

        def observed_signature(canonical_query: str) -> str:
            assert observer == {"close_count": 1, "close_completed": True}
            assert signing_events == []
            assert "signature=" not in canonical_query
            assert "timestamp=123" in canonical_query
            assert f"recvWindow={config.recv_window_ms}" in canonical_query
            assert "price=" not in canonical_query
            assert "timeInForce=" not in canonical_query
            assert "markPrice=" not in canonical_query
            signing_events.append("signed_after_permit_close")
            return real_signature(canonical_query)

        def authenticated_post(url, body, timeout, headers):
            body_text = body.decode("utf-8")
            params = {key: values[0] for key, values in parse_qs(body_text).items()}
            calls.append(("POST", url, params.get("newClientOrderId")))
            assert url == "https://demo-fapi.binance.com/fapi/v1/order/test"
            assert headers["Content-Type"] == "application/x-www-form-urlencoded"
            assert "X-MBX-APIKEY" in headers
            assert env[config.api_key_env_var] not in body_text
            assert env[config.api_secret_env_var] not in body_text
            assert observer == {"close_count": 1, "close_completed": True}
            assert signing_events == ["signed_after_permit_close"]
            assert len([call for call in http_get_calls if "/fapi/v1/premiumIndex" in call]) == 1
            _assert_consumed_at_transport(
                env,
                issued,
                fingerprint,
                observer,
                LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE,
            )

            transmitted_before_auth_removal = dict(params)
            auth_only = {"timestamp", "recvWindow", "signature"}
            assert auth_only <= set(transmitted_before_auth_removal)
            assert len(transmitted_before_auth_removal["signature"]) == 64
            actual_unsigned_transmitted = {
                key: value for key, value in transmitted_before_auth_removal.items() if key not in auth_only
            }
            assert set(actual_unsigned_transmitted) == set(captured["request"].transport_business_parameters)
            assert actual_unsigned_transmitted == captured["request"].transport_business_parameters
            assert actual_unsigned_transmitted["newClientOrderId"] == captured["fingerprint"].canonical_payload["client_order_id"] == client_order_id
            assert actual_unsigned_transmitted["positionSide"] == captured["fingerprint"].canonical_payload["position_side"] == "BOTH"
            assert actual_unsigned_transmitted["type"] == captured["fingerprint"].canonical_payload["order_type"] == "MARKET"
            assert actual_unsigned_transmitted["quantity"] == captured["fingerprint"].canonical_payload["quantity"] == "0.001"
            assert "price" not in actual_unsigned_transmitted
            assert "timeInForce" not in actual_unsigned_transmitted
            assert "markPrice" not in actual_unsigned_transmitted
            assert "reduceOnly" not in actual_unsigned_transmitted
            assert captured["fingerprint"].canonical_payload["price"] is None
            assert captured["fingerprint"].canonical_payload["time_in_force"] is None
            assert captured["fingerprint"].canonical_payload["reduce_only"] is False
            for forbidden in (
                "timestamp",
                "recvWindow",
                "signature",
                "apiKey",
                "headers",
                "credentials",
                "markPrice",
                "estimated_notional",
                "filter_metadata",
                "preview_metadata",
                "permit_id",
                "correlation_id",
            ):
                assert forbidden not in actual_unsigned_transmitted
                assert forbidden not in captured["request"].fingerprint_context
                assert forbidden not in captured["request"].transport_business_parameters
            captured["transmitted"] = transmitted_before_auth_removal

            independent_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
            try:
                with Session(independent_engine, future=True) as session:
                    stored = session.scalar(
                        select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == issued.permit_id)
                    )
                    audits = list(
                        session.scalars(
                            select(AuditEventORM).where(
                                AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                                AuditEventORM.action == "PERMIT_CONSUMED",
                            )
                        ).all()
                    )
                assert stored is not None
                assert stored.state == LiveExecutionPermitState.CONSUMED.value
                assert stored.version == issued.version + 1 == 2
                assert stored.consumed_at is not None
                assert stored.consumption_correlation_id is not None
                assert stored.operation == LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value
                assert stored.environment == "TESTNET"
                assert stored.symbol == "BTCUSDT"
                assert stored.request_fingerprint == captured["fingerprint"].request_fingerprint
                matching = [event for event in audits if event.metadata_json.get("permit_id") == issued.permit_id]
                assert len(matching) == 1
                assert matching[0].result == "PASS"
                assert matching[0].metadata_json["operation"] == LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value
                assert matching[0].metadata_json["environment"] == "TESTNET"
                assert matching[0].metadata_json["symbol"] == "BTCUSDT"
                assert matching[0].metadata_json["request_fingerprint"] == captured["fingerprint"].request_fingerprint
                assert matching[0].metadata_json["consumption_correlation_id"] == str(stored.consumption_correlation_id)
            finally:
                independent_engine.dispose()
            return BinanceOrderTestHTTPResponse(200, url, {}, 2)

        client.build_unsigned_business_request = captured_unsigned_builder
        client.submit_test_order = captured_submit_test_order
        client._signature = observed_signature
        client.authenticated_post = authenticated_post
        order_test_engine_module.build_signed_order_test_create_from_final_request = captured_fingerprint_builder

        engine = _order_test_engine(
            tmp_path,
            env=env,
            http_get=order_test_http_get,
            authenticated_post=authenticated_post,
            permit_gate=gate,
            now_ms_provider=lambda: 123,
        )
        engine._client = lambda loaded_config: client
        assert isinstance(engine, BinanceFuturesTestnetOrderTestEngine)
        assert isinstance(engine.permit_gate, LiveExecutionPermitGate)
        assert isinstance(client, BinanceFuturesTestnetOrderTestClient)

        result = engine.submit_test_order(
            client_order_id,
            "SELL",
            "MARKET",
            Decimal("0.001"),
            price=None,
            time_in_force=None,
            reduce_only=False,
            confirmation="CONFIRM_TESTNET_ORDER_TEST",
            config_path=str(config_path),
            permit=LiveExecutionPermitReference(issued.permit_id, issued.version),
        )

        assert captured["request"] is not None
        assert captured["fingerprint"] is not None
        assert captured["transmitted"] is not None
        assert request_snapshot == {
            "operation": unsigned_request.operation,
            "environment": unsigned_request.environment,
            "symbol": unsigned_request.symbol,
            "subject_type": unsigned_request.subject_type,
            "subject_id": unsigned_request.subject_id,
            "fingerprint_context": dict(unsigned_request.fingerprint_context),
            "transport_business_parameters": expected_business,
        }
        assert {
            "operation": captured["request"].operation,
            "environment": captured["request"].environment,
            "symbol": captured["request"].symbol,
            "subject_type": captured["request"].subject_type,
            "subject_id": captured["request"].subject_id,
            "fingerprint_context": dict(captured["request"].fingerprint_context),
            "transport_business_parameters": dict(captured["request"].transport_business_parameters),
        } == request_snapshot
        assert captured["fingerprint"].request_fingerprint == fingerprint.request_fingerprint
        assert captured["fingerprint"].canonical_payload == fingerprint.canonical_payload
        assert result.status == "PASS", (result.decision, result.reason, [issue.to_dict() for issue in result.issues])
        assert result.decision == "ORDER_TEST_ACCEPTED"
        assert result.test_order_request_transmitted is True
        assert result.authenticated_transport_invoked is True
        assert result.signature_generated is True
        assert result.request_metadata is not None
        assert result.request_metadata.retry_count == 0
        assert result.request_metadata.request_transmitted is True
        assert result.request_metadata.signature_generated is True
        assert calls == [("POST", "https://demo-fapi.binance.com/fapi/v1/order/test", client_order_id)]
        assert signing_events == ["signed_after_permit_close"]
        assert len([call for call in http_get_calls if "/fapi/v1/premiumIndex" in call]) == 1
        assert observer == {"close_count": 1, "close_completed": True}

        stored_engine = create_engine(env["ICT_DATABASE_URL"], future=True)
        try:
            with Session(stored_engine, future=True) as session:
                stored = session.scalar(
                    select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == issued.permit_id)
                )
                audits = list(
                    session.scalars(
                        select(AuditEventORM).where(
                            AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                            AuditEventORM.action == "PERMIT_CONSUMED",
                        )
                    ).all()
                )
            assert stored is not None
            assert stored.state == LiveExecutionPermitState.CONSUMED.value
            assert stored.version == 2
            assert stored.operation == LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value
            assert stored.environment == "TESTNET"
            assert stored.symbol == "BTCUSDT"
            assert stored.request_fingerprint == captured["fingerprint"].request_fingerprint
            assert len([event for event in audits if event.metadata_json.get("permit_id") == issued.permit_id]) == 1
        finally:
            stored_engine.dispose()
    finally:
        order_test_engine_module.build_signed_order_test_create_from_final_request = original_engine_fingerprint_builder
