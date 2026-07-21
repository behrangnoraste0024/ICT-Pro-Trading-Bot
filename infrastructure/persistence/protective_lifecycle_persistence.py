from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Iterator
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import create_engine, or_, select
from sqlalchemy.orm import Session

from infrastructure.persistence.execution_orm import AuditEventORM, ExchangeOrderIdentityORM, ProtectivePairORM
from infrastructure.persistence.execution_repositories import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyExchangeOrderIdentityRepository,
    SqlAlchemyExecutionIntentRepository,
    SqlAlchemyProtectivePairRepository,
    SqlAlchemyRecoveryEventRepository,
)
from infrastructure.persistence.schema_contract import validate_persistence_schema
from models.binance_futures_testnet_protective_orders import (
    BinanceFuturesTestnetProtectiveAlgoSummary,
    BinanceFuturesTestnetProtectiveJournal,
    BinanceFuturesTestnetProtectivePosition,
    BinanceFuturesTestnetProtectivePreview,
    ProtectiveMutationIntent,
    ProtectiveReconciliationResult,
)
from models.execution_persistence import (
    AuditEvent,
    DuplicateIdentityError,
    ExchangeOrderIdentity,
    ExecutionIntent,
    OptimisticLockError,
    ProtectivePair,
    RecoveryEvent,
)

ENVIRONMENT = "BINANCE_FUTURES_TESTNET"
SYMBOL = "BTCUSDT"
UNRESOLVED_PAIR_STATES = {"PENDING", "STOP_ACTIVE", "PAIR_ACTIVE", "CANCEL_PENDING", "RECOVERY_REQUIRED"}
TERMINAL_PAIR_STATES = {"RECOVERED", "COMPLETED", "FAILED_SAFE"}
PROTECTIVE_CLIENT_ID_PREFIX = "smcbot-protect-"
PROTECTIVE_IDENTITY_STATUSES = {"NEW", "ABSENT", "CANCELED", "EXPIRED", "REJECTED"}


