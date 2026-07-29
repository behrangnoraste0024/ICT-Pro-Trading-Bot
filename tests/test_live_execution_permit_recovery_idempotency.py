from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest
from sqlalchemy import Column, MetaData, String, Table, create_engine, func, select
from sqlalchemy.orm import Session

from engine.diagnostics import binance_futures_testnet_protective_orders_engine as protective_engine_module
from engine.diagnostics.binance_futures_testnet_protective_orders_engine import BinanceFuturesTestnetProtectiveOrdersEngine
from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import BinanceLifecycleHTTPResponse
from infrastructure.exchanges.binance_futures_testnet_protective_orders_client import (
    BinanceFuturesTestnetProtectiveAPIError,
    BinanceFuturesTestnetProtectiveOrdersClient,
)
from infrastructure.persistence.execution_orm import AuditEventORM, ExecutionPersistenceBase, LiveExecutionPermitORM
from infrastructure.persistence.kill_switch_persistence import KillSwitchPersistence
from infrastructure.persistence.live_execution_authorization_policy import LiveExecutionAuthorizationPolicy
from infrastructure.persistence.live_execution_permit_persistence import ISSUE_CONFIRMATION, LiveExecutionPermitPersistence
from infrastructure.persistence.protective_lifecycle_persistence import ProtectiveLifecyclePersistence
from infrastructure.persistence.schema_contract import PERSISTENCE_REVISION
from infrastructure.security.live_execution_mutation_fingerprint_adapter import build_protective_cancel_from_final_request
from infrastructure.security.live_execution_permit_gate import LiveExecutionPermitGate
from models.binance_futures_testnet_protective_orders import (
    BinanceFuturesTestnetProtectiveAlgoSummary,
    BinanceFuturesTestnetProtectiveJournal,
    BinanceFuturesTestnetProtectiveOrdersConfig,
    BinanceFuturesTestnetProtectivePosition,
    BinanceFuturesTestnetProtectivePreview,
)
from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit_enforcement import LiveExecutionPermitReference, LiveExecutionUnsignedMutationRequest
from tests.kill_switch_test_support import authorized_runtime_env


PAIR_ID = "pair-recovery-idempotency-001"
STOP_ID = "smcbot-protect-sl-idempotency-001"
TAKE_PROFIT_ID = "smcbot-protect-tp-idempotency-001"
RECOVERY_CONFIRMATION = "CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY"
STOP_CORRELATION = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
TAKE_PROFIT_CORRELATION = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2")


def _database(tmp_path: Path) -> tuple[str, object]:
    database_path = tmp_path / "persistence.sqlite"
    engine = create_engine(f"sqlite:///{database_path}", future=True)
    ExecutionPersistenceBase.metadata.create_all(engine)
    version = Table("alembic_version", MetaData(), Column("version_num", String(64), primary_key=True))
    version.create(engine)
    with engine.begin() as connection:
        connection.execute(version.insert().values(version_num=PERSISTENCE_REVISION))
    database_url = f"sqlite:///{database_path}"
    kill_switch = KillSwitchPersistence(env={"ICT_DATABASE_URL": database_url})
    kill_switch.ensure_available()
    try:
        kill_switch.engage()
        kill_switch.release(expected_version=1)
    finally:
        kill_switch.close()
    return database_url, engine


def _env(database_url: str) -> dict[str, str]:
    return authorized_runtime_env(
        {
            "ICT_DATABASE_URL": database_url,
            "BINANCE_FUTURES_TESTNET_API_KEY": "unit-test-key",
            "BINANCE_FUTURES_TESTNET_API_SECRET": "unit-test-secret",
        }
    )


def _write_runtime_config(tmp_path: Path) -> None:
    runtime = tmp_path / "configs" / "btc_paper_runtime.json"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(json.dumps({"live_trading_enabled": True, "dry_run": False}), encoding="utf-8")


def _write_protective_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "configs" / "binance_futures_testnet_protective_orders.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(BinanceFuturesTestnetProtectiveOrdersConfig().to_dict()), encoding="utf-8")
    return config_path


