from __future__ import annotations

import json
import inspect
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, MetaData, String, Table, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from api.live_control_plane_routes import get_persistence_read_model_service
from api.main import create_app
import api.persistence_read_model_service as service_module
from api.persistence_read_model_service import (
    PERSISTENCE_REVISION,
    PersistenceReadModelHTTPError,
    PersistenceReadModelService,
)
from infrastructure.persistence.execution_orm import (
    AuditEventORM,
    ExecutionIntentORM,
    ExecutionPersistenceBase,
    ExchangeOrderIdentityORM,
    ProtectivePairORM,
    RecoveryEventORM,
)
from infrastructure.persistence.execution_repositories import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyExchangeOrderIdentityRepository,
    SqlAlchemyExecutionIntentRepository,
    SqlAlchemyProtectivePairRepository,
    SqlAlchemyRecoveryEventRepository,
)
from models.execution_persistence import AuditEvent, ExchangeOrderIdentity, ExecutionIntent, ProtectivePair, RecoveryEvent


def _engine(path: Path):
    engine = create_engine(f"sqlite:///{path}", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _prepare_database(path: Path, with_schema: bool = True, revision: str = PERSISTENCE_REVISION):
    engine = _engine(path)
    if with_schema:
        ExecutionPersistenceBase.metadata.create_all(engine)
        metadata = MetaData()
        version_table = Table("alembic_version", metadata, Column("version_num", String(64), primary_key=True))
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(version_table.insert().values(version_num=revision))
    return engine


def _service(path: Path, session_factory=Session) -> PersistenceReadModelService:
    return PersistenceReadModelService(
        env={"ICT_DATABASE_URL": f"sqlite:///{path}"},
        engine_factory=create_engine,
        session_factory=session_factory,
    )


def _client(service: PersistenceReadModelService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_persistence_read_model_service] = lambda: service
    return TestClient(app)


def _unavailable_engine(*args, **kwargs):
    raise OSError("database connection failed")


def _seed(engine, *, include_orders: bool = True, include_events: bool = True):
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        intent = SqlAlchemyExecutionIntentRepository(session).create(
            ExecutionIntent(
                environment="BINANCE_FUTURES_TESTNET",
                symbol="BTCUSDT",
                intent_type="PROTECTIVE_PAIR",
                state="PERSISTED",
                requested_quantity=Decimal("0.001600000000000001"),
                requested_price=Decimal("63099.660000000000000001"),
                failure_code=None,
            )
        )
        pair = SqlAlchemyProtectivePairRepository(session).create(
            ProtectivePair(
                pair_id=f"pair-{uuid4()}",
                correlation_id=intent.correlation_id,
                execution_intent_id=intent.id,
                environment="BINANCE_FUTURES_TESTNET",
                symbol="BTCUSDT",
                position_side="BOTH",
                direction="LONG",
                quantity=Decimal("0.001600000000000001"),
                state="PAIR_ACTIVE",
                recovery_required=True,
                blocking_reason="EXACT_LOOKUP_REQUIRED",
            )
        )
        if include_orders:
            order_repo = SqlAlchemyExchangeOrderIdentityRepository(session)
            order_repo.create(
                ExchangeOrderIdentity(
                    protective_pair_id=pair.id,
                    environment="BINANCE_FUTURES_TESTNET",
                    symbol="BTCUSDT",
                    leg_type="TAKE_PROFIT",
                    client_algo_id="smcbot-protect-tp-read-model",
                    status="NEW",
                    trigger_price=Decimal("64000.123456789012345678"),
                )
            )
            order_repo.create(
                ExchangeOrderIdentity(
                    protective_pair_id=pair.id,
                    environment="BINANCE_FUTURES_TESTNET",
                    symbol="BTCUSDT",
                    leg_type="STOP",
                    client_algo_id="smcbot-protect-stop-read-model",
                    status="NEW",
                    trigger_price=Decimal("62000.123456789012345678"),
                )
            )
        if include_events:
            recovery_repo = SqlAlchemyRecoveryEventRepository(session)
            recovery_repo.append(
                RecoveryEvent(
                    correlation_id=intent.correlation_id,
                    protective_pair_id=pair.id,
                    event_type="LOOKUP",
                    result="RECOVERY_REQUIRED",
                    reason_code="EXACT_LOOKUP_REQUIRED",
                )
            )
            audit_repo = SqlAlchemyAuditEventRepository(session)
            audit_repo.append(
                AuditEvent(
                    correlation_id=intent.correlation_id,
                    category="CONTROL_PLANE",
                    action="READ",
                    environment="BINANCE_FUTURES_TESTNET",
                    symbol="BTCUSDT",
                    result="PASS",
                    metadata_json={"safe": "hidden from read model"},
                )
            )
            audit_repo.append(
                AuditEvent(
                    correlation_id=uuid4(),
                    category="CONTROL_PLANE",
                    action="UNRELATED",
                    environment="BINANCE_FUTURES_TESTNET",
                    symbol="BTCUSDT",
                    result="PASS",
                    metadata_json={"safe": True},
                )
            )
        session.commit()
    return intent, pair


def _order(pair: ProtectivePair, leg_type: str, client_algo_id: str) -> ExchangeOrderIdentity:
    return ExchangeOrderIdentity(
        protective_pair_id=pair.id,
        environment="BINANCE_FUTURES_TESTNET",
        symbol="BTCUSDT",
        leg_type=leg_type,
        client_algo_id=client_algo_id,
        status="NEW",
        trigger_price=Decimal("62000" if leg_type == "STOP" else "64000"),
    )


def test_persistence_routes_are_get_only_and_existing_routes_remain_registered() -> None:
    client = _client(PersistenceReadModelService(env={}))
    paths = client.get("/openapi.json").json()["paths"]
    new_paths = {
        "/api/v1/live/persistence/status",
        "/api/v1/live/execution-intents",
        "/api/v1/live/execution-intents/{correlation_id}",
        "/api/v1/live/exchange-orders",
        "/api/v1/live/protective-pairs/{pair_id}",
        "/api/v1/live/protective-pairs/{pair_id}/orders",
        "/api/v1/live/protective-pairs/{pair_id}/events",
    }
    assert new_paths.issubset(paths)
    assert all(set(paths[path]) == {"get"} for path in new_paths)
    for path in (
        "/api/v1/live/persistence/status",
        "/api/v1/live/execution-intents",
        "/api/v1/live/exchange-orders",
        "/api/v1/live/execution-intents/00000000-0000-0000-0000-000000000000",
    ):
        for method in (client.post, client.put, client.patch, client.delete):
            assert method(path).status_code == 405
    assert "/api/v1/live/readiness" in paths
    assert "/api/v1/live/recovery/status" in paths


def test_persistence_status_is_safe_when_unconfigured_unavailable_or_schema_missing(tmp_path: Path) -> None:
    unconfigured = _client(PersistenceReadModelService(env={})).get("/api/v1/live/persistence/status")
    assert unconfigured.status_code == 200
    assert unconfigured.json()["configured"] is False
    assert unconfigured.json()["read_only"] is True
    assert unconfigured.json()["source_of_truth"] is False

    unavailable_url = "postgresql+psycopg://user:password@database.internal:5432/hidden"
    unavailable = _client(PersistenceReadModelService(env={"ICT_DATABASE_URL": unavailable_url}, engine_factory=_unavailable_engine)).get("/api/v1/live/persistence/status")
    assert unavailable.status_code == 200
    assert unavailable.json()["configured"] is True
    assert unavailable.json()["reachable"] is False
    assert unavailable_url not in json.dumps(unavailable.json())
    assert "database.internal" not in json.dumps(unavailable.json())

    path = tmp_path / "wrong-schema.db"
    _prepare_database(path, with_schema=False).dispose()
    missing = _client(_service(path)).get("/api/v1/live/persistence/status")
    assert missing.status_code == 200
    assert missing.json()["reachable"] is True
    assert missing.json()["schema_ready"] is False
    query = _client(_service(path)).get("/api/v1/live/execution-intents/00000000-0000-0000-0000-000000000000")
    assert query.status_code == 503
    assert query.json()["detail"] == {"code": "PERSISTENCE_UNAVAILABLE", "message": "Persistence read model is unavailable.", "details": {}}


def test_persistence_status_returns_only_the_exact_supported_revision(tmp_path: Path) -> None:
    path = tmp_path / "supported-revision.db"
    _prepare_database(path, revision=PERSISTENCE_REVISION).dispose()

    response = _client(_service(path)).get("/api/v1/live/persistence/status")

    assert response.status_code == 200
    assert response.json()["schema_ready"] is True
    assert response.json()["migration_revision"] == PERSISTENCE_REVISION


@pytest.mark.parametrize(
    "revision",
    [
        "20260714_9999",
        "rawResponse",
        "signed-url",
        "postgresql://user:secret@database.internal/db",
        "connectionString=Server=database.internal",
        "SELECT * FROM execution_intents",
        "traceback\nrawResponse",
        "control\x01revision",
    ],
)
def test_persistence_status_never_echoes_unsupported_or_hostile_revision(tmp_path: Path, revision: str) -> None:
    path = tmp_path / f"hostile-revision-{uuid4()}.db"
    _prepare_database(path, revision=revision).dispose()

    response = _client(_service(path)).get("/api/v1/live/persistence/status")
    body = json.dumps(response.json())

    assert response.status_code == 200
    assert response.json()["reachable"] is True
    assert response.json()["schema_ready"] is False
    assert response.json()["migration_revision"] is None
    assert revision not in body


def test_read_model_returns_only_sanitized_exact_records(tmp_path: Path) -> None:
    path = tmp_path / "persistence.db"
    engine = _prepare_database(path)
    intent, pair = _seed(engine)
    engine.dispose()
    client = _client(_service(path))

    status = client.get("/api/v1/live/persistence/status")
    assert status.status_code == 200
    assert status.json()["migration_revision"] == PERSISTENCE_REVISION
    assert status.json()["schema_ready"] is True

    intent_response = client.get(f"/api/v1/live/execution-intents/{intent.correlation_id}")
    assert intent_response.status_code == 200
    intent_body = intent_response.json()
    assert intent_body["correlation_id"] == str(intent.correlation_id)
    assert intent_body["requested_quantity"] == "0.001600000000000001"
    assert intent_body["requested_price"] == "63099.660000000000000001"
    assert "id" not in intent_body
    assert intent_body["created_at"].endswith("+00:00")

    intent_list_response = client.get("/api/v1/live/execution-intents")
    assert intent_list_response.status_code == 200
    intent_list_body = intent_list_response.json()
    assert set(intent_list_body) == {"items", "limit", "offset", "count", "updated_at"}
    assert intent_list_body["limit"] == 50
    assert intent_list_body["offset"] == 0
    assert intent_list_body["count"] == len(intent_list_body["items"]) == 1
    assert intent_list_body["items"][0] == intent_body

    pair_response = client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}")
    assert pair_response.status_code == 200
    pair_body = pair_response.json()
    assert pair_body["recovery_required"] is True
    assert pair_body["blocking_reason"] == "EXACT_LOOKUP_REQUIRED"
    assert "id" not in pair_body
    assert "execution_intent_id" not in pair_body

    orders_response = client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/orders")
    assert orders_response.status_code == 200
    orders = orders_response.json()["orders"]
    assert [order["leg_type"] for order in orders] == ["STOP", "TAKE_PROFIT"]
    assert orders[0]["trigger_price"] == "62000.123456789012345678"
    assert all("id" not in order and "protective_pair_id" not in order for order in orders)

    events_response = client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events?limit=50&offset=0")
    assert events_response.status_code == 200
    events = events_response.json()["events"]
    assert {event["event_kind"] for event in events} == {"RECOVERY_EVENT", "AUDIT_EVENT"}
    assert all("metadata_json" not in event and "id" not in event for event in events)
    assert "hidden from read model" not in json.dumps(events)