class ProtectivePersistenceError(RuntimeError):
    def __init__(self, code: str, *, after_transport: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.after_transport = after_transport


@dataclass
class ProtectivePersistenceState:
    pair_id: UUID
    create_intent_id: UUID
    create_correlation_id: UUID
    stop_cancel_intent_id: UUID
    stop_cancel_correlation_id: UUID
    take_profit_cancel_intent_id: UUID
    take_profit_cancel_correlation_id: UUID
    stop_client_algo_id: str
    take_profit_client_algo_id: str


@dataclass(frozen=True)
class ProtectiveConsistencyResult:
    status: str
    state: ProtectivePersistenceState | None = None
    pair_state: str | None = None
    pair_recovery_required: bool | None = None
    correlation_id: UUID | None = None


class ProtectiveLifecyclePersistence:
    """Short, explicit persistence transactions around the journal-led lifecycle."""

    def __init__(
        self,
        env: dict[str, str] | None = None,
        engine_factory: Callable[..., Any] = create_engine,
        session_factory: Callable[..., Session] = Session,
    ) -> None:
        self.env = os.environ if env is None else env
        self._engine_factory = engine_factory
        self._session_factory = session_factory
        self._engine: Any | None = None

    def ensure_available(self) -> None:
        url = self.env.get("ICT_DATABASE_URL") or self.env.get("DATABASE_URL")
        if not isinstance(url, str) or not url.strip():
            raise ProtectivePersistenceError("PERSISTENCE_UNAVAILABLE")
        try:
            engine = self._engine_factory(url, future=True)
            with engine.connect() as connection:
                connection.execute(select(1)).scalar_one()
                if not validate_persistence_schema(connection):
                    raise ProtectivePersistenceError("PERSISTENCE_SCHEMA_INVALID")
            self._engine = engine
        except ProtectivePersistenceError:
            if "engine" in locals():
                engine.dispose()
            raise
        except Exception as exc:
            if "engine" in locals():
                engine.dispose()
            raise ProtectivePersistenceError("PERSISTENCE_UNAVAILABLE") from exc

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def check_consistency(
        self,
        journal: BinanceFuturesTestnetProtectiveJournal | None,
        pair_id: str,
        stop_client_algo_id: str,
        take_profit_client_algo_id: str,
    ) -> ProtectiveConsistencyResult:
        try:
            with self._session() as session:
                pairs = list(
                    session.scalars(
                        select(ProtectivePairORM)
                        .where(
                            ProtectivePairORM.environment == ENVIRONMENT,
                            ProtectivePairORM.symbol == SYMBOL,
                            ProtectivePairORM.state.in_(UNRESOLVED_PAIR_STATES),
                        )
                        .order_by(ProtectivePairORM.created_at.asc(), ProtectivePairORM.id.asc())
                        .limit(3)
                    ).all()
                )
                if len(pairs) > 1:
                    raise ProtectivePersistenceError("PERSISTENCE_MULTIPLE_UNRESOLVED")
                pair = SqlAlchemyProtectivePairRepository(session).get_by_pair_id(pair_id)
                if journal is None:
                    if pairs:
                        raise ProtectivePersistenceError("PERSISTENCE_DB_ONLY_UNRESOLVED")
                    if pair is None:
                        return ProtectiveConsistencyResult("FRESH")
                    self._validate_pair_scope(pair)
                    state = self._state(pair, stop_client_algo_id, take_profit_client_algo_id)
                    self._validate_persisted_ids(session, pair, stop_client_algo_id, take_profit_client_algo_id, None)
                    if pair.state == "COMPLETED" and not pair.recovery_required:
                        return ProtectiveConsistencyResult(
                            "ALREADY_COMPLETED", state, pair.state, pair.recovery_required, pair.correlation_id
                        )
                    raise ProtectivePersistenceError("PERSISTENCE_REPLAY_BLOCKED")
                if pair is None:
                    raise ProtectivePersistenceError("PERSISTENCE_JOURNAL_ONLY_UNRESOLVED")
                self._validate_pair_scope(pair)
                if journal.pair_id != pair.pair_id or journal.pair_id != pair_id:
                    raise ProtectivePersistenceError("PERSISTENCE_PAIR_MISMATCH")
                if journal.recovery_required and pair.state not in UNRESOLVED_PAIR_STATES:
                    raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH")
                if not journal.recovery_required and journal.phase in {"COMPLETE", "RECOVERY_COMPLETE"} and pair.state in UNRESOLVED_PAIR_STATES:
                    raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH")
                self._validate_persisted_ids(session, pair, stop_client_algo_id, take_profit_client_algo_id, journal)
                state = self._state(pair, stop_client_algo_id, take_profit_client_algo_id)
                if journal.phase in {"COMPLETE", "RECOVERY_COMPLETE"} and pair.state == "COMPLETED" and not pair.recovery_required:
                    return ProtectiveConsistencyResult(
                        "ALREADY_COMPLETED", state, pair.state, pair.recovery_required, pair.correlation_id
                    )
                return ProtectiveConsistencyResult(
                    "RECOVERY", state, pair.state, pair.recovery_required, pair.correlation_id
                )
        except ProtectivePersistenceError:
            raise
        except Exception as exc:
            raise ProtectivePersistenceError("PERSISTENCE_CONSISTENCY_UNAVAILABLE") from exc

    def validate_durable_projection_integrity(self, session: Session) -> None:
        """Validate every protective projection without changing durable state."""
        last_id = None
        while True:
            statement = select(ProtectivePairORM).order_by(ProtectivePairORM.id.asc()).limit(50)
            if last_id is not None:
                statement = statement.where(ProtectivePairORM.id > last_id)
            rows = session.scalars(statement).all()
            if not rows:
                self._validate_global_identity_owners(session)
                return
            for row in rows:
                pair = SqlAlchemyProtectivePairRepository(session).get_by_id(row.id)
                if pair is None:
                    raise ProtectivePersistenceError("PERSISTENCE_PAIR_MISSING")
                self._validate_pair_scope(pair)
                audits = session.scalars(
                    select(AuditEventORM)
                    .where(
                        AuditEventORM.correlation_id == pair.correlation_id,
                        AuditEventORM.action == "INTENT_PERSISTED",
                    )
                    .order_by(AuditEventORM.created_at.asc(), AuditEventORM.id.asc())
                    .limit(2)
                ).all()
                if len(audits) != 1 or not isinstance(audits[0].metadata_json, dict):
                    raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_MISSING")
                metadata = audits[0].metadata_json
                stop_id = metadata.get("stop_client_algo_id")
                take_id = metadata.get("take_profit_client_algo_id")
                self._validate_protective_client_id(stop_id)
                self._validate_protective_client_id(take_id)
                if stop_id == take_id:
                    raise ProtectivePersistenceError("PERSISTENCE_CLIENT_ID_MISMATCH")
                self._validate_persisted_ids(
                    session,
                    pair,
                    stop_id,
                    take_id,
                    None,
                    validate_state_matrix=False,
                    exact_identity_status=False,
                    validate_cancel_projection=False,
                )
            last_id = rows[-1].id

    def _validate_global_identity_owners(self, session: Session) -> None:
        orphan = session.scalar(
            select(ExchangeOrderIdentityORM.id)
            .outerjoin(
                ProtectivePairORM,
                ExchangeOrderIdentityORM.protective_pair_id == ProtectivePairORM.id,
            )
            .where(ProtectivePairORM.id.is_(None))
            .limit(1)
        )
        if orphan is not None:
            raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_ORPHANED")

        malformed = session.scalar(
            select(ExchangeOrderIdentityORM.id)
            .where(
                or_(
                    ExchangeOrderIdentityORM.environment != ENVIRONMENT,
                    ExchangeOrderIdentityORM.symbol != SYMBOL,
                    ~ExchangeOrderIdentityORM.leg_type.in_({"STOP", "TAKE_PROFIT"}),
                    ~ExchangeOrderIdentityORM.status.in_(PROTECTIVE_IDENTITY_STATUSES),
                )
            )
            .limit(1)
        )
        if malformed is not None:
            raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_MISMATCH")

        last_id = None
        while True:
            statement = select(ExchangeOrderIdentityORM).order_by(ExchangeOrderIdentityORM.id.asc()).limit(50)
            if last_id is not None:
                statement = statement.where(ExchangeOrderIdentityORM.id > last_id)
            rows = session.scalars(statement).all()
            if not rows:
                return
            for identity in rows:
                self._validate_protective_client_id(identity.client_algo_id)
            last_id = rows[-1].id

    def prepare_lifecycle(
        self,
        pair_id: str,
        stop_client_algo_id: str,
        take_profit_client_algo_id: str,
        position: BinanceFuturesTestnetProtectivePosition,
        preview: BinanceFuturesTestnetProtectivePreview,
    ) -> ProtectivePersistenceState:
        state = self._deterministic_state(pair_id, stop_client_algo_id, take_profit_client_algo_id)
        create_intent = ExecutionIntent(
            id=state.create_intent_id,
            correlation_id=state.create_correlation_id,
            environment=ENVIRONMENT,
            symbol=SYMBOL,
            intent_type="PROTECTIVE_PAIR_CREATE",
            state="PERSISTED",
            requested_quantity=abs(position.position_amt),
            requested_price=position.mark_price,
        )
        pair = ProtectivePair(
            id=state.pair_id,
            pair_id=pair_id,
            correlation_id=state.create_correlation_id,
            execution_intent_id=state.create_intent_id,
            environment=ENVIRONMENT,
            symbol=SYMBOL,
            position_side=position.position_side,
            direction=position.direction,
            quantity=abs(position.position_amt),
            state="PENDING",
        )
        audit = self._audit(
            state.create_correlation_id,
            "INTENT_PERSISTED",
            "PASS",
            {
                "pair_id": pair_id,
                "stop_client_algo_id": stop_client_algo_id,
                "take_profit_client_algo_id": take_profit_client_algo_id,
                "stop_trigger": self._decimal_text(preview.stop_trigger),
                "take_profit_trigger": self._decimal_text(preview.take_profit_trigger),
                "position_side": position.position_side,
                "direction": position.direction,
                "quantity": self._decimal_text(abs(position.position_amt)),
                "requested_price": self._decimal_text(position.mark_price),
            },
        )
        try:
            with self._transaction() as session:
                if SqlAlchemyProtectivePairRepository(session).get_by_pair_id(pair_id) is not None:
                    raise ProtectivePersistenceError("PERSISTENCE_DUPLICATE_PAIR")
                SqlAlchemyExecutionIntentRepository(session).create(create_intent)
                SqlAlchemyProtectivePairRepository(session).create(pair)
                SqlAlchemyAuditEventRepository(session).append(audit)
            return state
        except ProtectivePersistenceError:
            raise
        except (DuplicateIdentityError, OptimisticLockError) as exc:
            raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_CONFLICT") from exc
        except Exception as exc:
            raise ProtectivePersistenceError("PERSISTENCE_COMMIT_FAILED") from exc

    def mark_create_transmitted(self, state: ProtectivePersistenceState) -> None:
        self._transition_intent(state.create_intent_id, "TRANSMITTED", "MUTATION_TRANSMITTED", state.create_correlation_id, after_transport=True)

    def confirm_create(
        self,
        state: ProtectivePersistenceState,
        label: str,
        order: BinanceFuturesTestnetProtectiveAlgoSummary,
    ) -> None:
        target_pair_state = "STOP_ACTIVE" if label == "STOP" else "PAIR_ACTIVE"
        try:
            with self._transaction() as session:
                pair_repo = SqlAlchemyProtectivePairRepository(session)
                intent_repo = SqlAlchemyExecutionIntentRepository(session)
                identity_repo = SqlAlchemyExchangeOrderIdentityRepository(session)
                pair = self._require_pair(pair_repo, state.pair_id)
                expected_source_states = {"PENDING", "RECOVERY_REQUIRED"} if label == "STOP" else {"STOP_ACTIVE", "RECOVERY_REQUIRED"}
                if pair.state not in expected_source_states | {target_pair_state}:
                    raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH", after_transport=True)
                expected_client_id = state.stop_client_algo_id if label == "STOP" else state.take_profit_client_algo_id
                existing = identity_repo.get_by_client_algo_id(ENVIRONMENT, SYMBOL, expected_client_id)
                if existing is None:
                    identity_repo.create(
                        ExchangeOrderIdentity(
                            protective_pair_id=state.pair_id,
                            environment=ENVIRONMENT,
                            symbol=SYMBOL,
                            leg_type=label,
                            client_algo_id=expected_client_id,
                            exchange_algo_id=order.algo_id,
                            exchange_order_id=order.actual_order_id,
                            status=str(order.algo_status or "UNKNOWN"),
                            trigger_price=order.trigger_price,
                        )
                    )
                else:
                    self._validate_identity(
                        existing,
                        state.pair_id,
                        label,
                        expected_client_id,
                        order.trigger_price,
                        exchange_algo_id=order.algo_id,
                        exchange_order_id=order.actual_order_id,
                        status=str(order.algo_status or "UNKNOWN"),
                        exact_exchange_fields=True,
                    )
                if pair.state != target_pair_state or pair.recovery_required:
                    pair = pair_repo.update_state(pair.id, pair.version, target_pair_state, recovery_required=False)
                if label == "TAKE_PROFIT":
                    intent = self._require_intent(intent_repo, state.create_intent_id)
                    if intent.state not in {"TRANSMITTED", "RECOVERY_REQUIRED", "COMPLETED"}:
                        raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH", after_transport=True)
                    if intent.state != "COMPLETED":
                        intent_repo.update_state(intent.id, intent.version, "COMPLETED")
                SqlAlchemyAuditEventRepository(session).append(
                    self._audit(
                        state.create_correlation_id,
                        "CREATE_CONFIRMED",
                        "PASS",
                        {
                            "pair_id": pair.pair_id,
                            "leg_type": label,
                            "client_algo_id": expected_client_id,
                            "exchange_algo_id": order.algo_id,
                            "exchange_order_id": order.actual_order_id,
                            "trigger_price": self._decimal_text(order.trigger_price),
                            "status": str(order.algo_status or "UNKNOWN"),
                        },
                    )
                )
        except ProtectivePersistenceError:
            raise
        except (DuplicateIdentityError, OptimisticLockError) as exc:
            raise ProtectivePersistenceError("PERSISTENCE_VERSION_CONFLICT", after_transport=True) from exc
        except Exception as exc:
            raise ProtectivePersistenceError("PERSISTENCE_POST_TRANSPORT_FAILED", after_transport=True) from exc

    def prepare_cancel(self, state: ProtectivePersistenceState, label: str, quantity: Decimal, price: Decimal | None) -> None:
        intent_id, correlation_id = self._cancel_identity(state, label)
        client_id = state.stop_client_algo_id if label == "STOP" else state.take_profit_client_algo_id
        cancel_intent = ExecutionIntent(
            id=intent_id,
            correlation_id=correlation_id,
            environment=ENVIRONMENT,
            symbol=SYMBOL,
            intent_type="PROTECTIVE_PAIR_CANCEL",
            state="PERSISTED",
            requested_quantity=abs(quantity),
            requested_price=price,
        )
        try:
            with self._transaction() as session:
                intent_repo = SqlAlchemyExecutionIntentRepository(session)
                pair_repo = SqlAlchemyProtectivePairRepository(session)
                existing_intent = intent_repo.get_by_id(intent_id)
                pair = self._require_pair(pair_repo, state.pair_id)
                self._require_intent(intent_repo, state.create_intent_id)
                if abs(quantity) != pair.quantity:
                    raise ProtectivePersistenceError("PERSISTENCE_REPLAY_MISMATCH")
                if existing_intent is None:
                    if pair.state not in {"STOP_ACTIVE", "PAIR_ACTIVE", "CANCEL_PENDING", "RECOVERY_REQUIRED"}:
                        raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH")
                    intent_repo.create(cancel_intent)
                    if pair.state != "CANCEL_PENDING" or pair.recovery_required:
                        pair_repo.update_state(pair.id, pair.version, "CANCEL_PENDING", recovery_required=False)
                    SqlAlchemyAuditEventRepository(session).append(
                        self._audit(correlation_id, "INTENT_PERSISTED", "PASS", {"pair_id": pair.pair_id, "intent_type": "PROTECTIVE_PAIR_CANCEL", "leg_type": label, "client_algo_id": client_id})
                    )
                else:
                    self._validate_cancel_intent(existing_intent, state, label, quantity, price)
                    if pair.state not in {"CANCEL_PENDING", "RECOVERY_REQUIRED"}:
                        raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH")
        except ProtectivePersistenceError:
            raise
        except (DuplicateIdentityError, OptimisticLockError) as exc:
            raise ProtectivePersistenceError("PERSISTENCE_VERSION_CONFLICT") from exc
        except Exception as exc:
            raise ProtectivePersistenceError("PERSISTENCE_COMMIT_FAILED") from exc

    def mark_cancel_transmitted(self, state: ProtectivePersistenceState, label: str) -> None:
        intent_id, correlation_id = self._cancel_identity(state, label)
        try:
            with self._transaction() as session:
                repo = SqlAlchemyExecutionIntentRepository(session)
                intent = self._require_intent(repo, intent_id)
                if intent.state in {"PERSISTED", "RECOVERY_REQUIRED"}:
                    repo.update_state(intent.id, intent.version, "TRANSMITTED")
                    SqlAlchemyAuditEventRepository(session).append(
                        self._audit(correlation_id, "MUTATION_TRANSMITTED", "PASS", {"intent_type": "PROTECTIVE_PAIR_CANCEL", "leg_type": label})
                    )
                elif intent.state != "TRANSMITTED":
                    raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH", after_transport=True)
        except ProtectivePersistenceError:
            raise
        except OptimisticLockError as exc:
            raise ProtectivePersistenceError("PERSISTENCE_VERSION_CONFLICT", after_transport=True) from exc
        except Exception as exc:
            raise ProtectivePersistenceError("PERSISTENCE_POST_TRANSPORT_FAILED", after_transport=True) from exc

    def confirm_delete(self, state: ProtectivePersistenceState, label: str, status: str, complete: bool) -> None:
        intent_id, correlation_id = self._cancel_identity(state, label)
        try:
            with self._transaction() as session:
                identity_repo = SqlAlchemyExchangeOrderIdentityRepository(session)
                pair_repo = SqlAlchemyProtectivePairRepository(session)
                intent_repo = SqlAlchemyExecutionIntentRepository(session)
                client_id = state.stop_client_algo_id if label == "STOP" else state.take_profit_client_algo_id
                identity = identity_repo.get_by_client_algo_id(ENVIRONMENT, SYMBOL, client_id)
                if identity is None:
                    raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_MISSING", after_transport=True)
                self._validate_identity(identity, state.pair_id, label, client_id, identity.trigger_price)
                if identity.status != status:
                    identity_repo.update_status(identity.id, identity.version, status)
                pair = self._require_pair(pair_repo, state.pair_id)
                if pair.state not in {"CANCEL_PENDING", "RECOVERY_REQUIRED", "COMPLETED"}:
                    raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH", after_transport=True)
                intent = self._require_intent(intent_repo, intent_id)
                if intent.state not in {"TRANSMITTED", "RECOVERY_REQUIRED", "COMPLETED"}:
                    raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH", after_transport=True)
                if intent.state != "COMPLETED":
                    intent_repo.update_state(intent.id, intent.version, "COMPLETED")
                if complete:
                    if pair.state != "COMPLETED" or pair.recovery_required:
                        pair_repo.update_state(pair.id, pair.version, "COMPLETED", recovery_required=False)
                    create_intent = self._require_intent(intent_repo, state.create_intent_id)
                    if create_intent.state not in {"COMPLETED", "FAILED_SAFE"}:
                        intent_repo.update_state(create_intent.id, create_intent.version, "FAILED_SAFE", failure_code="PAIR_RECOVERED_WITHOUT_FULL_CREATE")
                elif pair.state == "RECOVERY_REQUIRED":
                    pair_repo.update_state(pair.id, pair.version, "CANCEL_PENDING", recovery_required=False)
                SqlAlchemyAuditEventRepository(session).append(
                    self._audit(correlation_id, "DELETE_CONFIRMED", "PASS", {"leg_type": label, "terminal": complete})
                )
        except ProtectivePersistenceError:
            raise
        except OptimisticLockError as exc:
            raise ProtectivePersistenceError("PERSISTENCE_VERSION_CONFLICT", after_transport=True) from exc
        except Exception as exc:
            raise ProtectivePersistenceError("PERSISTENCE_POST_TRANSPORT_FAILED", after_transport=True) from exc

    def mark_recovery_required(self, state: ProtectivePersistenceState, mutation_kind: str, reason_code: str) -> None:
        intent_ids = [(state.create_intent_id, state.create_correlation_id)] if mutation_kind == "CREATE" else [
            (state.stop_cancel_intent_id, state.stop_cancel_correlation_id),
            (state.take_profit_cancel_intent_id, state.take_profit_cancel_correlation_id),
        ]
        try:
            with self._transaction() as session:
                intent_repo = SqlAlchemyExecutionIntentRepository(session)
                pair_repo = SqlAlchemyProtectivePairRepository(session)
                existing_intents = []
                for intent_id, correlation_id in intent_ids:
                    intent = intent_repo.get_by_id(intent_id)
                    if intent is None:
                        continue
                    existing_intents.append((intent, correlation_id))
                    if intent.state != "RECOVERY_REQUIRED":
                        intent_repo.update_state(intent.id, intent.version, "RECOVERY_REQUIRED", failure_code=reason_code)
                if not existing_intents:
                    raise ProtectivePersistenceError("PERSISTENCE_INTENT_MISSING", after_transport=True)
                pair = self._require_pair(pair_repo, state.pair_id)
                if pair.state != "RECOVERY_REQUIRED" or not pair.recovery_required:
                    pair_repo.update_state(pair.id, pair.version, "RECOVERY_REQUIRED", recovery_required=True, blocking_reason=reason_code)
                for _, correlation_id in existing_intents:
                    SqlAlchemyRecoveryEventRepository(session).append(RecoveryEvent(
                        correlation_id=correlation_id,
                        protective_pair_id=state.pair_id,
                        event_type="RECOVERY_REQUIRED",
                        from_state=pair.state,
                        to_state="RECOVERY_REQUIRED",
                        reason_code=reason_code,
                        result="BLOCKED",
                    ))
                    SqlAlchemyAuditEventRepository(session).append(self._audit(correlation_id, "RECOVERY_REQUIRED", "FAIL", {"reason_code": reason_code}))
        except Exception as exc:
            raise ProtectivePersistenceError("PERSISTENCE_RECOVERY_WRITE_FAILED", after_transport=True) from exc

    def mark_failed_safe(self, state: ProtectivePersistenceState, mutation_kind: str, reason_code: str) -> None:
        if mutation_kind != "CREATE":
            raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH", after_transport=True)
        intent_id = state.create_intent_id
        correlation_id = state.create_correlation_id
        try:
            with self._transaction() as session:
                intent_repo = SqlAlchemyExecutionIntentRepository(session)
                pair_repo = SqlAlchemyProtectivePairRepository(session)
                intent = self._require_intent(intent_repo, intent_id)
                intent_repo.update_state(intent.id, intent.version, "FAILED_SAFE", failure_code=reason_code)
                pair = self._require_pair(pair_repo, state.pair_id)
                pair_repo.update_state(pair.id, pair.version, "FAILED_SAFE", recovery_required=False, blocking_reason=reason_code)
                SqlAlchemyAuditEventRepository(session).append(
                    self._audit(correlation_id, "FAILED_SAFE", "FAIL", {"reason_code": reason_code})
                )
        except Exception as exc:
            raise ProtectivePersistenceError("PERSISTENCE_POST_TRANSPORT_FAILED", after_transport=True) from exc

    def apply_reconciliation(
        self,
        state: ProtectivePersistenceState,
        journal_intent: ProtectiveMutationIntent,
        result: ProtectiveReconciliationResult,
    ) -> None:
        interpreted = result.interpreted_mutation_result
        if interpreted == "CREATE_CONFIRMED" and result.order is not None:
            self.mark_create_transmitted(state)
            self.confirm_create(state, journal_intent.label, result.order)
            return
        if interpreted == "CREATE_NOT_APPLIED":
            self.mark_failed_safe(state, "CREATE", "CREATE_NOT_APPLIED")
            return
        if interpreted in {"DELETE_CONFIRMED", "DELETE_CONFIRMED_TERMINAL"}:
            self.mark_cancel_transmitted(state, journal_intent.label)
            status = "ABSENT" if result.order is None else str(result.order.algo_status or "TERMINAL")
            self.confirm_delete(state, journal_intent.label, status, complete=journal_intent.label == "STOP")
            return
        if result.recovery_required:
            self.mark_recovery_required(state, journal_intent.mutation_kind, "RECONCILIATION_AMBIGUOUS")

    def needs_catch_up(self, state: ProtectivePersistenceState, journal_intent: ProtectiveMutationIntent) -> bool:
        try:
            with self._session() as session:
                pair = self._require_pair(SqlAlchemyProtectivePairRepository(session), state.pair_id)
                client_id = state.stop_client_algo_id if journal_intent.label == "STOP" else state.take_profit_client_algo_id
                identity = SqlAlchemyExchangeOrderIdentityRepository(session).get_by_client_algo_id(ENVIRONMENT, SYMBOL, client_id)
                if journal_intent.mutation_kind == "CREATE":
                    return identity is None
                intent_id, _ = self._cancel_identity(state, journal_intent.label)
                cancel_intent = SqlAlchemyExecutionIntentRepository(session).get_by_id(intent_id)
                if cancel_intent is None:
                    raise ProtectivePersistenceError("PERSISTENCE_INTENT_MISSING")
                terminal = identity is not None and identity.status in {"ABSENT", "CANCELED", "EXPIRED", "REJECTED"}
                return cancel_intent.state != "COMPLETED" or not terminal or (journal_intent.label == "STOP" and pair.state != "COMPLETED")
        except ProtectivePersistenceError:
            raise
        except Exception as exc:
            raise ProtectivePersistenceError("PERSISTENCE_CONSISTENCY_UNAVAILABLE") from exc

    def _transition_intent(self, intent_id: UUID, target: str, action: str, correlation_id: UUID, *, after_transport: bool) -> None:
        try:
            with self._transaction() as session:
                repo = SqlAlchemyExecutionIntentRepository(session)
                intent = self._require_intent(repo, intent_id)
                if intent.state == target:
                    return
                if intent.state not in {"PERSISTED", "RECOVERY_REQUIRED"}:
                    raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH", after_transport=after_transport)
                repo.update_state(intent.id, intent.version, target)
                SqlAlchemyAuditEventRepository(session).append(self._audit(correlation_id, action, "PASS", None))
        except ProtectivePersistenceError:
            raise
        except OptimisticLockError as exc:
            raise ProtectivePersistenceError("PERSISTENCE_VERSION_CONFLICT", after_transport=after_transport) from exc
        except Exception as exc:
            raise ProtectivePersistenceError("PERSISTENCE_POST_TRANSPORT_FAILED", after_transport=after_transport) from exc

    def _validate_persisted_ids(
        self,
        session: Session,
        pair: ProtectivePair,
        stop_id: str,
        take_id: str,
        journal: BinanceFuturesTestnetProtectiveJournal | None,
        *,
        validate_state_matrix: bool = True,
        exact_identity_status: bool = True,
        validate_cancel_projection: bool = True,
    ) -> None:
        state = self._state(pair, stop_id, take_id)
        intent_repo = SqlAlchemyExecutionIntentRepository(session)
        create_intent = intent_repo.get_by_id(pair.execution_intent_id)
        if create_intent is None:
            raise ProtectivePersistenceError("PERSISTENCE_INTENT_MISSING")
        if (
            create_intent.id != state.create_intent_id
            or create_intent.correlation_id != state.create_correlation_id
            or create_intent.correlation_id != pair.correlation_id
            or create_intent.environment != ENVIRONMENT
            or create_intent.symbol != SYMBOL
            or create_intent.intent_type != "PROTECTIVE_PAIR_CREATE"
            or create_intent.requested_quantity != pair.quantity
            or create_intent.requested_price is None
            or not create_intent.requested_price.is_finite()
            or create_intent.requested_price <= 0
            or pair.position_side != "BOTH"
            or pair.direction not in {"LONG", "SHORT"}
            or not pair.quantity.is_finite()
            or pair.quantity <= 0
        ):
            raise ProtectivePersistenceError("PERSISTENCE_REPLAY_MISMATCH")
        audit = session.scalar(
            select(AuditEventORM)
            .where(AuditEventORM.correlation_id == pair.correlation_id, AuditEventORM.action == "INTENT_PERSISTED")
            .order_by(AuditEventORM.created_at.asc(), AuditEventORM.id.asc())
            .limit(1)
        )
        metadata = None if audit is None else audit.metadata_json
        if not isinstance(metadata, dict):
            raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_MISSING")
        if metadata.get("pair_id") != pair.pair_id:
            raise ProtectivePersistenceError("PERSISTENCE_PAIR_MISMATCH")
        if metadata.get("stop_client_algo_id") != stop_id or metadata.get("take_profit_client_algo_id") != take_id:
            raise ProtectivePersistenceError("PERSISTENCE_CLIENT_ID_MISMATCH")
        stop_trigger = self._required_positive_decimal(metadata.get("stop_trigger"))
        take_trigger = self._required_positive_decimal(metadata.get("take_profit_trigger"))
        if (
            metadata.get("position_side") != pair.position_side
            or metadata.get("direction") != pair.direction
            or self._required_positive_decimal(metadata.get("quantity")) != pair.quantity
            or self._required_positive_decimal(metadata.get("requested_price")) != create_intent.requested_price
        ):
            raise ProtectivePersistenceError("PERSISTENCE_REPLAY_MISMATCH")
        identities = SqlAlchemyExchangeOrderIdentityRepository(session).list_by_protective_pair_id(pair.id, limit=3)
        if len(identities) > 2:
            raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_MISMATCH")
        confirmed_rows = list(
            session.scalars(
                select(AuditEventORM)
                .where(AuditEventORM.correlation_id == pair.correlation_id, AuditEventORM.action == "CREATE_CONFIRMED")
                .order_by(AuditEventORM.created_at.asc(), AuditEventORM.id.asc())
                .limit(3)
            ).all()
        )
        if len(confirmed_rows) > 2:
            raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_MISMATCH")
        confirmed_by_leg: dict[str, dict[str, Any]] = {}
        for row in confirmed_rows:
            confirmed = row.metadata_json
            if not isinstance(confirmed, dict) or confirmed.get("leg_type") not in {"STOP", "TAKE_PROFIT"}:
                raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_MISMATCH")
            label = confirmed["leg_type"]
            if label in confirmed_by_leg:
                raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_MISMATCH")
            confirmed_by_leg[label] = confirmed
        by_leg: dict[str, ExchangeOrderIdentity] = {}
        for identity in identities:
            expected = stop_id if identity.leg_type == "STOP" else take_id if identity.leg_type == "TAKE_PROFIT" else None
            trigger = stop_trigger if identity.leg_type == "STOP" else take_trigger
            if expected is None or identity.leg_type in by_leg:
                raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_MISMATCH")
            confirmed = confirmed_by_leg.get(identity.leg_type)
            if not isinstance(confirmed, dict):
                raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_MISSING")
            expected_status = (
                self._journal_identity_status(journal, identity.leg_type) or confirmed.get("status")
                if exact_identity_status
                else identity.status
            )
            self._validate_identity(
                identity,
                pair.id,
                identity.leg_type,
                expected,
                trigger,
                exchange_algo_id=confirmed.get("exchange_algo_id"),
                exchange_order_id=confirmed.get("exchange_order_id"),
                status=expected_status,
                exact_exchange_fields=True,
            )
            if confirmed.get("pair_id") != pair.pair_id or confirmed.get("client_algo_id") != expected or self._required_positive_decimal(confirmed.get("trigger_price")) != trigger:
                raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_MISMATCH")
            self._validate_protective_client_id(identity.client_algo_id)
            if not identity.exchange_algo_id or identity.status not in PROTECTIVE_IDENTITY_STATUSES:
                raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_MISMATCH")
            by_leg[identity.leg_type] = identity

        self._validate_global_identity_leg_projection(pair, confirmed_by_leg, by_leg)

        cancel_intents: dict[str, ExecutionIntent | None] = {}
        for label in ("STOP", "TAKE_PROFIT"):
            cancel_id, _ = self._cancel_identity(state, label)
            cancel_intents[label] = intent_repo.get_by_id(cancel_id)
            if validate_cancel_projection and cancel_intents[label] is not None:
                cancel_intent = cancel_intents[label]
                self._validate_cancel_intent(cancel_intent, state, label, pair.quantity, cancel_intent.requested_price)
                if cancel_intent.requested_price not in {None, create_intent.requested_price}:
                    raise ProtectivePersistenceError("PERSISTENCE_REPLAY_MISMATCH")
                cancel_audit = session.scalar(
                    select(AuditEventORM)
                    .where(AuditEventORM.correlation_id == cancel_intent.correlation_id, AuditEventORM.action == "INTENT_PERSISTED")
                    .order_by(AuditEventORM.created_at.asc(), AuditEventORM.id.asc())
                    .limit(1)
                )
                cancel_metadata = None if cancel_audit is None else cancel_audit.metadata_json
                expected_client = stop_id if label == "STOP" else take_id
                if not isinstance(cancel_metadata, dict) or cancel_metadata != {
                    "pair_id": pair.pair_id,
                    "intent_type": "PROTECTIVE_PAIR_CANCEL",
                    "leg_type": label,
                    "client_algo_id": expected_client,
                }:
                    raise ProtectivePersistenceError("PERSISTENCE_REPLAY_MISMATCH")

        self._validate_journal_projection(journal, pair, state, stop_trigger, take_trigger)
        if validate_state_matrix:
            self._validate_allowed_state_matrix(journal, pair, create_intent, cancel_intents, by_leg)

    @staticmethod
    def _validate_global_identity_leg_projection(
        pair: ProtectivePair,
        confirmed_by_leg: dict[str, dict[str, Any]],
        identities_by_leg: dict[str, ExchangeOrderIdentity],
    ) -> None:
        confirmed_legs = set(confirmed_by_leg)
        persisted_legs = set(identities_by_leg)
        if confirmed_legs != persisted_legs:
            raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_MISSING")

        terminal_statuses = {"ABSENT", "CANCELED", "EXPIRED", "REJECTED"}
        expected_both = {"STOP", "TAKE_PROFIT"}
        if pair.state == "PENDING":
            valid = not confirmed_legs and not persisted_legs
        elif pair.state == "STOP_ACTIVE":
            valid = confirmed_legs == {"STOP"} and identities_by_leg["STOP"].status == "NEW"
        elif pair.state == "PAIR_ACTIVE":
            valid = (
                confirmed_legs == expected_both
                and all(identities_by_leg[label].status == "NEW" for label in expected_both)
            )
        elif pair.state == "CANCEL_PENDING":
            # A recovery may be cancelling the sole STOP leg after an ambiguous
            # partial create; fresh mutation is still blocked by this state.
            valid = confirmed_legs == persisted_legs and persisted_legs in ({"STOP"}, expected_both)
        elif pair.state == "COMPLETED":
            valid = (
                confirmed_legs == expected_both
                and all(identities_by_leg[label].status in terminal_statuses for label in expected_both)
            )
        elif pair.state == "RECOVERY_REQUIRED":
            valid = pair.recovery_required
        elif pair.state == "FAILED_SAFE":
            valid = not confirmed_legs and not persisted_legs
        else:
            valid = False
        if not valid:
            raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_MISMATCH")

    @staticmethod
    def _validate_protective_client_id(value: object) -> None:
        if not isinstance(value, str) or not value.startswith(PROTECTIVE_CLIENT_ID_PREFIX) or len(value) > 36:
            raise ProtectivePersistenceError("PERSISTENCE_CLIENT_ID_MISMATCH")
        if any(char.isspace() or not (char.isalnum() or char in ".:/_-") for char in value):
            raise ProtectivePersistenceError("PERSISTENCE_CLIENT_ID_MISMATCH")

    @staticmethod
    def _required_positive_decimal(value: Any) -> Decimal:
        try:
            parsed = Decimal(str(value))
        except Exception as exc:
            raise ProtectivePersistenceError("PERSISTENCE_REPLAY_MISMATCH") from exc
        if not parsed.is_finite() or parsed <= 0:
            raise ProtectivePersistenceError("PERSISTENCE_REPLAY_MISMATCH")
        return parsed

    def _validate_journal_projection(
        self,
        journal: BinanceFuturesTestnetProtectiveJournal | None,
        pair: ProtectivePair,
        state: ProtectivePersistenceState,
        stop_trigger: Decimal,
        take_trigger: Decimal,
    ) -> None:
        if journal is None:
            return
        seen: set[tuple[str, str]] = set()
        for item in journal.mutation_intents:
            key = (item.label, item.mutation_kind)
            if key in seen or item.label not in {"STOP", "TAKE_PROFIT"} or item.mutation_kind not in {"CREATE", "DELETE"}:
                raise ProtectivePersistenceError("PERSISTENCE_JOURNAL_PROJECTION_MISMATCH")
            seen.add(key)
            expected_client = state.stop_client_algo_id if item.label == "STOP" else state.take_profit_client_algo_id
            expected_trigger = stop_trigger if item.label == "STOP" else take_trigger
            if (
                item.pair_id != pair.pair_id
                or item.symbol != SYMBOL
                or item.client_algo_id != expected_client
                or item.expected_trigger_price != expected_trigger
                or abs(item.baseline_position_amount or Decimal("0")) != pair.quantity
                or item.baseline_position_direction != pair.direction
            ):
                raise ProtectivePersistenceError("PERSISTENCE_JOURNAL_PROJECTION_MISMATCH")

    @staticmethod
    def _journal_identity_status(journal: BinanceFuturesTestnetProtectiveJournal | None, label: str) -> str | None:
        if journal is None:
            return None
        phase = f"{label}_CANCELED"
        for entry in reversed(journal.entries):
            if entry.get("phase") != phase or not isinstance(entry.get("details"), dict):
                continue
            status = entry["details"].get("status")
            return status if isinstance(status, str) and status else None
        return None

    def _validate_allowed_state_matrix(
        self,
        journal: BinanceFuturesTestnetProtectiveJournal | None,
        pair: ProtectivePair,
        create_intent: ExecutionIntent,
        cancel_intents: dict[str, ExecutionIntent | None],
        identities: dict[str, ExchangeOrderIdentity],
    ) -> None:
        terminal_statuses = {"ABSENT", "CANCELED", "EXPIRED", "REJECTED"}
        active_legs = {label for label, identity in identities.items() if identity.status == "NEW"}
        terminal_legs = {label for label, identity in identities.items() if identity.status in terminal_statuses}
        terminal_journal = journal is not None and journal.phase in {"COMPLETE", "RECOVERY_COMPLETE"}
        unresolved_journal = journal is not None and any(not item.resolved for item in journal.mutation_intents)

        if journal is not None:
            if journal.recovery_required != pair.recovery_required:
                raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH")
            if terminal_journal and (unresolved_journal or pair.state != "COMPLETED"):
                raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH")
            if not terminal_journal and pair.state == "COMPLETED":
                raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH")

        stop_cancel = cancel_intents["STOP"]
        take_cancel = cancel_intents["TAKE_PROFIT"]
        allowed = False
        if pair.state == "PENDING":
            allowed = create_intent.state in {"PERSISTED", "TRANSMITTED"} and not pair.recovery_required and not identities and stop_cancel is None and take_cancel is None
        elif pair.state == "STOP_ACTIVE":
            allowed = create_intent.state == "TRANSMITTED" and not pair.recovery_required and active_legs == {"STOP"} and stop_cancel is None and take_cancel is None
        elif pair.state == "PAIR_ACTIVE":
            allowed = create_intent.state == "COMPLETED" and not pair.recovery_required and active_legs == {"STOP", "TAKE_PROFIT"} and stop_cancel is None and take_cancel is None
        elif pair.state == "CANCEL_PENDING":
            cancel_states = [item.state for item in (stop_cancel, take_cancel) if item is not None]
            allowed = create_intent.state in {"COMPLETED", "FAILED_SAFE"} and not pair.recovery_required and len(identities) == 2 and bool(cancel_states) and all(state in {"PERSISTED", "TRANSMITTED", "COMPLETED"} for state in cancel_states)
        elif pair.state == "RECOVERY_REQUIRED":
            relevant_states = [create_intent.state] + [item.state for item in (stop_cancel, take_cancel) if item is not None]
            allowed = pair.recovery_required and journal is not None and journal.recovery_required and "RECOVERY_REQUIRED" in relevant_states
        elif pair.state == "COMPLETED":
            allowed = (
                not pair.recovery_required
                and (journal is None or terminal_journal)
                and create_intent.state in {"COMPLETED", "FAILED_SAFE"}
                and stop_cancel is not None
                and stop_cancel.state == "COMPLETED"
                and take_cancel is not None
                and take_cancel.state == "COMPLETED"
                and terminal_legs == {"STOP", "TAKE_PROFIT"}
            )
        if not allowed:
            raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH")
        if journal is not None:
            self._validate_exact_phase_projection(journal, pair, create_intent, cancel_intents, identities)

    def _validate_exact_phase_projection(
        self,
        journal: BinanceFuturesTestnetProtectiveJournal,
        pair: ProtectivePair,
        create_intent: ExecutionIntent,
        cancel_intents: dict[str, ExecutionIntent | None],
        identities: dict[str, ExchangeOrderIdentity],
    ) -> None:
        """Bind every durable journal boundary to its exact persisted projection."""
        phase = journal.phase
        intent_keys = {(item.label, item.mutation_kind) for item in journal.mutation_intents}
        stop_create = ("STOP", "CREATE")
        take_create = ("TAKE_PROFIT", "CREATE")
        stop_delete = ("STOP", "DELETE")
        take_delete = ("TAKE_PROFIT", "DELETE")
        create_keys = {stop_create, take_create}
        all_keys = create_keys | {stop_delete, take_delete}
        stop_cancel = cancel_intents["STOP"]
        take_cancel = cancel_intents["TAKE_PROFIT"]
        stop_status = identities.get("STOP").status if identities.get("STOP") is not None else None
        take_status = identities.get("TAKE_PROFIT").status if identities.get("TAKE_PROFIT") is not None else None
        terminal = {"ABSENT", "CANCELED", "EXPIRED", "REJECTED"}

        def require(condition: bool) -> None:
            if not condition:
                raise ProtectivePersistenceError("PERSISTENCE_PHASE_PROJECTION_MISMATCH")

        early_create = {"PRECHECK_STARTED", "POSITION_VALIDATED", "STOP_CREATE_STARTED"}
        stop_active = {"STOP_CREATED", "STOP_QUERY_COMPLETE", "TAKE_PROFIT_CREATE_STARTED"}
        pair_active = {"TAKE_PROFIT_CREATED", "TAKE_PROFIT_QUERY_COMPLETE"}

        if phase in early_create:
            require(pair.state == "PENDING" and create_intent.state == "PERSISTED" and intent_keys == set())
            require(stop_cancel is None and take_cancel is None and not identities)
            return
        if phase == "STOP_CREATE_INTENT_PERSISTED":
            require(pair.state == "PENDING" and create_intent.state in {"PERSISTED", "TRANSMITTED"} and intent_keys == {stop_create})
            require(stop_cancel is None and take_cancel is None and not identities)
            return
        if phase.startswith("STOP_CREATE_"):
            require(intent_keys == {stop_create} and stop_cancel is None and take_cancel is None)
            require(
                (pair.state == "PENDING" and create_intent.state == "TRANSMITTED" and not identities)
                or (pair.state == "STOP_ACTIVE" and create_intent.state == "TRANSMITTED" and stop_status == "NEW" and take_status is None)
            )
            return
        if phase in stop_active:
            require(pair.state == "STOP_ACTIVE" and create_intent.state == "TRANSMITTED" and intent_keys == {stop_create})
            require(stop_cancel is None and take_cancel is None and stop_status == "NEW" and take_status is None)
            return
        if phase == "TAKE_PROFIT_CREATE_INTENT_PERSISTED":
            require(pair.state == "STOP_ACTIVE" and create_intent.state == "TRANSMITTED" and intent_keys == create_keys)
            require(stop_cancel is None and take_cancel is None and stop_status == "NEW" and take_status is None)
            return
        if phase.startswith("TAKE_PROFIT_CREATE_"):
            require(intent_keys == create_keys and stop_cancel is None and take_cancel is None and stop_status == "NEW")
            require(
                (pair.state == "STOP_ACTIVE" and create_intent.state == "TRANSMITTED" and take_status is None)
                or (pair.state == "PAIR_ACTIVE" and create_intent.state == "COMPLETED" and take_status == "NEW")
            )
            return
        if phase in pair_active:
            require(intent_keys == create_keys and stop_status == "NEW" and take_status == "NEW")
            if pair.state == "PAIR_ACTIVE":
                require(create_intent.state == "COMPLETED" and stop_cancel is None and take_cancel is None)
            else:
                require(
                    phase == "TAKE_PROFIT_QUERY_COMPLETE"
                    and pair.state == "CANCEL_PENDING"
                    and create_intent.state == "COMPLETED"
                    and stop_cancel is None
                    and take_cancel is not None
                    and take_cancel.state == "PERSISTED"
                )
            return
        if phase == "TAKE_PROFIT_CANCEL_STARTED":
            require(pair.state == "CANCEL_PENDING" and create_intent.state == "COMPLETED" and intent_keys == create_keys)
            require(stop_cancel is None and take_cancel is not None and take_cancel.state == "PERSISTED" and stop_status == "NEW" and take_status == "NEW")
            return
        if phase == "TAKE_PROFIT_DELETE_INTENT_PERSISTED" or phase.startswith("TAKE_PROFIT_DELETE_"):
            require(pair.state == "CANCEL_PENDING" and create_intent.state == "COMPLETED" and intent_keys == create_keys | {take_delete})
            require(stop_cancel is None and take_cancel is not None and take_cancel.state in {"PERSISTED", "TRANSMITTED", "COMPLETED"})
            require(stop_status == "NEW" and take_status in {"NEW", *terminal})
            return
        if phase == "TAKE_PROFIT_CANCELED":
            require(pair.state == "CANCEL_PENDING" and create_intent.state == "COMPLETED" and intent_keys == create_keys | {take_delete})
            require(take_cancel is not None and take_cancel.state == "COMPLETED" and stop_status == "NEW" and take_status in terminal)
            require(stop_cancel is None or stop_cancel.state == "PERSISTED")
            return
        if phase == "STOP_CANCEL_STARTED":
            require(pair.state == "CANCEL_PENDING" and create_intent.state == "COMPLETED" and intent_keys == create_keys | {take_delete})
            require(stop_cancel is not None and stop_cancel.state == "PERSISTED" and take_cancel is not None and take_cancel.state == "COMPLETED")
            require(stop_status == "NEW" and take_status in terminal)
            return
        if phase == "STOP_DELETE_INTENT_PERSISTED" or phase.startswith("STOP_DELETE_"):
            require(intent_keys == all_keys and stop_cancel is not None and take_cancel is not None and take_cancel.state == "COMPLETED")
            require(stop_cancel.state in {"PERSISTED", "TRANSMITTED", "COMPLETED"} and take_status in terminal)
            require(
                (pair.state == "CANCEL_PENDING" and stop_status in {"NEW", *terminal})
                or (pair.state == "COMPLETED" and stop_cancel.state == "COMPLETED" and stop_status in terminal)
            )
            return
        if phase == "STOP_CANCELED":
            require(pair.state == "COMPLETED" and create_intent.state in {"COMPLETED", "FAILED_SAFE"} and intent_keys == all_keys)
            require(stop_cancel is not None and stop_cancel.state == "COMPLETED" and take_cancel is not None and take_cancel.state == "COMPLETED")
            require(stop_status in terminal and take_status in terminal)
            return
        if phase in {"COMPLETE", "RECOVERY_COMPLETE"}:
            require(not journal.recovery_required and pair.state == "COMPLETED" and not pair.recovery_required and intent_keys == all_keys)
            require(stop_cancel is not None and stop_cancel.state == "COMPLETED" and take_cancel is not None and take_cancel.state == "COMPLETED")
            require(stop_status in terminal and take_status in terminal)
            return
        if phase in {"RECOVERY_REQUIRED", "RECOVERY_STARTED"} or phase == "FAILED":
            require(journal.recovery_required and pair.state == "RECOVERY_REQUIRED" and pair.recovery_required)
            persisted_delete_keys = {
                key for key, item in ((stop_delete, stop_cancel), (take_delete, take_cancel)) if item is not None
            }
            require(intent_keys == ({key for key in intent_keys if key in create_keys} | persisted_delete_keys))
            require(stop_create in intent_keys)
            if identities.get("TAKE_PROFIT") is not None or stop_cancel is not None or take_cancel is not None:
                require(take_create in intent_keys)
            require(any(item is not None and item.state == "RECOVERY_REQUIRED" for item in (stop_cancel, take_cancel)) or create_intent.state == "RECOVERY_REQUIRED")
            return
        raise ProtectivePersistenceError("PERSISTENCE_PHASE_PROJECTION_MISMATCH")

    def _state(self, pair: ProtectivePair, stop_id: str, take_id: str) -> ProtectivePersistenceState:
        expected = self._deterministic_state(pair.pair_id, stop_id, take_id)
        if pair.id != expected.pair_id or pair.execution_intent_id != expected.create_intent_id or pair.correlation_id != expected.create_correlation_id:
            raise ProtectivePersistenceError("PERSISTENCE_CORRELATION_MISMATCH")
        return expected

    def _deterministic_state(self, pair_id: str, stop_id: str, take_id: str) -> ProtectivePersistenceState:
        root = f"{ENVIRONMENT}:{SYMBOL}:{pair_id}:{stop_id}:{take_id}"
        return ProtectivePersistenceState(
            pair_id=uuid5(NAMESPACE_URL, f"{root}:pair"),
            create_intent_id=uuid5(NAMESPACE_URL, f"{root}:create:intent"),
            create_correlation_id=uuid5(NAMESPACE_URL, f"{root}:create:correlation"),
            stop_cancel_intent_id=uuid5(NAMESPACE_URL, f"{root}:cancel:STOP:intent"),
            stop_cancel_correlation_id=uuid5(NAMESPACE_URL, f"{root}:cancel:STOP:correlation"),
            take_profit_cancel_intent_id=uuid5(NAMESPACE_URL, f"{root}:cancel:TAKE_PROFIT:intent"),
            take_profit_cancel_correlation_id=uuid5(NAMESPACE_URL, f"{root}:cancel:TAKE_PROFIT:correlation"),
            stop_client_algo_id=stop_id,
            take_profit_client_algo_id=take_id,
        )

    def _validate_pair_scope(self, pair: ProtectivePair) -> None:
        if pair.environment != ENVIRONMENT or pair.symbol != SYMBOL or pair.state not in UNRESOLVED_PAIR_STATES | TERMINAL_PAIR_STATES:
            raise ProtectivePersistenceError("PERSISTENCE_SCOPE_INVALID")

    def _validate_cancel_intent(
        self,
        intent: ExecutionIntent,
        state: ProtectivePersistenceState,
        label: str,
        quantity: Decimal,
        price: Decimal | None,
    ) -> None:
        intent_id, correlation_id = self._cancel_identity(state, label)
        if (
            intent.id != intent_id
            or intent.correlation_id != correlation_id
            or intent.environment != ENVIRONMENT
            or intent.symbol != SYMBOL
            or intent.intent_type != "PROTECTIVE_PAIR_CANCEL"
            or intent.state not in {"PERSISTED", "TRANSMITTED", "RECOVERY_REQUIRED", "COMPLETED"}
            or intent.requested_quantity != abs(quantity)
            or intent.requested_price != price
        ):
            raise ProtectivePersistenceError("PERSISTENCE_REPLAY_MISMATCH")

    def _validate_identity(
        self,
        identity: ExchangeOrderIdentity,
        pair_id: UUID,
        label: str,
        client_id: str,
        trigger: Decimal | None,
        *,
        exchange_algo_id: str | None = None,
        exchange_order_id: str | None = None,
        status: str | None = None,
        exact_exchange_fields: bool = False,
    ) -> None:
        if (
            identity.protective_pair_id != pair_id
            or identity.environment != ENVIRONMENT
            or identity.symbol != SYMBOL
            or identity.leg_type != label
            or identity.client_algo_id != client_id
            or (trigger is not None and identity.trigger_price != trigger)
            or (exact_exchange_fields and identity.exchange_algo_id != exchange_algo_id)
            or (exact_exchange_fields and identity.exchange_order_id != exchange_order_id)
            or (exact_exchange_fields and identity.status != status)
        ):
            raise ProtectivePersistenceError("PERSISTENCE_IDENTITY_MISMATCH", after_transport=True)

    @staticmethod
    def _cancel_identity(state: ProtectivePersistenceState, label: str) -> tuple[UUID, UUID]:
        if label == "STOP":
            return state.stop_cancel_intent_id, state.stop_cancel_correlation_id
        if label == "TAKE_PROFIT":
            return state.take_profit_cancel_intent_id, state.take_profit_cancel_correlation_id
        raise ProtectivePersistenceError("PERSISTENCE_REPLAY_MISMATCH")

    def _require_pair(self, repo: SqlAlchemyProtectivePairRepository, pair_id: UUID) -> ProtectivePair:
        pair = repo.get_by_id(pair_id)
        if pair is None:
            raise ProtectivePersistenceError("PERSISTENCE_PAIR_MISSING")
        self._validate_pair_scope(pair)
        return pair

    @staticmethod
    def _require_pair_state(pair: ProtectivePair, states: set[str]) -> None:
        if pair.state not in states:
            raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH", after_transport=True)

    @staticmethod
    def _require_intent(repo: SqlAlchemyExecutionIntentRepository, intent_id: UUID) -> ExecutionIntent:
        intent = repo.get_by_id(intent_id)
        if intent is None:
            raise ProtectivePersistenceError("PERSISTENCE_INTENT_MISSING")
        return intent

    @staticmethod
    def _decimal_text(value: Decimal | None) -> str | None:
        return None if value is None else format(value, "f")

    @staticmethod
    def _audit(correlation_id: UUID, action: str, result: str, metadata: dict[str, Any] | None) -> AuditEvent:
        return AuditEvent(
            correlation_id=correlation_id,
            category="PROTECTIVE_LIFECYCLE",
            action=action,
            environment=ENVIRONMENT,
            symbol=SYMBOL,
            result=result,
            metadata_json=metadata,
        )

    @contextmanager
    def _session(self) -> Iterator[Session]:
        if self._engine is None:
            raise ProtectivePersistenceError("PERSISTENCE_UNAVAILABLE")
        session = self._session_factory(bind=self._engine, future=True, autoflush=False, expire_on_commit=False)
        try:
            yield session
        finally:
            session.close()

    @contextmanager
    def _transaction(self) -> Iterator[Session]:
        with self._session() as session:
            try:
                with session.begin():
                    yield session
            except Exception:
                session.rollback()
                raise