def _position() -> BinanceFuturesTestnetProtectivePosition:
    return BinanceFuturesTestnetProtectivePosition(
        symbol="BTCUSDT",
        position_side="BOTH",
        position_amt=Decimal("0.001"),
        entry_price=Decimal("49000"),
        mark_price=Decimal("50000"),
        notional=Decimal("50"),
        direction="LONG",
    )


def _preview() -> BinanceFuturesTestnetProtectivePreview:
    return BinanceFuturesTestnetProtectivePreview(
        pair_id=PAIR_ID,
        symbol="BTCUSDT",
        position_direction="LONG",
        position_amount=Decimal("0.001"),
        entry_price=Decimal("49000"),
        mark_price=Decimal("50000"),
        protective_side="SELL",
        stop_client_algo_id=STOP_ID,
        take_profit_client_algo_id=TAKE_PROFIT_ID,
        stop_trigger=Decimal("45000.00"),
        take_profit_trigger=Decimal("55000.00"),
        transmission_ready=True,
    )


def _order(client_id: str, order_type: str, status: str = "NEW") -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "algoType": "CONDITIONAL",
        "clientAlgoId": client_id,
        "algoId": "42" if order_type == "STOP_MARKET" else "43",
        "side": "SELL",
        "positionSide": "BOTH",
        "orderType": order_type,
        "triggerPrice": "45000.00" if order_type == "STOP_MARKET" else "55000.00",
        "algoStatus": status,
        "actualQty": "0",
        "actualPrice": "0",
        "closePosition": True,
        "workingType": "MARK_PRICE",
        "priceProtect": True,
    }


def _algo_summary(client_id: str, label: str) -> BinanceFuturesTestnetProtectiveAlgoSummary:
    order_type = "STOP_MARKET" if label == "STOP" else "TAKE_PROFIT_MARKET"
    return BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig()).sanitize_algo_summary(
        _order(client_id, order_type),
        client_id,
    )


def _http_get(url: str, timeout: int) -> BinanceLifecycleHTTPResponse:
    if url.endswith("/fapi/v1/time"):
        return BinanceLifecycleHTTPResponse(200, url, {"serverTime": 1000}, 1)
    if "/fapi/v1/exchangeInfo" in url:
        return BinanceLifecycleHTTPResponse(
            200,
            url,
            {"symbols": [{"symbol": "BTCUSDT", "filters": [{"filterType": "PRICE_FILTER", "minPrice": "1", "maxPrice": "1000000", "tickSize": "0.10"}]}]},
            1,
        )
    raise AssertionError(f"unexpected public request: {url}")