def test_read_model_validates_identifiers_scope_pagination_and_not_found(tmp_path: Path) -> None:
    path = tmp_path / "persistence.db"
    engine = _prepare_database(path)
    intent, pair = _seed(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        production = SqlAlchemyExecutionIntentRepository(session).create(
            ExecutionIntent(environment="BINANCE_FUTURES_PRODUCTION", symbol="BTCUSDT", intent_type="PROTECTIVE_PAIR", state="PENDING")
        )
        eth_intent = SqlAlchemyExecutionIntentRepository(session).create(
            ExecutionIntent(environment="BINANCE_FUTURES_TESTNET", symbol="ETHUSDT", intent_type="PROTECTIVE_PAIR", state="PENDING")
        )
        session.commit()
    engine.dispose()
    client = _client(_service(path))

    assert client.get("/api/v1/live/execution-intents/not-a-uuid").status_code == 400
    assert client.get("/api/v1/live/protective-pairs/bad!").status_code == 400
    assert client.get("/api/v1/live/execution-intents/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get(f"/api/v1/live/execution-intents/{production.correlation_id}").status_code == 403
    assert client.get(f"/api/v1/live/execution-intents/{eth_intent.correlation_id}").status_code == 403
    assert client.get("/api/v1/live/execution-intents?limit=0").status_code == 400
    assert client.get("/api/v1/live/execution-intents?limit=101").status_code == 400
    assert client.get("/api/v1/live/execution-intents?offset=-1").status_code == 400
    assert client.get("/api/v1/live/execution-intents?limit=invalid").status_code == 400
    assert client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events?limit=101").status_code == 400
    assert client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events?offset=-1").status_code == 400
    assert client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events?limit=invalid").status_code == 400
    assert client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events?limit=1&offset=1").status_code == 200


def test_execution_intent_collection_empty_page_limit_edges_and_repository_bounds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "empty-intents.db"
    _prepare_database(path).dispose()
    calls: list[tuple[int, int]] = []

    class FakeRepository:
        def __init__(self, session) -> None:
            pass

        def list_recent(self, limit, offset=0):
            calls.append((limit, offset))
            return []

    monkeypatch.setattr(service_module, "SqlAlchemyExecutionIntentRepository", FakeRepository)
    client = _client(_service(path))

    default = client.get("/api/v1/live/execution-intents")
    limit_one = client.get("/api/v1/live/execution-intents?limit=1&offset=2")
    limit_hundred = client.get("/api/v1/live/execution-intents?limit=100")

    assert default.status_code == 200
    assert default.json()["items"] == []
    assert default.json()["count"] == 0
    assert default.json()["limit"] == 50
    assert default.json()["offset"] == 0
    assert limit_one.status_code == 200
    assert limit_hundred.status_code == 200
    assert calls == [(50, 0), (1, 2), (100, 0)]


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "limit=invalid"])
def test_execution_intent_collection_invalid_pagination_fails_before_persistence_access(query: str) -> None:
    response = _client(PersistenceReadModelService(env={})).get(f"/api/v1/live/execution-intents?{query}")

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "INVALID_PERSISTENCE_PAGINATION",
        "message": "Persistence pagination is invalid.",
        "details": {},
    }


