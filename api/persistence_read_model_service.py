from __future__ import annotations

import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Callable, Iterator
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from infrastructure.persistence.execution_repositories import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyExchangeOrderIdentityRepository,
    SqlAlchemyExecutionIntentRepository,
    SqlAlchemyProtectivePairRepository,
    SqlAlchemyRecoveryEventRepository,
)
from infrastructure.persistence.schema_contract import PERSISTENCE_REVISION, validate_persistence_schema
from models.execution_persistence import AuditEvent, ExchangeOrderIdentity, ExecutionIntent, ProtectivePair, RecoveryEvent

PAIR_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
SAFE_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
FORBIDDEN_NORMALIZED_TEXT_MARKERS = (
    "apikey",
    "apisecret",
    "secret",
    "signature",
    "authorization",
    "password",
    "headers",
    "signedurl",
    "databaseurl",
    "connectionstring",
    "postgresql",
    "mysql",
    "sqlite",
    "http",
    "traceback",
    "rawresponse",
    "rawexchangeresponse",
    "exchangeresponse",
    "metadatajson",
    "ormrepr",
    "credentiallength",
    "selectfrom",
    "sql",
)


@dataclass
class PersistenceReadModelHTTPError(Exception):
    status_code: int
    code: str
    message: str


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class PersistenceReadModelService:
    """Read-only projection of Release 2.86 persistence; it is not a mutation source of truth."""

    def __init__(
        self,
        env: dict[str, str] | None = None,
        engine_factory: Callable[..., Any] = create_engine,
        session_factory: Callable[..., Session] = Session,
    ) -> None:
        self.env = os.environ if env is None else env
        self._engine_factory = engine_factory
        self._session_factory = session_factory

    def status(self) -> dict[str, Any]:
        url = self._database_url()
        response = self._status_response(configured=url is not None)
        if url is None:
            return response
        engine = None
        try:
            engine = self._engine_factory(url, future=True)
            with engine.connect() as connection:
                connection.execute(select(1)).scalar_one()
                schema_ready, revision = self._schema_state(connection)
            return self._status_response(configured=True, reachable=True, schema_ready=schema_ready, migration_revision=revision)
        except Exception:
            return self._status_response(configured=True)
        finally:
            if engine is not None:
                engine.dispose()

    def execution_intent(self, correlation_id: str) -> dict[str, Any]:
        parsed = self._parse_uuid(correlation_id)
        with self._read_session() as session:
            record = SqlAlchemyExecutionIntentRepository(session).get_by_correlation_id(parsed)
        if record is None:
            raise PersistenceReadModelHTTPError(404, "PERSISTENCE_NOT_FOUND", "Persistence record was not found.")
        self._require_supported_scope(record.environment, record.symbol)
        return self._intent_response(record)

    def execution_intents(self, limit: int | str = 50, offset: int | str = 0) -> dict[str, Any]:
        limit, offset = self._normalize_pagination(limit, offset)
        with self._read_session() as session:
            records = SqlAlchemyExecutionIntentRepository(session).list_recent(limit=limit, offset=offset)
        items = []
        for record in records:
            self._require_supported_scope(record.environment, record.symbol)
            items.append(self._intent_response(record))
        return {"items": items, "limit": limit, "offset": offset, "count": len(items), "updated_at": _now()}

    def protective_pair(self, pair_id: str) -> dict[str, Any]:
        return self._pair_response(self._load_pair(pair_id))

    def protective_pair_orders(self, pair_id: str) -> dict[str, Any]:
        pair = self._load_pair(pair_id)
        with self._read_session() as session:
            orders = SqlAlchemyExchangeOrderIdentityRepository(session).list_by_protective_pair_id(pair.id, limit=3)
        if len(orders) > 2:
            raise self._unavailable()
        seen_legs: set[str] = set()
        seen_client_algo_ids: set[str] = set()
        for order in orders:
            self._require_supported_scope(order.environment, order.symbol)
            if order.protective_pair_id != pair.id:
                raise self._unavailable()
            client_algo_id = self._safe_identifier(order.client_algo_id, max_length=80)
            if (
                order.leg_type not in {"STOP", "TAKE_PROFIT"}
                or order.leg_type in seen_legs
                or client_algo_id in seen_client_algo_ids
            ):
                raise self._unavailable()
            seen_legs.add(order.leg_type)
            seen_client_algo_ids.add(client_algo_id)
        return {"pair_id": self._safe_text(pair.pair_id), "orders": [self._order_response(order) for order in orders]}

    def protective_pair_events(self, pair_id: str, limit: int | str = 50, offset: int | str = 0) -> dict[str, Any]:
        limit, offset = self._normalize_pagination(limit, offset)
        pair = self._load_pair(pair_id)
        with self._read_session() as session:
            recovery_repo = SqlAlchemyRecoveryEventRepository(session)
            audit_repo = SqlAlchemyAuditEventRepository(session)
            recovery_events = self._paged_source(
                lambda page_limit, page_offset: recovery_repo.list_by_protective_pair_id(
                    pair.id, limit=page_limit, offset=page_offset
                ),
                lambda event: self._validated_recovery_timeline_entry(event, pair),
            )
            audit_events = self._paged_source(
                lambda page_limit, page_offset: audit_repo.list_by_correlation_id(
                    pair.correlation_id, limit=page_limit, offset=page_offset
                ),
                lambda event: self._validated_audit_timeline_entry(event, pair),
            )
            events = self._merge_timeline_page(recovery_events, audit_events, limit=limit, offset=offset)
        return {"pair_id": self._safe_text(pair.pair_id), "events": events, "limit": limit, "offset": offset}

    def _load_pair(self, pair_id: str) -> ProtectivePair:
        self._validate_pair_id(pair_id)
        with self._read_session() as session:
            pair = SqlAlchemyProtectivePairRepository(session).get_by_pair_id(pair_id)
        if pair is None:
            raise PersistenceReadModelHTTPError(404, "PERSISTENCE_NOT_FOUND", "Persistence record was not found.")
        self._require_supported_scope(pair.environment, pair.symbol)
        return pair

    @contextmanager
    def _read_session(self) -> Iterator[Session]:
        url = self._database_url()
        if url is None:
            raise self._unavailable()
        engine = None
        session = None
        try:
            engine = self._engine_factory(url, future=True)
            with engine.connect() as connection:
                connection.execute(select(1)).scalar_one()
                schema_ready, _ = self._schema_state(connection)
            if not schema_ready:
                raise PersistenceReadModelHTTPError(503, "PERSISTENCE_UNAVAILABLE", "Persistence read model is unavailable.")
            session = self._session_factory(bind=engine, future=True, autoflush=False, expire_on_commit=False)
            yield session
        except PersistenceReadModelHTTPError:
            raise
        except Exception as exc:
            if session is not None:
                session.rollback()
            raise self._unavailable() from exc
        finally:
            if session is not None:
                session.close()
            if engine is not None:
                engine.dispose()

    def _database_url(self) -> str | None:
        return self.env.get("ICT_DATABASE_URL") or self.env.get("DATABASE_URL")

    def _schema_state(self, connection: Any) -> tuple[bool, str | None]:
        if not validate_persistence_schema(connection):
            return False, None
        return True, PERSISTENCE_REVISION

    def _status_response(
        self,
        configured: bool,
        reachable: bool = False,
        schema_ready: bool = False,
        migration_revision: str | None = None,
    ) -> dict[str, Any]:
        return {
            "configured": configured,
            "reachable": reachable,
            "schema_ready": schema_ready,
            "migration_revision": migration_revision,
            "read_only": True,
            "source_of_truth": False,
            "updated_at": _now(),
        }

    def _parse_uuid(self, value: str) -> UUID:
        try:
            parsed = UUID(value)
        except (TypeError, ValueError) as exc:
            raise PersistenceReadModelHTTPError(400, "INVALID_PERSISTENCE_IDENTIFIER", "Persistence identifier is invalid.") from exc
        if str(parsed) != value.lower():
            raise PersistenceReadModelHTTPError(400, "INVALID_PERSISTENCE_IDENTIFIER", "Persistence identifier is invalid.")
        return parsed

    def _validate_pair_id(self, pair_id: str) -> None:
        if not isinstance(pair_id, str) or PAIR_ID_PATTERN.fullmatch(pair_id) is None:
            raise PersistenceReadModelHTTPError(400, "INVALID_PERSISTENCE_IDENTIFIER", "Persistence identifier is invalid.")

    def _normalize_pagination(self, limit: int | str, offset: int | str) -> tuple[int, int]:
        limit = self._parse_pagination_value(limit)
        offset = self._parse_pagination_value(offset)
        self._validate_pagination(limit, offset)
        return limit, offset

    def _parse_pagination_value(self, value: int | str) -> int:
        if isinstance(value, bool):
            raise PersistenceReadModelHTTPError(400, "INVALID_PERSISTENCE_PAGINATION", "Persistence pagination is invalid.")
        if isinstance(value, int):
            return value
        if not isinstance(value, str) or not value.isdecimal():
            raise PersistenceReadModelHTTPError(400, "INVALID_PERSISTENCE_PAGINATION", "Persistence pagination is invalid.")
        return int(value)

    def _validate_pagination(self, limit: int, offset: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise PersistenceReadModelHTTPError(400, "INVALID_PERSISTENCE_PAGINATION", "Persistence pagination is invalid.")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise PersistenceReadModelHTTPError(400, "INVALID_PERSISTENCE_PAGINATION", "Persistence pagination is invalid.")

    def _require_supported_scope(self, environment: Any, symbol: Any) -> None:
        if not isinstance(environment, str) or not isinstance(symbol, str):
            raise self._unavailable()
        self._safe_code(environment, max_length=64)
        self._safe_code(symbol, max_length=32)
        if environment != "BINANCE_FUTURES_TESTNET" or symbol != "BTCUSDT":
            raise PersistenceReadModelHTTPError(403, "PERSISTENCE_SCOPE_FORBIDDEN", "Persistence scope is forbidden.")

    def _paged_source(
        self,
        fetch_page: Callable[[int, int], list[Any]],
        serialize: Callable[[Any], tuple[tuple[str, str, str], dict[str, Any]]],
    ) -> Iterator[tuple[tuple[str, str, str], dict[str, Any]]]:
        page_offset = 0
        page_size = 100
        while True:
            page = fetch_page(page_size, page_offset)
            for event in page:
                yield serialize(event)
            if len(page) < page_size:
                return
            page_offset += page_size

    def _validated_recovery_timeline_entry(
        self, event: RecoveryEvent, pair: ProtectivePair
    ) -> tuple[tuple[str, str, str], dict[str, Any]]:
        if event.protective_pair_id != pair.id or event.correlation_id != pair.correlation_id:
            raise self._unavailable()
        timestamp = self._timestamp(event.created_at)
        return (timestamp, self._uuid_text(event.id), "RECOVERY_EVENT"), self._recovery_event_response(event)

    def _validated_audit_timeline_entry(
        self, event: AuditEvent, pair: ProtectivePair
    ) -> tuple[tuple[str, str, str], dict[str, Any]]:
        if event.correlation_id != pair.correlation_id:
            raise self._unavailable()
        self._require_supported_scope(event.environment, event.symbol)
        timestamp = self._timestamp(event.created_at)
        return (timestamp, self._uuid_text(event.id), "AUDIT_EVENT"), self._audit_event_response(event)

    def _merge_timeline_page(
        self,
        recovery_events: Iterator[tuple[tuple[str, str, str], dict[str, Any]]],
        audit_events: Iterator[tuple[tuple[str, str, str], dict[str, Any]]],
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        sentinel = object()
        recovery_item: Any = next(recovery_events, sentinel)
        audit_item: Any = next(audit_events, sentinel)
        skipped = 0
        page: list[dict[str, Any]] = []
        while len(page) < limit and (recovery_item is not sentinel or audit_item is not sentinel):
            if audit_item is sentinel or (recovery_item is not sentinel and recovery_item[0] <= audit_item[0]):
                item = recovery_item
                recovery_item = next(recovery_events, sentinel)
            else:
                item = audit_item
                audit_item = next(audit_events, sentinel)
            if skipped < offset:
                skipped += 1
            else:
                page.append(item[1])
        return page

    def _intent_response(self, record: ExecutionIntent) -> dict[str, Any]:
        return {
            "correlation_id": self._uuid_text(record.correlation_id),
            "environment": self._safe_code(record.environment, max_length=64),
            "symbol": self._safe_code(record.symbol, max_length=32),
            "intent_type": self._safe_code(record.intent_type, max_length=64),
            "state": self._safe_code(record.state, max_length=32),
            "requested_quantity": self._decimal(record.requested_quantity),
            "requested_price": self._decimal(record.requested_price),
            "failure_code": self._safe_code(record.failure_code, nullable=True, max_length=128),
            "version": self._version(record.version),
            "created_at": self._timestamp(record.created_at),
            "updated_at": self._timestamp(record.updated_at),
        }

    def _pair_response(self, record: ProtectivePair) -> dict[str, Any]:
        return {
            "pair_id": self._safe_text(record.pair_id),
            "correlation_id": self._uuid_text(record.correlation_id),
            "environment": self._safe_code(record.environment, max_length=64),
            "symbol": self._safe_code(record.symbol, max_length=32),
            "position_side": self._safe_code(record.position_side, max_length=16),
            "direction": self._safe_code(record.direction, max_length=16),
            "quantity": self._decimal(record.quantity),
            "state": self._safe_code(record.state, max_length=32),
            "recovery_required": self._boolean(record.recovery_required),
            "blocking_reason": self._safe_text(record.blocking_reason, nullable=True),
            "version": self._version(record.version),
            "created_at": self._timestamp(record.created_at),
            "updated_at": self._timestamp(record.updated_at),
        }

    def _order_response(self, record: ExchangeOrderIdentity) -> dict[str, Any]:
        return {
            "leg_type": self._safe_code(record.leg_type, max_length=16),
            "client_algo_id": self._safe_identifier(record.client_algo_id, max_length=80),
            "exchange_algo_id": self._safe_identifier(record.exchange_algo_id, nullable=True, max_length=80),
            "exchange_order_id": self._safe_identifier(record.exchange_order_id, nullable=True, max_length=80),
            "status": self._safe_code(record.status, max_length=32),
            "trigger_price": self._decimal(record.trigger_price),
            "version": self._version(record.version),
            "created_at": self._timestamp(record.created_at),
            "updated_at": self._timestamp(record.updated_at),
        }

    def _recovery_event_response(self, event: RecoveryEvent) -> dict[str, Any]:
        return {
            "event_kind": "RECOVERY_EVENT",
            "correlation_id": self._uuid_text(event.correlation_id),
            "event_type": self._safe_code(event.event_type, max_length=80),
            "action": None,
            "from_state": self._safe_code(event.from_state, nullable=True, max_length=32),
            "to_state": self._safe_code(event.to_state, nullable=True, max_length=32),
            "reason_code": self._safe_code(event.reason_code, nullable=True, max_length=128),
            "result": self._safe_code(event.result, max_length=32),
            "error_code": None,
            "created_at": self._timestamp(event.created_at),
        }

    def _audit_event_response(self, event: AuditEvent) -> dict[str, Any]:
        return {
            "event_kind": "AUDIT_EVENT",
            "correlation_id": None if event.correlation_id is None else self._uuid_text(event.correlation_id),
            "event_type": None,
            "action": self._safe_code(event.action, max_length=80),
            "from_state": None,
            "to_state": None,
            "reason_code": None,
            "result": self._safe_code(event.result, max_length=32),
            "error_code": self._safe_code(event.error_code, nullable=True, max_length=128),
            "created_at": self._timestamp(event.created_at),
        }

    def _safe_text(self, value: Any, nullable: bool = False) -> str | None:
        if value is None and nullable:
            return None
        if not isinstance(value, str) or len(value) > 256:
            raise self._unavailable()
        self._reject_unsafe_text(value)
        return value

    def _safe_code(self, value: Any, nullable: bool = False, max_length: int = 128) -> str | None:
        if value is None and nullable:
            return None
        if not isinstance(value, str) or not 1 <= len(value) <= max_length or SAFE_CODE_PATTERN.fullmatch(value) is None:
            raise self._unavailable()
        self._reject_unsafe_text(value)
        return value

    def _safe_identifier(self, value: Any, nullable: bool = False, max_length: int = 80) -> str | None:
        if value is None and nullable:
            return None
        if not isinstance(value, str) or not 1 <= len(value) <= max_length or SAFE_IDENTIFIER_PATTERN.fullmatch(value) is None:
            raise self._unavailable()
        self._reject_unsafe_text(value)
        return value

    def _reject_unsafe_text(self, value: str) -> None:
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise self._unavailable()
        normalized = re.sub(r"[^a-z0-9]+", "", value.casefold())
        if any(marker in normalized for marker in FORBIDDEN_NORMALIZED_TEXT_MARKERS):
            raise self._unavailable()

    def _uuid_text(self, value: Any) -> str:
        if not isinstance(value, UUID):
            raise self._unavailable()
        return str(value)

    def _decimal(self, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, Decimal) or not value.is_finite():
            raise self._unavailable()
        return format(value, "f")

    def _timestamp(self, value: Any) -> str:
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise self._unavailable()
        return value.astimezone(UTC).isoformat()

    def _version(self, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise self._unavailable()
        return value

    def _boolean(self, value: Any) -> bool:
        if not isinstance(value, bool):
            raise self._unavailable()
        return value

    @staticmethod
    def _unavailable() -> PersistenceReadModelHTTPError:
        return PersistenceReadModelHTTPError(503, "PERSISTENCE_UNAVAILABLE", "Persistence read model is unavailable.")