class RecordingTransport:
    def __init__(self, database_url: str, counters: dict[str, int], expected_permits: dict[str, str]) -> None:
        self.database_url = database_url
        self.counters = counters
        self.expected_permits = expected_permits
        self.calls: list[dict[str, object]] = []
        self.created = {STOP_ID, TAKE_PROFIT_ID}
        self.deleted: set[str] = set()
        self.delete_client_ids: list[str] = []
        self.delete_bodies: list[dict[str, list[str]]] = []

    def __call__(self, method: str, url: str, body: bytes, timeout: int, headers: dict[str, str]) -> BinanceLifecycleHTTPResponse:
        params = parse_qs(body.decode("utf-8"))
        parsed = urlparse(url)
        self.calls.append({"method": method, "url": url, "params": params})
        if parsed.hostname != "demo-fapi.binance.com":
            raise AssertionError("non-testnet host reached")
        if "positionSide/dual" in url:
            if method != "GET":
                raise AssertionError("position mode must be GET-only")
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 1)
        if "positionRisk" in url:
            if method != "GET":
                raise AssertionError("position risk must be GET-only")
            return BinanceLifecycleHTTPResponse(200, url, [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": "0.001", "entryPrice": "49000", "markPrice": "50000", "notional": "50"}], 1)
        if parsed.path != "/fapi/v1/algoOrder":
            raise AssertionError(f"unexpected authenticated path: {parsed.path}")
        if method == "POST":
            self.counters["post_calls"] += 1
            raise AssertionError("recovery idempotency test must never create protective orders")
        client_id = params.get("clientAlgoId", [None])[0]
        if client_id not in {STOP_ID, TAKE_PROFIT_ID}:
            raise AssertionError(f"unexpected clientAlgoId: {client_id}")
        order_type = "STOP_MARKET" if client_id == STOP_ID else "TAKE_PROFIT_MARKET"
        if method == "GET":
            if client_id in self.deleted or client_id not in self.created:
                raise BinanceFuturesTestnetProtectiveAPIError(
                    "NO_SUCH_ORDER",
                    http_status=400,
                    binance_code=-2013,
                    method="GET",
                    path="/fapi/v1/algoOrder",
                    request_transmitted=True,
                    response_received=True,
                    deterministic_rejection=True,
                )
            return BinanceLifecycleHTTPResponse(200, url, _order(client_id, order_type), 1)
        if method == "DELETE":
            self.counters["delete_calls"] += 1
            self.counters["delete_signatures"] += 1 if "signature" in params else 0
            self.delete_client_ids.append(str(client_id))
            self.delete_bodies.append(params)
            if "cancelAll" in url or "openOrders" in url:
                raise AssertionError("cancel-all or wildcard endpoint reached")
            assert set(params) == {"clientAlgoId", "recvWindow", "signature", "symbol", "timestamp"}
            assert params["symbol"] == ["BTCUSDT"]
            assert params["clientAlgoId"] == [client_id]
            assert headers.get("X-MBX-APIKEY") == "unit-test-key"
            label = "STOP" if client_id == STOP_ID else "TAKE_PROFIT"
            expected = self.expected_permits[label]
            snapshot = _permit_snapshot(self.database_url, expected)
            assert snapshot["state"] == "CONSUMED"
            assert snapshot["version"] == 2
            assert snapshot["consumed_at"] is not None
            assert snapshot["consumption_correlation_id"] is not None
            assert len(_consume_audit_snapshots(self.database_url, expected)) == 1
            if label == "TAKE_PROFIT":
                assert self.counters["permit_close_calls"] == 1
            else:
                assert self.counters["permit_close_calls"] == 2
                assert _permit_snapshot(self.database_url, self.expected_permits["TAKE_PROFIT"])["state"] == "CONSUMED"
            self.deleted.add(str(client_id))
            return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": "42" if label == "STOP" else "43", "code": 200}, 1)
        raise AssertionError(f"unexpected authenticated method: {method}")


def _seed_recovery_state(tmp_path: Path, env: dict[str, str], config_path: Path) -> None:
    engine = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=env, http_get=_http_get, authenticated_request=lambda *args: None, now_ms_provider=lambda: 1000)
    config = engine.load_config(str(config_path))
    position = _position()
    preview = _preview()
    persistence = ProtectiveLifecyclePersistence(env=env)
    persistence.ensure_available()
    try:
        state = persistence.prepare_lifecycle(PAIR_ID, STOP_ID, TAKE_PROFIT_ID, position, preview)
        persistence.mark_create_transmitted(state)
        persistence.confirm_create(state, "STOP", _algo_summary(STOP_ID, "STOP"))
        persistence.confirm_create(state, "TAKE_PROFIT", _algo_summary(TAKE_PROFIT_ID, "TAKE_PROFIT"))
    finally:
        persistence.close()
    journal = BinanceFuturesTestnetProtectiveJournal(
        pair_id=PAIR_ID,
        stop_client_algo_id=STOP_ID,
        take_profit_client_algo_id=TAKE_PROFIT_ID,
        recovery_required=False,
        baseline_available=True,
        baseline_position_amount=position.position_amt,
        baseline_position_direction=position.direction,
        stop_trigger=preview.stop_trigger,
        take_profit_trigger=preview.take_profit_trigger,
    )
    for label in ("STOP", "TAKE_PROFIT"):
        intent = engine._mutation_intent(journal, preview, label, "CREATE", f"{label}_CREATE_STARTED")
        intent.resolved = True
        intent.reconciliation_state = "PRESENT"
        intent.reconciliation_reason = "Seeded active protective order for idempotent recovery test."
        journal.mutation_intents.append(intent)
    engine._write_journal(config, journal, "TAKE_PROFIT_QUERY_COMPLETE", {"reason": "idempotency regression setup"})


def _issue_permit(env: dict[str, str], fingerprint) -> object:
    persistence = LiveExecutionPermitPersistence(env=env)
    persistence.ensure_available()
    try:
        return persistence.issue(
            fingerprint,
            ttl_seconds=300,
            issued_by="operator-1",
            confirmation=ISSUE_CONFIRMATION,
        )
    finally:
        persistence.close()


def _permit_snapshot(database_url: str, permit_id: str) -> dict[str, object]:
    engine = create_engine(database_url, future=True)
    try:
        with Session(engine) as session:
            row = session.scalar(select(LiveExecutionPermitORM).where(LiveExecutionPermitORM.permit_id == permit_id))
            assert row is not None
            return {
                "permit_id": row.permit_id,
                "operation": row.operation,
                "environment": row.environment,
                "symbol": row.symbol,
                "request_fingerprint": row.request_fingerprint,
                "subject_type": row.subject_type,
                "subject_id": row.subject_id,
                "state": row.state,
                "version": row.version,
                "consumed_at": None if row.consumed_at is None else row.consumed_at.isoformat(),
                "consumption_correlation_id": None if row.consumption_correlation_id is None else str(row.consumption_correlation_id),
            }
    finally:
        engine.dispose()


def _consume_audit_snapshots(database_url: str, permit_id: str) -> list[tuple[object, ...]]:
    engine = create_engine(database_url, future=True)
    try:
        with Session(engine) as session:
            rows = session.scalars(
                select(AuditEventORM)
                .where(AuditEventORM.category == "LIVE_EXECUTION_PERMIT", AuditEventORM.action == "PERMIT_CONSUMED")
                .order_by(AuditEventORM.created_at.asc(), AuditEventORM.id.asc())
            ).all()
            snapshots = []
            for row in rows:
                metadata = row.metadata_json or {}
                if metadata.get("permit_id") != permit_id:
                    continue
                snapshots.append(
                    (
                        row.category,
                        row.action,
                        row.environment,
                        row.symbol,
                        row.result,
                        json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                    )
                )
            return snapshots
    finally:
        engine.dispose()


def _request_snapshot(request: LiveExecutionUnsignedMutationRequest) -> dict[str, object]:
    return {
        "operation": request.operation,
        "environment": request.environment,
        "symbol": request.symbol,
        "subject_type": request.subject_type,
        "subject_id": request.subject_id,
        "fingerprint_context": dict(request.fingerprint_context),
        "transport_business_parameters": dict(request.transport_business_parameters),
    }


def _assert_unsigned_request_is_clean(snapshot: dict[str, object], label: str, client_algo_id: str) -> None:
    assert snapshot["operation"] == LiveExecutionOperation.PROTECTIVE_CANCEL
    assert snapshot["environment"] == "TESTNET"
    assert snapshot["symbol"] == "BTCUSDT"
    assert snapshot["subject_type"] == "PROTECTIVE_PAIR"
    assert snapshot["subject_id"] == PAIR_ID
    context = snapshot["fingerprint_context"]
    transport = snapshot["transport_business_parameters"]
    assert isinstance(context, dict)
    assert isinstance(transport, dict)
    assert context["pair_id"] == PAIR_ID
    assert context["leg_type"] == label
    assert context["client_algo_id"] == client_algo_id
    assert transport == {"symbol": "BTCUSDT", "clientAlgoId": client_algo_id}
    forbidden = {"timestamp", "recvWindow", "signature", "credentials", "headers", "permit_id", "permitId", "correlation_id", "correlationId", "exchangeResponse", "rawResponse"}
    assert forbidden.isdisjoint(context)
    assert forbidden.isdisjoint(transport)


def test_protective_recovery_rerun_after_success_is_idempotent_without_additional_permit_consumption_or_delete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_url, database_engine = _database(tmp_path)
    env = _env(database_url)
    _write_runtime_config(tmp_path)
    config_path = _write_protective_config(tmp_path)
    _seed_recovery_state(tmp_path, env, config_path)

    seed_engine = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=env, http_get=_http_get, authenticated_request=lambda *args: None, now_ms_provider=lambda: 1000)
    seed_client = seed_engine._client(seed_engine.load_config(str(config_path)))
    stop_seed_request = seed_client.build_cancel_unsigned_business_request(_preview(), "STOP")
    take_seed_request = seed_client.build_cancel_unsigned_business_request(_preview(), "TAKE_PROFIT")
    stop_seed_fingerprint = build_protective_cancel_from_final_request(stop_seed_request)
    take_seed_fingerprint = build_protective_cancel_from_final_request(take_seed_request)
    stop_permit = _issue_permit(env, stop_seed_fingerprint)
    take_permit = _issue_permit(env, take_seed_fingerprint)
    assert stop_permit.permit_id != take_permit.permit_id
    assert stop_seed_fingerprint.request_fingerprint != take_seed_fingerprint.request_fingerprint
    assert stop_seed_fingerprint.subject_id != take_seed_fingerprint.subject_id
    assert STOP_ID != TAKE_PROFIT_ID

    counters = {
        "gate_calls": 0,
        "authorization_policy_calls": 0,
        "permit_persistence_factory_calls": 0,
        "correlation_provider_calls": 0,
        "permit_consume_calls": 0,
        "permit_close_calls": 0,
        "cancel_builder_calls": 0,
        "cancel_fingerprint_adapter_calls": 0,
        "delete_calls": 0,
        "delete_signatures": 0,
        "post_calls": 0,
        "delete_retries": 0,
    }
    captured_requests: dict[str, LiveExecutionUnsignedMutationRequest] = {}
    captured_fingerprints: dict[str, object] = {}
    expected_permits = {"STOP": stop_permit.permit_id, "TAKE_PROFIT": take_permit.permit_id}
    transport = RecordingTransport(database_url, counters, expected_permits)

    original_builder = BinanceFuturesTestnetProtectiveOrdersClient.build_cancel_unsigned_business_request

    def counted_builder(self, preview, label):
        counters["cancel_builder_calls"] += 1
        request = original_builder(self, preview, label)
        captured_requests[label] = request
        return request

    original_adapter = protective_engine_module.build_protective_cancel_from_final_request

    def counted_adapter(envelope):
        counters["cancel_fingerprint_adapter_calls"] += 1
        fingerprint = original_adapter(envelope)
        captured_fingerprints[envelope.fingerprint_context["leg_type"]] = fingerprint
        return fingerprint

    monkeypatch.setattr(BinanceFuturesTestnetProtectiveOrdersClient, "build_cancel_unsigned_business_request", counted_builder)
    monkeypatch.setattr(protective_engine_module, "build_protective_cancel_from_final_request", counted_adapter)

    original_consume = LiveExecutionPermitPersistence.consume
    original_close = LiveExecutionPermitPersistence.close

    def counting_factory(**kwargs):
        counters["permit_persistence_factory_calls"] += 1
        persistence = LiveExecutionPermitPersistence(**kwargs)

        def counted_consume(**consume_kwargs):
            counters["permit_consume_calls"] += 1
            return original_consume(persistence, **consume_kwargs)

        def counted_close():
            counters["permit_close_calls"] += 1
            return original_close(persistence)

        persistence.consume = counted_consume  # type: ignore[method-assign]
        persistence.close = counted_close  # type: ignore[method-assign]
        return persistence

    correlations = [TAKE_PROFIT_CORRELATION, STOP_CORRELATION]

    def correlation_provider() -> UUID:
        counters["correlation_provider_calls"] += 1
        return correlations.pop(0)

    policy = LiveExecutionAuthorizationPolicy(repo_root=tmp_path, env=env)
    original_authorize = policy.authorize

    def counted_authorize(*args, **kwargs):
        counters["authorization_policy_calls"] += 1
        return original_authorize(*args, **kwargs)

    policy.authorize = counted_authorize  # type: ignore[method-assign]
    gate = LiveExecutionPermitGate(
        authorization_policy=policy,
        permit_persistence_factory=counting_factory,
        correlation_id_provider=correlation_provider,
        env=env,
    )
    original_gate = gate.authorize_and_consume

    def counted_gate(**kwargs):
        counters["gate_calls"] += 1
        return original_gate(**kwargs)

    gate.authorize_and_consume = counted_gate  # type: ignore[method-assign]

    recovery_engine = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=env,
        http_get=_http_get,
        authenticated_request=transport,
        now_ms_provider=lambda: 1000,
        persistence_factory=ProtectiveLifecyclePersistence,
        authorization_policy=policy,
        permit_gate=gate,
    )
    stop_reference = LiveExecutionPermitReference(stop_permit.permit_id, stop_permit.version)
    take_reference = LiveExecutionPermitReference(take_permit.permit_id, take_permit.version)

    first = recovery_engine.recover_protective_pair(
        STOP_ID,
        TAKE_PROFIT_ID,
        confirmation=RECOVERY_CONFIRMATION,
        config_path=str(config_path),
        stop_cancel_permit=stop_reference,
        take_profit_cancel_permit=take_reference,
    )

    assert first.status == "PASS", (first.decision, first.reason)
    assert first.decision == "RECOVERY_COMPLETE"
    assert first.recovery_required is False
    assert first.unexpected_trigger is False
    assert first.unexpected_position_change is False
    assert first.lifecycle_complete is True
    assert first.stop_order is not None and first.stop_order.algo_status == "NEW"
    assert first.take_profit_order is not None and first.take_profit_order.algo_status == "NEW"
    assert first.final_stop_order is None
    assert first.final_take_profit_order is None
    assert {result.client_algo_id: result.reconciliation_state for result in first.reconciliation_results if result.mutation_kind == "DELETE" and result.resolved} == {
        STOP_ID: "ABSENT",
        TAKE_PROFIT_ID: "ABSENT",
    }

    assert transport.delete_client_ids == [TAKE_PROFIT_ID, STOP_ID]
    assert counters["gate_calls"] == 2
    assert counters["authorization_policy_calls"] == 2
    assert counters["permit_persistence_factory_calls"] == 2
    assert counters["correlation_provider_calls"] == 2
    assert counters["permit_consume_calls"] == 2
    assert counters["permit_close_calls"] == 2
    assert counters["cancel_builder_calls"] == 2
    assert counters["cancel_fingerprint_adapter_calls"] == 2
    assert counters["delete_calls"] == 2
    assert counters["delete_signatures"] == 2
    assert counters["delete_retries"] == 0
    assert counters["post_calls"] == 0
    assert [request.method for request in first.cancel_requests] == ["DELETE", "DELETE"]
    assert [request.retry_count for request in first.cancel_requests] == [0, 0]
    assert all(request.path == "/fapi/v1/algoOrder" and request.signature_generated for request in first.cancel_requests)

    stop_request_snapshot = _request_snapshot(captured_requests["STOP"])
    take_request_snapshot = _request_snapshot(captured_requests["TAKE_PROFIT"])
    _assert_unsigned_request_is_clean(stop_request_snapshot, "STOP", STOP_ID)
    _assert_unsigned_request_is_clean(take_request_snapshot, "TAKE_PROFIT", TAKE_PROFIT_ID)
    assert captured_fingerprints["STOP"].request_fingerprint == stop_seed_fingerprint.request_fingerprint
    assert captured_fingerprints["TAKE_PROFIT"].request_fingerprint == take_seed_fingerprint.request_fingerprint
    assert _permit_snapshot(database_url, stop_permit.permit_id)["request_fingerprint"] == captured_fingerprints["STOP"].request_fingerprint
    assert _permit_snapshot(database_url, take_permit.permit_id)["request_fingerprint"] == captured_fingerprints["TAKE_PROFIT"].request_fingerprint

    stop_after_first = _permit_snapshot(database_url, stop_permit.permit_id)
    take_after_first = _permit_snapshot(database_url, take_permit.permit_id)
    stop_audits_after_first = _consume_audit_snapshots(database_url, stop_permit.permit_id)
    take_audits_after_first = _consume_audit_snapshots(database_url, take_permit.permit_id)
    assert stop_after_first["state"] == "CONSUMED"
    assert take_after_first["state"] == "CONSUMED"
    assert stop_after_first["version"] == 2
    assert take_after_first["version"] == 2
    assert stop_after_first["consumption_correlation_id"] == str(STOP_CORRELATION)
    assert take_after_first["consumption_correlation_id"] == str(TAKE_PROFIT_CORRELATION)
    assert len(stop_audits_after_first) == 1
    assert len(take_audits_after_first) == 1
    first_counters = dict(counters)
    first_delete_count = len(transport.delete_client_ids)
    first_transport_count = len(transport.calls)
    first_post_count = counters["post_calls"]

    second = recovery_engine.recover_protective_pair(
        STOP_ID,
        TAKE_PROFIT_ID,
        confirmation=RECOVERY_CONFIRMATION,
        config_path=str(config_path),
        stop_cancel_permit=stop_reference,
        take_profit_cancel_permit=take_reference,
    )

    assert second.status == "PASS", (second.decision, second.reason)
    assert second.decision == "RECOVERY_COMPLETE"
    assert second.recovery_required is False
    assert second.unexpected_trigger is False
    assert second.unexpected_position_change is False
    assert second.lifecycle_complete is True
    assert second.stop_order is None
    assert second.take_profit_order is None
    assert second.final_stop_order is None
    assert second.final_take_profit_order is None
    assert second.cancel_requests == []
    second_calls = transport.calls[first_transport_count:]
    second_algo_gets = [
        call["params"].get("clientAlgoId", [None])[0]
        for call in second_calls
        if call["method"] == "GET" and urlparse(str(call["url"])).path == "/fapi/v1/algoOrder"
    ]
    assert second_algo_gets == [STOP_ID, TAKE_PROFIT_ID]

    assert counters["gate_calls"] - first_counters["gate_calls"] == 0
    assert counters["authorization_policy_calls"] - first_counters["authorization_policy_calls"] == 0
    assert counters["permit_persistence_factory_calls"] - first_counters["permit_persistence_factory_calls"] == 0
    assert counters["correlation_provider_calls"] - first_counters["correlation_provider_calls"] == 0
    assert counters["permit_consume_calls"] - first_counters["permit_consume_calls"] == 0
    assert counters["permit_close_calls"] - first_counters["permit_close_calls"] == 0
    assert counters["cancel_builder_calls"] - first_counters["cancel_builder_calls"] == 0
    assert counters["cancel_fingerprint_adapter_calls"] - first_counters["cancel_fingerprint_adapter_calls"] == 0
    assert counters["delete_calls"] - first_counters["delete_calls"] == 0
    assert counters["delete_signatures"] - first_counters["delete_signatures"] == 0
    assert counters["post_calls"] - first_post_count == 0
    assert len(transport.delete_client_ids) - first_delete_count == 0

    assert _permit_snapshot(database_url, stop_permit.permit_id) == stop_after_first
    assert _permit_snapshot(database_url, take_permit.permit_id) == take_after_first
    assert _consume_audit_snapshots(database_url, stop_permit.permit_id) == stop_audits_after_first
    assert _consume_audit_snapshots(database_url, take_permit.permit_id) == take_audits_after_first
    assert _request_snapshot(captured_requests["STOP"]) == stop_request_snapshot
    assert _request_snapshot(captured_requests["TAKE_PROFIT"]) == take_request_snapshot

    with Session(database_engine) as session:
        permit_count = session.scalar(select(func.count()).select_from(LiveExecutionPermitORM).where(LiveExecutionPermitORM.operation == "PROTECTIVE_CANCEL"))
    assert permit_count == 2
    assert counters == {
        "gate_calls": 2,
        "authorization_policy_calls": 2,
        "permit_persistence_factory_calls": 2,
        "correlation_provider_calls": 2,
        "permit_consume_calls": 2,
        "permit_close_calls": 2,
        "cancel_builder_calls": 2,
        "cancel_fingerprint_adapter_calls": 2,
        "delete_calls": 2,
        "delete_signatures": 2,
        "post_calls": 0,
        "delete_retries": 0,
    }
    assert not (tmp_path / "data" / "runtime" / "binance_futures_testnet_protective_orders" / "protective.lock").exists()