def test_execution_intent_collection_orders_by_created_at_desc_and_id_desc(tmp_path: Path) -> None:
    path = tmp_path / "intent-ordering.db"
    engine = _prepare_database(path)
    older = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    newer = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    same = datetime(2026, 1, 1, 0, 2, tzinfo=UTC)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        repo = SqlAlchemyExecutionIntentRepository(session)
        first = repo.create(
            ExecutionIntent(
                id=UUID(int=1),
                correlation_id=UUID(int=101),
                environment="BINANCE_FUTURES_TESTNET",
                symbol="BTCUSDT",
                intent_type="PROTECTIVE_PAIR",
                state="PERSISTED",
                created_at=older,
                updated_at=older,
            )
        )
        second = repo.create(
            ExecutionIntent(
                id=UUID(int=2),
                correlation_id=UUID(int=102),
                environment="BINANCE_FUTURES_TESTNET",
                symbol="BTCUSDT",
                intent_type="PROTECTIVE_PAIR",
                state="PERSISTED",
                created_at=same,
                updated_at=same,
            )
        )
        third = repo.create(
            ExecutionIntent(
                id=UUID(int=3),
                correlation_id=UUID(int=103),
                environment="BINANCE_FUTURES_TESTNET",
                symbol="BTCUSDT",
                intent_type="PROTECTIVE_PAIR",
                state="PERSISTED",
                created_at=same,
                updated_at=same,
            )
        )
        fourth = repo.create(
            ExecutionIntent(
                id=UUID(int=4),
                correlation_id=UUID(int=104),
                environment="BINANCE_FUTURES_TESTNET",
                symbol="BTCUSDT",
                intent_type="PROTECTIVE_PAIR",
                state="PERSISTED",
                created_at=newer,
                updated_at=newer,
            )
        )
        session.commit()
    engine.dispose()

    response = _client(_service(path)).get("/api/v1/live/execution-intents?limit=3&offset=0")

    assert response.status_code == 200
    assert [item["correlation_id"] for item in response.json()["items"]] == [
        str(third.correlation_id),
        str(second.correlation_id),
        str(fourth.correlation_id),
    ]
    assert first.correlation_id not in {UUID(item["correlation_id"]) for item in response.json()["items"]}


def _insert_identity(engine, pair: ProtectivePair, *, identity_id: UUID, client_algo_id: str, leg_type: str, created_at: datetime) -> None:
    with engine.begin() as connection:
        connection.execute(
            ExchangeOrderIdentityORM.__table__.insert().values(
                id=identity_id,
                protective_pair_id=pair.id,
                environment="BINANCE_FUTURES_TESTNET",
                symbol="BTCUSDT",
                leg_type=leg_type,
                client_algo_id=client_algo_id,
                status="NEW",
                trigger_price=Decimal("62000" if leg_type == "STOP" else "64000"),
                created_at=created_at,
                updated_at=created_at,
                version=1,
            )
        )


def test_exchange_order_collection_empty_default_pagination_and_exact_fields(tmp_path: Path) -> None:
    path = tmp_path / "empty-exchange-orders.db"
    _prepare_database(path).dispose()

    response = _client(_service(path)).get("/api/v1/live/exchange-orders")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["limit"] == 50
    assert payload["offset"] == 0
    assert payload["count"] == 0
    assert set(payload) == {"items", "limit", "offset", "count", "updated_at"}


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "limit=invalid", "offset=invalid"])
def test_exchange_order_collection_invalid_pagination_fails_before_persistence_access(query: str) -> None:
    def forbidden_engine(*args, **kwargs):
        raise AssertionError("invalid pagination must not construct persistence providers")

    response = _client(PersistenceReadModelService(env={}, engine_factory=forbidden_engine)).get(
        f"/api/v1/live/exchange-orders?{query}"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "INVALID_PERSISTENCE_PAGINATION",
        "message": "Persistence pagination is invalid.",
        "details": {},
    }


