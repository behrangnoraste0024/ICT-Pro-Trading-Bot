from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from infrastructure.persistence.execution_orm import AuditEventORM, LiveExecutionPermitORM
from infrastructure.persistence.live_execution_permit_persistence import ISSUE_CONFIRMATION, LiveExecutionPermitPersistence
from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import BinanceFuturesTestnetOrderLifecycleClient
from infrastructure.exchanges.binance_futures_testnet_order_test_client import BinanceFuturesTestnetOrderTestClient
from infrastructure.exchanges.binance_futures_testnet_protective_orders_client import BinanceFuturesTestnetProtectiveOrdersClient
from infrastructure.security.live_execution_mutation_fingerprint_adapter import (
    build_lifecycle_cancel_from_final_request,
    build_lifecycle_create_from_final_request,
    build_protective_cancel_from_final_request,
    build_protective_create_from_final_request,
    build_signed_order_test_create_from_final_request,
)
from infrastructure.security.live_execution_permit_gate import LiveExecutionPermitGate
from models.binance_futures_testnet_order_lifecycle import (
    BinanceFuturesTestnetLifecyclePreview,
    BinanceFuturesTestnetOrderLifecycleConfig,
)
from models.binance_futures_testnet_order_test import (
    BinanceFuturesTestnetExchangeFilterSummary,
    BinanceFuturesTestnetOrderTestConfig,
)
from models.binance_futures_testnet_protective_orders import (
    BinanceFuturesTestnetProtectiveOrdersConfig,
    BinanceFuturesTestnetProtectivePreview,
)
from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit import LiveExecutionPermitState
from models.live_execution_permit_enforcement import LiveExecutionPermitGateError, LiveExecutionPermitReference, LiveExecutionUnsignedMutationRequest
from tests.kill_switch_test_support import durable_state_env


CORRELATION_ID = UUID("11111111-1111-4111-8111-111111111141")
EXPECTED_DRIFT_FIELDS = {
    "pair_id",
    "leg_type",
    "client_algo_id",
    "side",
    "position_side",
    "quantity",
    "trigger_price",
    "close_position",
    "reduce_only",
    "order_type",
    "working_type",
    "price_protect",
}


def _baseline_request() -> LiveExecutionUnsignedMutationRequest:
    fingerprint_context = {
        "schema_version": "1.0",
        "operation": "PROTECTIVE_CREATE",
        "environment": "TESTNET",
        "symbol": "BTCUSDT",
        "pair_id": "pair-drift-001",
        "leg_type": "STOP",
        "side": "SELL",
        "position_side": "BOTH",
        "quantity": "0.002",
        "trigger_price": "49000.1",
        "close_position": True,
        "reduce_only": None,
        "client_algo_id": "smcbot-protect-sl-drift-001",
        "order_type": "STOP_MARKET",
        "working_type": "MARK_PRICE",
        "price_protect": True,
    }
    transport_business_parameters = {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "STOP_MARKET",
        "stopPrice": "49000.1",
        "closePosition": "true",
        "workingType": "MARK_PRICE",
        "priceProtect": "TRUE",
        "positionSide": "BOTH",
        "newClientOrderId": "smcbot-protect-sl-drift-001",
    }
    return LiveExecutionUnsignedMutationRequest(
        operation=LiveExecutionOperation.PROTECTIVE_CREATE,
        environment="TESTNET",
        symbol="BTCUSDT",
        subject_type="PROTECTIVE_LEG",
        subject_id="pair-drift-001:STOP:smcbot-protect-sl-drift-001",
        fingerprint_context=fingerprint_context,
        transport_business_parameters=transport_business_parameters,
    )


def _variant_request(baseline: LiveExecutionUnsignedMutationRequest, field: str, value: Any) -> LiveExecutionUnsignedMutationRequest:
    fingerprint_context = dict(baseline.fingerprint_context)
    transport = dict(baseline.transport_business_parameters)
    fingerprint_context[field] = value
    if field == "pair_id":
        pass
    elif field == "leg_type":
        transport["type"] = "TAKE_PROFIT_MARKET"
    elif field == "client_algo_id":
        transport["newClientOrderId"] = value
    elif field == "side":
        transport["side"] = value
    elif field == "position_side":
        transport["positionSide"] = value
    elif field == "quantity":
        # closePosition protective creates bind quantity in the permit but do not transmit it.
        pass
    elif field == "trigger_price":
        transport["stopPrice"] = value
    elif field == "close_position":
        transport["closePosition"] = "false" if value is False else "true"
    elif field == "reduce_only":
        transport["reduceOnly"] = "true"
    elif field == "order_type":
        transport["type"] = value
    elif field == "working_type":
        transport["workingType"] = value
    elif field == "price_protect":
        transport["priceProtect"] = "FALSE" if value is False else "TRUE"
    else:
        raise AssertionError(f"unexpected drift field: {field}")
    return LiveExecutionUnsignedMutationRequest(
        operation=baseline.operation,
        environment=baseline.environment,
        symbol=baseline.symbol,
        subject_type=baseline.subject_type,
        subject_id=baseline.subject_id,
        fingerprint_context=fingerprint_context,
        transport_business_parameters=transport,
    )


def _issue(env: dict[str, str], fingerprint):
    persistence = LiveExecutionPermitPersistence(env=env)
    persistence.ensure_available()
    try:
        return persistence.issue(fingerprint, ttl_seconds=300, issued_by="field-drift-test", confirmation=ISSUE_CONFIRMATION)
    finally:
        persistence.close()


def _permit_and_audits(env: dict[str, str], permit_id: str):
    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine, future=True) as session:
            permit = session.scalar(select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == permit_id))
            audits = list(
                session.scalars(
                    select(AuditEventORM).where(
                        AuditEventORM.category == "LIVE_EXECUTION_PERMIT",
                        AuditEventORM.metadata_json["permit_id"].as_string() == permit_id,
                    )
                ).all()
            )
        return permit, audits
    finally:
        engine.dispose()