def test_exchange_order_collection_orders_by_created_at_desc_and_id_desc_with_exact_fields(tmp_path: Path) -> None:
    path = tmp_path / "exchange-ordering.db"
    engine = _prepare_database(path)
    _, pair = _seed(engine, include_orders=False, include_events=False)
    _, second_pair = _seed(engine, include_orders=False, include_events=False)
    older = datetime(2026, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 1, 2, tzinfo=UTC)
    _insert_identity(engine, pair, identity_id=UUID(int=1), client_algo_id="smcbot-old", leg_type="STOP", created_at=older)
    _insert_identity(engine, second_pair, identity_id=UUID(int=2), client_algo_id="smcbot-new-low", leg_type="STOP", created_at=newer)
    _insert_identity(engine, pair, identity_id=UUID(int=3), client_algo_id="smcbot-new-high", leg_type="TAKE_PROFIT", created_at=newer)
    engine.dispose()

    client = _client(_service(path))
    default = client.get("/api/v1/live/exchange-orders")
    limit_one = client.get("/api/v1/live/exchange-orders?limit=1")
    limit_hundred = client.get("/api/v1/live/exchange-orders?limit=100&offset=0")

    assert default.status_code == 200
    assert limit_one.status_code == 200
    assert limit_hundred.status_code == 200
    payload = default.json()
    assert payload["count"] == len(payload["items"]) == 3
    assert [item["client_algo_id"] for item in payload["items"]] == ["smcbot-new-high", "smcbot-new-low", "smcbot-old"]
    assert [item["client_algo_id"] for item in limit_one.json()["items"]] == ["smcbot-new-high"]
    item_keys = {
        "pair_id",
        "correlation_id",
        "leg_type",
        "client_algo_id",
        "exchange_algo_id",
        "exchange_order_id",
        "status",
        "trigger_price",
        "version",
        "created_at",
        "updated_at",
    }
    assert all(set(item) == item_keys for item in payload["items"])
    assert payload["items"][0]["pair_id"] == pair.pair_id
    assert payload["items"][0]["correlation_id"] == str(pair.correlation_id)
    assert payload["items"][1]["pair_id"] == second_pair.pair_id
    assert payload["items"][1]["correlation_id"] == str(second_pair.correlation_id)
    assert payload["items"][2]["pair_id"] == pair.pair_id
    assert payload["items"][2]["correlation_id"] == str(pair.correlation_id)
    serialized = json.dumps(payload)
    assert str(pair.id) not in serialized
    assert "protective_pair_id" not in serialized


def test_exchange_order_collection_uses_exact_repository_bounds_and_no_total_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "exchange-bounds.db"
    _prepare_database(path).dispose()
    calls = []

    class FakeOrderRepository:
        def __init__(self, session) -> None:
            pass

        def list_recent(self, limit, offset=0):
            calls.append((limit, offset))
            return []

    monkeypatch.setattr(service_module, "SqlAlchemyExchangeOrderIdentityRepository", FakeOrderRepository)
    response = _client(_service(path)).get("/api/v1/live/exchange-orders?limit=7&offset=3")

    assert response.status_code == 200
    assert calls == [(7, 3)]
    assert response.json()["count"] == 0


@pytest.mark.parametrize(
    "order_mutator,pair_mutator,expected_status",
    [
        (lambda order: replace(order, environment="BINANCE_FUTURES_PRODUCTION"), lambda pair: pair, 403),
        (lambda order: replace(order, symbol="ETHUSDT"), lambda pair: pair, 403),
        (lambda order: order, lambda pair: replace(pair, environment="BINANCE_FUTURES_PRODUCTION"), 403),
        (lambda order: order, lambda pair: replace(pair, symbol="ETHUSDT"), 403),
        (lambda order: replace(order, environment=None), lambda pair: pair, 503),
        (lambda order: replace(order, symbol=None), lambda pair: pair, 503),
        (lambda order: order, lambda pair: replace(pair, environment=None), 503),
        (lambda order: order, lambda pair: replace(pair, symbol=None), 503),
        (lambda order: replace(order, protective_pair_id=uuid4()), lambda pair: pair, 503),
        (lambda order: replace(order, client_algo_id=None), lambda pair: pair, 503),
        (lambda order: replace(order, status=None), lambda pair: pair, 503),
    ],
)
def test_exchange_order_collection_scope_and_malformed_rows_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, order_mutator, pair_mutator, expected_status: int
) -> None:
    path = tmp_path / f"exchange-scope-{uuid4()}.db"
    engine = _prepare_database(path)
    _, pair = _seed(engine, include_orders=False, include_events=False)
    engine.dispose()
    order = order_mutator(_order(pair, "STOP", "safe-stop"))
    stored_pair = pair_mutator(pair)

    class FakeOrderRepository:
        def __init__(self, session) -> None:
            pass

        def list_recent(self, limit, offset=0):
            return [order]

    class FakePairRepository:
        def __init__(self, session) -> None:
            pass

        def get_by_id(self, pair_id):
            return stored_pair

    monkeypatch.setattr(service_module, "SqlAlchemyExchangeOrderIdentityRepository", FakeOrderRepository)
    monkeypatch.setattr(service_module, "SqlAlchemyProtectivePairRepository", FakePairRepository)

    response = _client(_service(path)).get("/api/v1/live/exchange-orders")
    body = json.dumps(response.json())

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] in {"PERSISTENCE_SCOPE_FORBIDDEN", "PERSISTENCE_UNAVAILABLE"}
    assert "safe-stop" not in body


def test_exchange_order_collection_orphan_duplicate_and_provider_failures_are_sanitized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / f"exchange-sanitized-{uuid4()}.db"
    engine = _prepare_database(path)
    _, pair = _seed(engine, include_orders=False, include_events=False)
    engine.dispose()
    order = _order(pair, "STOP", "same-client")

    class DuplicateOrderRepository:
        def __init__(self, session) -> None:
            pass

        def list_recent(self, limit, offset=0):
            return [order, replace(order, leg_type="TAKE_PROFIT")]

    class PairRepository:
        def __init__(self, session) -> None:
            pass

        def get_by_id(self, pair_id):
            return pair

    monkeypatch.setattr(service_module, "SqlAlchemyExchangeOrderIdentityRepository", DuplicateOrderRepository)
    monkeypatch.setattr(service_module, "SqlAlchemyProtectivePairRepository", PairRepository)
    duplicate = _client(_service(path)).get("/api/v1/live/exchange-orders")
    assert duplicate.status_code == 503

    class OrphanPairRepository(PairRepository):
        def get_by_id(self, pair_id):
            return None

    monkeypatch.setattr(service_module, "SqlAlchemyProtectivePairRepository", OrphanPairRepository)
    orphan = _client(_service(path)).get("/api/v1/live/exchange-orders")
    assert orphan.status_code == 503

    class FailingOrderRepository:
        def __init__(self, session) -> None:
            pass

        def list_recent(self, limit, offset=0):
            raise RuntimeError("postgresql://user:secret@db SELECT * FROM exchange_order_identities rawResponse traceback signature")

    monkeypatch.setattr(service_module, "SqlAlchemyExchangeOrderIdentityRepository", FailingOrderRepository)
    failed = _client(_service(path)).get("/api/v1/live/exchange-orders")
    body = json.dumps(failed.json()).casefold()

    assert failed.status_code == 503
    for marker in ("postgresql://", "secret", "select * from", "rawresponse", "traceback", "signature"):
        assert marker not in body


@pytest.mark.parametrize(
    ("environment", "symbol"),
    [
        ("BINANCE_FUTURES_PRODUCTION", "BTCUSDT"),
        ("BINANCE_FUTURES_TESTNET", "ETHUSDT"),
    ],
)
def test_execution_intent_collection_valid_unsupported_scope_returns_sanitized_403(
    tmp_path: Path, environment: str, symbol: str
) -> None:
    path = tmp_path / f"unsupported-scope-{uuid4()}.db"
    engine = _prepare_database(path)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        SqlAlchemyExecutionIntentRepository(session).create(
            ExecutionIntent(environment=environment, symbol=symbol, intent_type="PROTECTIVE_PAIR", state="PERSISTED")
        )
        session.commit()
    engine.dispose()

    response = _client(_service(path)).get("/api/v1/live/execution-intents")

    assert response.status_code == 403
    assert response.json()["detail"] == {
        "code": "PERSISTENCE_SCOPE_FORBIDDEN",
        "message": "Persistence scope is forbidden.",
        "details": {},
    }


@pytest.mark.parametrize(
    "mutator",
    [
        lambda intent: replace(intent, environment=None),
        lambda intent: replace(intent, environment="rawResponse"),
        lambda intent: replace(intent, symbol=None),
        lambda intent: replace(intent, symbol="rawResponse"),
        lambda intent: replace(intent, state=None),
    ],
)
def test_execution_intent_collection_malformed_rows_fail_closed_with_sanitized_503(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutator
) -> None:
    path = tmp_path / f"malformed-intents-{uuid4()}.db"
    _prepare_database(path).dispose()
    valid = ExecutionIntent(
        environment="BINANCE_FUTURES_TESTNET",
        symbol="BTCUSDT",
        intent_type="PROTECTIVE_PAIR",
        state="PERSISTED",
    )

    class FakeRepository:
        def __init__(self, session) -> None:
            pass

        def list_recent(self, limit, offset=0):
            return [mutator(valid)]

    monkeypatch.setattr(service_module, "SqlAlchemyExecutionIntentRepository", FakeRepository)

    response = _client(_service(path)).get("/api/v1/live/execution-intents")
    body = json.dumps(response.json())

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "PERSISTENCE_UNAVAILABLE",
        "message": "Persistence read model is unavailable.",
        "details": {},
    }
    assert "rawResponse" not in body


def test_execution_intent_collection_provider_exception_is_sanitized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "provider-error.db"
    _prepare_database(path).dispose()

    class FakeRepository:
        def __init__(self, session) -> None:
            pass

        def list_recent(self, limit, offset=0):
            raise RuntimeError("postgresql://user:secret@db SELECT * FROM rawResponse traceback signature")

    monkeypatch.setattr(service_module, "SqlAlchemyExecutionIntentRepository", FakeRepository)

    response = _client(_service(path)).get("/api/v1/live/execution-intents")
    body = json.dumps(response.json())

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PERSISTENCE_UNAVAILABLE"
    for marker in ("postgresql://", "secret", "SELECT * FROM", "rawResponse", "traceback", "signature"):
        assert marker not in body


class RecordingSession(Session):
    commit_calls = 0
    flush_calls = 0

    def commit(self) -> None:
        type(self).commit_calls += 1
        raise AssertionError("read service must not commit")

    def flush(self, *args, **kwargs) -> None:
        type(self).flush_calls += 1
        raise AssertionError("read service must not flush")


def test_read_model_does_not_mutate_rows_commit_flush_or_journal(tmp_path: Path) -> None:
    path = tmp_path / "persistence.db"
    journal = tmp_path / "protective.json"
    journal.write_bytes(b'{"unchanged":true}')
    engine = _prepare_database(path)
    intent, pair = _seed(engine)
    with engine.connect() as connection:
        before = {
            "intent": connection.scalar(select(ExecutionIntentORM.version).where(ExecutionIntentORM.id == intent.id)),
            "pair": connection.scalar(select(ProtectivePairORM.version).where(ProtectivePairORM.id == pair.id)),
            "orders": connection.scalar(select(ExchangeOrderIdentityORM).count()) if False else None,
        }
    engine.dispose()

    RecordingSession.commit_calls = 0
    RecordingSession.flush_calls = 0
    client = _client(_service(path, session_factory=RecordingSession))
    assert client.get("/api/v1/live/execution-intents").status_code == 200
    assert client.get(f"/api/v1/live/execution-intents/{intent.correlation_id}").status_code == 200
    assert client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/orders").status_code == 200
    assert client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events").status_code == 200
    assert RecordingSession.commit_calls == 0
    assert RecordingSession.flush_calls == 0
    assert journal.read_bytes() == b'{"unchanged":true}'

    engine = _engine(path)
    with engine.connect() as connection:
        assert connection.scalar(select(ExecutionIntentORM.version).where(ExecutionIntentORM.id == intent.id)) == before["intent"]
        assert connection.scalar(select(ProtectivePairORM.version).where(ProtectivePairORM.id == pair.id)) == before["pair"]
        assert connection.scalar(select(RecoveryEventORM.id).where(RecoveryEventORM.protective_pair_id == pair.id)) is not None
        assert connection.scalar(select(AuditEventORM.id).where(AuditEventORM.correlation_id == intent.correlation_id)) is not None
    engine.dispose()