def test_protective_create_field_drift_matrix_denies_without_consuming_or_transport() -> None:
    baseline = _baseline_request()
    baseline_snapshot = {
        "operation": baseline.operation,
        "environment": baseline.environment,
        "symbol": baseline.symbol,
        "subject_type": baseline.subject_type,
        "subject_id": baseline.subject_id,
        "fingerprint_context": dict(baseline.fingerprint_context),
        "transport_business_parameters": dict(baseline.transport_business_parameters),
    }
    baseline_fingerprint = build_protective_create_from_final_request(baseline)
    assert baseline.operation == LiveExecutionOperation.PROTECTIVE_CREATE
    assert baseline.environment == "TESTNET"
    assert baseline.symbol == "BTCUSDT"
    assert baseline.subject_type == "PROTECTIVE_LEG"
    assert baseline.subject_id == "pair-drift-001:STOP:smcbot-protect-sl-drift-001"
    assert set(baseline.fingerprint_context) == {
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
    assert baseline_fingerprint.request_fingerprint

    cases = [
        ("pair_id", "pair-drift-002"),
        ("leg_type", "TAKE_PROFIT"),
        ("client_algo_id", "smcbot-protect-sl-drift-002"),
        ("side", "BUY"),
        ("position_side", "LONG"),
        ("quantity", "0.003"),
        ("trigger_price", "49100.2"),
        ("close_position", False),
        ("reduce_only", True),
        ("order_type", "TAKE_PROFIT_MARKET"),
        ("working_type", "CONTRACT_PRICE"),
        ("price_protect", False),
    ]
    assert {field for field, _ in cases} == EXPECTED_DRIFT_FIELDS
    assert len(cases) == len(EXPECTED_DRIFT_FIELDS)

    row_results: list[dict[str, object]] = []
    signing_count = 0
    post_count = 0
    delete_count = 0
    retry_count = 0
    identity_coupled_fields = {"pair_id", "leg_type", "client_algo_id"}

    for index, (field, altered_value) in enumerate(cases, start=1):
        env = durable_state_env("RELEASED")
        permit = _issue(env, baseline_fingerprint)
        altered = _variant_request(baseline, field, altered_value)
        altered_fingerprint = build_protective_create_from_final_request(altered)
        assert altered_fingerprint.canonical_payload != baseline_fingerprint.canonical_payload
        assert altered_fingerprint.request_fingerprint != baseline_fingerprint.request_fingerprint
        assert permit.request_fingerprint == baseline_fingerprint.request_fingerprint
        assert permit.state == LiveExecutionPermitState.ISSUED
        assert permit.version == 1

        gate = LiveExecutionPermitGate(
            env=env,
            correlation_id_provider=lambda i=index: UUID(f"11111111-1111-4111-8111-{140 + i:012d}"),
        )
        try:
            gate.authorize_and_consume(
                operation=LiveExecutionOperation.PROTECTIVE_CREATE,
                fingerprint=altered_fingerprint,
                permit_reference=LiveExecutionPermitReference(permit.permit_id, permit.version),
                confirmation_verified=True,
                credentials_configured=True,
                runtime_config_path=env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
            )
            raise AssertionError(f"drift row unexpectedly consumed permit: {field}")
        except LiveExecutionPermitGateError as exc:
            denial_code = exc.code

        expected_denial = "PERMIT_SUBJECT_MISMATCH" if field in identity_coupled_fields else "PERMIT_FINGERPRINT_MISMATCH"
        assert denial_code == expected_denial
        stored, audits = _permit_and_audits(env, permit.permit_id)
        assert stored is not None
        assert stored.state == LiveExecutionPermitState.ISSUED.value
        assert stored.version == 1
        assert stored.consumed_at is None
        assert stored.consumption_correlation_id is None
        assert stored.request_fingerprint == baseline_fingerprint.request_fingerprint
        consumed_audits = [audit for audit in audits if audit.action == "PERMIT_CONSUMED"]
        denied_audits = [audit for audit in audits if audit.action == "PERMIT_DENIED"]
        assert consumed_audits == []
        assert denied_audits == []
        assert len([audit for audit in audits if audit.action == "PERMIT_ISSUED"]) == 1
        row_results.append(
            {
                "field": field,
                "baseline": baseline.fingerprint_context[field],
                "altered": altered_value,
                "digest": altered_fingerprint.request_fingerprint,
                "denial": denial_code,
            }
        )

    assert {row["field"] for row in row_results} == EXPECTED_DRIFT_FIELDS
    assert signing_count == 0
    assert post_count == 0
    assert delete_count == 0
    assert retry_count == 0
    assert {
        "operation": baseline.operation,
        "environment": baseline.environment,
        "symbol": baseline.symbol,
        "subject_type": baseline.subject_type,
        "subject_id": baseline.subject_id,
        "fingerprint_context": dict(baseline.fingerprint_context),
        "transport_business_parameters": dict(baseline.transport_business_parameters),
    } == baseline_snapshot
    for forbidden in ("timestamp", "recvWindow", "signature", "apiKey", "headers", "credentials", "permit_id"):
        assert forbidden not in baseline.fingerprint_context
        assert forbidden not in baseline.transport_business_parameters

    positive_env = durable_state_env("RELEASED")
    positive_permit = _issue(positive_env, baseline_fingerprint)
    positive_gate = LiveExecutionPermitGate(
        env=positive_env,
        correlation_id_provider=lambda: UUID("11111111-1111-4111-8111-111111111199"),
    )
    receipt = positive_gate.authorize_and_consume(
        operation=LiveExecutionOperation.PROTECTIVE_CREATE,
        fingerprint=baseline_fingerprint,
        permit_reference=LiveExecutionPermitReference(positive_permit.permit_id, positive_permit.version),
        confirmation_verified=True,
        credentials_configured=True,
        runtime_config_path=positive_env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
    )
    assert receipt.permit_id == positive_permit.permit_id
    assert receipt.previous_version == 1
    assert receipt.consumed_version == 2
    assert receipt.request_fingerprint == baseline_fingerprint.request_fingerprint
    stored_positive, positive_audits = _permit_and_audits(positive_env, positive_permit.permit_id)
    assert stored_positive is not None
    assert stored_positive.state == LiveExecutionPermitState.CONSUMED.value
    assert stored_positive.version == 2
    assert stored_positive.consumed_at is not None
    assert stored_positive.consumption_correlation_id is not None
    assert stored_positive.request_fingerprint == baseline_fingerprint.request_fingerprint
    assert len([audit for audit in positive_audits if audit.action == "PERMIT_CONSUMED"]) == 1
    assert signing_count == 0
    assert post_count == 0
    assert delete_count == 0
    assert retry_count == 0

EXPECTED_CANCEL_DRIFT_FIELDS = {
    "pair_id",
    "leg_type",
    "client_algo_id",
}


def _baseline_cancel_request() -> LiveExecutionUnsignedMutationRequest:
    config = BinanceFuturesTestnetProtectiveOrdersConfig()
    client = BinanceFuturesTestnetProtectiveOrdersClient(config, http_get=lambda *args, **kwargs: None, env={})
    preview = BinanceFuturesTestnetProtectivePreview(
        pair_id="pair-cancel-drift-001",
        symbol="BTCUSDT",
        position_direction="LONG",
        position_amount="0.002",
        entry_price="50000",
        mark_price="50000",
        protective_side="SELL",
        stop_client_algo_id="smcbot-protect-sl-cancel-drift-001",
        take_profit_client_algo_id="smcbot-protect-tp-cancel-drift-001",
        stop_trigger="49000.1",
        take_profit_trigger="51000.1",
        transmission_ready=True,
    )
    return client.build_cancel_unsigned_business_request(preview, "STOP")


def _cancel_variant_request(
    baseline: LiveExecutionUnsignedMutationRequest,
    field: str,
    value: Any,
) -> LiveExecutionUnsignedMutationRequest:
    fingerprint_context = dict(baseline.fingerprint_context)
    transport = dict(baseline.transport_business_parameters)
    fingerprint_context[field] = value
    if field == "pair_id":
        subject_id = value
    elif field == "leg_type":
        subject_id = baseline.subject_id
    elif field == "client_algo_id":
        subject_id = baseline.subject_id
        transport["clientAlgoId"] = value
    else:
        raise AssertionError(f"unexpected cancel drift field: {field}")
    return LiveExecutionUnsignedMutationRequest(
        operation=baseline.operation,
        environment=baseline.environment,
        symbol=baseline.symbol,
        subject_type=baseline.subject_type,
        subject_id=subject_id,
        fingerprint_context=fingerprint_context,
        transport_business_parameters=transport,
    )


def test_protective_cancel_field_drift_matrix_denies_without_consuming_or_transport() -> None:
    baseline = _baseline_cancel_request()
    baseline_snapshot = {
        "operation": baseline.operation,
        "environment": baseline.environment,
        "symbol": baseline.symbol,
        "subject_type": baseline.subject_type,
        "subject_id": baseline.subject_id,
        "fingerprint_context": dict(baseline.fingerprint_context),
        "transport_business_parameters": dict(baseline.transport_business_parameters),
    }
    baseline_fingerprint = build_protective_cancel_from_final_request(baseline)
    assert baseline.operation == LiveExecutionOperation.PROTECTIVE_CANCEL
    assert baseline.environment == "TESTNET"
    assert baseline.symbol == "BTCUSDT"
    assert baseline.subject_type == "PROTECTIVE_PAIR"
    assert baseline.subject_id == "pair-cancel-drift-001"
    assert baseline_fingerprint.subject_type == "PROTECTIVE_LEG"
    assert baseline_fingerprint.subject_id == "pair-cancel-drift-001:STOP:smcbot-protect-sl-cancel-drift-001"
    assert set(baseline.fingerprint_context) == {
        "schema_version",
        "operation",
        "environment",
        "symbol",
        "pair_id",
        "leg_type",
        "client_algo_id",
    }
    assert baseline_fingerprint.canonical_payload["client_algo_id"] == baseline.transport_business_parameters["clientAlgoId"]
    assert baseline.symbol == baseline.transport_business_parameters["symbol"] == "BTCUSDT"
    assert baseline.transport_business_parameters == {
        "symbol": "BTCUSDT",
        "clientAlgoId": "smcbot-protect-sl-cancel-drift-001",
    }
    assert set(baseline.transport_business_parameters) == {"symbol", "clientAlgoId"}
    assert "pair_id" not in baseline.transport_business_parameters
    assert "leg" not in baseline.transport_business_parameters
    assert "cancelAll" not in baseline.transport_business_parameters
    assert baseline_fingerprint.request_fingerprint

    cases = [
        ("pair_id", "pair-cancel-drift-001", "pair-cancel-drift-002"),
        ("leg_type", "STOP", "TAKE_PROFIT"),
        (
            "client_algo_id",
            "smcbot-protect-sl-cancel-drift-001",
            "smcbot-protect-sl-cancel-drift-002",
        ),
    ]
    assert {field for field, _, _ in cases} == EXPECTED_CANCEL_DRIFT_FIELDS
    assert len(cases) == 3

    row_results: list[dict[str, object]] = []
    signing_count = 0
    post_count = 0
    delete_count = 0
    retry_count = 0
    timestamp_signing_count = 0
    auth_augmentation_count = 0
    transport_callback_count = 0

    for index, (field, baseline_value, altered_value) in enumerate(cases, start=1):
        assert baseline.fingerprint_context[field] == baseline_value
        env = durable_state_env("RELEASED")
        permit = _issue(env, baseline_fingerprint)
        altered = _cancel_variant_request(baseline, field, altered_value)
        altered_fingerprint = build_protective_cancel_from_final_request(altered)
        assert altered_fingerprint.canonical_payload != baseline_fingerprint.canonical_payload
        assert altered_fingerprint.request_fingerprint != baseline_fingerprint.request_fingerprint
        assert permit.request_fingerprint == baseline_fingerprint.request_fingerprint
        assert permit.state == LiveExecutionPermitState.ISSUED
        assert permit.version == 1

        gate = LiveExecutionPermitGate(
            env=env,
            correlation_id_provider=lambda i=index: UUID(f"11111111-1111-4111-8111-{240 + i:012d}"),
        )
        try:
            gate.authorize_and_consume(
                operation=LiveExecutionOperation.PROTECTIVE_CANCEL,
                fingerprint=altered_fingerprint,
                permit_reference=LiveExecutionPermitReference(permit.permit_id, permit.version),
                confirmation_verified=True,
                credentials_configured=True,
                runtime_config_path=env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
            )
            raise AssertionError(f"cancel drift row unexpectedly consumed permit: {field}")
        except LiveExecutionPermitGateError as exc:
            denial_code = exc.code
            assert denial_code in {"PERMIT_SUBJECT_MISMATCH", "PERMIT_FINGERPRINT_MISMATCH"}
            response_text = str(exc)
            for forbidden in (
                "SELECT",
                "Traceback",
                "http://",
                "https://",
                "canonical_payload",
                "signature",
                "X-MBX-APIKEY",
                "headers",
            ):
                assert forbidden not in response_text

        stored, audits = _permit_and_audits(env, permit.permit_id)
        assert stored is not None
        assert stored.state == LiveExecutionPermitState.ISSUED.value
        assert stored.version == 1
        assert stored.consumed_at is None
        assert stored.consumption_correlation_id is None
        assert stored.request_fingerprint == baseline_fingerprint.request_fingerprint
        consumed_audits = [audit for audit in audits if audit.action == "PERMIT_CONSUMED"]
        denied_audits = [audit for audit in audits if audit.action == "PERMIT_DENIED"]
        assert consumed_audits == []
        assert denied_audits == []
        assert len([audit for audit in audits if audit.action == "PERMIT_ISSUED"]) == 1
        for audit in audits:
            assert "canonical_payload" not in str(audit.metadata_json)
            assert "signature" not in str(audit.metadata_json)
            assert "X-MBX-APIKEY" not in str(audit.metadata_json)
        row_results.append(
            {
                "field": field,
                "baseline": baseline_value,
                "altered": altered_value,
                "digest": altered_fingerprint.request_fingerprint,
                "denial": denial_code,
            }
        )

    assert {row["field"] for row in row_results} == EXPECTED_CANCEL_DRIFT_FIELDS
    assert signing_count == 0
    assert post_count == 0
    assert delete_count == 0
    assert retry_count == 0
    assert timestamp_signing_count == 0
    assert auth_augmentation_count == 0
    assert transport_callback_count == 0
    assert {
        "operation": baseline.operation,
        "environment": baseline.environment,
        "symbol": baseline.symbol,
        "subject_type": baseline.subject_type,
        "subject_id": baseline.subject_id,
        "fingerprint_context": dict(baseline.fingerprint_context),
        "transport_business_parameters": dict(baseline.transport_business_parameters),
    } == baseline_snapshot
    for forbidden in (
        "timestamp",
        "recvWindow",
        "signature",
        "apiKey",
        "headers",
        "credentials",
        "permit_id",
        "correlation_id",
    ):
        assert forbidden not in baseline.fingerprint_context
        assert forbidden not in baseline.transport_business_parameters

    positive_env = durable_state_env("RELEASED")
    positive_permit = _issue(positive_env, baseline_fingerprint)
    positive_gate = LiveExecutionPermitGate(
        env=positive_env,
        correlation_id_provider=lambda: UUID("11111111-1111-4111-8111-111111111299"),
    )
    receipt = positive_gate.authorize_and_consume(
        operation=LiveExecutionOperation.PROTECTIVE_CANCEL,
        fingerprint=baseline_fingerprint,
        permit_reference=LiveExecutionPermitReference(positive_permit.permit_id, positive_permit.version),
        confirmation_verified=True,
        credentials_configured=True,
        runtime_config_path=positive_env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
    )
    assert receipt.permit_id == positive_permit.permit_id
    assert receipt.previous_version == 1
    assert receipt.consumed_version == 2
    assert receipt.request_fingerprint == baseline_fingerprint.request_fingerprint
    stored_positive, positive_audits = _permit_and_audits(positive_env, positive_permit.permit_id)
    assert stored_positive is not None
    assert stored_positive.state == LiveExecutionPermitState.CONSUMED.value
    assert stored_positive.version == 2
    assert stored_positive.consumed_at is not None
    assert stored_positive.consumption_correlation_id is not None
    assert stored_positive.request_fingerprint == baseline_fingerprint.request_fingerprint
    assert len([audit for audit in positive_audits if audit.action == "PERMIT_CONSUMED"]) == 1
    assert signing_count == 0
    assert post_count == 0
    assert delete_count == 0
    assert retry_count == 0
    assert timestamp_signing_count == 0
    assert auth_augmentation_count == 0
    assert transport_callback_count == 0


EXPECTED_LIFECYCLE_CREATE_DRIFT_FIELDS = {
    "client_order_id",
    "side",
    "position_side",
    "order_type",
    "quantity",
    "price",
    "time_in_force",
    "reduce_only",
}


def _baseline_lifecycle_create_request() -> LiveExecutionUnsignedMutationRequest:
    config = BinanceFuturesTestnetOrderLifecycleConfig()
    client = BinanceFuturesTestnetOrderLifecycleClient(config, http_get=lambda *args, **kwargs: None, env={})
    preview = BinanceFuturesTestnetLifecyclePreview(
        lifecycle_id="lifecycle-create-drift-001",
        client_order_id="smcbot-lifecycle-create-drift-001",
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        time_in_force="GTX",
        quantity=Decimal("0.002"),
        price_offset_bps=1000,
        best_bid=Decimal("50000"),
        best_ask=Decimal("50001"),
        derived_price=Decimal("49000"),
        estimated_notional=Decimal("98"),
        exchange_filters_valid=True,
        non_marketable_price_valid=True,
        post_only_valid=True,
        local_rules_valid=True,
        transmission_ready=True,
    )
    return client.build_create_unsigned_business_request(preview)


def _lifecycle_create_variant_request(
    baseline: LiveExecutionUnsignedMutationRequest,
    field: str,
    value: Any,
) -> LiveExecutionUnsignedMutationRequest:
    fingerprint_context = dict(baseline.fingerprint_context)
    transport = dict(baseline.transport_business_parameters)
    fingerprint_context[field] = value
    subject_id = baseline.subject_id
    if field == "client_order_id":
        subject_id = str(value)
        transport["newClientOrderId"] = value
    elif field == "side":
        transport["side"] = value
    elif field == "position_side":
        transport["positionSide"] = value
    elif field == "order_type":
        transport["type"] = value
    elif field == "quantity":
        transport["quantity"] = value
    elif field == "price":
        transport["price"] = value
    elif field == "time_in_force":
        transport["timeInForce"] = value
    elif field == "reduce_only":
        transport["reduceOnly"] = "true" if value is True else "false"
    else:
        raise AssertionError(f"unexpected lifecycle create drift field: {field}")
    return LiveExecutionUnsignedMutationRequest(
        operation=baseline.operation,
        environment=baseline.environment,
        symbol=baseline.symbol,
        subject_type=baseline.subject_type,
        subject_id=subject_id,
        fingerprint_context=fingerprint_context,
        transport_business_parameters=transport,
    )


def test_lifecycle_create_field_drift_matrix_denies_without_consuming_or_transport() -> None:
    baseline = _baseline_lifecycle_create_request()
    baseline_snapshot = {
        "operation": baseline.operation,
        "environment": baseline.environment,
        "symbol": baseline.symbol,
        "subject_type": baseline.subject_type,
        "subject_id": baseline.subject_id,
        "fingerprint_context": dict(baseline.fingerprint_context),
        "transport_business_parameters": dict(baseline.transport_business_parameters),
    }
    baseline_fingerprint = build_lifecycle_create_from_final_request(baseline)
    assert baseline.operation == LiveExecutionOperation.ORDER_LIFECYCLE_CREATE
    assert baseline.environment == "TESTNET"
    assert baseline.symbol == "BTCUSDT"
    assert baseline.subject_type == "ORDER_LIFECYCLE"
    assert baseline.subject_id == "smcbot-lifecycle-create-drift-001"
    assert baseline_fingerprint.subject_type == "CLIENT_ORDER"
    assert baseline_fingerprint.subject_id == "smcbot-lifecycle-create-drift-001"
    assert set(baseline.fingerprint_context) == {
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
    assert baseline.fingerprint_context == {
        "schema_version": "1.0",
        "operation": "ORDER_LIFECYCLE_CREATE",
        "environment": "TESTNET",
        "symbol": "BTCUSDT",
        "client_order_id": "smcbot-lifecycle-create-drift-001",
        "side": "BUY",
        "position_side": "BOTH",
        "order_type": "LIMIT",
        "quantity": "0.002",
        "price": "49000",
        "time_in_force": "GTX",
        "reduce_only": False,
    }
    assert baseline.transport_business_parameters == {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "timeInForce": "GTX",
        "quantity": "0.002",
        "price": "49000",
        "newClientOrderId": "smcbot-lifecycle-create-drift-001",
        "newOrderRespType": "ACK",
        "positionSide": "BOTH",
    }
    assert baseline_fingerprint.canonical_payload["client_order_id"] == baseline.transport_business_parameters["newClientOrderId"]
    assert baseline_fingerprint.canonical_payload["quantity"] == baseline.transport_business_parameters["quantity"] == "0.002"
    assert baseline_fingerprint.canonical_payload["price"] == baseline.transport_business_parameters["price"] == "49000"
    assert baseline_fingerprint.canonical_payload["time_in_force"] == baseline.transport_business_parameters["timeInForce"] == "GTX"
    assert baseline_fingerprint.canonical_payload["reduce_only"] is False
    assert "reduceOnly" not in baseline.transport_business_parameters
    assert baseline.transport_business_parameters["newOrderRespType"] == "ACK"
    assert baseline_fingerprint.request_fingerprint

    cases = [
        ("client_order_id", "smcbot-lifecycle-create-drift-001", "smcbot-lifecycle-create-drift-002", "subject/newClientOrderId"),
        ("side", "BUY", "SELL", "side"),
        ("position_side", "BOTH", "LONG", "positionSide"),
        ("order_type", "LIMIT", "MARKET", "type; pre-gate invalid because lifecycle create fingerprint supports LIMIT only"),
        ("quantity", "0.002", "0.003", "quantity"),
        ("price", "49000", "49100", "price"),
        ("time_in_force", "GTX", "IOC", "timeInForce; pre-gate invalid because lifecycle create fingerprint supports GTX/GTC only"),
        ("reduce_only", False, True, "reduceOnly=true"),
    ]
    assert {field for field, _, _, _ in cases} == EXPECTED_LIFECYCLE_CREATE_DRIFT_FIELDS
    assert len(cases) == 8

    row_results: list[dict[str, object]] = []
    signing_count = 0
    post_count = 0
    delete_count = 0
    retry_count = 0
    timestamp_signing_count = 0
    auth_augmentation_count = 0
    transport_callback_count = 0
    gate_invocation_count = 0

    for index, (field, baseline_value, altered_value, coupling) in enumerate(cases, start=1):
        assert baseline.fingerprint_context[field] == baseline_value
        env = durable_state_env("RELEASED")
        permit = _issue(env, baseline_fingerprint)
        assert permit.request_fingerprint == baseline_fingerprint.request_fingerprint
        assert permit.state == LiveExecutionPermitState.ISSUED
        assert permit.version == 1

        denial_code: str
        altered_digest: str | None = None
        try:
            altered = _lifecycle_create_variant_request(baseline, field, altered_value)
            if field == "reduce_only":
                assert altered.fingerprint_context["reduce_only"] is True
                assert altered.transport_business_parameters["reduceOnly"] == "true"
                invalid_omitted_transport = dict(baseline.transport_business_parameters)
                invalid_omitted_fingerprint = {**dict(baseline.fingerprint_context), "reduce_only": True}
                try:
                    LiveExecutionUnsignedMutationRequest(
                        operation=baseline.operation,
                        environment=baseline.environment,
                        symbol=baseline.symbol,
                        subject_type=baseline.subject_type,
                        subject_id=baseline.subject_id,
                        fingerprint_context=invalid_omitted_fingerprint,
                        transport_business_parameters=invalid_omitted_transport,
                    )
                    raise AssertionError("reduce_only=True without reduceOnly transport unexpectedly validated")
                except ValueError as exc:
                    assert str(exc) == "PERMIT_REQUEST_INVALID"
            altered_fingerprint = build_lifecycle_create_from_final_request(altered)
            altered_digest = altered_fingerprint.request_fingerprint
            assert altered_fingerprint.canonical_payload != baseline_fingerprint.canonical_payload
            assert altered_fingerprint.request_fingerprint != baseline_fingerprint.request_fingerprint
            gate = LiveExecutionPermitGate(
                env=env,
                correlation_id_provider=lambda i=index: UUID(f"11111111-1111-4111-8111-{440 + i:012d}"),
            )
            gate_invocation_count += 1
            try:
                gate.authorize_and_consume(
                    operation=LiveExecutionOperation.ORDER_LIFECYCLE_CREATE,
                    fingerprint=altered_fingerprint,
                    permit_reference=LiveExecutionPermitReference(permit.permit_id, permit.version),
                    confirmation_verified=True,
                    credentials_configured=True,
                    runtime_config_path=env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
                )
                raise AssertionError(f"lifecycle create drift row unexpectedly consumed permit: {field}")
            except LiveExecutionPermitGateError as exc:
                denial_code = exc.code
                expected = "PERMIT_SUBJECT_MISMATCH" if field == "client_order_id" else "PERMIT_FINGERPRINT_MISMATCH"
                assert denial_code == expected
                response_text = str(exc)
        except ValueError as exc:
            denial_code = str(exc)
            assert field in {"order_type", "time_in_force"}
            assert denial_code in {"PERMIT_REQUEST_INVALID", "PERMIT_INVALID"}
            response_text = denial_code

        for forbidden in (
            "SELECT",
            "Traceback",
            "http://",
            "https://",
            "canonical_payload",
            "signature",
            "X-MBX-APIKEY",
            "headers",
        ):
            assert forbidden not in response_text
        stored, audits = _permit_and_audits(env, permit.permit_id)
        assert stored is not None
        assert stored.state == LiveExecutionPermitState.ISSUED.value
        assert stored.version == 1
        assert stored.consumed_at is None
        assert stored.consumption_correlation_id is None
        assert stored.request_fingerprint == baseline_fingerprint.request_fingerprint
        consumed_audits = [audit for audit in audits if audit.action == "PERMIT_CONSUMED"]
        denied_audits = [audit for audit in audits if audit.action == "PERMIT_DENIED"]
        assert consumed_audits == []
        assert denied_audits == []
        assert len([audit for audit in audits if audit.action == "PERMIT_ISSUED"]) == 1
        for audit in audits:
            audit_text = str(audit.metadata_json)
            for forbidden in (
                "canonical_payload",
                "request_body",
                "signature",
                "credential",
                "apiKey",
                "X-MBX-APIKEY",
                "headers",
                "SELECT",
                "Traceback",
            ):
                assert forbidden not in audit_text
        row_results.append(
            {
                "field": field,
                "baseline": baseline_value,
                "altered": altered_value,
                "coupling": coupling,
                "digest": altered_digest,
                "denial": denial_code,
            }
        )

    assert {row["field"] for row in row_results} == EXPECTED_LIFECYCLE_CREATE_DRIFT_FIELDS
    assert gate_invocation_count == 6
    assert signing_count == 0
    assert post_count == 0
    assert delete_count == 0
    assert retry_count == 0
    assert timestamp_signing_count == 0
    assert auth_augmentation_count == 0
    assert transport_callback_count == 0
    assert {
        "operation": baseline.operation,
        "environment": baseline.environment,
        "symbol": baseline.symbol,
        "subject_type": baseline.subject_type,
        "subject_id": baseline.subject_id,
        "fingerprint_context": dict(baseline.fingerprint_context),
        "transport_business_parameters": dict(baseline.transport_business_parameters),
    } == baseline_snapshot
    for forbidden in (
        "timestamp",
        "recvWindow",
        "signature",
        "apiKey",
        "headers",
        "credentials",
        "permit_id",
        "correlation_id",
        "exchange_response",
    ):
        assert forbidden not in baseline.fingerprint_context
        assert forbidden not in baseline.transport_business_parameters

    positive_env = durable_state_env("RELEASED")
    positive_permit = _issue(positive_env, baseline_fingerprint)
    positive_gate = LiveExecutionPermitGate(
        env=positive_env,
        correlation_id_provider=lambda: UUID("11111111-1111-4111-8111-111111111499"),
    )
    receipt = positive_gate.authorize_and_consume(
        operation=LiveExecutionOperation.ORDER_LIFECYCLE_CREATE,
        fingerprint=baseline_fingerprint,
        permit_reference=LiveExecutionPermitReference(positive_permit.permit_id, positive_permit.version),
        confirmation_verified=True,
        credentials_configured=True,
        runtime_config_path=positive_env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
    )
    assert receipt.permit_id == positive_permit.permit_id
    assert receipt.previous_version == 1
    assert receipt.consumed_version == 2
    assert receipt.request_fingerprint == baseline_fingerprint.request_fingerprint
    stored_positive, positive_audits = _permit_and_audits(positive_env, positive_permit.permit_id)
    assert stored_positive is not None
    assert stored_positive.state == LiveExecutionPermitState.CONSUMED.value
    assert stored_positive.version == 2
    assert stored_positive.consumed_at is not None
    assert stored_positive.consumption_correlation_id is not None
    assert stored_positive.request_fingerprint == baseline_fingerprint.request_fingerprint
    assert len([audit for audit in positive_audits if audit.action == "PERMIT_CONSUMED"]) == 1
    assert signing_count == 0
    assert post_count == 0
    assert delete_count == 0
    assert retry_count == 0
    assert timestamp_signing_count == 0
    assert auth_augmentation_count == 0
    assert transport_callback_count == 0



EXPECTED_LIFECYCLE_CANCEL_DRIFT_FIELDS = {
    "client_order_id",
}


def _baseline_lifecycle_cancel_request() -> LiveExecutionUnsignedMutationRequest:
    config = BinanceFuturesTestnetOrderLifecycleConfig()
    client = BinanceFuturesTestnetOrderLifecycleClient(config, http_get=lambda *args, **kwargs: None, env={})
    return client.build_cancel_unsigned_business_request("smcbot-lifecycle-cancel-drift-001")


def _lifecycle_cancel_variant_request(
    baseline: LiveExecutionUnsignedMutationRequest,
    client_order_id: str,
) -> LiveExecutionUnsignedMutationRequest:
    return LiveExecutionUnsignedMutationRequest(
        operation=baseline.operation,
        environment=baseline.environment,
        symbol=baseline.symbol,
        subject_type=baseline.subject_type,
        subject_id=client_order_id,
        fingerprint_context={**dict(baseline.fingerprint_context), "client_order_id": client_order_id},
        transport_business_parameters={
            **dict(baseline.transport_business_parameters),
            "origClientOrderId": client_order_id,
        },
    )


def test_lifecycle_cancel_field_drift_matrix_denies_without_consuming_or_transport() -> None:
    baseline = _baseline_lifecycle_cancel_request()
    baseline_snapshot = {
        "operation": baseline.operation,
        "environment": baseline.environment,
        "symbol": baseline.symbol,
        "subject_type": baseline.subject_type,
        "subject_id": baseline.subject_id,
        "fingerprint_context": dict(baseline.fingerprint_context),
        "transport_business_parameters": dict(baseline.transport_business_parameters),
    }
    baseline_fingerprint = build_lifecycle_cancel_from_final_request(baseline)
    assert baseline.operation == LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL
    assert baseline.environment == "TESTNET"
    assert baseline.symbol == "BTCUSDT"
    assert baseline.subject_type == "ORDER_LIFECYCLE"
    assert baseline.subject_id == "smcbot-lifecycle-cancel-drift-001"
    assert baseline_fingerprint.subject_type == "CLIENT_ORDER"
    assert baseline_fingerprint.subject_id == "smcbot-lifecycle-cancel-drift-001"
    assert set(baseline.fingerprint_context) == {
        "schema_version",
        "operation",
        "environment",
        "symbol",
        "client_order_id",
    }
    assert baseline.transport_business_parameters == {
        "symbol": "BTCUSDT",
        "origClientOrderId": "smcbot-lifecycle-cancel-drift-001",
    }
    assert set(baseline.transport_business_parameters) == {"symbol", "origClientOrderId"}
    assert baseline_fingerprint.canonical_payload["client_order_id"] == baseline.transport_business_parameters["origClientOrderId"]
    assert baseline_fingerprint.canonical_payload["client_order_id"] == "smcbot-lifecycle-cancel-drift-001"
    for forbidden in (
        "timestamp",
        "recvWindow",
        "signature",
        "apiKey",
        "headers",
        "credentials",
        "orderId",
        "journal",
        "recovery",
        "cancelAll",
    ):
        assert forbidden not in baseline.fingerprint_context
        assert forbidden not in baseline.transport_business_parameters
    assert baseline_fingerprint.request_fingerprint

    cases = [
        (
            "client_order_id",
            "smcbot-lifecycle-cancel-drift-001",
            "smcbot-lifecycle-cancel-drift-002",
            "subject/origClientOrderId",
        ),
    ]
    assert {field for field, _, _, _ in cases} == EXPECTED_LIFECYCLE_CANCEL_DRIFT_FIELDS
    assert len(cases) == 1

    signing_count = 0
    post_count = 0
    delete_count = 0
    retry_count = 0
    timestamp_signing_count = 0
    auth_augmentation_count = 0
    transport_callback_count = 0
    row_results: list[dict[str, object]] = []

    for index, (field, baseline_value, altered_value, coupling) in enumerate(cases, start=1):
        assert baseline.fingerprint_context[field] == baseline_value
        env = durable_state_env("RELEASED")
        permit = _issue(env, baseline_fingerprint)
        altered = _lifecycle_cancel_variant_request(baseline, altered_value)
        altered_fingerprint = build_lifecycle_cancel_from_final_request(altered)
        assert altered.fingerprint_context["client_order_id"] == altered.transport_business_parameters["origClientOrderId"]
        assert altered.fingerprint_context["client_order_id"] == altered_value
        assert altered_fingerprint.canonical_payload != baseline_fingerprint.canonical_payload
        assert altered_fingerprint.request_fingerprint != baseline_fingerprint.request_fingerprint
        assert baseline.fingerprint_context["client_order_id"] == baseline_value
        assert permit.request_fingerprint == baseline_fingerprint.request_fingerprint
        assert permit.state == LiveExecutionPermitState.ISSUED
        assert permit.version == 1

        gate = LiveExecutionPermitGate(
            env=env,
            correlation_id_provider=lambda i=index: UUID(f"11111111-1111-4111-8111-{640 + i:012d}"),
        )
        try:
            gate.authorize_and_consume(
                operation=LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL,
                fingerprint=altered_fingerprint,
                permit_reference=LiveExecutionPermitReference(permit.permit_id, permit.version),
                confirmation_verified=True,
                credentials_configured=True,
                runtime_config_path=env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
            )
            raise AssertionError("lifecycle cancel drift row unexpectedly consumed permit")
        except LiveExecutionPermitGateError as exc:
            denial_code = exc.code
            assert denial_code in {"PERMIT_SUBJECT_MISMATCH", "PERMIT_FINGERPRINT_MISMATCH"}
            response_text = str(exc)

        for forbidden in (
            "SELECT",
            "Traceback",
            "http://",
            "https://",
            "canonical_payload",
            "request_parameters",
            "signature",
            "X-MBX-APIKEY",
            "headers",
            "credential",
        ):
            assert forbidden not in response_text
        stored, audits = _permit_and_audits(env, permit.permit_id)
        assert stored is not None
        assert stored.state == LiveExecutionPermitState.ISSUED.value
        assert stored.version == 1
        assert stored.consumed_at is None
        assert stored.consumption_correlation_id is None
        assert stored.request_fingerprint == baseline_fingerprint.request_fingerprint
        consumed_audits = [audit for audit in audits if audit.action == "PERMIT_CONSUMED"]
        denied_audits = [audit for audit in audits if audit.action == "PERMIT_DENIED"]
        assert consumed_audits == []
        assert denied_audits == []
        assert len([audit for audit in audits if audit.action == "PERMIT_ISSUED"]) == 1
        for audit in audits:
            audit_text = str(audit.metadata_json)
            for forbidden in (
                "canonical_payload",
                "request_parameters",
                "signature",
                "apiKey",
                "credential",
                "headers",
                "SELECT",
                "Traceback",
            ):
                assert forbidden not in audit_text
        row_results.append(
            {
                "field": field,
                "baseline": baseline_value,
                "altered": altered_value,
                "coupling": coupling,
                "digest": altered_fingerprint.request_fingerprint,
                "denial": denial_code,
            }
        )

    assert {row["field"] for row in row_results} == EXPECTED_LIFECYCLE_CANCEL_DRIFT_FIELDS
    assert signing_count == 0
    assert post_count == 0
    assert delete_count == 0
    assert retry_count == 0
    assert timestamp_signing_count == 0
    assert auth_augmentation_count == 0
    assert transport_callback_count == 0
    assert {
        "operation": baseline.operation,
        "environment": baseline.environment,
        "symbol": baseline.symbol,
        "subject_type": baseline.subject_type,
        "subject_id": baseline.subject_id,
        "fingerprint_context": dict(baseline.fingerprint_context),
        "transport_business_parameters": dict(baseline.transport_business_parameters),
    } == baseline_snapshot
    for forbidden in (
        "timestamp",
        "recvWindow",
        "signature",
        "apiKey",
        "headers",
        "credentials",
        "permit_id",
        "correlation_id",
        "exchange_response",
        "journal",
    ):
        assert forbidden not in baseline.fingerprint_context
        assert forbidden not in baseline.transport_business_parameters

    positive_env = durable_state_env("RELEASED")
    positive_permit = _issue(positive_env, baseline_fingerprint)
    positive_gate = LiveExecutionPermitGate(
        env=positive_env,
        correlation_id_provider=lambda: UUID("11111111-1111-4111-8111-111111111699"),
    )
    receipt = positive_gate.authorize_and_consume(
        operation=LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL,
        fingerprint=baseline_fingerprint,
        permit_reference=LiveExecutionPermitReference(positive_permit.permit_id, positive_permit.version),
        confirmation_verified=True,
        credentials_configured=True,
        runtime_config_path=positive_env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
    )
    assert receipt.permit_id == positive_permit.permit_id
    assert receipt.previous_version == 1
    assert receipt.consumed_version == 2
    assert receipt.request_fingerprint == baseline_fingerprint.request_fingerprint
    stored_positive, positive_audits = _permit_and_audits(positive_env, positive_permit.permit_id)
    assert stored_positive is not None
    assert stored_positive.state == LiveExecutionPermitState.CONSUMED.value
    assert stored_positive.version == 2
    assert stored_positive.consumed_at is not None
    assert stored_positive.consumption_correlation_id is not None
    assert stored_positive.request_fingerprint == baseline_fingerprint.request_fingerprint
    assert len([audit for audit in positive_audits if audit.action == "PERMIT_CONSUMED"]) == 1
    assert signing_count == 0
    assert post_count == 0
    assert delete_count == 0
    assert retry_count == 0
    assert timestamp_signing_count == 0
    assert auth_augmentation_count == 0
    assert transport_callback_count == 0

EXPECTED_ORDER_TEST_LIMIT_DRIFT_FIELDS = {
    "client_order_id",
    "side",
    "position_side",
    "order_type",
    "quantity",
    "price",
    "time_in_force",
    "reduce_only",
}


def _order_test_filters() -> BinanceFuturesTestnetExchangeFilterSummary:
    return BinanceFuturesTestnetExchangeFilterSummary(
        symbol="BTCUSDT",
        price_tick_size=Decimal("0.1"),
        min_price=Decimal("0.1"),
        max_price=Decimal("1000000"),
        lot_step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        max_qty=Decimal("100"),
        market_lot_step_size=Decimal("0.001"),
        market_min_qty=Decimal("0.001"),
        market_max_qty=Decimal("100"),
        min_notional=Decimal("5"),
    )


def _order_test_client() -> BinanceFuturesTestnetOrderTestClient:
    return BinanceFuturesTestnetOrderTestClient(
        BinanceFuturesTestnetOrderTestConfig(client_order_id_prefix="smcbot-order-test-"),
        http_get=lambda *args, **kwargs: None,
        env={},
    )


def _baseline_order_test_limit_request() -> LiveExecutionUnsignedMutationRequest:
    client = _order_test_client()
    preview = client.build_order_test_preview(
        "smcbot-order-test-limit-drift-001",
        "BUY",
        "LIMIT",
        Decimal("0.001"),
        Decimal("50000"),
        "GTC",
        False,
        exchange_filters=_order_test_filters(),
    )
    return client.build_unsigned_business_request(preview)


def _order_test_market_variant_request(baseline: LiveExecutionUnsignedMutationRequest) -> LiveExecutionUnsignedMutationRequest:
    client = _order_test_client()
    preview = client.build_order_test_preview(
        str(baseline.fingerprint_context["client_order_id"]),
        str(baseline.fingerprint_context["side"]),
        "MARKET",
        Decimal(str(baseline.fingerprint_context["quantity"])),
        price=None,
        time_in_force=None,
        reduce_only=bool(baseline.fingerprint_context["reduce_only"]),
        exchange_filters=_order_test_filters(),
        mark_price=Decimal("50000"),
    )
    return client.build_unsigned_business_request(preview)


def _order_test_limit_variant_request(
    baseline: LiveExecutionUnsignedMutationRequest,
    field: str,
    value: Any,
) -> LiveExecutionUnsignedMutationRequest:
    if field == "order_type":
        return _order_test_market_variant_request(baseline)
    fingerprint_context = dict(baseline.fingerprint_context)
    transport = dict(baseline.transport_business_parameters)
    fingerprint_context[field] = value
    subject_id = baseline.subject_id
    if field == "client_order_id":
        subject_id = str(value)
        transport["newClientOrderId"] = value
    elif field == "side":
        transport["side"] = value
    elif field == "position_side":
        transport["positionSide"] = value
    elif field == "quantity":
        transport["quantity"] = value
    elif field == "price":
        transport["price"] = value
    elif field == "time_in_force":
        transport["timeInForce"] = value
    elif field == "reduce_only":
        transport["reduceOnly"] = "true" if value is True else "false"
    else:
        raise AssertionError(f"unexpected order-test LIMIT drift field: {field}")
    return LiveExecutionUnsignedMutationRequest(
        operation=baseline.operation,
        environment=baseline.environment,
        symbol=baseline.symbol,
        subject_type=baseline.subject_type,
        subject_id=subject_id,
        fingerprint_context=fingerprint_context,
        transport_business_parameters=transport,
    )


def test_order_test_limit_field_drift_matrix_denies_without_consuming_or_transport() -> None:
    baseline = _baseline_order_test_limit_request()
    baseline_snapshot = {
        "operation": baseline.operation,
        "environment": baseline.environment,
        "symbol": baseline.symbol,
        "subject_type": baseline.subject_type,
        "subject_id": baseline.subject_id,
        "fingerprint_context": dict(baseline.fingerprint_context),
        "transport_business_parameters": dict(baseline.transport_business_parameters),
    }
    baseline_fingerprint = build_signed_order_test_create_from_final_request(baseline)
    assert baseline.operation == LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE
    assert baseline.environment == "TESTNET"
    assert baseline.symbol == "BTCUSDT"
    assert baseline.subject_type == "ORDER_TEST"
    assert baseline.subject_id == "smcbot-order-test-limit-drift-001"
    assert baseline_fingerprint.subject_type == "CLIENT_ORDER"
    assert baseline_fingerprint.subject_id == "smcbot-order-test-limit-drift-001"
    assert set(baseline.fingerprint_context) == {
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
    assert baseline.fingerprint_context == {
        "schema_version": "1.0",
        "operation": "SIGNED_ORDER_TEST_CREATE",
        "environment": "TESTNET",
        "symbol": "BTCUSDT",
        "client_order_id": "smcbot-order-test-limit-drift-001",
        "side": "BUY",
        "position_side": "BOTH",
        "order_type": "LIMIT",
        "quantity": "0.001",
        "price": "50000",
        "time_in_force": "GTC",
        "reduce_only": False,
    }
    assert baseline.transport_business_parameters == {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "quantity": "0.001",
        "price": "50000",
        "newClientOrderId": "smcbot-order-test-limit-drift-001",
        "timeInForce": "GTC",
        "positionSide": "BOTH",
    }
    assert baseline_fingerprint.canonical_payload["client_order_id"] == baseline.transport_business_parameters["newClientOrderId"]
    assert baseline_fingerprint.canonical_payload["quantity"] == baseline.transport_business_parameters["quantity"] == "0.001"
    assert baseline_fingerprint.canonical_payload["price"] == baseline.transport_business_parameters["price"] == "50000"
    assert baseline_fingerprint.canonical_payload["time_in_force"] == baseline.transport_business_parameters["timeInForce"] == "GTC"
    assert baseline_fingerprint.canonical_payload["position_side"] == baseline.transport_business_parameters["positionSide"] == "BOTH"
    assert baseline_fingerprint.canonical_payload["reduce_only"] is False
    assert "reduceOnly" not in baseline.transport_business_parameters
    for forbidden in (
        "mark_price",
        "timestamp",
        "recvWindow",
        "signature",
        "apiKey",
        "headers",
        "credentials",
        "permit_id",
        "correlation_id",
    ):
        assert forbidden not in baseline.fingerprint_context
        assert forbidden not in baseline.transport_business_parameters
    assert baseline_fingerprint.request_fingerprint

    cases = [
        ("client_order_id", "smcbot-order-test-limit-drift-001", "smcbot-order-test-limit-drift-002", "subject/newClientOrderId"),
        ("side", "BUY", "SELL", "side"),
        ("position_side", "BOTH", "LONG", "positionSide"),
        ("order_type", "LIMIT", "MARKET", "price/time_in_force null and transport price/timeInForce omitted"),
        ("quantity", "0.001", "0.002", "quantity"),
        ("price", "50000", "50001", "price"),
        ("time_in_force", "GTC", "IOC", "timeInForce; pre-gate invalid because fingerprint supports GTC/GTX only"),
        ("reduce_only", False, True, "reduceOnly=true"),
    ]
    assert {field for field, _, _, _ in cases} == EXPECTED_ORDER_TEST_LIMIT_DRIFT_FIELDS
    assert len(cases) == 8

    signing_count = 0
    post_count = 0
    delete_count = 0
    retry_count = 0
    server_time_for_signing_count = 0
    timestamp_augmentation_count = 0
    auth_augmentation_count = 0
    transport_callback_count = 0
    gate_invocation_count = 0
    row_results: list[dict[str, object]] = []

    for index, (field, baseline_value, altered_value, coupling) in enumerate(cases, start=1):
        assert baseline.fingerprint_context[field] == baseline_value
        env = durable_state_env("RELEASED")
        permit = _issue(env, baseline_fingerprint)
        assert permit.request_fingerprint == baseline_fingerprint.request_fingerprint
        assert permit.state == LiveExecutionPermitState.ISSUED
        assert permit.version == 1

        altered_digest: str | None = None
        try:
            altered = _order_test_limit_variant_request(baseline, field, altered_value)
            if field == "order_type":
                assert altered.fingerprint_context["order_type"] == "MARKET"
                assert altered.fingerprint_context["price"] is None
                assert altered.fingerprint_context["time_in_force"] is None
                assert "price" not in altered.transport_business_parameters
                assert "timeInForce" not in altered.transport_business_parameters
            if field == "reduce_only":
                assert altered.fingerprint_context["reduce_only"] is True
                assert altered.transport_business_parameters["reduceOnly"] == "true"
                invalid_omitted_transport = dict(baseline.transport_business_parameters)
                invalid_omitted_fingerprint = {**dict(baseline.fingerprint_context), "reduce_only": True}
                try:
                    LiveExecutionUnsignedMutationRequest(
                        operation=baseline.operation,
                        environment=baseline.environment,
                        symbol=baseline.symbol,
                        subject_type=baseline.subject_type,
                        subject_id=baseline.subject_id,
                        fingerprint_context=invalid_omitted_fingerprint,
                        transport_business_parameters=invalid_omitted_transport,
                    )
                    raise AssertionError("reduce_only=True without reduceOnly transport unexpectedly validated")
                except ValueError as exc:
                    assert str(exc) == "PERMIT_REQUEST_INVALID"
            if field == "client_order_id":
                assert altered.fingerprint_context["client_order_id"] == altered.transport_business_parameters["newClientOrderId"]
                assert altered.fingerprint_context["client_order_id"] == "smcbot-order-test-limit-drift-002"
            if field == "position_side":
                assert altered.fingerprint_context["position_side"] == altered.transport_business_parameters["positionSide"] == "LONG"
            altered_fingerprint = build_signed_order_test_create_from_final_request(altered)
            altered_digest = altered_fingerprint.request_fingerprint
            assert altered_fingerprint.canonical_payload != baseline_fingerprint.canonical_payload
            assert altered_fingerprint.request_fingerprint != baseline_fingerprint.request_fingerprint
            gate = LiveExecutionPermitGate(
                env=env,
                correlation_id_provider=lambda i=index: UUID(f"11111111-1111-4111-8111-{740 + i:012d}"),
            )
            gate_invocation_count += 1
            try:
                gate.authorize_and_consume(
                    operation=LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE,
                    fingerprint=altered_fingerprint,
                    permit_reference=LiveExecutionPermitReference(permit.permit_id, permit.version),
                    confirmation_verified=True,
                    credentials_configured=True,
                    runtime_config_path=env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
                )
                raise AssertionError(f"order-test LIMIT drift row unexpectedly consumed permit: {field}")
            except LiveExecutionPermitGateError as exc:
                denial_code = exc.code
                expected = "PERMIT_SUBJECT_MISMATCH" if field == "client_order_id" else "PERMIT_FINGERPRINT_MISMATCH"
                assert denial_code == expected
                response_text = str(exc)
        except ValueError as exc:
            denial_code = str(exc)
            assert field == "time_in_force"
            assert denial_code in {"PERMIT_REQUEST_INVALID", "PERMIT_INVALID"}
            response_text = denial_code

        for forbidden in (
            "SELECT",
            "Traceback",
            "http://",
            "https://",
            "canonical_payload",
            "request_parameters",
            "signature",
            "X-MBX-APIKEY",
            "headers",
            "credential",
        ):
            assert forbidden not in response_text
        stored, audits = _permit_and_audits(env, permit.permit_id)
        assert stored is not None
        assert stored.state == LiveExecutionPermitState.ISSUED.value
        assert stored.version == 1
        assert stored.consumed_at is None
        assert stored.consumption_correlation_id is None
        assert stored.request_fingerprint == baseline_fingerprint.request_fingerprint
        consumed_audits = [audit for audit in audits if audit.action == "PERMIT_CONSUMED"]
        denied_audits = [audit for audit in audits if audit.action == "PERMIT_DENIED"]
        assert consumed_audits == []
        assert denied_audits == []
        assert len([audit for audit in audits if audit.action == "PERMIT_ISSUED"]) == 1
        for audit in audits:
            audit_text = str(audit.metadata_json)
            for forbidden in (
                "canonical_payload",
                "request_parameters",
                "signature",
                "apiKey",
                "credential",
                "headers",
                "SELECT",
                "Traceback",
            ):
                assert forbidden not in audit_text
        row_results.append(
            {
                "field": field,
                "baseline": baseline_value,
                "altered": altered_value,
                "coupling": coupling,
                "digest": altered_digest,
                "denial": denial_code,
            }
        )

    assert {row["field"] for row in row_results} == EXPECTED_ORDER_TEST_LIMIT_DRIFT_FIELDS
    assert gate_invocation_count == 7
    assert signing_count == 0
    assert post_count == 0
    assert delete_count == 0
    assert retry_count == 0
    assert server_time_for_signing_count == 0
    assert timestamp_augmentation_count == 0
    assert auth_augmentation_count == 0
    assert transport_callback_count == 0
    assert {
        "operation": baseline.operation,
        "environment": baseline.environment,
        "symbol": baseline.symbol,
        "subject_type": baseline.subject_type,
        "subject_id": baseline.subject_id,
        "fingerprint_context": dict(baseline.fingerprint_context),
        "transport_business_parameters": dict(baseline.transport_business_parameters),
    } == baseline_snapshot
    for forbidden in (
        "mark_price",
        "timestamp",
        "recvWindow",
        "signature",
        "apiKey",
        "headers",
        "credentials",
        "permit_id",
        "correlation_id",
        "exchange_response",
    ):
        assert forbidden not in baseline.fingerprint_context
        assert forbidden not in baseline.transport_business_parameters

    positive_env = durable_state_env("RELEASED")
    positive_permit = _issue(positive_env, baseline_fingerprint)
    positive_gate = LiveExecutionPermitGate(
        env=positive_env,
        correlation_id_provider=lambda: UUID("11111111-1111-4111-8111-111111111799"),
    )
    receipt = positive_gate.authorize_and_consume(
        operation=LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE,
        fingerprint=baseline_fingerprint,
        permit_reference=LiveExecutionPermitReference(positive_permit.permit_id, positive_permit.version),
        confirmation_verified=True,
        credentials_configured=True,
        runtime_config_path=positive_env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
    )
    assert receipt.permit_id == positive_permit.permit_id
    assert receipt.previous_version == 1
    assert receipt.consumed_version == 2
    assert receipt.request_fingerprint == baseline_fingerprint.request_fingerprint
    stored_positive, positive_audits = _permit_and_audits(positive_env, positive_permit.permit_id)
    assert stored_positive is not None
    assert stored_positive.state == LiveExecutionPermitState.CONSUMED.value
    assert stored_positive.version == 2
    assert stored_positive.consumed_at is not None
    assert stored_positive.consumption_correlation_id is not None
    assert stored_positive.request_fingerprint == baseline_fingerprint.request_fingerprint
    assert len([audit for audit in positive_audits if audit.action == "PERMIT_CONSUMED"]) == 1
    assert signing_count == 0
    assert post_count == 0
    assert delete_count == 0
    assert retry_count == 0
    assert server_time_for_signing_count == 0
    assert timestamp_augmentation_count == 0
    assert auth_augmentation_count == 0
    assert transport_callback_count == 0

EXPECTED_ORDER_TEST_MARKET_DRIFT_FIELDS = {
    "client_order_id",
    "side",
    "position_side",
    "order_type",
    "quantity",
    "price",
    "time_in_force",
    "reduce_only",
}


def _baseline_order_test_market_request(mark_price: Decimal = Decimal("50000")) -> LiveExecutionUnsignedMutationRequest:
    client = _order_test_client()
    preview = client.build_order_test_preview(
        "smcbot-order-test-market-drift-001",
        "BUY",
        "MARKET",
        Decimal("0.001"),
        price=None,
        time_in_force=None,
        reduce_only=False,
        exchange_filters=_order_test_filters(),
        mark_price=mark_price,
    )
    return client.build_unsigned_business_request(preview)


def _order_test_market_to_limit_variant_request(baseline: LiveExecutionUnsignedMutationRequest) -> LiveExecutionUnsignedMutationRequest:
    client = _order_test_client()
    preview = client.build_order_test_preview(
        str(baseline.fingerprint_context["client_order_id"]),
        str(baseline.fingerprint_context["side"]),
        "LIMIT",
        Decimal(str(baseline.fingerprint_context["quantity"])),
        price=Decimal("50000"),
        time_in_force="GTC",
        reduce_only=bool(baseline.fingerprint_context["reduce_only"]),
        exchange_filters=_order_test_filters(),
    )
    return client.build_unsigned_business_request(preview)


def _order_test_market_drift_variant_request(
    baseline: LiveExecutionUnsignedMutationRequest,
    field: str,
    value: Any,
) -> LiveExecutionUnsignedMutationRequest:
    if field == "order_type":
        return _order_test_market_to_limit_variant_request(baseline)
    fingerprint_context = dict(baseline.fingerprint_context)
    transport = dict(baseline.transport_business_parameters)
    fingerprint_context[field] = value
    subject_id = baseline.subject_id
    if field == "client_order_id":
        subject_id = str(value)
        transport["newClientOrderId"] = value
    elif field == "side":
        transport["side"] = value
    elif field == "position_side":
        transport["positionSide"] = value
    elif field == "quantity":
        transport["quantity"] = value
    elif field == "price":
        transport["price"] = value
    elif field == "time_in_force":
        transport["timeInForce"] = value
    elif field == "reduce_only":
        transport["reduceOnly"] = "true" if value is True else "false"
    else:
        raise AssertionError(f"unexpected order-test MARKET drift field: {field}")
    return LiveExecutionUnsignedMutationRequest(
        operation=baseline.operation,
        environment=baseline.environment,
        symbol=baseline.symbol,
        subject_type=baseline.subject_type,
        subject_id=subject_id,
        fingerprint_context=fingerprint_context,
        transport_business_parameters=transport,
    )


def test_order_test_market_field_drift_matrix_denies_without_consuming_or_transport() -> None:
    baseline = _baseline_order_test_market_request()
    alternate_mark = _baseline_order_test_market_request(Decimal("51000"))
    baseline_snapshot = {
        "operation": baseline.operation,
        "environment": baseline.environment,
        "symbol": baseline.symbol,
        "subject_type": baseline.subject_type,
        "subject_id": baseline.subject_id,
        "fingerprint_context": dict(baseline.fingerprint_context),
        "transport_business_parameters": dict(baseline.transport_business_parameters),
    }
    baseline_fingerprint = build_signed_order_test_create_from_final_request(baseline)
    alternate_mark_fingerprint = build_signed_order_test_create_from_final_request(alternate_mark)
    assert baseline.operation == LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE
    assert baseline.environment == "TESTNET"
    assert baseline.symbol == "BTCUSDT"
    assert baseline.subject_type == "ORDER_TEST"
    assert baseline.subject_id == "smcbot-order-test-market-drift-001"
    assert baseline_fingerprint.subject_type == "CLIENT_ORDER"
    assert baseline_fingerprint.subject_id == "smcbot-order-test-market-drift-001"
    assert set(baseline.fingerprint_context) == {
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
    assert baseline.fingerprint_context == {
        "schema_version": "1.0",
        "operation": "SIGNED_ORDER_TEST_CREATE",
        "environment": "TESTNET",
        "symbol": "BTCUSDT",
        "client_order_id": "smcbot-order-test-market-drift-001",
        "side": "BUY",
        "position_side": "BOTH",
        "order_type": "MARKET",
        "quantity": "0.001",
        "price": None,
        "time_in_force": None,
        "reduce_only": False,
    }
    assert baseline.transport_business_parameters == {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
        "quantity": "0.001",
        "newClientOrderId": "smcbot-order-test-market-drift-001",
        "positionSide": "BOTH",
    }
    assert baseline_fingerprint.canonical_payload["client_order_id"] == baseline.transport_business_parameters["newClientOrderId"]
    assert baseline_fingerprint.canonical_payload["quantity"] == baseline.transport_business_parameters["quantity"] == "0.001"
    assert baseline_fingerprint.canonical_payload["price"] is None
    assert baseline_fingerprint.canonical_payload["time_in_force"] is None
    assert "price" not in baseline.transport_business_parameters
    assert "timeInForce" not in baseline.transport_business_parameters
    assert baseline_fingerprint.canonical_payload["position_side"] == baseline.transport_business_parameters["positionSide"] == "BOTH"
    assert baseline_fingerprint.canonical_payload["reduce_only"] is False
    assert "reduceOnly" not in baseline.transport_business_parameters
    assert "mark_price" not in baseline.fingerprint_context
    assert "estimated_notional" not in baseline.fingerprint_context
    assert "markPrice" not in baseline.transport_business_parameters
    assert "estimatedNotional" not in baseline.transport_business_parameters
    assert "mark_price" not in baseline_fingerprint.canonical_payload
    assert "estimated_notional" not in baseline_fingerprint.canonical_payload
    assert dict(alternate_mark.fingerprint_context) == dict(baseline.fingerprint_context)
    assert dict(alternate_mark.transport_business_parameters) == dict(baseline.transport_business_parameters)
    assert alternate_mark_fingerprint.canonical_payload == baseline_fingerprint.canonical_payload
    assert alternate_mark_fingerprint.request_fingerprint == baseline_fingerprint.request_fingerprint
    for forbidden in (
        "mark_price",
        "estimated_notional",
        "timestamp",
        "recvWindow",
        "signature",
        "apiKey",
        "headers",
        "credentials",
        "permit_id",
        "correlation_id",
    ):
        assert forbidden not in baseline.fingerprint_context
        assert forbidden not in baseline.transport_business_parameters
    assert baseline_fingerprint.request_fingerprint

    cases = [
        ("client_order_id", "smcbot-order-test-market-drift-001", "smcbot-order-test-market-drift-002", "subject/newClientOrderId"),
        ("side", "BUY", "SELL", "side"),
        ("position_side", "BOTH", "LONG", "positionSide"),
        ("order_type", "MARKET", "LIMIT", "price=50000 and time_in_force=GTC required by LIMIT invariant"),
        ("quantity", "0.001", "0.002", "quantity"),
        ("price", None, "50000", "invalid MARKET price transport"),
        ("time_in_force", None, "GTC", "invalid MARKET timeInForce transport"),
        ("reduce_only", False, True, "reduceOnly=true"),
    ]
    assert {field for field, _, _, _ in cases} == EXPECTED_ORDER_TEST_MARKET_DRIFT_FIELDS
    assert len(cases) == 8

    signing_count = 0
    post_count = 0
    delete_count = 0
    retry_count = 0
    server_time_for_signing_count = 0
    timestamp_augmentation_count = 0
    auth_augmentation_count = 0
    transport_callback_count = 0
    gate_invocation_count = 0
    row_results: list[dict[str, object]] = []

    for index, (field, baseline_value, altered_value, coupling) in enumerate(cases, start=1):
        assert baseline.fingerprint_context[field] == baseline_value
        env = durable_state_env("RELEASED")
        permit = _issue(env, baseline_fingerprint)
        assert permit.request_fingerprint == baseline_fingerprint.request_fingerprint
        assert permit.state == LiveExecutionPermitState.ISSUED
        assert permit.version == 1

        altered_digest: str | None = None
        try:
            altered = _order_test_market_drift_variant_request(baseline, field, altered_value)
            if field == "order_type":
                assert altered.fingerprint_context["order_type"] == "LIMIT"
                assert altered.fingerprint_context["price"] == "50000"
                assert altered.fingerprint_context["time_in_force"] == "GTC"
                assert altered.transport_business_parameters["price"] == "50000"
                assert altered.transport_business_parameters["timeInForce"] == "GTC"
            if field == "price":
                assert altered.fingerprint_context["order_type"] == "MARKET"
                assert altered.fingerprint_context["price"] == "50000"
                assert altered.transport_business_parameters["price"] == "50000"
            if field == "time_in_force":
                assert altered.fingerprint_context["order_type"] == "MARKET"
                assert altered.fingerprint_context["time_in_force"] == "GTC"
                assert altered.transport_business_parameters["timeInForce"] == "GTC"
            if field == "reduce_only":
                assert altered.fingerprint_context["reduce_only"] is True
                assert altered.transport_business_parameters["reduceOnly"] == "true"
                invalid_omitted_transport = dict(baseline.transport_business_parameters)
                invalid_omitted_fingerprint = {**dict(baseline.fingerprint_context), "reduce_only": True}
                try:
                    LiveExecutionUnsignedMutationRequest(
                        operation=baseline.operation,
                        environment=baseline.environment,
                        symbol=baseline.symbol,
                        subject_type=baseline.subject_type,
                        subject_id=baseline.subject_id,
                        fingerprint_context=invalid_omitted_fingerprint,
                        transport_business_parameters=invalid_omitted_transport,
                    )
                    raise AssertionError("reduce_only=True without reduceOnly transport unexpectedly validated")
                except ValueError as exc:
                    assert str(exc) == "PERMIT_REQUEST_INVALID"
            if field == "client_order_id":
                assert altered.fingerprint_context["client_order_id"] == altered.transport_business_parameters["newClientOrderId"]
                assert altered.fingerprint_context["client_order_id"] == "smcbot-order-test-market-drift-002"
            if field == "position_side":
                assert altered.fingerprint_context["position_side"] == altered.transport_business_parameters["positionSide"] == "LONG"
            altered_fingerprint = build_signed_order_test_create_from_final_request(altered)
            altered_digest = altered_fingerprint.request_fingerprint
            assert altered_fingerprint.canonical_payload != baseline_fingerprint.canonical_payload
            assert altered_fingerprint.request_fingerprint != baseline_fingerprint.request_fingerprint
            gate = LiveExecutionPermitGate(
                env=env,
                correlation_id_provider=lambda i=index: UUID(f"11111111-1111-4111-8111-{940 + i:012d}"),
            )
            gate_invocation_count += 1
            try:
                gate.authorize_and_consume(
                    operation=LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE,
                    fingerprint=altered_fingerprint,
                    permit_reference=LiveExecutionPermitReference(permit.permit_id, permit.version),
                    confirmation_verified=True,
                    credentials_configured=True,
                    runtime_config_path=env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
                )
                raise AssertionError(f"order-test MARKET drift row unexpectedly consumed permit: {field}")
            except LiveExecutionPermitGateError as exc:
                denial_code = exc.code
                expected = "PERMIT_SUBJECT_MISMATCH" if field == "client_order_id" else "PERMIT_FINGERPRINT_MISMATCH"
                assert denial_code == expected
                response_text = str(exc)
        except ValueError as exc:
            denial_code = str(exc)
            assert field in {"price", "time_in_force"}
            assert denial_code in {"PERMIT_REQUEST_INVALID", "PERMIT_INVALID"}
            response_text = denial_code

        for forbidden in (
            "SELECT",
            "Traceback",
            "http://",
            "https://",
            "canonical_payload",
            "request_parameters",
            "mark_price",
            "estimated_notional",
            "signature",
            "X-MBX-APIKEY",
            "headers",
            "credential",
        ):
            assert forbidden not in response_text
        stored, audits = _permit_and_audits(env, permit.permit_id)
        assert stored is not None
        assert stored.state == LiveExecutionPermitState.ISSUED.value
        assert stored.version == 1
        assert stored.consumed_at is None
        assert stored.consumption_correlation_id is None
        assert stored.request_fingerprint == baseline_fingerprint.request_fingerprint
        consumed_audits = [audit for audit in audits if audit.action == "PERMIT_CONSUMED"]
        denied_audits = [audit for audit in audits if audit.action == "PERMIT_DENIED"]
        assert consumed_audits == []
        assert denied_audits == []
        assert len([audit for audit in audits if audit.action == "PERMIT_ISSUED"]) == 1
        for audit in audits:
            audit_text = str(audit.metadata_json)
            for forbidden in (
                "canonical_payload",
                "request_parameters",
                "mark_price",
                "estimated_notional",
                "signature",
                "apiKey",
                "credential",
                "headers",
                "SELECT",
                "Traceback",
            ):
                assert forbidden not in audit_text
        row_results.append(
            {
                "field": field,
                "baseline": baseline_value,
                "altered": altered_value,
                "coupling": coupling,
                "digest": altered_digest,
                "denial": denial_code,
            }
        )

    assert {row["field"] for row in row_results} == EXPECTED_ORDER_TEST_MARKET_DRIFT_FIELDS
    assert gate_invocation_count == 6
    assert signing_count == 0
    assert post_count == 0
    assert delete_count == 0
    assert retry_count == 0
    assert server_time_for_signing_count == 0
    assert timestamp_augmentation_count == 0
    assert auth_augmentation_count == 0
    assert transport_callback_count == 0
    assert {
        "operation": baseline.operation,
        "environment": baseline.environment,
        "symbol": baseline.symbol,
        "subject_type": baseline.subject_type,
        "subject_id": baseline.subject_id,
        "fingerprint_context": dict(baseline.fingerprint_context),
        "transport_business_parameters": dict(baseline.transport_business_parameters),
    } == baseline_snapshot
    for forbidden in (
        "mark_price",
        "estimated_notional",
        "timestamp",
        "recvWindow",
        "signature",
        "apiKey",
        "headers",
        "credentials",
        "permit_id",
        "correlation_id",
        "exchange_response",
    ):
        assert forbidden not in baseline.fingerprint_context
        assert forbidden not in baseline.transport_business_parameters

    positive_env = durable_state_env("RELEASED")
    positive_permit = _issue(positive_env, baseline_fingerprint)
    positive_gate = LiveExecutionPermitGate(
        env=positive_env,
        correlation_id_provider=lambda: UUID("11111111-1111-4111-8111-111111111999"),
    )
    receipt = positive_gate.authorize_and_consume(
        operation=LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE,
        fingerprint=baseline_fingerprint,
        permit_reference=LiveExecutionPermitReference(positive_permit.permit_id, positive_permit.version),
        confirmation_verified=True,
        credentials_configured=True,
        runtime_config_path=positive_env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"],
    )
    assert receipt.permit_id == positive_permit.permit_id
    assert receipt.previous_version == 1
    assert receipt.consumed_version == 2
    assert receipt.request_fingerprint == baseline_fingerprint.request_fingerprint
    stored_positive, positive_audits = _permit_and_audits(positive_env, positive_permit.permit_id)
    assert stored_positive is not None
    assert stored_positive.state == LiveExecutionPermitState.CONSUMED.value
    assert stored_positive.version == 2
    assert stored_positive.consumed_at is not None
    assert stored_positive.consumption_correlation_id is not None
    assert stored_positive.request_fingerprint == baseline_fingerprint.request_fingerprint
    assert len([audit for audit in positive_audits if audit.action == "PERMIT_CONSUMED"]) == 1
    assert signing_count == 0
    assert post_count == 0
    assert delete_count == 0
    assert retry_count == 0
    assert server_time_for_signing_count == 0
    assert timestamp_augmentation_count == 0
    assert auth_augmentation_count == 0
    assert transport_callback_count == 0