def test_persistence_responses_never_expose_database_or_sensitive_fields(tmp_path: Path) -> None:
    path = tmp_path / "persistence.db"
    engine = _prepare_database(path)
    intent, pair = _seed(engine)
    engine.dispose()
    database_url = f"sqlite:///{path}"
    client = _client(PersistenceReadModelService(env={"ICT_DATABASE_URL": database_url}, engine_factory=create_engine))
    responses = [
        client.get("/api/v1/live/persistence/status"),
        client.get("/api/v1/live/execution-intents"),
        client.get(f"/api/v1/live/execution-intents/{intent.correlation_id}"),
        client.get("/api/v1/live/exchange-orders"),
        client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}"),
        client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/orders"),
        client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events"),
    ]
    forbidden = (database_url, str(path), "api_key", "api_secret", "signature", "signed_url", "authorization", "headers", "raw_response", "metadata_json", "traceback")
    for response in responses:
        body = json.dumps(response.json()).casefold()
        assert all(item.casefold() not in body for item in forbidden)


@pytest.mark.parametrize(
    "hostile_value",
    [
        "rawResponse",
        "raw-response",
        "raw_response",
        "headers",
        "authenticatedHeaders",
        "signed-url",
        "signedUrl",
        "authorization",
        "apiKey",
        "apiSecret",
        "X-MBX-APIKEY",
        "signature",
        "databaseUrl",
        "connectionString",
        "SELECT * FROM execution_intents",
        "traceback text",
        "line-one\nline-two",
        "control\x01value",
    ],
)
def test_hostile_persisted_text_variants_fail_closed(hostile_value: str) -> None:
    service = PersistenceReadModelService(env={})

    with pytest.raises(PersistenceReadModelHTTPError) as exc:
        service._safe_text(hostile_value)

    assert exc.value.status_code == 503
    assert exc.value.code == "PERSISTENCE_UNAVAILABLE"
    assert hostile_value not in exc.value.message


def test_every_exposed_persisted_text_field_uses_fail_closed_validation() -> None:
    service = PersistenceReadModelService(env={})
    intent = ExecutionIntent(
        environment="BINANCE_FUTURES_TESTNET",
        symbol="BTCUSDT",
        intent_type="PROTECTIVE_PAIR",
        state="PERSISTED",
        failure_code="SAFE_CODE",
    )
    pair = ProtectivePair(
        pair_id="pair-safe",
        correlation_id=intent.correlation_id,
        execution_intent_id=intent.id,
        environment="BINANCE_FUTURES_TESTNET",
        symbol="BTCUSDT",
        position_side="BOTH",
        direction="LONG",
        quantity=Decimal("0.0016"),
        state="PAIR_ACTIVE",
        blocking_reason="SAFE_REASON",
    )
    order = _order(pair, "STOP", "safe-stop-id")
    recovery = RecoveryEvent(
        correlation_id=pair.correlation_id,
        protective_pair_id=pair.id,
        event_type="LOOKUP",
        from_state="PENDING",
        to_state="RECOVERY_REQUIRED",
        reason_code="SAFE_REASON",
        result="PASS",
    )
    audit = AuditEvent(
        correlation_id=pair.correlation_id,
        category="CONTROL_PLANE",
        action="READ",
        environment="BINANCE_FUTURES_TESTNET",
        symbol="BTCUSDT",
        result="PASS",
        error_code="SAFE_ERROR",
    )
    cases = [
        (service._intent_response, intent, field)
        for field in ("environment", "symbol", "intent_type", "state", "failure_code")
    ]
    cases.extend(
        (service._pair_response, pair, field)
        for field in ("pair_id", "environment", "symbol", "position_side", "direction", "state", "blocking_reason")
    )
    cases.extend(
        (service._order_response, order, field)
        for field in ("leg_type", "client_algo_id", "exchange_algo_id", "exchange_order_id", "status")
    )
    cases.extend(
        (service._recovery_event_response, recovery, field)
        for field in ("event_type", "from_state", "to_state", "reason_code", "result")
    )
    cases.extend(
        (service._audit_event_response, audit, field)
        for field in ("action", "result", "error_code")
    )

    for serializer, record, field in cases:
        hostile_record = replace(record)
        object.__setattr__(hostile_record, field, "rawResponse")
        with pytest.raises(PersistenceReadModelHTTPError):
            serializer(hostile_record)


def test_combined_event_pagination_is_complete_bounded_and_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "pagination.db"
    engine = _prepare_database(path)
    intent, pair = _seed(engine, include_orders=False, include_events=False)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        repository = SqlAlchemyRecoveryEventRepository(session)
        for index in range(130):
            repository.append(
                RecoveryEvent(
                    id=UUID(int=index + 1),
                    correlation_id=intent.correlation_id,
                    protective_pair_id=pair.id,
                    event_type=f"EVENT_{index:03d}",
                    result="PASS",
                    reason_code=f"EVENT_{index:03d}",
                    created_at=timestamp,
                )
            )
        session.commit()
    engine.dispose()
    client = _client(_service(path))

    first = client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events?limit=100&offset=0")
    second = client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events?limit=30&offset=100")

    assert first.status_code == 200
    assert second.status_code == 200
    combined = first.json()["events"] + second.json()["events"]
    assert [event["reason_code"] for event in combined] == [f"EVENT_{index:03d}" for index in range(130)]
    assert len({event["reason_code"] for event in combined}) == 130


def test_combined_event_pagination_merges_sources_and_nonzero_offsets(tmp_path: Path) -> None:
    path = tmp_path / "merged-pagination.db"
    engine = _prepare_database(path)
    intent, pair = _seed(engine, include_orders=False, include_events=False)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        recovery_repo = SqlAlchemyRecoveryEventRepository(session)
        audit_repo = SqlAlchemyAuditEventRepository(session)
        for index in range(3):
            recovery_repo.append(
                RecoveryEvent(
                    correlation_id=intent.correlation_id,
                    protective_pair_id=pair.id,
                    event_type=f"RECOVERY_{index}",
                    result="PASS",
                    created_at=start + timedelta(seconds=index * 2),
                )
            )
            audit_repo.append(
                AuditEvent(
                    correlation_id=intent.correlation_id,
                    category="CONTROL_PLANE",
                    action=f"AUDIT_{index}",
                    environment="BINANCE_FUTURES_TESTNET",
                    symbol="BTCUSDT",
                    result="PASS",
                    created_at=start + timedelta(seconds=index * 2 + 1),
                )
            )
        session.commit()
    engine.dispose()
    client = _client(_service(path))

    page = client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events?limit=3&offset=2")

    assert page.status_code == 200
    assert [(event["event_type"], event["action"]) for event in page.json()["events"]] == [
        ("RECOVERY_1", None),
        (None, "AUDIT_1"),
        ("RECOVERY_2", None),
    ]


def test_combined_event_pagination_equal_timestamp_cross_source_tie_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "equal-timestamp-cross-source.db"
    engine = _prepare_database(path)
    intent, pair = _seed(engine, include_orders=False, include_events=False)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    shared_id = UUID(int=1)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        SqlAlchemyRecoveryEventRepository(session).append(
            RecoveryEvent(
                id=shared_id,
                correlation_id=intent.correlation_id,
                protective_pair_id=pair.id,
                event_type="RECOVERY_EQUAL_TIME",
                result="PASS",
                created_at=timestamp,
            )
        )
        SqlAlchemyAuditEventRepository(session).append(
            AuditEvent(
                id=shared_id,
                correlation_id=intent.correlation_id,
                category="CONTROL_PLANE",
                action="AUDIT_EQUAL_TIME",
                environment="BINANCE_FUTURES_TESTNET",
                symbol="BTCUSDT",
                result="PASS",
                created_at=timestamp,
            )
        )
        session.commit()
    engine.dispose()
    client = _client(_service(path))

    first_call = client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events?limit=2&offset=0")
    second_call = client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events?limit=2&offset=0")
    first_page = client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events?limit=1&offset=0")
    second_page = client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events?limit=1&offset=1")

    expected = [
        ("AUDIT_EVENT", None, "AUDIT_EQUAL_TIME"),
        ("RECOVERY_EVENT", "RECOVERY_EQUAL_TIME", None),
    ]
    first_events = first_call.json()["events"]
    second_events = second_call.json()["events"]
    paged_events = first_page.json()["events"] + second_page.json()["events"]
    assert first_call.status_code == second_call.status_code == 200
    assert first_page.status_code == second_page.status_code == 200
    assert [(event["event_kind"], event["event_type"], event["action"]) for event in first_events] == expected
    assert second_events == first_events
    assert paged_events == first_events


@pytest.mark.parametrize(
    ("environment", "symbol"),
    [
        ("BINANCE_FUTURES_TESTNET", None),
        ("BINANCE_FUTURES_TESTNET", ""),
        ("BINANCE_FUTURES_TESTNET", "ETHUSDT"),
        ("BINANCE_FUTURES_PRODUCTION", "BTCUSDT"),
        ("MALFORMED", "BTCUSDT"),
    ],
)
def test_audit_event_scope_is_exact_and_fails_closed(tmp_path: Path, environment: str, symbol: str | None) -> None:
    path = tmp_path / f"audit-scope-{uuid4()}.db"
    engine = _prepare_database(path)
    intent, pair = _seed(engine, include_orders=False, include_events=False)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        SqlAlchemyAuditEventRepository(session).append(
            AuditEvent(
                correlation_id=intent.correlation_id,
                category="CONTROL_PLANE",
                action="READ",
                environment=environment,
                symbol=symbol,
                result="PASS",
            )
        )
        session.commit()
    engine.dispose()

    response = _client(_service(path)).get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events")

    assert response.status_code in {403, 503}
    assert response.json()["detail"]["code"] in {"PERSISTENCE_SCOPE_FORBIDDEN", "PERSISTENCE_UNAVAILABLE"}


def test_audit_events_require_exact_correlation_and_accept_exact_testnet_btc_scope(tmp_path: Path) -> None:
    path = tmp_path / "audit-correlation.db"
    engine = _prepare_database(path)
    intent, pair = _seed(engine, include_orders=False, include_events=False)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        repository = SqlAlchemyAuditEventRepository(session)
        repository.append(
            AuditEvent(
                correlation_id=uuid4(),
                category="CONTROL_PLANE",
                action="UNRELATED",
                environment="BINANCE_FUTURES_TESTNET",
                symbol="BTCUSDT",
                result="PASS",
            )
        )
        repository.append(
            AuditEvent(
                correlation_id=intent.correlation_id,
                category="CONTROL_PLANE",
                action="EXACT",
                environment="BINANCE_FUTURES_TESTNET",
                symbol="BTCUSDT",
                result="PASS",
            )
        )
        session.commit()
    engine.dispose()

    response = _client(_service(path)).get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events")

    assert response.status_code == 200
    assert [event["action"] for event in response.json()["events"]] == ["EXACT"]


@pytest.mark.parametrize("legs", [[], ["STOP"], ["TAKE_PROFIT"], ["STOP", "TAKE_PROFIT"]])
def test_order_identity_valid_cardinality_and_ordering(tmp_path: Path, legs: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / f"orders-{uuid4()}.db"
    engine = _prepare_database(path)
    _, pair = _seed(engine, include_orders=False, include_events=False)
    engine.dispose()
    orders = [_order(pair, leg, f"safe-{leg.lower()}") for leg in reversed(legs)]

    class FakeRepository:
        def __init__(self, session) -> None:
            pass

        def list_by_protective_pair_id(self, protective_pair_id, limit, offset=0):
            assert protective_pair_id == pair.id
            assert limit == 3
            return sorted(orders, key=lambda order: 0 if order.leg_type == "STOP" else 1)

    monkeypatch.setattr(service_module, "SqlAlchemyExchangeOrderIdentityRepository", FakeRepository)
    response = _client(_service(path)).get(f"/api/v1/live/protective-pairs/{pair.pair_id}/orders")

    assert response.status_code == 200
    assert [order["leg_type"] for order in response.json()["orders"]] == sorted(legs, key=lambda leg: 0 if leg == "STOP" else 1)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda pair: [_order(pair, "STOP", "stop-1"), _order(pair, "TAKE_PROFIT", "tp-1"), _order(pair, "STOP", "stop-2")],
        lambda pair: [_order(pair, "STOP", "stop-1"), _order(pair, "STOP", "stop-2")],
        lambda pair: [_order(pair, "TAKE_PROFIT", "tp-1"), _order(pair, "TAKE_PROFIT", "tp-2")],
        lambda pair: [_order(pair, "STOP", "same-id"), _order(pair, "TAKE_PROFIT", "same-id")],
        lambda pair: [replace(_order(pair, "STOP", "stop-1"), environment="BINANCE_FUTURES_PRODUCTION")],
        lambda pair: [replace(_order(pair, "STOP", "stop-1"), symbol="ETHUSDT")],
        lambda pair: [replace(_order(pair, "STOP", "stop-1"), protective_pair_id=uuid4())],
        lambda pair: [replace(_order(pair, "STOP", "stop-1"), client_algo_id=None)],
        lambda pair: [replace(_order(pair, "STOP", "stop-1"), status=None)],
    ],
)
def test_order_identity_malformed_sets_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutator) -> None:
    path = tmp_path / f"malformed-orders-{uuid4()}.db"
    engine = _prepare_database(path)
    _, pair = _seed(engine, include_orders=False, include_events=False)
    engine.dispose()
    orders = mutator(pair)

    class FakeRepository:
        def __init__(self, session) -> None:
            pass

        def list_by_protective_pair_id(self, protective_pair_id, limit, offset=0):
            return orders

    monkeypatch.setattr(service_module, "SqlAlchemyExchangeOrderIdentityRepository", FakeRepository)
    response = _client(_service(path)).get(f"/api/v1/live/protective-pairs/{pair.pair_id}/orders")

    assert response.status_code in {403, 503}


def test_third_unknown_persisted_order_is_not_silently_ignored(tmp_path: Path) -> None:
    path = tmp_path / "third-order.db"
    engine = _prepare_database(path)
    _, pair = _seed(engine, include_events=False)
    with engine.begin() as connection:
        connection.execute(
            ExchangeOrderIdentityORM.__table__.insert().values(
                id=uuid4(),
                protective_pair_id=pair.id,
                environment="BINANCE_FUTURES_TESTNET",
                symbol="BTCUSDT",
                leg_type="UNKNOWN",
                client_algo_id="malformed-third-order",
                status="NEW",
                trigger_price=Decimal("65000"),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                version=1,
            )
        )
    engine.dispose()

    response = _client(_service(path)).get(f"/api/v1/live/protective-pairs/{pair.pair_id}/orders")

    assert response.status_code == 503


def test_read_queries_issue_no_dml(tmp_path: Path) -> None:
    path = tmp_path / "no-dml.db"
    engine = _prepare_database(path)
    intent, pair = _seed(engine)
    engine.dispose()
    statements: list[str] = []

    def recording_engine(*args, **kwargs):
        read_engine = create_engine(*args, **kwargs)

        @event.listens_for(read_engine, "before_cursor_execute")
        def record_statement(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement.strip().upper())

        return read_engine

    service = PersistenceReadModelService(
        env={"ICT_DATABASE_URL": f"sqlite:///{path}"},
        engine_factory=recording_engine,
    )
    client = _client(service)
    assert client.get("/api/v1/live/execution-intents").status_code == 200
    assert client.get(f"/api/v1/live/execution-intents/{intent.correlation_id}").status_code == 200
    assert client.get("/api/v1/live/exchange-orders").status_code == 200
    assert client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/orders").status_code == 200
    assert client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events").status_code == 200

    assert statements
    assert all(not statement.startswith(("INSERT", "UPDATE", "DELETE")) for statement in statements)
    assert all("FOR UPDATE" not in statement for statement in statements)
    assert all("COUNT" not in statement for statement in statements)


def test_read_service_has_no_binance_alembic_or_journal_execution_path(tmp_path: Path) -> None:
    source = inspect.getsource(service_module).casefold()
    journal = tmp_path / "protective.json"
    journal.write_bytes(b'{"exact":"bytes"}')

    assert "infrastructure.exchanges" not in source
    assert "alembic.command" not in source
    assert "protective.json" not in source
    assert journal.read_bytes() == b'{"exact":"bytes"}'


def test_read_session_never_commits(tmp_path: Path) -> None:
    path = tmp_path / "no-commit.db"
    engine = _prepare_database(path)
    intent, _ = _seed(engine)
    engine.dispose()
    RecordingSession.commit_calls = 0

    client = _client(_service(path, session_factory=RecordingSession))
    response = client.get(f"/api/v1/live/execution-intents/{intent.correlation_id}")
    collection = client.get("/api/v1/live/execution-intents")
    orders = client.get("/api/v1/live/exchange-orders")

    assert response.status_code == 200
    assert collection.status_code == 200
    assert orders.status_code == 200
    assert RecordingSession.commit_calls == 0


def test_read_session_never_flushes(tmp_path: Path) -> None:
    path = tmp_path / "no-flush.db"
    engine = _prepare_database(path)
    _, pair = _seed(engine)
    engine.dispose()
    RecordingSession.flush_calls = 0

    client = _client(_service(path, session_factory=RecordingSession))
    response = client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/orders")
    collection = client.get("/api/v1/live/exchange-orders")

    assert response.status_code == 200
    assert collection.status_code == 200
    assert RecordingSession.flush_calls == 0


def test_internal_ids_are_hidden_from_every_record_response(tmp_path: Path) -> None:
    path = tmp_path / "hidden-ids.db"
    engine = _prepare_database(path)
    intent, pair = _seed(engine)
    engine.dispose()
    client = _client(_service(path))

    bodies = [
        client.get("/api/v1/live/execution-intents").json(),
        client.get(f"/api/v1/live/execution-intents/{intent.correlation_id}").json(),
        client.get("/api/v1/live/exchange-orders").json(),
        client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}").json(),
        client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/orders").json(),
        client.get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events").json(),
    ]
    serialized = json.dumps(bodies)

    assert str(intent.id) not in serialized
    assert str(pair.id) not in serialized
    assert "execution_intent_id" not in serialized
    assert "protective_pair_id" not in serialized


def test_audit_metadata_is_never_returned(tmp_path: Path) -> None:
    path = tmp_path / "hidden-metadata.db"
    engine = _prepare_database(path)
    _, pair = _seed(engine)
    engine.dispose()

    response = _client(_service(path)).get(f"/api/v1/live/protective-pairs/{pair.pair_id}/events")
    serialized = json.dumps(response.json())

    assert response.status_code == 200
    assert "metadata_json" not in serialized
    assert "hidden from read model" not in serialized
