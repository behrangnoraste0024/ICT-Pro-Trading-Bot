from __future__ import annotations

import json
import os
import uuid
from decimal import InvalidOperation
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from infrastructure.exchanges.binance_futures_testnet_protective_orders_client import BinanceFuturesTestnetProtectiveAPIError, BinanceFuturesTestnetProtectiveOrdersClient
from infrastructure.persistence.protective_lifecycle_persistence import (
    ProtectiveLifecyclePersistence,
    ProtectivePersistenceError,
    ProtectivePersistenceState,
)
from infrastructure.persistence.live_execution_authorization_policy import LiveExecutionAuthorizationPolicy
from infrastructure.security.live_execution_mutation_fingerprint_adapter import (
    build_protective_cancel_from_final_request,
    build_protective_create_from_final_request,
)
from infrastructure.security.live_execution_permit_gate import LiveExecutionPermitGate
from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit_enforcement import LiveExecutionPermitGateError, LiveExecutionPermitReference
from models.binance_futures_testnet_protective_orders import (
    BinanceFuturesTestnetProtectiveAlgoSummary,
    BinanceFuturesTestnetProtectiveCredentialMetadata,
    BinanceFuturesTestnetProtectiveExchangeFilters,
    BinanceFuturesTestnetProtectiveIssue,
    BinanceFuturesTestnetProtectiveJournal,
    BinanceFuturesTestnetProtectiveOrdersConfig,
    BinanceFuturesTestnetProtectivePosition,
    BinanceFuturesTestnetProtectivePreview,
    BinanceFuturesTestnetProtectiveRequestMetadata,
    BinanceFuturesTestnetProtectiveResult,
    BinanceFuturesTestnetProtectiveValidationReport,
    PROTECTIVE_JOURNAL_SCHEMA_VERSION,
    ProtectiveMutationIntent,
    ProtectiveMutationKind,
    ProtectiveReconciliationResult,
    ProtectiveReconciliationState,
)


class ProtectiveAbort(RuntimeError):
    def __init__(
        self,
        decision: str,
        reason: str,
        recovery: bool = False,
        critical: bool = False,
        permit_consumed: bool = False,
        mutation_transmitted: bool = False,
    ) -> None:
        super().__init__(reason)
        self.decision = decision
        self.reason = reason
        self.recovery = recovery
        self.critical = critical
        self.permit_consumed = permit_consumed
        self.mutation_transmitted = mutation_transmitted


class BinanceFuturesTestnetProtectiveOrdersEngine:
    TERMINAL_SAFE_STATUSES = {"CANCELED", "EXPIRED", "REJECTED"}
    TRIGGERED_STATUSES = {"TRIGGERED", "FILLED", "PARTIALLY_FILLED", "FINISHED"}

    def __init__(
        self,
        repo_root: str | Path | None = None,
        http_get=None,
        authenticated_request=None,
        env: dict[str, str] | None = None,
        now_ms_provider=None,
        now_provider=None,
        persistence_factory=None,
        kill_switch_gate=None,
        authorization_policy=None,
        permit_gate=None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.http_get = http_get
        self.authenticated_request = authenticated_request
        self.env = {} if env is None else env
        self.now_ms_provider = now_ms_provider
        self.now_provider = now_provider
        self.persistence_factory = persistence_factory or ProtectiveLifecyclePersistence
        self.authorization_policy = authorization_policy or LiveExecutionAuthorizationPolicy(
            repo_root=self.repo_root,
            env=self.env,
            kill_switch_gate=kill_switch_gate,
        )
        self.permit_gate = permit_gate or LiveExecutionPermitGate(
            authorization_policy=self.authorization_policy,
            env=self.env,
        )

    def _require_mutation_permission(self, operation: LiveExecutionOperation, current_pair_id: str | None = None) -> None:
        decision = self.authorization_policy.authorize(
            operation,
            environment="TESTNET",
            symbol="BTCUSDT",
            confirmation_verified=True,
            credentials_configured=True,
            current_pair_id=current_pair_id,
        )
        if not decision.allowed:
            raise ProtectiveAbort(
                decision.code,
                decision.message,
                recovery=current_pair_id is not None,
            )

    def _require_permit_for_mutation(
        self,
        *,
        operation: LiveExecutionOperation,
        fingerprint,
        permit_reference: LiveExecutionPermitReference | None,
        config: BinanceFuturesTestnetProtectiveOrdersConfig,
        current_pair_id: str | None,
    ) -> None:
        try:
            self.permit_gate.authorize_and_consume(
                operation=operation,
                fingerprint=fingerprint,
                permit_reference=permit_reference,
                confirmation_verified=True,
                credentials_configured=True,
                runtime_config_path=getattr(config, "runtime_config_path", "configs/btc_paper_runtime.json"),
                current_pair_id=current_pair_id,
            )
        except LiveExecutionPermitGateError as exc:
            # A pair identifier only identifies local lifecycle state. It is not
            # evidence that a mutation reached Binance. Preserve the gate's
            # durable-consumption fact so callers can distinguish a pre-consume
            # denial from a consumed-but-not-transmitted boundary failure.
            raise ProtectiveAbort(
                exc.code,
                exc.message,
                recovery=exc.permit_consumed,
                permit_consumed=exc.permit_consumed,
            ) from None

    @staticmethod
    def _require_distinct_permit_references(*references: LiveExecutionPermitReference | None, require_all: bool = False) -> None:
        seen: set[str] = set()
        for reference in references:
            if reference is None:
                if require_all:
                    raise ProtectiveAbort("PERMIT_REQUIRED", "A durable one-time live execution permit is required.")
                continue
            if not isinstance(reference, LiveExecutionPermitReference):
                raise ProtectiveAbort("PERMIT_REFERENCE_INVALID", "The live execution permit reference is invalid.")
            if reference.permit_id in seen:
                raise ProtectiveAbort("PERMIT_REFERENCE_INVALID", "Each mutation boundary requires a distinct permit.")
            seen.add(reference.permit_id)

    def _require_preflight_permission(self) -> None:
        decision = self.authorization_policy.authorize_preflight(
            LiveExecutionOperation.PROTECTIVE_CREATE,
            environment="TESTNET",
            symbol="BTCUSDT",
            confirmation_verified=True,
            credentials_configured=True,
        )
        if not decision.allowed:
            raise ProtectiveAbort(decision.code, decision.message)

    def validate(self, config_path: str = "configs/binance_futures_testnet_protective_orders.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetProtectiveValidationReport:
        issues: list[BinanceFuturesTestnetProtectiveIssue] = []
        config = None
        try:
            config = self.load_config(config_path)
        except Exception as exc:
            issues.append(self._issue("config_invalid", "FAIL", f"Protective order config could not be loaded: {exc}"))
            return self._report(config_path, config, issues)
        self._validate_config(config, expected_profile, issues)
        return self._report(config_path, config, issues)

    def check_credentials(self, config_path: str = "configs/binance_futures_testnet_protective_orders.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetProtectiveResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetProtectiveOrdersConfig()
        if report.status == "FAIL":
            return self._result(config, "CHECK_CREDENTIALS", "FAIL", "OPERATION_BLOCKED", "Protective config failed validation.", issues=list(report.issues))
        metadata = self._client(config).inspect_credentials()
        decision = "CREDENTIALS_PRESENT" if metadata.credentials_complete else "CREDENTIALS_INCOMPLETE" if metadata.api_key_present or metadata.api_secret_present else "CREDENTIALS_NOT_CONFIGURED"
        status = "PASS" if metadata.credentials_complete else "WARNING"
        return self._result(config, "CHECK_CREDENTIALS", status, decision, "Dedicated testnet credential metadata inspected.", credential_metadata=metadata)

    def build_preview(
        self,
        pair_id: str,
        stop_client_algo_id: str,
        take_profit_client_algo_id: str,
        position_amount: float | str,
        mark_price: float | str,
        entry_price: float | str,
        tick_size: float | str,
        stop_offset_bps: int | None = None,
        take_profit_offset_bps: int | None = None,
        config_path: str = "configs/binance_futures_testnet_protective_orders.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BinanceFuturesTestnetProtectiveResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetProtectiveOrdersConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, "BUILD_PREVIEW", "FAIL", "OPERATION_BLOCKED", "Protective config failed validation.", issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        client = self._client(config)
        try:
            position = client.require_protectable_position([{"symbol": config.exchange_symbol, "positionSide": "BOTH", "positionAmt": str(position_amount), "entryPrice": str(entry_price), "markPrice": str(mark_price)}])
            filters = client.parse_exchange_filters({"symbols": [{"symbol": config.exchange_symbol, "filters": [{"filterType": "PRICE_FILTER", "minPrice": "1", "maxPrice": "1000000", "tickSize": str(tick_size)}]}]})
            preview = client.build_preview(pair_id, stop_client_algo_id, take_profit_client_algo_id, position, filters, stop_offset_bps, take_profit_offset_bps)
            return self._result(config, "BUILD_PREVIEW", "PASS", "PROTECTIVE_PREVIEW_VALID", "Local protective preview is valid and non-executable.", preview=preview, position=position, exchange_filters=filters, issues=issues, pair_id=pair_id, stop_client_algo_id=preview.stop_client_algo_id, take_profit_client_algo_id=preview.take_profit_client_algo_id, phase="CREATED_LOCALLY")
        except Exception as exc:
            issues.append(self._issue("protective_preview_rejected", "FAIL", self._sanitize(str(exc))))
            return self._result(config, "BUILD_PREVIEW", "FAIL", "OPERATION_BLOCKED", "Local protective preview was rejected.", issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)

    def run_protective_lifecycle(
        self,
        pair_id: str,
        stop_client_algo_id: str,
        take_profit_client_algo_id: str,
        stop_offset_bps: int | None = None,
        take_profit_offset_bps: int | None = None,
        confirmation: str | None = None,
        config_path: str = "configs/binance_futures_testnet_protective_orders.json",
        expected_profile: str = "balanced_smc_decision_065",
        stop_create_permit: LiveExecutionPermitReference | None = None,
        take_profit_create_permit: LiveExecutionPermitReference | None = None,
        take_profit_cancel_permit: LiveExecutionPermitReference | None = None,
        stop_cancel_permit: LiveExecutionPermitReference | None = None,
    ) -> BinanceFuturesTestnetProtectiveResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetProtectiveOrdersConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "FAIL", "OPERATION_BLOCKED", "Protective config failed validation.", issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        if confirmation != config.pair_confirmation_phrase:
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "WARNING", "CONFIRMATION_REQUIRED", "Explicit protective pair confirmation is required.", issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        try:
            self._require_distinct_permit_references(stop_create_permit, take_profit_create_permit, take_profit_cancel_permit, stop_cancel_permit, require_all=True)
        except ProtectiveAbort as exc:
            issues.append(self._issue(exc.decision.lower(), "FAIL", exc.reason))
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "FAIL", exc.decision, exc.reason, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        client = self._client(config)
        try:
            metadata = client.inspect_credentials()
        except Exception:
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "FAIL", "CREDENTIALS_UNAVAILABLE", "Testnet credential readiness is unavailable.", issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        if not metadata.credentials_complete:
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "WARNING", "CREDENTIALS_NOT_CONFIGURED", "Dedicated testnet credentials are incomplete or missing.", credential_metadata=metadata, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        try:
            self._require_preflight_permission()
        except ProtectiveAbort as exc:
            issues.append(self._issue(exc.decision.lower(), "FAIL", exc.reason))
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "FAIL", exc.decision, exc.reason, credential_metadata=metadata, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        persistence = self.persistence_factory(env=self.env)
        try:
            persistence.ensure_available()
        except ProtectivePersistenceError as exc:
            issues.append(self._issue(exc.code.lower(), "FAIL", "Protective persistence is unavailable or invalid."))
            persistence.close()
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "FAIL", exc.code, "Protective persistence preflight failed safely before runtime mutation.", credential_metadata=metadata, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        lock_path = self._resolve(config.lock_path)
        lock_token = self._lock_token("run_protective_lifecycle", pair_id, stop_client_algo_id, take_profit_client_algo_id)
        lock_acquired = self._acquire_owned_lock(lock_path, lock_token)
        if not lock_acquired:
            issues.append(self._issue("protective_lock_exists", "FAIL", "An active protective-order lock already exists."))
            persistence.close()
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "FAIL", "RECOVERY_REQUIRED", "Existing protective lock blocks a new lifecycle.", credential_metadata=metadata, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, recovery_required=True)
        filters = None
        position = final_position = None
        preview = None
        stop_order = take_order = final_stop = final_take = None
        create_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata] = []
        query_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata] = []
        cancel_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata] = []
        reconciliation_results: list[ProtectiveReconciliationResult] = []
        persistence_state: ProtectivePersistenceState | None = None
        journal = BinanceFuturesTestnetProtectiveJournal(pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        stop_create_started = take_create_started = cancel_started = False
        try:
            try:
                existing_journal = self._load_existing_journal_strict(config, pair_id, stop_client_algo_id, take_profit_client_algo_id)
            except ProtectiveAbort as exc:
                issues.append(self._issue(exc.decision.lower(), "FAIL", exc.reason))
                return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "FAIL", exc.decision, exc.reason, credential_metadata=metadata, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="RECOVERY_REQUIRED", recovery_required=True)
            except Exception as exc:
                message = self._sanitize(str(exc))
                issues.append(self._issue("protective_journal_load_failed", "FAIL", message))
                return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "FAIL", "RECOVERY_REQUIRED", "Protective journal could not be trusted; recovery is required.", credential_metadata=metadata, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="RECOVERY_REQUIRED", recovery_required=True)
            try:
                consistency = persistence.check_consistency(existing_journal, pair_id, stop_client_algo_id, take_profit_client_algo_id)
            except ProtectivePersistenceError as exc:
                issues.append(self._issue("persistence_consistency_blocked", "FAIL", "Protective journal and persistence state are inconsistent."))
                return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "FAIL", exc.code, "Protective persistence consistency check blocked mutation.", credential_metadata=metadata, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="RECOVERY_REQUIRED", recovery_required=True)
            if consistency.status == "ALREADY_COMPLETED":
                return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "PASS", "PROTECTIVE_LIFECYCLE_ALREADY_COMPLETED", "Persisted protective lifecycle is already complete; no mutation was resent.", credential_metadata=metadata, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="COMPLETE", lifecycle_complete=True)
            persistence_state = consistency.state
            if existing_journal is not None:
                journal = existing_journal
                self._handle_existing_lifecycle_journal(client, config, journal, pair_id, stop_client_algo_id, take_profit_client_algo_id, query_requests, reconciliation_results, persistence, persistence_state)
                stop_client_algo_id = stop_client_algo_id or journal.stop_client_algo_id
                take_profit_client_algo_id = take_profit_client_algo_id or journal.take_profit_client_algo_id
                self._archive_resolved_journal(config, journal)
                journal = BinanceFuturesTestnetProtectiveJournal(pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
            filters = client.fetch_exchange_filters()
            self._server_time_or_issue(client, config, issues)
            if client.fetch_position_mode():
                raise ProtectiveAbort("POSITION_MODE_UNSUPPORTED", "Position mode is Hedge Mode; One-way Mode is required.")
            position = client.require_protectable_position(client.fetch_position_risk())
            preview = client.build_preview(pair_id, stop_client_algo_id, take_profit_client_algo_id, position, filters, stop_offset_bps, take_profit_offset_bps)
            stop_client_algo_id = preview.stop_client_algo_id
            take_profit_client_algo_id = preview.take_profit_client_algo_id
            journal.stop_client_algo_id = stop_client_algo_id
            journal.take_profit_client_algo_id = take_profit_client_algo_id
            self._attach_journal_baseline(journal, position, preview)
            persistence_state = persistence.prepare_lifecycle(pair_id, stop_client_algo_id, take_profit_client_algo_id, position, preview)
            self._write_journal(config, journal, "PRECHECK_STARTED", {"pair_id": pair_id})
            self._write_journal(config, journal, "POSITION_VALIDATED", self._position_details(position))
            self._write_journal(config, journal, "STOP_CREATE_STARTED", {"client_algo_id": stop_client_algo_id})
            stop_create_started = True
            stop_order = self._create_with_reconciliation(client, config, journal, preview, "STOP", create_requests, query_requests, reconciliation_results, persistence, persistence_state, stop_create_permit)
            self._write_journal(config, journal, "STOP_CREATED", self._algo_details(stop_order))
            stop_order, meta = client.query_algo_order(stop_client_algo_id)
            query_requests.append(meta)
            self._validate_algo_identity(stop_order, preview, "STOP")
            self._require_new(stop_order, "STOP")
            self._write_journal(config, journal, "STOP_QUERY_COMPLETE", self._algo_details(stop_order))
            self._write_journal(config, journal, "TAKE_PROFIT_CREATE_STARTED", {"client_algo_id": take_profit_client_algo_id})
            take_create_started = True
            take_order = self._create_with_reconciliation(client, config, journal, preview, "TAKE_PROFIT", create_requests, query_requests, reconciliation_results, persistence, persistence_state, take_profit_create_permit)
            self._write_journal(config, journal, "TAKE_PROFIT_CREATED", self._algo_details(take_order))
            take_order, meta = client.query_algo_order(take_profit_client_algo_id)
            query_requests.append(meta)
            self._validate_algo_identity(take_order, preview, "TAKE_PROFIT")
            self._require_new(take_order, "TAKE_PROFIT")
            self._write_journal(config, journal, "TAKE_PROFIT_QUERY_COMPLETE", self._algo_details(take_order))
            self._require_same_position(position, client.require_protectable_position(client.fetch_position_risk()))
            cancel_started = True
            take_delete_absent = self._delete_with_reconciliation(client, config, journal, preview, "TAKE_PROFIT", cancel_requests, query_requests, reconciliation_results, persistence, persistence_state, take_profit_cancel_permit)
            if take_delete_absent:
                final_take = None
                self._write_journal(config, journal, "TAKE_PROFIT_CANCELED", {"client_algo_id": take_profit_client_algo_id, "status": "ABSENT"})
            else:
                final_take, meta = client.query_algo_order(take_profit_client_algo_id)
                query_requests.append(meta)
                self._validate_algo_identity(final_take, preview, "TAKE_PROFIT")
                self._require_terminal_safe(final_take, "TAKE_PROFIT")
                self._write_journal(config, journal, "TAKE_PROFIT_CANCELED", self._algo_details(final_take))
            stop_delete_absent = self._delete_with_reconciliation(client, config, journal, preview, "STOP", cancel_requests, query_requests, reconciliation_results, persistence, persistence_state, stop_cancel_permit)
            if stop_delete_absent:
                final_stop = None
                self._write_journal(config, journal, "STOP_CANCELED", {"client_algo_id": stop_client_algo_id, "status": "ABSENT"})
            else:
                final_stop, meta = client.query_algo_order(stop_client_algo_id)
                query_requests.append(meta)
                self._validate_algo_identity(final_stop, preview, "STOP")
                self._require_terminal_safe(final_stop, "STOP")
                self._write_journal(config, journal, "STOP_CANCELED", self._algo_details(final_stop))
            final_position = client.require_protectable_position(client.fetch_position_risk())
            self._require_same_position(position, final_position)
            journal.recovery_required = False
            self._write_journal(config, journal, "COMPLETE", {"stop_status": "ABSENT" if final_stop is None else final_stop.algo_status, "take_profit_status": "ABSENT" if final_take is None else final_take.algo_status})
        except ProtectivePersistenceError as exc:
            recovery = bool(exc.after_transport or stop_create_started or take_create_started or cancel_started)
            issues.append(self._issue(exc.code.lower(), "FAIL", "Protective persistence transition failed safely."))
            journal.recovery_required = recovery
            preserve_journal = not exc.after_transport and exc.code in {
                "PERSISTENCE_COMMIT_FAILED",
                "PERSISTENCE_VERSION_CONFLICT",
                "PERSISTENCE_REPLAY_MISMATCH",
                "PERSISTENCE_STATE_MISMATCH",
            }
            if journal.entries and not preserve_journal:
                self._try_write_journal(config, journal, "RECOVERY_REQUIRED" if recovery else "FAILED", {"reason": exc.code})
            if recovery and persistence_state is not None and not preserve_journal:
                try:
                    persistence.mark_recovery_required(persistence_state, "DELETE" if cancel_started else "CREATE", exc.code)
                except ProtectivePersistenceError:
                    pass
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "FAIL", "RECOVERY_REQUIRED" if recovery else exc.code, "Protective persistence transition failed safely.", credential_metadata=metadata, exchange_filters=filters, position=position, final_position=final_position, preview=preview, stop_order=stop_order, take_profit_order=take_order, final_stop_order=final_stop, final_take_profit_order=final_take, create_requests=create_requests, query_requests=query_requests, cancel_requests=cancel_requests, reconciliation_results=reconciliation_results, journal=journal if journal.entries else None, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="RECOVERY_REQUIRED" if recovery else "FAILED", recovery_required=recovery)
        except ProtectiveAbort as exc:
            issues.append(self._issue(exc.decision.lower(), "CRITICAL" if exc.critical else "FAIL", exc.reason))
            delete_recovery = cancel_started or any(
                intent.mutation_kind == ProtectiveMutationKind.DELETE.value and not intent.resolved
                for intent in journal.mutation_intents
            )
            # Lifecycle-started flags are written before the final permit gate.
            # They must not turn a pre-consume denial into exchange ambiguity.
            # Recovery requires either explicit boundary evidence, an unresolved
            # delete intent, or a previously confirmed protective order.
            recovery = bool(
                exc.recovery
                or exc.critical
                or delete_recovery
                or stop_order is not None
                or take_order is not None
            )
            journal.recovery_required = recovery
            if persistence_state is not None and recovery:
                try:
                    persistence.mark_recovery_required(persistence_state, "DELETE" if delete_recovery else "CREATE", exc.decision)
                except ProtectivePersistenceError:
                    pass
            if exc.decision != "JOURNAL_ARCHIVE_FAILED":
                self._write_journal(config, journal, "RECOVERY_REQUIRED" if recovery else "FAILED", {"reason": exc.reason})
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "CRITICAL" if exc.critical else "FAIL", exc.decision, exc.reason, credential_metadata=metadata, exchange_filters=filters, position=position, final_position=final_position, preview=preview, stop_order=stop_order, take_profit_order=take_order, final_stop_order=final_stop, final_take_profit_order=final_take, create_requests=create_requests, query_requests=query_requests, cancel_requests=cancel_requests, reconciliation_results=reconciliation_results, journal=journal, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="RECOVERY_REQUIRED" if exc.decision == "JOURNAL_ARCHIVE_FAILED" else journal.phase, recovery_required=recovery, unexpected_trigger=exc.critical, unexpected_position_change=exc.decision == "UNEXPECTED_POSITION_CHANGE")
        except BinanceFuturesTestnetProtectiveAPIError as exc:
            message = self._sanitize_api_error(exc)
            recovery = bool((stop_create_started or take_create_started or cancel_started) and exc.request_transmitted)
            decision = "TIMESTAMP_OUTSIDE_RECV_WINDOW" if exc.binance_code == -1021 else "RECOVERY_REQUIRED" if recovery else "PROTECTIVE_PRECHECK_FAILED"
            issues.append(self._issue(decision.lower(), "FAIL", message))
            journal.recovery_required = recovery
            if recovery and persistence_state is not None:
                try:
                    persistence.mark_recovery_required(persistence_state, "DELETE" if cancel_started else "CREATE", decision)
                except ProtectivePersistenceError:
                    pass
            self._write_journal(config, journal, "RECOVERY_REQUIRED" if recovery else "FAILED", {"reason": message})
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "FAIL", decision, "Protective lifecycle failed safely.", credential_metadata=metadata, exchange_filters=filters, position=position, final_position=final_position, preview=preview, stop_order=stop_order, take_profit_order=take_order, final_stop_order=final_stop, final_take_profit_order=final_take, create_requests=create_requests, query_requests=query_requests, cancel_requests=cancel_requests, reconciliation_results=reconciliation_results, journal=journal, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase=journal.phase, recovery_required=recovery)
        except Exception as exc:
            message = self._sanitize(str(exc))
            recovery = stop_create_started or take_create_started or cancel_started
            decision = "RECOVERY_REQUIRED" if recovery else "PROTECTIVE_PRECHECK_FAILED"
            issues.append(self._issue("protective_lifecycle_failed", "FAIL", message))
            journal.recovery_required = recovery
            if recovery and persistence_state is not None:
                try:
                    persistence.mark_recovery_required(persistence_state, "DELETE" if cancel_started else "CREATE", decision)
                except ProtectivePersistenceError:
                    pass
            self._write_journal(config, journal, "RECOVERY_REQUIRED" if recovery else "FAILED", {"reason": message})
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "FAIL", decision, "Protective lifecycle failed safely.", credential_metadata=metadata, exchange_filters=filters, position=position, final_position=final_position, preview=preview, stop_order=stop_order, take_profit_order=take_order, final_stop_order=final_stop, final_take_profit_order=final_take, create_requests=create_requests, query_requests=query_requests, cancel_requests=cancel_requests, reconciliation_results=reconciliation_results, journal=journal, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase=journal.phase, recovery_required=recovery)
        finally:
            self._release_owned_lock(lock_path, lock_token, lock_acquired)
            persistence.close()
        return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "PASS", "PROTECTIVE_LIFECYCLE_COMPLETE", "Protective STOP_MARKET and TAKE_PROFIT_MARKET lifecycle completed without changing the position.", credential_metadata=metadata, exchange_filters=filters, position=position, final_position=final_position, preview=preview, stop_order=stop_order, take_profit_order=take_order, final_stop_order=final_stop, final_take_profit_order=final_take, create_requests=create_requests, query_requests=query_requests, cancel_requests=cancel_requests, reconciliation_results=reconciliation_results, journal=journal, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="COMPLETE", lifecycle_complete=True)

    def query_protective_pair(self, stop_client_algo_id: str, take_profit_client_algo_id: str, config_path: str = "configs/binance_futures_testnet_protective_orders.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetProtectiveResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetProtectiveOrdersConfig()
        issues = list(report.issues)
        client = self._client(config)
        try:
            metadata = client.inspect_credentials()
        except Exception:
            return self._result(config, "QUERY_PROTECTIVE_PAIR", "FAIL", "CREDENTIALS_UNAVAILABLE", "Testnet credential readiness is unavailable.", issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        if report.status == "FAIL" or not metadata.credentials_complete:
            return self._result(config, "QUERY_PROTECTIVE_PAIR", "WARNING" if not metadata.credentials_complete else "FAIL", "CREDENTIALS_NOT_CONFIGURED" if not metadata.credentials_complete else "OPERATION_BLOCKED", "Query requires valid config and credentials.", credential_metadata=metadata, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        self._server_time_or_issue(client, config, issues)
        try:
            stop, stop_meta = client.query_algo_order(stop_client_algo_id)
            take, take_meta = client.query_algo_order(take_profit_client_algo_id)
            self._validate_algo_identity(stop, None, "STOP", stop_client_algo_id=stop_client_algo_id)
            self._validate_algo_identity(take, None, "TAKE_PROFIT", take_profit_client_algo_id=take_profit_client_algo_id)
            self._require_matching_query_pair(stop, take)
            self._check_unexpected_trigger(stop)
            self._check_unexpected_trigger(take)
            return self._result(config, "QUERY_PROTECTIVE_PAIR", "PASS", "QUERY_COMPLETE", "Protective pair queried read-only by exact clientAlgoId.", credential_metadata=metadata, stop_order=stop, take_profit_order=take, query_requests=[stop_meta, take_meta], issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="QUERY_COMPLETE")
        except ProtectiveAbort as exc:
            issues.append(self._issue(exc.decision.lower(), "CRITICAL" if exc.critical else "FAIL", exc.reason))
            return self._result(config, "QUERY_PROTECTIVE_PAIR", "CRITICAL" if exc.critical else "FAIL", exc.decision, exc.reason, credential_metadata=metadata, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="QUERY_COMPLETE", recovery_required=exc.recovery or exc.critical, unexpected_trigger=exc.critical)
        except Exception as exc:
            issues.append(self._issue("query_failed", "FAIL", self._sanitize_api_error(exc)))
            return self._result(config, "QUERY_PROTECTIVE_PAIR", "FAIL", "QUERY_FAILED", "Protective pair query failed safely without mutation.", credential_metadata=metadata, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="QUERY_FAILED", recovery_required=False)

    def recover_protective_pair(self, stop_client_algo_id: str, take_profit_client_algo_id: str, confirmation: str | None = None, config_path: str = "configs/binance_futures_testnet_protective_orders.json", expected_profile: str = "balanced_smc_decision_065", reconcile_only: bool = False, stop_cancel_permit: LiveExecutionPermitReference | None = None, take_profit_cancel_permit: LiveExecutionPermitReference | None = None) -> BinanceFuturesTestnetProtectiveResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetProtectiveOrdersConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "FAIL", "OPERATION_BLOCKED", "Protective config failed validation.", issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        if confirmation != config.recovery_confirmation_phrase:
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "WARNING", "CONFIRMATION_REQUIRED", "Explicit protective recovery confirmation is required.", issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        client = self._client(config)
        try:
            metadata = client.inspect_credentials()
        except Exception:
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "FAIL", "CREDENTIALS_UNAVAILABLE", "Testnet credential readiness is unavailable.", issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        if not metadata.credentials_complete:
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "WARNING", "CREDENTIALS_NOT_CONFIGURED", "Dedicated testnet credentials are incomplete or missing.", credential_metadata=metadata, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        persistence = self.persistence_factory(env=self.env)
        try:
            persistence.ensure_available()
        except ProtectivePersistenceError as exc:
            issues.append(self._issue(exc.code.lower(), "FAIL", "Protective persistence is unavailable or invalid."))
            persistence.close()
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "FAIL", exc.code, "Protective persistence preflight failed safely before runtime mutation.", credential_metadata=metadata, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        lock_path = self._resolve(config.lock_path)
        lock_token = self._lock_token("recover_protective_pair", "", stop_client_algo_id, take_profit_client_algo_id)
        lock_acquired = self._acquire_owned_lock(lock_path, lock_token)
        if not lock_acquired:
            issues.append(self._issue("protective_lock_exists", "FAIL", "An active protective-order lock already exists."))
            persistence.close()
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "FAIL", "RECOVERY_REQUIRED", "Existing protective lock blocks exact recovery.", credential_metadata=metadata, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, recovery_required=True)
        journal = BinanceFuturesTestnetProtectiveJournal(stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, recovery_required=True)
        query_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata] = []
        cancel_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata] = []
        reconciliation_results: list[ProtectiveReconciliationResult] = []
        stop = take = final_stop = final_take = None
        position = None
        persistence_state: ProtectivePersistenceState | None = None
        try:
            try:
                journal = self._load_or_new_journal(config, stop_client_algo_id, take_profit_client_algo_id)
            except ProtectiveAbort as exc:
                issues.append(self._issue(exc.decision.lower(), "FAIL", exc.reason))
                return self._result(config, "RECOVER_PROTECTIVE_PAIR", "FAIL", exc.decision, exc.reason, credential_metadata=metadata, journal=journal, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="RECOVERY_REQUIRED", recovery_required=True)
            except Exception as exc:
                message = self._sanitize(str(exc))
                issues.append(self._issue("protective_journal_load_failed", "FAIL", message))
                return self._result(config, "RECOVER_PROTECTIVE_PAIR", "FAIL", "RECOVERY_REQUIRED", "Protective journal could not be trusted; recovery is required.", credential_metadata=metadata, journal=journal, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="RECOVERY_REQUIRED", recovery_required=True)
            try:
                consistency = persistence.check_consistency(journal, journal.pair_id, stop_client_algo_id, take_profit_client_algo_id)
                persistence_state = consistency.state
                if persistence_state is None and not getattr(persistence, "legacy_noop", False):
                    raise ProtectivePersistenceError("PERSISTENCE_STATE_MISSING")
                if consistency.status == "ALREADY_COMPLETED":
                    self._server_time_or_issue(client, config, issues)
                    stop, meta = self._query_or_absent(client, stop_client_algo_id, journal, "STOP")
                    if meta is not None:
                        query_requests.append(meta)
                    take, meta = self._query_or_absent(client, take_profit_client_algo_id, journal, "TAKE_PROFIT")
                    if meta is not None:
                        query_requests.append(meta)
                    self._validate_recovery_pair(stop, take, journal, stop_client_algo_id, take_profit_client_algo_id)
                    if stop is not None:
                        self._require_terminal_safe(stop, "STOP")
                    if take is not None:
                        self._require_terminal_safe(take, "TAKE_PROFIT")
                    return self._result(config, "RECOVER_PROTECTIVE_PAIR", "PASS", "RECOVERY_COMPLETE", "Protective pair exact recovery was already complete; no mutation was resent.", credential_metadata=metadata, stop_order=stop, take_profit_order=take, final_stop_order=stop, final_take_profit_order=take, query_requests=query_requests, cancel_requests=cancel_requests, reconciliation_results=reconciliation_results, journal=journal, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="RECOVERY_COMPLETE", lifecycle_complete=True)
            except ProtectivePersistenceError as exc:
                issues.append(self._issue("persistence_consistency_blocked", "FAIL", "Protective journal and persistence state are inconsistent."))
                return self._result(config, "RECOVER_PROTECTIVE_PAIR", "FAIL", exc.code, "Protective persistence consistency check blocked recovery mutation.", credential_metadata=metadata, journal=journal, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="RECOVERY_REQUIRED", recovery_required=True)
            self._write_journal(config, journal, "RECOVERY_STARTED", {"stop_client_algo_id": stop_client_algo_id, "take_profit_client_algo_id": take_profit_client_algo_id})
            self._server_time_or_issue(client, config, issues)
            caught_up: list[tuple[ProtectiveMutationIntent, ProtectiveReconciliationResult]] = []
            if not getattr(persistence, "legacy_noop", False):
                caught_up = self._catch_up_resolved_intents(client, journal, query_requests, reconciliation_results, persistence, persistence_state)
            if reconcile_only:
                return self._run_reconcile_only_recovery(
                    client,
                    config,
                    journal,
                    stop_client_algo_id,
                    take_profit_client_algo_id,
                    query_requests,
                    reconciliation_results,
                    persistence,
                    persistence_state,
                    metadata,
                    issues,
                    caught_up,
                )
            self._reconcile_unresolved_intents(client, config, journal, stop_client_algo_id, take_profit_client_algo_id, query_requests, reconciliation_results, persistence, persistence_state)
            stop, meta = self._query_or_absent(client, stop_client_algo_id, journal, "STOP")
            if meta is not None:
                query_requests.append(meta)
            take, meta = self._query_or_absent(client, take_profit_client_algo_id, journal, "TAKE_PROFIT")
            if meta is not None:
                query_requests.append(meta)
            self._validate_recovery_pair(stop, take, journal, stop_client_algo_id, take_profit_client_algo_id)
            if stop is not None:
                self._check_unexpected_trigger(stop)
            if take is not None:
                self._check_unexpected_trigger(take)
            if (stop is not None and stop.algo_status == "NEW") or (take is not None and take.algo_status == "NEW"):
                position = self._current_position_for_recovery(client)
                self._compare_recovery_baseline(journal, position)
                self._attach_recovery_baseline_from_orders(journal, position, stop, take)
            if take is not None and take.algo_status == "NEW":
                recovery_preview = self._recovery_preview_from_journal(journal, stop_client_algo_id, take_profit_client_algo_id)
                take_delete_absent = self._delete_with_reconciliation(client, config, journal, recovery_preview, "TAKE_PROFIT", cancel_requests, query_requests, reconciliation_results, persistence, persistence_state, take_profit_cancel_permit)
                final_take = None if take_delete_absent else reconciliation_results[-1].order
            else:
                final_take, meta = self._query_or_absent(client, take_profit_client_algo_id, journal, "TAKE_PROFIT")
                if meta is not None:
                    query_requests.append(meta)
            if final_take is not None:
                self._validate_recovery_identity(final_take, journal, "TAKE_PROFIT", take_profit_client_algo_id)
                self._check_unexpected_trigger(final_take)
            if stop is not None and stop.algo_status == "NEW":
                recovery_preview = self._recovery_preview_from_journal(journal, stop_client_algo_id, take_profit_client_algo_id)
                stop_delete_absent = self._delete_with_reconciliation(client, config, journal, recovery_preview, "STOP", cancel_requests, query_requests, reconciliation_results, persistence, persistence_state, stop_cancel_permit)
                final_stop = None if stop_delete_absent else reconciliation_results[-1].order
            else:
                final_stop, meta = self._query_or_absent(client, stop_client_algo_id, journal, "STOP")
                if meta is not None:
                    query_requests.append(meta)
            if final_stop is not None:
                self._validate_recovery_identity(final_stop, journal, "STOP", stop_client_algo_id)
                self._check_unexpected_trigger(final_stop)
            position = self._current_position_for_recovery(client)
            self._compare_recovery_baseline(journal, position)
            if final_take is not None:
                self._require_terminal_safe(final_take, "TAKE_PROFIT")
            if final_stop is not None:
                self._require_terminal_safe(final_stop, "STOP")
            journal.recovery_required = False
            self._write_journal(config, journal, "RECOVERY_COMPLETE", {"stop_status": "ABSENT" if final_stop is None else final_stop.algo_status, "take_profit_status": "ABSENT" if final_take is None else final_take.algo_status})
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "PASS", "RECOVERY_COMPLETE", "Protective pair exact recovery completed.", credential_metadata=metadata, position=position, stop_order=stop, take_profit_order=take, final_stop_order=final_stop, final_take_profit_order=final_take, query_requests=query_requests, cancel_requests=cancel_requests, reconciliation_results=reconciliation_results, journal=journal, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="RECOVERY_COMPLETE", lifecycle_complete=True)
        except ProtectivePersistenceError as exc:
            issues.append(self._issue(exc.code.lower(), "FAIL", "Protective persistence transition failed safely."))
            journal.recovery_required = True
            self._try_write_journal(config, journal, "RECOVERY_REQUIRED", {"reason": exc.code})
            if persistence_state is not None:
                try:
                    persistence.mark_recovery_required(persistence_state, "DELETE", exc.code)
                except ProtectivePersistenceError:
                    pass
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "FAIL", "RECOVERY_REQUIRED", "Protective persistence transition failed safely.", credential_metadata=metadata, position=position, stop_order=stop, take_profit_order=take, final_stop_order=final_stop, final_take_profit_order=final_take, query_requests=query_requests, cancel_requests=cancel_requests, reconciliation_results=reconciliation_results, journal=journal, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="RECOVERY_REQUIRED", recovery_required=True)
        except ProtectiveAbort as exc:
            issues.append(self._issue(exc.decision.lower(), "CRITICAL" if exc.critical else "FAIL", exc.reason))
            journal.recovery_required = True
            if persistence_state is not None:
                try:
                    persistence.mark_recovery_required(persistence_state, "DELETE", exc.decision)
                except ProtectivePersistenceError:
                    pass
            self._try_write_journal(config, journal, "RECOVERY_REQUIRED", {"reason": exc.reason})
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "CRITICAL" if exc.critical else "FAIL", exc.decision, exc.reason, credential_metadata=metadata, position=position, stop_order=stop, take_profit_order=take, final_stop_order=final_stop, final_take_profit_order=final_take, query_requests=query_requests, cancel_requests=cancel_requests, reconciliation_results=reconciliation_results, journal=journal, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="RECOVERY_REQUIRED", recovery_required=True, unexpected_trigger=exc.critical)
        except Exception as exc:
            message = self._sanitize(str(exc))
            issues.append(self._issue("protective_recovery_failed", "FAIL", message))
            journal.recovery_required = True
            if persistence_state is not None:
                try:
                    persistence.mark_recovery_required(persistence_state, "DELETE", "RECOVERY_RUNTIME_FAILURE")
                except ProtectivePersistenceError:
                    pass
            self._try_write_journal(config, journal, "RECOVERY_REQUIRED", {"reason": message})
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "FAIL", "RECOVERY_REQUIRED", "Protective pair recovery failed safely.", credential_metadata=metadata, position=position, stop_order=stop, take_profit_order=take, final_stop_order=final_stop, final_take_profit_order=final_take, query_requests=query_requests, cancel_requests=cancel_requests, reconciliation_results=reconciliation_results, journal=journal, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="RECOVERY_REQUIRED", recovery_required=True)
        finally:
            self._release_owned_lock(lock_path, lock_token, lock_acquired)
            persistence.close()

    def _run_reconcile_only_recovery(
        self,
        client: BinanceFuturesTestnetProtectiveOrdersClient,
        config: BinanceFuturesTestnetProtectiveOrdersConfig,
        journal: BinanceFuturesTestnetProtectiveJournal,
        stop_client_algo_id: str,
        take_profit_client_algo_id: str,
        query_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata],
        reconciliation_results: list[ProtectiveReconciliationResult],
        persistence: ProtectiveLifecyclePersistence,
        persistence_state: ProtectivePersistenceState | None,
        metadata: BinanceFuturesTestnetProtectiveCredentialMetadata,
        issues: list[BinanceFuturesTestnetProtectiveIssue],
        caught_up: list[tuple[ProtectiveMutationIntent, ProtectiveReconciliationResult]],
    ) -> BinanceFuturesTestnetProtectiveResult:
        if persistence_state is None:
            raise ProtectivePersistenceError("PERSISTENCE_STATE_MISSING")
        staged: list[tuple[ProtectiveMutationIntent, ProtectiveReconciliationResult]] = []
        for intent in journal.mutation_intents:
            if intent.resolved:
                continue
            self._validate_persisted_intent(intent, journal.pair_id, stop_client_algo_id, take_profit_client_algo_id)
            result = self._reconcile_intent(client, intent, query_requests)
            interpreted = self._interpret_mutation(intent, result)
            result.interpreted_mutation_result = interpreted
            result.resolved = interpreted == "CREATE_CONFIRMED" if intent.mutation_kind == ProtectiveMutationKind.CREATE.value else self._is_delete_confirmed(interpreted)
            result.recovery_required = not result.resolved
            reconciliation_results.append(result)
            if not result.resolved:
                raise ProtectiveAbort(
                    "RECOVERY_REQUIRED",
                    f"Exact {intent.label} {intent.mutation_kind} reconciliation remains unresolved.",
                    recovery=True,
                )
            staged.append((intent, result))

        for intent, result in staged:
            persistence.apply_reconciliation(persistence_state, intent, result)
            intent.reconciliation_state = result.reconciliation_state
            intent.reconciliation_reason = result.reason
            intent.resolved = True

        if any(not intent.resolved for intent in journal.mutation_intents):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective reconciliation remains unresolved.", recovery=True)

        stop, stop_meta = self._query_or_absent(client, stop_client_algo_id, journal, "STOP")
        if stop_meta is not None:
            query_requests.append(stop_meta)
        take, take_meta = self._query_or_absent(client, take_profit_client_algo_id, journal, "TAKE_PROFIT")
        if take_meta is not None:
            query_requests.append(take_meta)
        self._validate_recovery_pair(stop, take, journal, stop_client_algo_id, take_profit_client_algo_id)
        if stop is not None:
            self._check_unexpected_trigger(stop)
        if take is not None:
            self._check_unexpected_trigger(take)

        final_phase = journal.phase
        reconciled = [*caught_up, *staged]
        if reconciled:
            last_intent, last_result = reconciled[-1]
            if last_intent.mutation_kind == ProtectiveMutationKind.DELETE.value:
                final_phase = f"{last_intent.label}_CANCELED"
            else:
                final_phase = f"{last_intent.label}_{last_intent.mutation_kind}_{last_result.interpreted_mutation_result}"

        if journal.recovery_required or reconciled:
            journal.recovery_required = False
            details = {
                "mode": "RECONCILE_ONLY",
                "stop_status": "ABSENT" if stop is None else stop.algo_status,
                "take_profit_status": "ABSENT" if take is None else take.algo_status,
            }
            if reconciled and reconciled[-1][0].mutation_kind == ProtectiveMutationKind.DELETE.value:
                label = reconciled[-1][0].label
                details["status"] = details["stop_status" if label == "STOP" else "take_profit_status"]
            self._write_journal(
                config,
                journal,
                final_phase,
                details,
            )
            if final_phase == "STOP_CANCELED" and stop is None and take is None:
                self._write_journal(config, journal, "RECOVERY_COMPLETE", {"mode": "RECONCILE_ONLY"})
        consistency = persistence.check_consistency(
            journal, journal.pair_id, stop_client_algo_id, take_profit_client_algo_id
        )
        if consistency.status not in {"RECOVERY", "ALREADY_COMPLETED"}:
            raise ProtectivePersistenceError("PERSISTENCE_STATE_MISMATCH", after_transport=True)
        lifecycle_complete = journal.phase == "RECOVERY_COMPLETE"
        return self._result(
            config,
            "RECONCILE_PROTECTIVE_PAIR",
            "PASS",
            "RECONCILIATION_COMPLETE",
            "Protective pair exact GET-only reconciliation completed.",
            credential_metadata=metadata,
            stop_order=stop,
            take_profit_order=take,
            final_stop_order=stop,
            final_take_profit_order=take,
            query_requests=query_requests,
            reconciliation_results=reconciliation_results,
            journal=journal,
            issues=issues,
            stop_client_algo_id=stop_client_algo_id,
            take_profit_client_algo_id=take_profit_client_algo_id,
            phase=journal.phase,
            lifecycle_complete=lifecycle_complete,
            recovery_required=False,
        )

    def load_config(self, config_path: str) -> BinanceFuturesTestnetProtectiveOrdersConfig:
        path = Path(config_path)
        if not path.is_absolute():
            path = self.repo_root / path
        payload = json.loads(path.read_text(encoding="utf-8"))
        return BinanceFuturesTestnetProtectiveOrdersConfig(**payload)

    def _client(self, config: BinanceFuturesTestnetProtectiveOrdersConfig) -> BinanceFuturesTestnetProtectiveOrdersClient:
        return BinanceFuturesTestnetProtectiveOrdersClient(config, http_get=self.http_get, authenticated_request=self.authenticated_request, env=self.env, now_ms_provider=self.now_ms_provider)

    def _validate_config(self, config: BinanceFuturesTestnetProtectiveOrdersConfig, expected_profile: str, issues: list[BinanceFuturesTestnetProtectiveIssue]) -> None:
        self._expect(config.project_scope == "BTC_ONLY", issues, "project_scope", "project_scope must be BTC_ONLY.")
        self._expect(config.symbol == "BTC/USDT", issues, "symbol", "symbol must be BTC/USDT.")
        self._expect(config.exchange_symbol == "BTCUSDT", issues, "exchange_symbol", "exchange_symbol must be BTCUSDT.")
        self._expect(config.exchange == "binance", issues, "exchange", "exchange must be binance.")
        self._expect(config.market_type == "futures", issues, "market_type", "market_type must be futures.")
        self._expect(config.futures_contract_type == "USDT_PERPETUAL", issues, "futures_contract_type", "futures_contract_type must be USDT_PERPETUAL.")
        self._expect(config.strategy_profile == expected_profile, issues, "strategy_profile", f"strategy_profile must be {expected_profile}.")
        self._expect(config.rest_base_url == "https://demo-fapi.binance.com", issues, "rest_base_url", "Only Binance USD-M Futures Testnet is allowed.")
        self._expect(config.allowed_hosts == ["demo-fapi.binance.com"] and urlparse(config.rest_base_url).hostname in config.allowed_hosts, issues, "allowed_hosts", "Allowed hosts must be exactly demo-fapi.binance.com.")
        self._expect(config.api_key_env_var == "BINANCE_FUTURES_TESTNET_API_KEY", issues, "api_key_env_var", "API key env var must be dedicated testnet key.")
        self._expect(config.api_secret_env_var == "BINANCE_FUTURES_TESTNET_API_SECRET", issues, "api_secret_env_var", "API secret env var must be dedicated testnet secret.")
        self._expect(config.server_time_path == "/fapi/v1/time", issues, "server_time_path", "server time path must be exact.")
        self._expect(config.exchange_info_path == "/fapi/v1/exchangeInfo", issues, "exchange_info_path", "exchange info path must be exact.")
        self._expect(config.position_mode_path == "/fapi/v1/positionSide/dual", issues, "position_mode_path", "position mode path must be exact.")
        self._expect(config.position_risk_path == "/fapi/v3/positionRisk", issues, "position_risk_path", "position risk path must be exact.")
        self._expect(config.feature_enabled is False and config.automatic_execution_enabled is False, issues, "disabled_by_default", "Protective orders must be disabled by default.")
        self._expect(config.explicit_cli_only and config.manual_only and config.testnet_only, issues, "manual_testnet_only", "Feature must be explicit CLI, manual and testnet-only.")
        self._expect(config.allowed_algo_type == "CONDITIONAL", issues, "allowed_algo_type", "algoType must be CONDITIONAL.")
        self._expect(config.allowed_order_types == ["STOP_MARKET", "TAKE_PROFIT_MARKET"], issues, "allowed_order_types", "Only STOP_MARKET and TAKE_PROFIT_MARKET are allowed.")
        self._expect(config.allowed_methods == ["POST", "GET", "DELETE"], issues, "allowed_methods", "Only exact POST/GET/DELETE are allowed.")
        self._expect(config.algo_order_path == "/fapi/v1/algoOrder", issues, "algo_order_path", "Protective orders must use /fapi/v1/algoOrder.")
        self._expect(config.request_timeout_seconds == 30 and config.recv_window_ms == 10000 and config.maximum_recv_window_ms == 10000 and config.maximum_clock_skew_ms <= 5000 and 0 < int(config.maximum_server_time_sync_age_ms) <= 5000, issues, "timeout_recv_window", "Timeout, recvWindow, server-time sync age and clock skew must remain hardened.")
        self._expect(config.required_position_mode == "ONE_WAY" and config.required_position_side == "BOTH" and config.working_type == "MARK_PRICE" and config.close_position and config.price_protect and config.new_order_response_type == "ACK", issues, "close_position_safety", "Protective algo orders must be closePosition/BOTH/MARK_PRICE/priceProtect/ACK.")
        self._expect(0 < float(config.maximum_position_abs_quantity) <= 0.002, issues, "maximum_position_abs_quantity", "Maximum position quantity must be > 0 and <= 0.002.")
        self._expect(0 < float(config.maximum_position_notional_usdt) <= 150.0, issues, "maximum_position_notional_usdt", "Maximum notional must be > 0 and <= 150.")
        self._expect(int(config.minimum_stop_offset_bps) >= 500 and int(config.maximum_stop_offset_bps) <= 3000 and int(config.minimum_stop_offset_bps) <= int(config.default_stop_offset_bps) <= int(config.maximum_stop_offset_bps), issues, "stop_offsets", "Stop offsets must remain within safe configured range.")
        self._expect(int(config.minimum_take_profit_offset_bps) >= 500 and int(config.maximum_take_profit_offset_bps) <= 3000 and int(config.minimum_take_profit_offset_bps) <= int(config.default_take_profit_offset_bps) <= int(config.maximum_take_profit_offset_bps), issues, "take_profit_offsets", "Take-profit offsets must remain within safe configured range.")
        self._expect(config.max_create_retries == 0 and config.max_cancel_retries == 0 and config.max_query_retries in (0, 1), issues, "mutation_retries", "POST/DELETE retries must be zero and GET retry at most one.")
        self._expect(config.client_algo_id_prefix == "smcbot-protect-" and int(config.maximum_client_algo_id_length) <= 36, issues, "client_algo_id_policy", "Protective clientAlgoId policy must remain fixed.")
        self._expect(config.pair_confirmation_phrase == "CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", issues, "pair_confirmation_phrase", "Pair confirmation phrase must remain exact.")
        self._expect(config.recovery_confirmation_phrase == "CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", issues, "recovery_confirmation_phrase", "Recovery confirmation phrase must remain exact.")
        self._expect(config.allow_sanitized_local_journal is True, issues, "allow_sanitized_local_journal", "Sanitized journal must remain enabled.")
        unsafe = [
            config.allow_position_entry,
            config.allow_position_close,
            config.allow_market_order,
            config.allow_regular_limit_order,
            config.allow_cancel_all,
            config.allow_open_algo_order_list,
            config.allow_order_history,
            config.allow_trade_history,
            config.allow_leverage_change,
            config.allow_margin_mode_change,
            config.allow_position_mode_change,
            config.allow_production_endpoint,
            config.allow_real_funds,
            config.allow_raw_request_persistence,
            config.allow_raw_response_persistence,
            config.allow_authenticated_header_logging,
            config.allow_signature_logging,
            config.allow_signed_url_logging,
        ]
        self._expect(not any(unsafe), issues, "hard_safety_flags", "Unsafe protective-order capabilities must remain disabled.")
        for name, value in (("journal_path", config.journal_path), ("lock_path", config.lock_path)):
            path = Path(value)
            self._expect(not path.is_absolute() and ".." not in path.parts and len(path.parts) >= 3 and path.parts[0] == "data" and path.parts[1] == "runtime" and path.parts[2] == "binance_futures_testnet_protective_orders", issues, name, f"{name} must stay under data/runtime/binance_futures_testnet_protective_orders.")
        report_dir = Path(config.report_export_dir)
        self._expect(not report_dir.is_absolute() and ".." not in report_dir.parts and len(report_dir.parts) >= 2 and report_dir.parts[0] == "reports" and report_dir.parts[1] == "binance_futures_testnet_protective_orders", issues, "report_export_dir", "report_export_dir must stay under reports/binance_futures_testnet_protective_orders.")



    def _handle_existing_lifecycle_journal(
        self,
        client: BinanceFuturesTestnetProtectiveOrdersClient,
        config: BinanceFuturesTestnetProtectiveOrdersConfig,
        journal: BinanceFuturesTestnetProtectiveJournal,
        pair_id: str,
        stop_client_algo_id: str,
        take_profit_client_algo_id: str,
        query_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata],
        reconciliation_results: list[ProtectiveReconciliationResult],
        persistence: ProtectiveLifecyclePersistence | None = None,
        persistence_state: ProtectivePersistenceState | None = None,
    ) -> None:
        self._validate_journal_identity(journal, pair_id, stop_client_algo_id, take_profit_client_algo_id)
        if journal.recovery_required and persistence is not None and persistence_state is not None:
            self._server_time_or_issue(client, config, [])
            self._catch_up_resolved_intents(client, journal, query_requests, reconciliation_results, persistence, persistence_state)
        unresolved = [intent for intent in journal.mutation_intents if not intent.resolved]
        if unresolved:
            self._server_time_or_issue(client, config, [])
            self._reconcile_unresolved_intents(
                client,
                config,
                journal,
                journal.stop_client_algo_id,
                journal.take_profit_client_algo_id,
                query_requests,
                reconciliation_results,
                persistence,
                persistence_state,
            )
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Existing unresolved protective mutation intent was reconciled; start recovery before a new lifecycle.", recovery=True)
        if journal.phase not in ("COMPLETE", "RECOVERY_COMPLETE"):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Existing protective journal is not complete; recovery is required before a new lifecycle.", recovery=True)

    def _load_existing_journal_strict(
        self,
        config: BinanceFuturesTestnetProtectiveOrdersConfig,
        pair_id: str,
        stop_client_algo_id: str,
        take_profit_client_algo_id: str,
    ) -> BinanceFuturesTestnetProtectiveJournal | None:
        path = self._resolve(config.journal_path)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal JSON is malformed.", recovery=True) from exc
        if not isinstance(payload, dict):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal schema is invalid.", recovery=True)
        journal = self._journal_from_payload_strict(payload, pair_id, stop_client_algo_id, take_profit_client_algo_id)
        return journal

    def _journal_from_payload_strict(
        self,
        payload: dict[str, Any],
        pair_id: str,
        stop_client_algo_id: str,
        take_profit_client_algo_id: str,
    ) -> BinanceFuturesTestnetProtectiveJournal:
        required = (
            "schema_version",
            "pair_id",
            "stop_client_algo_id",
            "take_profit_client_algo_id",
            "phase",
            "recovery_required",
            "baseline_available",
            "baseline_position_amount",
            "baseline_position_direction",
            "stop_trigger",
            "take_profit_trigger",
            "entries",
            "mutation_intents",
        )
        for field in required:
            if field not in payload:
                raise ProtectiveAbort("RECOVERY_REQUIRED", f"Protective journal missing required field: {field}.", recovery=True)
        schema_version = payload["schema_version"]
        if not isinstance(schema_version, str) or not schema_version.strip():
            raise ProtectiveAbort("UNSUPPORTED_JOURNAL_SCHEMA", "Protective journal schema_version is invalid.", recovery=True)
        if schema_version != PROTECTIVE_JOURNAL_SCHEMA_VERSION:
            raise ProtectiveAbort("UNSUPPORTED_JOURNAL_SCHEMA", "Protective journal schema_version is unsupported.", recovery=True)
        stored_pair = self._required_journal_string(payload, "pair_id")
        stored_stop = self._required_journal_string(payload, "stop_client_algo_id")
        stored_take = self._required_journal_string(payload, "take_profit_client_algo_id")
        if pair_id and stored_pair != pair_id:
            raise ProtectiveAbort("STALE_OR_MISMATCHED_JOURNAL", "Existing protective journal belongs to a different pair_id.", recovery=True)
        if stop_client_algo_id and stored_stop != stop_client_algo_id:
            raise ProtectiveAbort("STALE_OR_MISMATCHED_JOURNAL", "Existing protective journal STOP clientAlgoId is incompatible.", recovery=True)
        if take_profit_client_algo_id and stored_take != take_profit_client_algo_id:
            raise ProtectiveAbort("STALE_OR_MISMATCHED_JOURNAL", "Existing protective journal TAKE_PROFIT clientAlgoId is incompatible.", recovery=True)
        self._validate_client_algo_id_text(stored_stop)
        self._validate_client_algo_id_text(stored_take)
        if stored_stop == stored_take:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal clientAlgoIds must be distinct.", recovery=True)
        phase = self._required_journal_string(payload, "phase")
        allowed_phases = {
            "PRECHECK_STARTED",
            "POSITION_VALIDATED",
            "STOP_CREATE_STARTED",
            "STOP_CREATE_INTENT_PERSISTED",
            "STOP_CREATED",
            "STOP_QUERY_COMPLETE",
            "TAKE_PROFIT_CREATE_STARTED",
            "TAKE_PROFIT_CREATE_INTENT_PERSISTED",
            "TAKE_PROFIT_CREATED",
            "TAKE_PROFIT_QUERY_COMPLETE",
            "TAKE_PROFIT_CANCEL_STARTED",
            "TAKE_PROFIT_DELETE_INTENT_PERSISTED",
            "TAKE_PROFIT_CANCELED",
            "STOP_CANCEL_STARTED",
            "STOP_DELETE_INTENT_PERSISTED",
            "STOP_CANCELED",
            "COMPLETE",
            "RECOVERY_STARTED",
            "RECOVERY_COMPLETE",
            "RECOVERY_REQUIRED",
            "FAILED",
        }
        if phase not in allowed_phases or "_AMBIGUOUS" in phase or phase.endswith("_CREATE_CONFIRMED") or phase.endswith("_CREATE_NOT_APPLIED") or phase.endswith("_DELETE_CONFIRMED") or phase.endswith("_DELETE_NOT_APPLIED"):
            dynamic_prefixes = ("STOP_CREATE_", "TAKE_PROFIT_CREATE_", "STOP_DELETE_", "TAKE_PROFIT_DELETE_")
            dynamic_suffixes = ("AMBIGUOUS", "CREATE_CONFIRMED", "CREATE_NOT_APPLIED", "DELETE_CONFIRMED", "DELETE_NOT_APPLIED", "RECOVERY_REQUIRED", "PRESENT", "ABSENT", "IDENTITY_MISMATCH")
            if not any(phase.startswith(prefix) and phase.endswith(suffix) for prefix in dynamic_prefixes for suffix in dynamic_suffixes):
                raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal phase is invalid.", recovery=True)
        recovery_required = self._required_journal_bool(payload, "recovery_required")
        baseline_available = self._required_journal_bool(payload, "baseline_available")
        entries = payload["entries"]
        if not isinstance(entries, list):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal entries must be a list.", recovery=True)
        for entry in entries:
            self._validate_journal_entry(entry)
        raw_intents = payload["mutation_intents"]
        if not isinstance(raw_intents, list):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal mutation_intents must be a list.", recovery=True)
        baseline_amount = self._optional_journal_decimal(payload, "baseline_position_amount")
        if baseline_amount is not None and (not baseline_amount.is_finite() or baseline_amount == 0):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal baseline amount is invalid.", recovery=True)
        baseline_direction = payload["baseline_position_direction"]
        if baseline_direction is not None and baseline_direction not in ("LONG", "SHORT"):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal baseline direction is invalid.", recovery=True)
        stop_trigger = self._optional_journal_decimal(payload, "stop_trigger")
        take_profit_trigger = self._optional_journal_decimal(payload, "take_profit_trigger")
        for trigger in (stop_trigger, take_profit_trigger):
            if trigger is not None and (not trigger.is_finite() or trigger <= 0):
                raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal trigger is invalid.", recovery=True)
        if baseline_available:
            if baseline_amount is None or baseline_direction not in ("LONG", "SHORT"):
                raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal baseline metadata is incomplete.", recovery=True)
        elif baseline_amount is not None or baseline_direction is not None or stop_trigger is not None or take_profit_trigger is not None:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal baseline metadata is inconsistent.", recovery=True)
        if phase in ("COMPLETE", "RECOVERY_COMPLETE") and recovery_required:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Resolved protective journal cannot require recovery.", recovery=True)
        journal = BinanceFuturesTestnetProtectiveJournal(
            schema_version=schema_version,
            pair_id=stored_pair,
            stop_client_algo_id=stored_stop,
            take_profit_client_algo_id=stored_take,
            phase=phase,
            recovery_required=recovery_required,
            baseline_available=baseline_available,
            baseline_position_amount=baseline_amount,
            baseline_position_direction=baseline_direction,
            stop_trigger=stop_trigger,
            take_profit_trigger=take_profit_trigger,
            entries=entries,
            mutation_intents=[],
        )
        for item in raw_intents:
            if not isinstance(item, dict):
                raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent schema is invalid.", recovery=True)
            intent = self._intent_from_payload(item)
            self._validate_persisted_intent(intent, journal.pair_id, journal.stop_client_algo_id, journal.take_profit_client_algo_id)
            journal.mutation_intents.append(intent)
        return journal

    def _required_journal_string(self, payload: dict[str, Any], field: str) -> str:
        value = payload[field]
        if not isinstance(value, str) or not value.strip():
            raise ProtectiveAbort("RECOVERY_REQUIRED", f"Protective journal field {field} must be a non-empty string.", recovery=True)
        return value

    def _required_journal_bool(self, payload: dict[str, Any], field: str) -> bool:
        value = payload[field]
        if not isinstance(value, bool):
            raise ProtectiveAbort("RECOVERY_REQUIRED", f"Protective journal field {field} must be a boolean.", recovery=True)
        return value

    def _optional_journal_decimal(self, payload: dict[str, Any], field: str):
        value = payload[field]
        if value is None:
            return None
        if isinstance(value, bool):
            raise ProtectiveAbort("RECOVERY_REQUIRED", f"Protective journal field {field} is invalid.", recovery=True)
        try:
            return self._decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ProtectiveAbort("RECOVERY_REQUIRED", f"Protective journal field {field} is invalid.", recovery=True) from exc

    def _validate_journal_entry(self, entry: Any) -> None:
        if not isinstance(entry, dict):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal entry schema is invalid.", recovery=True)
        if "created_at" not in entry or "phase" not in entry or "details" not in entry:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal entry is missing required fields.", recovery=True)
        if not isinstance(entry["created_at"], str) or not entry["created_at"].strip():
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal entry created_at is invalid.", recovery=True)
        if not isinstance(entry["phase"], str) or not entry["phase"].strip():
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal entry phase is invalid.", recovery=True)
        if not isinstance(entry["details"], dict):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal entry details must be an object.", recovery=True)

    def _validate_journal_identity(self, journal: BinanceFuturesTestnetProtectiveJournal, pair_id: str, stop_client_algo_id: str, take_profit_client_algo_id: str) -> None:
        if pair_id and journal.pair_id and journal.pair_id != pair_id:
            raise ProtectiveAbort("STALE_OR_MISMATCHED_JOURNAL", "Existing protective journal belongs to a different pair_id.", recovery=True)
        if stop_client_algo_id and journal.stop_client_algo_id != stop_client_algo_id:
            raise ProtectiveAbort("STALE_OR_MISMATCHED_JOURNAL", "Existing protective journal STOP clientAlgoId is incompatible.", recovery=True)
        if take_profit_client_algo_id and journal.take_profit_client_algo_id != take_profit_client_algo_id:
            raise ProtectiveAbort("STALE_OR_MISMATCHED_JOURNAL", "Existing protective journal TAKE_PROFIT clientAlgoId is incompatible.", recovery=True)

    def _validate_persisted_intent(self, intent: ProtectiveMutationIntent, pair_id: str, stop_client_algo_id: str, take_profit_client_algo_id: str) -> None:
        if intent.intent_version != "1.0":
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Unsupported protective mutation intent version.", recovery=True)
        if intent.pair_id != pair_id:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent pair_id mismatch.", recovery=True)
        if intent.symbol != "BTCUSDT":
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent symbol mismatch.", recovery=True)
        if intent.label not in ("STOP", "TAKE_PROFIT"):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent label is invalid.", recovery=True)
        if intent.mutation_kind not in (ProtectiveMutationKind.CREATE.value, ProtectiveMutationKind.DELETE.value):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent kind is invalid.", recovery=True)
        expected_id = stop_client_algo_id if intent.label == "STOP" else take_profit_client_algo_id
        if intent.client_algo_id != expected_id:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent clientAlgoId mismatch.", recovery=True)
        self._validate_client_algo_id_text(intent.client_algo_id)
        expected_type = "STOP_MARKET" if intent.label == "STOP" else "TAKE_PROFIT_MARKET"
        if intent.expected_order_type != expected_type:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent order type mismatch.", recovery=True)
        if intent.expected_side not in ("BUY", "SELL"):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent side is invalid.", recovery=True)
        if intent.expected_trigger_price is None or not intent.expected_trigger_price.is_finite() or intent.expected_trigger_price <= 0:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent trigger is invalid.", recovery=True)
        if intent.expected_close_position is not True or intent.expected_working_type != "MARK_PRICE" or intent.expected_price_protect is not True:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent safety flags are invalid.", recovery=True)
        if intent.baseline_position_amount is None or not intent.baseline_position_amount.is_finite() or intent.baseline_position_amount == 0 or intent.baseline_position_direction not in ("LONG", "SHORT"):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent baseline metadata is invalid.", recovery=True)
        if not intent.created_at or not intent.mutation_phase:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent lifecycle metadata is invalid.", recovery=True)
        allowed_states = {"", "PENDING", ProtectiveReconciliationState.PRESENT.value, ProtectiveReconciliationState.ABSENT.value, ProtectiveReconciliationState.AMBIGUOUS.value, ProtectiveReconciliationState.IDENTITY_MISMATCH.value}
        if intent.reconciliation_state not in allowed_states:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent reconciliation state is invalid.", recovery=True)
        if intent.resolved and intent.reconciliation_state in ("", "PENDING", ProtectiveReconciliationState.AMBIGUOUS.value, ProtectiveReconciliationState.IDENTITY_MISMATCH.value):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Resolved protective mutation intent state is inconsistent.", recovery=True)
        if intent.resolved and intent.reconciliation_state in ("", ProtectiveReconciliationState.AMBIGUOUS.value):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent resolved state is inconsistent.", recovery=True)
        self._parse_intent_created_at(intent.created_at)

    def _parse_intent_created_at(self, value: str | None) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent created_at is invalid.", recovery=True)
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent created_at is invalid.", recovery=True) from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent created_at must include timezone information.", recovery=True)
        return parsed.astimezone(UTC)

    def _archive_resolved_journal(self, config: BinanceFuturesTestnetProtectiveOrdersConfig, journal: BinanceFuturesTestnetProtectiveJournal) -> None:
        self._validate_archiveable_journal(journal)
        path = self._resolve(config.journal_path)
        if not path.exists():
            return
        context = self._lock_token_part(f"{journal.pair_id}-{journal.stop_client_algo_id}-{journal.take_profit_client_algo_id}")[:80]
        timestamp = self._now().replace(':', '').replace('-', '').replace('.', '').replace('+', '')
        for _ in range(100):
            archive = path.with_name(f"{path.name}.archived.{context}.{timestamp}.{uuid.uuid4().hex}")
            if archive.exists():
                continue
            try:
                path.rename(archive)
                self._fsync_parent_directory(path.parent)
            except OSError as exc:
                raise ProtectiveAbort("JOURNAL_ARCHIVE_FAILED", "Protective journal archive failed; recovery is required before a new lifecycle.", recovery=True) from exc
            return
        raise ProtectiveAbort("RECOVERY_REQUIRED", "Could not allocate a unique protective journal archive path.", recovery=True)

    def _validate_archiveable_journal(self, journal: BinanceFuturesTestnetProtectiveJournal) -> None:
        if journal.phase not in ("COMPLETE", "RECOVERY_COMPLETE") or journal.recovery_required:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Only terminal resolved protective journals may be archived.", recovery=True)
        if not journal.pair_id or not journal.stop_client_algo_id or not journal.take_profit_client_algo_id:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal archive identity is incomplete.", recovery=True)
        if journal.stop_client_algo_id == journal.take_profit_client_algo_id:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective journal archive IDs must be distinct.", recovery=True)
        self._validate_client_algo_id_text(journal.stop_client_algo_id)
        self._validate_client_algo_id_text(journal.take_profit_client_algo_id)
        for intent in journal.mutation_intents:
            self._validate_persisted_intent(intent, journal.pair_id, journal.stop_client_algo_id, journal.take_profit_client_algo_id)
            if not intent.resolved or intent.reconciliation_state in ("", ProtectiveReconciliationState.AMBIGUOUS.value, ProtectiveReconciliationState.IDENTITY_MISMATCH.value, "PENDING"):
                raise ProtectiveAbort("RECOVERY_REQUIRED", "Unresolved protective mutation intent blocks archive.", recovery=True)

    def _create_with_reconciliation(
        self,
        client: BinanceFuturesTestnetProtectiveOrdersClient,
        config: BinanceFuturesTestnetProtectiveOrdersConfig,
        journal: BinanceFuturesTestnetProtectiveJournal,
        preview: BinanceFuturesTestnetProtectivePreview,
        label: str,
        create_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata],
        query_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata],
        reconciliation_results: list[ProtectiveReconciliationResult],
        persistence: ProtectiveLifecyclePersistence | None = None,
        persistence_state: ProtectivePersistenceState | None = None,
        permit_reference: LiveExecutionPermitReference | None = None,
    ) -> BinanceFuturesTestnetProtectiveAlgoSummary:
        intent = self._mutation_intent(journal, preview, label, ProtectiveMutationKind.CREATE.value, f"{label}_CREATE_STARTED")
        self._persist_intent(config, journal, intent, f"{label}_CREATE_INTENT_PERSISTED")
        pre_create = self._reconcile_intent(client, intent, query_requests)
        pre_create.interpreted_mutation_result = self._interpret_mutation(intent, pre_create)
        if pre_create.reconciliation_state == ProtectiveReconciliationState.PRESENT.value:
            pre_create.resolved = True
            pre_create.recovery_required = False
            reconciliation_results.append(pre_create)
            self._resolve_intent(config, journal, intent, pre_create)
            if pre_create.order is None:
                raise ProtectiveAbort("RECOVERY_REQUIRED", f"{label} pre-create lookup returned no order.", recovery=True)
            if persistence is not None and persistence_state is not None:
                persistence.mark_create_transmitted(persistence_state)
                persistence.confirm_create(persistence_state, label, pre_create.order)
            self._check_unexpected_trigger(pre_create.order)
            return pre_create.order
        if pre_create.reconciliation_state != ProtectiveReconciliationState.ABSENT.value:
            pre_create.recovery_required = True
            reconciliation_results.append(pre_create)
            self._resolve_intent(config, journal, intent, pre_create)
            raise ProtectiveAbort("RECOVERY_REQUIRED", f"{label} pre-create lookup result: {pre_create.reconciliation_state}.", recovery=True)
        reconciliation_results.append(pre_create)
        try:
            client.synchronize_server_time(force=True)
            unsigned_request = client.build_create_unsigned_business_request(preview, label)
            fingerprint = build_protective_create_from_final_request(unsigned_request)
            try:
                self._require_permit_for_mutation(
                    operation=LiveExecutionOperation.PROTECTIVE_CREATE,
                    fingerprint=fingerprint,
                    permit_reference=permit_reference,
                    config=config,
                    current_pair_id=journal.pair_id,
                )
            except ProtectiveAbort as exc:
                result = self._reconciliation_result(
                    intent,
                    ProtectiveReconciliationState.ABSENT.value,
                    "CREATE_NOT_APPLIED",
                    True,
                    exc.permit_consumed,
                    "Create was not transmitted because permit gate denied it.",
                    None,
                )
                reconciliation_results.append(result)
                self._resolve_intent(config, journal, intent, result)
                if persistence is not None and persistence_state is not None:
                    if exc.permit_consumed:
                        persistence.mark_recovery_required(persistence_state, "CREATE", exc.decision)
                    else:
                        persistence.mark_failed_safe(persistence_state, "CREATE", "CREATE_NOT_APPLIED")
                raise ProtectiveAbort(
                    exc.decision,
                    exc.reason,
                    recovery=exc.permit_consumed,
                    permit_consumed=exc.permit_consumed,
                ) from None
            order, meta = client.create_stop_order(preview, unsigned_business_request=unsigned_request) if label == "STOP" else client.create_take_profit_order(preview, unsigned_business_request=unsigned_request)
            create_requests.append(meta)
            if persistence is not None and persistence_state is not None:
                persistence.mark_create_transmitted(persistence_state)
            self._validate_algo_identity(order, preview, label)
            self._check_unexpected_trigger(order)
            result = self._reconciliation_result(intent, ProtectiveReconciliationState.PRESENT.value, "CREATE_CONFIRMED", True, False, "Create response was deterministic.", order)
            reconciliation_results.append(result)
            self._resolve_intent(config, journal, intent, result)
            if persistence is not None and persistence_state is not None:
                persistence.confirm_create(persistence_state, label, order)
            return order
        except (TimeoutError, OSError, ConnectionResetError) as exc:
            if persistence is not None and persistence_state is not None:
                persistence.mark_create_transmitted(persistence_state)
            self._mark_intent_ambiguous(config, journal, intent, self._sanitize(str(exc)))
            result = self._reconcile_intent(client, intent, query_requests)
            interpreted = self._interpret_mutation(intent, result)
            result.interpreted_mutation_result = interpreted
            result.resolved = result.reconciliation_state in (ProtectiveReconciliationState.PRESENT.value, ProtectiveReconciliationState.ABSENT.value)
            result.recovery_required = interpreted != "CREATE_CONFIRMED"
            reconciliation_results.append(result)
            self._resolve_intent(config, journal, intent, result)
            if interpreted == "CREATE_CONFIRMED" and result.order is not None:
                if persistence is not None and persistence_state is not None:
                    persistence.confirm_create(persistence_state, label, result.order)
                self._check_unexpected_trigger(result.order)
                return result.order
            if interpreted == "CREATE_NOT_APPLIED":
                if persistence is not None and persistence_state is not None:
                    persistence.mark_failed_safe(persistence_state, "CREATE", "CREATE_NOT_APPLIED")
                    raise ProtectiveAbort("CREATE_NOT_APPLIED", f"{label} create was confirmed absent.") from exc
                raise ProtectiveAbort("RECOVERY_REQUIRED", f"{label} create was confirmed absent; operator review is required.", recovery=True) from exc
            if persistence is not None and persistence_state is not None:
                persistence.mark_recovery_required(persistence_state, "CREATE", "CREATE_RECONCILIATION_AMBIGUOUS")
            raise ProtectiveAbort("RECOVERY_REQUIRED", f"{label} create reconciliation result: {interpreted}.", recovery=True) from exc
        except BinanceFuturesTestnetProtectiveAPIError as exc:
            if exc.http_status is not None and exc.http_status >= 500:
                if persistence is not None and persistence_state is not None:
                    persistence.mark_create_transmitted(persistence_state)
                self._mark_intent_ambiguous(config, journal, intent, self._sanitize_api_error(exc))
                result = self._reconcile_intent(client, intent, query_requests)
                result.interpreted_mutation_result = self._interpret_mutation(intent, result)
                result.recovery_required = result.interpreted_mutation_result != "CREATE_CONFIRMED"
                reconciliation_results.append(result)
                self._resolve_intent(config, journal, intent, result)
                if result.interpreted_mutation_result == "CREATE_CONFIRMED" and result.order is not None:
                    if persistence is not None and persistence_state is not None:
                        persistence.confirm_create(persistence_state, label, result.order)
                    return result.order
                if result.interpreted_mutation_result == "CREATE_NOT_APPLIED":
                    if persistence is not None and persistence_state is not None:
                        persistence.mark_failed_safe(persistence_state, "CREATE", "CREATE_NOT_APPLIED")
                        raise ProtectiveAbort("CREATE_NOT_APPLIED", f"{label} create was confirmed absent.") from exc
                    raise ProtectiveAbort("RECOVERY_REQUIRED", f"{label} create was confirmed absent; operator review is required.", recovery=True) from exc
                if persistence is not None and persistence_state is not None:
                    persistence.mark_recovery_required(persistence_state, "CREATE", "CREATE_RECONCILIATION_AMBIGUOUS")
                raise ProtectiveAbort("RECOVERY_REQUIRED", f"{label} create reconciliation result: {result.interpreted_mutation_result}.", recovery=True) from exc
            if persistence is not None and persistence_state is not None:
                persistence.mark_failed_safe(persistence_state, "CREATE", "CREATE_REJECTED")
            raise

    def _delete_with_reconciliation(
        self,
        client: BinanceFuturesTestnetProtectiveOrdersClient,
        config: BinanceFuturesTestnetProtectiveOrdersConfig,
        journal: BinanceFuturesTestnetProtectiveJournal,
        preview: BinanceFuturesTestnetProtectivePreview,
        label: str,
        cancel_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata],
        query_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata],
        reconciliation_results: list[ProtectiveReconciliationResult],
        persistence: ProtectiveLifecyclePersistence | None = None,
        persistence_state: ProtectivePersistenceState | None = None,
        permit_reference: LiveExecutionPermitReference | None = None,
    ) -> bool:
        client_algo_id = preview.stop_client_algo_id if label == "STOP" else preview.take_profit_client_algo_id
        intent = self._mutation_intent(journal, preview, label, ProtectiveMutationKind.DELETE.value, f"{label}_DELETE_STARTED")
        if persistence is not None and persistence_state is not None:
            mark_price = preview.mark_price if preview.mark_price > 0 else None
            persistence.prepare_cancel(persistence_state, label, preview.position_amount, mark_price)
        self._write_journal(config, journal, f"{label}_CANCEL_STARTED", {"client_algo_id": client_algo_id})
        self._persist_intent(config, journal, intent, f"{label}_DELETE_INTENT_PERSISTED")
        try:
            client.synchronize_server_time(force=True)
            unsigned_request = client.build_cancel_unsigned_business_request(preview, label)
            fingerprint = build_protective_cancel_from_final_request(unsigned_request)
            try:
                self._require_permit_for_mutation(
                    operation=LiveExecutionOperation.PROTECTIVE_CANCEL,
                    fingerprint=fingerprint,
                    permit_reference=permit_reference,
                    config=config,
                    current_pair_id=journal.pair_id,
                )
            except ProtectiveAbort as exc:
                # A denied cancel is not ambiguous merely because a preceding
                # create exists. The outer lifecycle retains recovery because of
                # that actual exchange state; this boundary itself stays
                # explicitly not-transmitted unless the permit was consumed.
                raise ProtectiveAbort(
                    exc.decision,
                    exc.reason,
                    recovery=exc.permit_consumed,
                    permit_consumed=exc.permit_consumed,
                ) from None
            order, meta = client.cancel_algo_order_exact(client_algo_id, unsigned_business_request=unsigned_request)
            cancel_requests.append(meta)
            if persistence is not None and persistence_state is not None:
                persistence.mark_cancel_transmitted(persistence_state, label)
            self._validate_delete_ack(order, client_algo_id)
            ack = self._reconciliation_result(intent, "PENDING", "DELETE_ACKNOWLEDGED", False, False, "Delete response was deterministic; exact lookup still required.", None)
            reconciliation_results.append(ack)
            lookup = self._reconcile_intent(client, intent, query_requests)
            lookup.interpreted_mutation_result = self._interpret_mutation(intent, lookup)
            lookup.resolved = self._is_delete_confirmed(lookup.interpreted_mutation_result)
            lookup.recovery_required = not lookup.resolved
            reconciliation_results.append(lookup)
            self._resolve_intent(config, journal, intent, lookup)
            if not lookup.resolved:
                if persistence is not None and persistence_state is not None:
                    persistence.mark_recovery_required(persistence_state, "DELETE", "DELETE_NOT_CONFIRMED")
                raise ProtectiveAbort("RECOVERY_REQUIRED", f"{label} delete reconciliation result: {lookup.interpreted_mutation_result}.", recovery=True)
            if persistence is not None and persistence_state is not None:
                status = "ABSENT" if lookup.order is None else str(lookup.order.algo_status or "TERMINAL")
                persistence.confirm_delete(persistence_state, label, status, complete=label == "STOP")
            return lookup.reconciliation_state == ProtectiveReconciliationState.ABSENT.value
        except (TimeoutError, OSError, ConnectionResetError) as exc:
            if persistence is not None and persistence_state is not None:
                persistence.mark_cancel_transmitted(persistence_state, label)
            self._mark_intent_ambiguous(config, journal, intent, self._sanitize(str(exc)))
            result = self._reconcile_intent(client, intent, query_requests)
            result.interpreted_mutation_result = self._interpret_mutation(intent, result)
            result.resolved = self._is_delete_confirmed(result.interpreted_mutation_result)
            result.recovery_required = not result.resolved
            reconciliation_results.append(result)
            self._resolve_intent(config, journal, intent, result)
            if not result.resolved:
                if persistence is not None and persistence_state is not None:
                    persistence.mark_recovery_required(persistence_state, "DELETE", "DELETE_RECONCILIATION_AMBIGUOUS")
                raise ProtectiveAbort("RECOVERY_REQUIRED", f"{label} delete reconciliation result: {result.interpreted_mutation_result}.", recovery=True) from exc
            if persistence is not None and persistence_state is not None:
                status = "ABSENT" if result.order is None else str(result.order.algo_status or "TERMINAL")
                persistence.confirm_delete(persistence_state, label, status, complete=label == "STOP")
            return result.reconciliation_state == ProtectiveReconciliationState.ABSENT.value
        except BinanceFuturesTestnetProtectiveAPIError as exc:
            if exc.http_status is not None and exc.http_status >= 500:
                if persistence is not None and persistence_state is not None:
                    persistence.mark_cancel_transmitted(persistence_state, label)
                self._mark_intent_ambiguous(config, journal, intent, self._sanitize_api_error(exc))
                result = self._reconcile_intent(client, intent, query_requests)
                result.interpreted_mutation_result = self._interpret_mutation(intent, result)
                result.resolved = self._is_delete_confirmed(result.interpreted_mutation_result)
                result.recovery_required = not result.resolved
                reconciliation_results.append(result)
                self._resolve_intent(config, journal, intent, result)
                if not result.resolved:
                    if persistence is not None and persistence_state is not None:
                        persistence.mark_recovery_required(persistence_state, "DELETE", "DELETE_RECONCILIATION_AMBIGUOUS")
                    raise ProtectiveAbort("RECOVERY_REQUIRED", f"{label} delete reconciliation result: {result.interpreted_mutation_result}.", recovery=True) from exc
                if persistence is not None and persistence_state is not None:
                    status = "ABSENT" if result.order is None else str(result.order.algo_status or "TERMINAL")
                    persistence.confirm_delete(persistence_state, label, status, complete=label == "STOP")
                return result.reconciliation_state == ProtectiveReconciliationState.ABSENT.value
            raise


    def _reconcile_unresolved_intents(
        self,
        client: BinanceFuturesTestnetProtectiveOrdersClient,
        config: BinanceFuturesTestnetProtectiveOrdersConfig,
        journal: BinanceFuturesTestnetProtectiveJournal,
        stop_client_algo_id: str,
        take_profit_client_algo_id: str,
        query_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata],
        reconciliation_results: list[ProtectiveReconciliationResult],
        persistence: ProtectiveLifecyclePersistence | None = None,
        persistence_state: ProtectivePersistenceState | None = None,
    ) -> None:
        for intent in list(journal.mutation_intents):
            if intent.resolved:
                continue
            if intent.client_algo_id not in (stop_client_algo_id, take_profit_client_algo_id):
                raise ProtectiveAbort("RECOVERY_REQUIRED", "Persisted mutation intent belongs to a different protective pair.", recovery=True)
            expected_label = "STOP" if intent.client_algo_id == stop_client_algo_id else "TAKE_PROFIT"
            if intent.label != expected_label or intent.symbol != "BTCUSDT":
                raise ProtectiveAbort("RECOVERY_REQUIRED", "Persisted mutation intent identity is stale or malformed.", recovery=True)
            self._validate_persisted_intent(intent, journal.pair_id, stop_client_algo_id, take_profit_client_algo_id)
            result = self._reconcile_intent(client, intent, query_requests)
            result.interpreted_mutation_result = self._interpret_mutation(intent, result)
            result.recovery_required = result.interpreted_mutation_result in ("RECOVERY_REQUIRED", "DELETE_NOT_APPLIED")
            result.resolved = not result.recovery_required
            reconciliation_results.append(result)
            self._resolve_intent(config, journal, intent, result)
            if persistence is not None and persistence_state is not None:
                persistence.apply_reconciliation(persistence_state, intent, result)
            if result.recovery_required:
                raise ProtectiveAbort("RECOVERY_REQUIRED", f"Unresolved persisted {intent.label} {intent.mutation_kind} intent: {result.interpreted_mutation_result}.", recovery=True)

    def _catch_up_resolved_intents(
        self,
        client: BinanceFuturesTestnetProtectiveOrdersClient,
        journal: BinanceFuturesTestnetProtectiveJournal,
        query_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata],
        reconciliation_results: list[ProtectiveReconciliationResult],
        persistence: ProtectiveLifecyclePersistence,
        persistence_state: ProtectivePersistenceState | None,
    ) -> list[tuple[ProtectiveMutationIntent, ProtectiveReconciliationResult]]:
        if persistence_state is None:
            raise ProtectivePersistenceError("PERSISTENCE_STATE_MISSING")
        caught_up: list[tuple[ProtectiveMutationIntent, ProtectiveReconciliationResult]] = []
        for intent in journal.mutation_intents:
            if not intent.resolved or not persistence.needs_catch_up(persistence_state, intent):
                continue
            result = self._reconcile_intent(client, intent, query_requests)
            interpreted = self._interpret_mutation(intent, result)
            result.interpreted_mutation_result = interpreted
            result.resolved = interpreted == "CREATE_CONFIRMED" if intent.mutation_kind == ProtectiveMutationKind.CREATE.value else self._is_delete_confirmed(interpreted)
            result.recovery_required = not result.resolved
            reconciliation_results.append(result)
            expected_state = intent.reconciliation_state
            if intent.mutation_kind == ProtectiveMutationKind.CREATE.value:
                exact_match = expected_state == ProtectiveReconciliationState.PRESENT.value and interpreted == "CREATE_CONFIRMED" and result.order is not None
            else:
                exact_match = expected_state in {ProtectiveReconciliationState.ABSENT.value, ProtectiveReconciliationState.PRESENT.value} and self._is_delete_confirmed(interpreted)
            if not exact_match:
                raise ProtectivePersistenceError("PERSISTENCE_CATCH_UP_MISMATCH", after_transport=True)
            persistence.apply_reconciliation(persistence_state, intent, result)
            caught_up.append((intent, result))
        return caught_up

    def _attach_recovery_baseline_from_orders(self, journal: BinanceFuturesTestnetProtectiveJournal, position: BinanceFuturesTestnetProtectivePosition, stop, take) -> None:
        if journal.baseline_available:
            return
        if position.position_amt == 0 or position.direction not in ("LONG", "SHORT"):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective recovery requires baseline metadata before mutation.", recovery=True)
        journal.baseline_available = True
        journal.baseline_position_amount = position.position_amt
        journal.baseline_position_direction = position.direction
        if stop is not None:
            journal.stop_trigger = stop.trigger_price
        if take is not None:
            journal.take_profit_trigger = take.trigger_price

    def _recovery_preview_from_journal(self, journal: BinanceFuturesTestnetProtectiveJournal, stop_client_algo_id: str, take_profit_client_algo_id: str) -> BinanceFuturesTestnetProtectivePreview:
        if not journal.baseline_available:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective recovery journal is missing baseline metadata.", recovery=True)
        if journal.baseline_position_amount is None or journal.baseline_position_amount == 0:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective recovery journal baseline amount is invalid.", recovery=True)
        if journal.baseline_position_direction not in ("LONG", "SHORT"):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective recovery journal baseline direction is invalid.", recovery=True)
        if journal.stop_trigger is None and journal.take_profit_trigger is None:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective recovery journal trigger metadata is missing.", recovery=True)
        return BinanceFuturesTestnetProtectivePreview(
            pair_id=journal.pair_id,
            symbol="BTCUSDT",
            position_direction=journal.baseline_position_direction,
            position_amount=journal.baseline_position_amount,
            protective_side="SELL" if journal.baseline_position_direction == "LONG" else "BUY",
            stop_client_algo_id=stop_client_algo_id,
            take_profit_client_algo_id=take_profit_client_algo_id,
            stop_trigger=journal.stop_trigger,
            take_profit_trigger=journal.take_profit_trigger,
            transmission_ready=True,
        )

    def _mutation_intent(self, journal: BinanceFuturesTestnetProtectiveJournal, preview: BinanceFuturesTestnetProtectivePreview, label: str, kind: str, phase: str) -> ProtectiveMutationIntent:
        trigger = preview.stop_trigger if label == "STOP" else preview.take_profit_trigger
        client_algo_id = preview.stop_client_algo_id if label == "STOP" else preview.take_profit_client_algo_id
        order_type = "STOP_MARKET" if label == "STOP" else "TAKE_PROFIT_MARKET"
        return ProtectiveMutationIntent(
            pair_id=preview.pair_id or journal.pair_id,
            symbol=preview.symbol,
            label=label,
            mutation_kind=kind,
            client_algo_id=client_algo_id,
            expected_order_type=order_type,
            expected_side=preview.protective_side,
            expected_trigger_price=trigger,
            expected_close_position=True,
            expected_working_type="MARK_PRICE",
            expected_price_protect=True,
            baseline_position_amount=preview.position_amount,
            baseline_position_direction=preview.position_direction,
            created_at=self._now(),
            mutation_phase=phase,
        )

    def _persist_intent(self, config: BinanceFuturesTestnetProtectiveOrdersConfig, journal: BinanceFuturesTestnetProtectiveJournal, intent: ProtectiveMutationIntent, phase: str) -> None:
        journal.mutation_intents = [item for item in journal.mutation_intents if not (item.client_algo_id == intent.client_algo_id and item.mutation_kind == intent.mutation_kind and item.label == intent.label)]
        journal.mutation_intents.append(intent)
        self._write_journal(config, journal, phase, {"mutation_intent": intent.to_dict()})

    def _mark_intent_ambiguous(self, config: BinanceFuturesTestnetProtectiveOrdersConfig, journal: BinanceFuturesTestnetProtectiveJournal, intent: ProtectiveMutationIntent, reason: str) -> None:
        intent.reconciliation_state = ProtectiveReconciliationState.AMBIGUOUS.value
        intent.reconciliation_reason = reason
        intent.resolved = False
        self._persist_intent(config, journal, intent, f"{intent.label}_{intent.mutation_kind}_AMBIGUOUS")

    def _resolve_intent(self, config: BinanceFuturesTestnetProtectiveOrdersConfig, journal: BinanceFuturesTestnetProtectiveJournal, intent: ProtectiveMutationIntent, result: ProtectiveReconciliationResult) -> None:
        intent.reconciliation_state = result.reconciliation_state
        intent.reconciliation_reason = result.reason
        intent.resolved = result.resolved
        self._persist_intent(config, journal, intent, f"{intent.label}_{intent.mutation_kind}_{result.interpreted_mutation_result or result.reconciliation_state}")

    def _reconcile_intent(self, client: BinanceFuturesTestnetProtectiveOrdersClient, intent: ProtectiveMutationIntent, query_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata]) -> ProtectiveReconciliationResult:
        try:
            order, meta = client.query_algo_order(intent.client_algo_id)
            query_requests.append(meta)
            try:
                self._validate_algo_identity(order, None, intent.label, stop_client_algo_id=intent.client_algo_id if intent.label == "STOP" else None, take_profit_client_algo_id=intent.client_algo_id if intent.label == "TAKE_PROFIT" else None, expected_side=intent.expected_side, expected_trigger=intent.expected_trigger_price)
            except ProtectiveAbort as exc:
                return self._reconciliation_result(intent, ProtectiveReconciliationState.IDENTITY_MISMATCH.value, "RECOVERY_REQUIRED", False, True, exc.reason, order)
            return self._reconciliation_result(intent, ProtectiveReconciliationState.PRESENT.value, "", True, False, "Exact clientAlgoId lookup found a matching order.", order)
        except BinanceFuturesTestnetProtectiveAPIError as exc:
            if exc.binance_code == -2013 and exc.deterministic_rejection:
                return self._reconciliation_result(intent, ProtectiveReconciliationState.ABSENT.value, "", True, False, "Exact clientAlgoId lookup returned deterministic not-found.", None)
            return self._reconciliation_result(intent, ProtectiveReconciliationState.AMBIGUOUS.value, "RECOVERY_REQUIRED", False, True, self._sanitize_api_error(exc), None)
        except (TimeoutError, OSError, ConnectionResetError) as exc:
            return self._reconciliation_result(intent, ProtectiveReconciliationState.AMBIGUOUS.value, "RECOVERY_REQUIRED", False, True, self._sanitize(str(exc)), None)

    @staticmethod
    def _is_delete_confirmed(interpreted_mutation_result: str) -> bool:
        return interpreted_mutation_result in ("DELETE_CONFIRMED", "DELETE_CONFIRMED_TERMINAL")

    def _interpret_mutation(self, intent: ProtectiveMutationIntent, result: ProtectiveReconciliationResult) -> str:
        if result.reconciliation_state == ProtectiveReconciliationState.IDENTITY_MISMATCH.value:
            return "RECOVERY_REQUIRED"
        if result.reconciliation_state == ProtectiveReconciliationState.AMBIGUOUS.value:
            return "RECOVERY_REQUIRED"
        if intent.mutation_kind == ProtectiveMutationKind.CREATE.value:
            return "CREATE_CONFIRMED" if result.reconciliation_state == ProtectiveReconciliationState.PRESENT.value else "CREATE_NOT_APPLIED"
        if intent.mutation_kind == ProtectiveMutationKind.DELETE.value:
            if result.reconciliation_state == ProtectiveReconciliationState.ABSENT.value:
                return "DELETE_CONFIRMED"
            if result.reconciliation_state == ProtectiveReconciliationState.PRESENT.value and result.order is not None:
                self._check_unexpected_trigger(result.order)
                if str(result.order.algo_status or "").upper() in self.TERMINAL_SAFE_STATUSES:
                    return "DELETE_CONFIRMED_TERMINAL"
            return "DELETE_NOT_APPLIED"
        return "RECOVERY_REQUIRED"

    def _reconciliation_result(self, intent: ProtectiveMutationIntent, state: str, interpreted: str, resolved: bool, recovery_required: bool, reason: str, order: BinanceFuturesTestnetProtectiveAlgoSummary | None) -> ProtectiveReconciliationResult:
        return ProtectiveReconciliationResult(label=intent.label, mutation_kind=intent.mutation_kind, client_algo_id=intent.client_algo_id, reconciliation_state=state, interpreted_mutation_result=interpreted, resolved=resolved, recovery_required=recovery_required, reason=reason, order=order)

    def _intent_from_payload(self, payload: dict[str, Any]) -> ProtectiveMutationIntent:
        required = (
            "intent_version",
            "pair_id",
            "symbol",
            "label",
            "mutation_kind",
            "client_algo_id",
            "expected_order_type",
            "expected_side",
            "expected_trigger_price",
            "expected_close_position",
            "expected_working_type",
            "expected_price_protect",
            "baseline_position_amount",
            "baseline_position_direction",
            "created_at",
            "mutation_phase",
            "resolved",
            "reconciliation_state",
            "reconciliation_reason",
        )
        for field in required:
            if field not in payload or payload[field] is None:
                raise ProtectiveAbort("RECOVERY_REQUIRED", f"Protective mutation intent missing required field: {field}.", recovery=True)
        string_fields = ("intent_version", "pair_id", "symbol", "label", "mutation_kind", "client_algo_id", "expected_order_type", "expected_side", "expected_working_type", "baseline_position_direction", "created_at", "mutation_phase", "reconciliation_state", "reconciliation_reason")
        for field in string_fields:
            if not isinstance(payload[field], str):
                raise ProtectiveAbort("RECOVERY_REQUIRED", f"Protective mutation intent field {field} must be a string.", recovery=True)
        for field in ("expected_close_position", "expected_price_protect", "resolved"):
            if not isinstance(payload[field], bool):
                raise ProtectiveAbort("RECOVERY_REQUIRED", f"Protective mutation intent field {field} must be a boolean.", recovery=True)
        try:
            trigger = self._decimal(payload["expected_trigger_price"])
            baseline_amount = self._decimal(payload["baseline_position_amount"])
        except (InvalidOperation, ValueError) as exc:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent decimal field is invalid.", recovery=True) from exc
        if not trigger.is_finite() or trigger <= 0:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent trigger is invalid.", recovery=True)
        if not baseline_amount.is_finite() or baseline_amount == 0:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective mutation intent baseline amount is invalid.", recovery=True)
        self._parse_intent_created_at(payload["created_at"])
        return ProtectiveMutationIntent(
            intent_version=payload["intent_version"],
            pair_id=payload["pair_id"],
            symbol=payload["symbol"],
            label=payload["label"],
            mutation_kind=payload["mutation_kind"],
            client_algo_id=payload["client_algo_id"],
            expected_order_type=payload["expected_order_type"],
            expected_side=payload["expected_side"],
            expected_trigger_price=trigger,
            expected_close_position=payload["expected_close_position"],
            expected_working_type=payload["expected_working_type"],
            expected_price_protect=payload["expected_price_protect"],
            baseline_position_amount=baseline_amount,
            baseline_position_direction=payload["baseline_position_direction"],
            created_at=payload["created_at"],
            mutation_phase=payload["mutation_phase"],
            resolved=payload["resolved"],
            reconciliation_state=payload["reconciliation_state"],
            reconciliation_reason=payload["reconciliation_reason"],
        )


    def _validate_client_algo_id_text(self, client_algo_id: str) -> None:
        if not client_algo_id or not client_algo_id.startswith("smcbot-protect-") or len(client_algo_id) > 36:
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective clientAlgoId is invalid.", recovery=True)
        if any(char.isspace() for char in client_algo_id) or any(not (char.isalnum() or char in ".:/_-") for char in client_algo_id):
            raise ProtectiveAbort("RECOVERY_REQUIRED", "Protective clientAlgoId contains unsafe characters.", recovery=True)

    def _server_time_or_issue(self, client: BinanceFuturesTestnetProtectiveOrdersClient, config: BinanceFuturesTestnetProtectiveOrdersConfig, issues: list[BinanceFuturesTestnetProtectiveIssue]) -> None:
        try:
            client.synchronize_server_time(force=True)
        except ValueError:
            raise ProtectiveAbort("PUBLIC_PREFLIGHT_FAILED", "Clock skew exceeds protective maximum.")

    def _check_unexpected_trigger(self, order: BinanceFuturesTestnetProtectiveAlgoSummary | None) -> None:
        if order is None:
            return
        actual_price = order.actual_price or 0
        if order.actual_order_id or order.executed_quantity > 0 or actual_price > 0 or str(order.algo_status or "").upper() in self.TRIGGERED_STATUSES:
            raise ProtectiveAbort("UNEXPECTED_TRIGGER_DETECTED", "Protective order appears triggered or executed.", recovery=True, critical=True)

    def _validate_algo_identity(
        self,
        order: BinanceFuturesTestnetProtectiveAlgoSummary,
        preview: BinanceFuturesTestnetProtectivePreview | None,
        label: str,
        stop_client_algo_id: str | None = None,
        take_profit_client_algo_id: str | None = None,
        expected_side: str | None = None,
        expected_trigger: Any | None = None,
    ) -> None:
        expected_id = preview.stop_client_algo_id if preview and label == "STOP" else preview.take_profit_client_algo_id if preview else stop_client_algo_id if label == "STOP" else take_profit_client_algo_id
        expected_type = "STOP_MARKET" if label == "STOP" else "TAKE_PROFIT_MARKET"
        expected_side = preview.protective_side if preview else expected_side
        expected_trigger = preview.stop_trigger if preview and label == "STOP" else preview.take_profit_trigger if preview else expected_trigger
        if order.client_algo_id != expected_id:
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", f"{label} clientAlgoId mismatch.", recovery=True)
        if order.algo_id in (None, ""):
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", f"{label} algoId missing.", recovery=True)
        if order.symbol != "BTCUSDT":
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", f"{label} symbol mismatch.", recovery=True)
        if order.algo_type != "CONDITIONAL":
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", f"{label} algoType mismatch.", recovery=True)
        if order.order_type != expected_type:
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", f"{label} orderType mismatch.", recovery=True)
        if expected_side is not None and order.side != expected_side:
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", f"{label} side mismatch.", recovery=True)
        if expected_side is None and order.side not in ("BUY", "SELL"):
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", f"{label} side missing or invalid.", recovery=True)
        if order.position_side != "BOTH":
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", f"{label} positionSide mismatch.", recovery=True)
        if order.algo_status in (None, ""):
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", f"{label} algoStatus missing.", recovery=True)
        if order.trigger_price is None or order.trigger_price <= 0:
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", f"{label} triggerPrice missing.", recovery=True)
        if expected_trigger is not None and order.trigger_price != expected_trigger:
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", f"{label} triggerPrice mismatch.", recovery=True)
        if order.close_position is not True:
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", f"{label} closePosition mismatch.", recovery=True)
        if order.working_type != "MARK_PRICE":
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", f"{label} workingType mismatch.", recovery=True)
        if order.price_protect is not True:
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", f"{label} priceProtect mismatch.", recovery=True)

    def _validate_delete_ack(self, order: BinanceFuturesTestnetProtectiveAlgoSummary, expected_client_algo_id: str) -> None:
        if order.client_algo_id != expected_client_algo_id:
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", "DELETE clientAlgoId mismatch.", recovery=True)
        if order.algo_id in (None, ""):
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", "DELETE algoId missing.", recovery=True)
        if order.response_code is not None and order.response_code not in (0, 200):
            raise ProtectiveAbort("ORDER_STATE_UNKNOWN", "DELETE response was not deterministic success.", recovery=True)

    def _query_or_absent(self, client: BinanceFuturesTestnetProtectiveOrdersClient, client_algo_id: str, journal: BinanceFuturesTestnetProtectiveJournal, label: str, after_delete: bool = False):
        try:
            return client.query_algo_order(client_algo_id)
        except BinanceFuturesTestnetProtectiveAPIError as exc:
            if exc.binance_code == -2013 and exc.deterministic_rejection:
                if self._journal_confirms_created(journal, label) and not after_delete and not self._journal_confirms_deleted(journal, label):
                    raise ProtectiveAbort("RECOVERY_REQUIRED", f"{label} was journal-confirmed but exact query returned absent.", recovery=True) from exc
                return None, None
            raise

    def _journal_confirms_created(self, journal: BinanceFuturesTestnetProtectiveJournal, label: str) -> bool:
        phases = {"STOP": {"STOP_CREATED", "STOP_QUERY_COMPLETE"}, "TAKE_PROFIT": {"TAKE_PROFIT_CREATED", "TAKE_PROFIT_QUERY_COMPLETE"}}[label]
        return any(str(entry.get("phase")) in phases for entry in journal.entries)

    @staticmethod
    def _journal_confirms_deleted(journal: BinanceFuturesTestnetProtectiveJournal, label: str) -> bool:
        return any(
            intent.label == label
            and intent.mutation_kind == ProtectiveMutationKind.DELETE.value
            and intent.resolved
            and intent.reconciliation_state in {ProtectiveReconciliationState.ABSENT.value, ProtectiveReconciliationState.PRESENT.value}
            for intent in journal.mutation_intents
        )

    def _validate_recovery_pair(self, stop, take, journal: BinanceFuturesTestnetProtectiveJournal, stop_client_algo_id: str, take_profit_client_algo_id: str) -> None:
        if stop is None and take is None:
            return
        if stop is not None:
            self._validate_recovery_identity(stop, journal, "STOP", stop_client_algo_id)
        if take is not None:
            self._validate_recovery_identity(take, journal, "TAKE_PROFIT", take_profit_client_algo_id)
        present = [order for order in (stop, take) if order is not None]
        if len(present) == 2 and present[0].side != present[1].side:
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", "Protective pair sides do not match.", recovery=True)

    def _validate_recovery_identity(self, order: BinanceFuturesTestnetProtectiveAlgoSummary, journal: BinanceFuturesTestnetProtectiveJournal, label: str, client_algo_id: str) -> None:
        expected_side = None
        expected_trigger = None
        if journal.baseline_available:
            expected_side = "SELL" if journal.baseline_position_direction == "LONG" else "BUY" if journal.baseline_position_direction == "SHORT" else None
            expected_trigger = journal.stop_trigger if label == "STOP" else journal.take_profit_trigger
        self._validate_algo_identity(order, None, label, stop_client_algo_id=client_algo_id if label == "STOP" else None, take_profit_client_algo_id=client_algo_id if label == "TAKE_PROFIT" else None, expected_side=expected_side, expected_trigger=expected_trigger)

    def _require_matching_query_pair(self, stop: BinanceFuturesTestnetProtectiveAlgoSummary, take: BinanceFuturesTestnetProtectiveAlgoSummary) -> None:
        if stop.side not in ("BUY", "SELL") or take.side not in ("BUY", "SELL") or stop.side != take.side:
            raise ProtectiveAbort("ORDER_IDENTITY_MISMATCH", "Protective query pair sides do not match.", recovery=False)

    def _require_new(self, order: BinanceFuturesTestnetProtectiveAlgoSummary, label: str) -> None:
        self._check_unexpected_trigger(order)
        if order.algo_status != "NEW":
            raise ProtectiveAbort("ORDER_STATE_UNKNOWN", f"{label} protective order was not NEW after exact query.", recovery=True)

    def _require_terminal_safe(self, order: BinanceFuturesTestnetProtectiveAlgoSummary, label: str) -> None:
        self._check_unexpected_trigger(order)
        if order.algo_status not in self.TERMINAL_SAFE_STATUSES:
            raise ProtectiveAbort("ORDER_STATE_UNKNOWN", f"{label} protective order is not in a safe terminal state.", recovery=True)

    def _require_same_position(self, before: BinanceFuturesTestnetProtectivePosition, after: BinanceFuturesTestnetProtectivePosition) -> None:
        if before.position_amt != after.position_amt or before.direction != after.direction:
            raise ProtectiveAbort("UNEXPECTED_POSITION_CHANGE", "BTCUSDT position amount or direction changed during protective lifecycle.", recovery=True, critical=True)

    def _attach_journal_baseline(self, journal: BinanceFuturesTestnetProtectiveJournal, position: BinanceFuturesTestnetProtectivePosition, preview: BinanceFuturesTestnetProtectivePreview) -> None:
        journal.baseline_available = True
        journal.baseline_position_amount = position.position_amt
        journal.baseline_position_direction = position.direction
        journal.stop_trigger = preview.stop_trigger
        journal.take_profit_trigger = preview.take_profit_trigger

    def _load_or_new_journal(self, config: BinanceFuturesTestnetProtectiveOrdersConfig, stop_client_algo_id: str, take_profit_client_algo_id: str) -> BinanceFuturesTestnetProtectiveJournal:
        existing = self._load_existing_journal_strict(config, "", stop_client_algo_id, take_profit_client_algo_id)
        if existing is not None:
            return existing
        return BinanceFuturesTestnetProtectiveJournal(pair_id="manual-recovery", stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, recovery_required=True, entries=[{"created_at": self._now(), "phase": "RECOVERY_STARTED", "details": {"baseline_available": False}}])

    def _current_position_for_recovery(self, client: BinanceFuturesTestnetProtectiveOrdersClient) -> BinanceFuturesTestnetProtectivePosition:
        rows = client.fetch_position_risk()
        try:
            return client.require_protectable_position(rows)
        except ValueError:
            relevant = [row for row in rows if row.get("symbol") == "BTCUSDT"]
            if len(relevant) == 1 and self._decimal(relevant[0].get("positionAmt", "0")) == 0:
                return BinanceFuturesTestnetProtectivePosition(symbol="BTCUSDT", position_side=str(relevant[0].get("positionSide") or ""), position_amt=self._decimal("0"), entry_price=self._decimal(relevant[0].get("entryPrice", "0")), mark_price=self._decimal(relevant[0].get("markPrice", "0")), notional=self._decimal("0"), direction="NONE")
            raise

    def _compare_recovery_baseline(self, journal: BinanceFuturesTestnetProtectiveJournal, position: BinanceFuturesTestnetProtectivePosition) -> None:
        if not journal.baseline_available:
            return
        if journal.baseline_position_amount != position.position_amt or journal.baseline_position_direction != position.direction:
            raise ProtectiveAbort("UNEXPECTED_POSITION_CHANGE", "Recovered current position does not match protective journal baseline.", recovery=True, critical=True)

    def _decimal(self, value: Any):
        from decimal import Decimal

        return Decimal(str(value))

    def _try_write_journal(self, config: BinanceFuturesTestnetProtectiveOrdersConfig, journal: BinanceFuturesTestnetProtectiveJournal, phase: str, details: dict[str, Any]) -> bool:
        try:
            self._write_journal(config, journal, phase, details)
            return True
        except Exception:
            return False

    def _write_journal(self, config: BinanceFuturesTestnetProtectiveOrdersConfig, journal: BinanceFuturesTestnetProtectiveJournal, phase: str, details: dict[str, Any]) -> None:
        if not config.allow_sanitized_local_journal:
            return
        journal.phase = phase
        journal.entries.append({"created_at": self._now(), "phase": phase, "details": details})
        path = self._resolve(config.journal_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                handle.write(json.dumps(journal.to_dict(), indent=2))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
            self._fsync_parent_directory(path.parent)
        except Exception:
            try:
                if temp.exists():
                    temp.unlink()
            except OSError:
                pass
            raise

    def _fsync_parent_directory(self, directory: Path) -> None:
        if os.name == "nt":
            return
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _lock_token(self, operation: str, pair_id: str, stop_client_algo_id: str, take_profit_client_algo_id: str) -> str:
        parts = [self._lock_token_part(value) for value in (operation, pair_id, stop_client_algo_id, take_profit_client_algo_id)]
        return "|".join(parts) + f"|token={uuid.uuid4().hex}"

    def _lock_token_part(self, value: str) -> str:
        return "".join(char if char.isalnum() or char in ("-", "_", ".") else "_" for char in str(value))[:120]

    def _acquire_owned_lock(self, path: Path, token: str) -> bool:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(token)
            return True
        except FileExistsError:
            return False

    def _release_owned_lock(self, path: Path, token: str, lock_acquired: bool) -> None:
        if not lock_acquired or not path.exists():
            return
        try:
            if path.read_text(encoding="utf-8") == token:
                path.unlink()
        except OSError:
            return

    def _result(self, config: BinanceFuturesTestnetProtectiveOrdersConfig, action: str, status: str, decision: str, reason: str, **kwargs) -> BinanceFuturesTestnetProtectiveResult:
        return BinanceFuturesTestnetProtectiveResult(
            created_at=self._now(),
            action=action,
            status=status,
            decision=decision,
            reason=reason,
            create_request_transmitted=any(item.request_transmitted for item in kwargs.get("create_requests", [])),
            query_request_transmitted=any(item.request_transmitted for item in kwargs.get("query_requests", [])),
            cancel_request_transmitted=any(item.request_transmitted for item in kwargs.get("cancel_requests", [])),
            production_endpoint_used=urlparse(config.rest_base_url).hostname != "demo-fapi.binance.com",
            real_funds_used=False,
            secrets_exposed=False,
            **kwargs,
        )

    def _report(self, config_path: str, config: BinanceFuturesTestnetProtectiveOrdersConfig | None, issues: list[BinanceFuturesTestnetProtectiveIssue]) -> BinanceFuturesTestnetProtectiveValidationReport:
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        fails = sum(1 for issue in issues if issue.severity == "FAIL")
        return BinanceFuturesTestnetProtectiveValidationReport(
            config_path=config_path,
            created_at=self._now(),
            status="FAIL" if fails else "WARNING" if warnings else "PASS",
            issue_count=len(issues),
            warning_count=warnings,
            fail_count=fails,
            config=config,
            issues=issues,
            diagnostics={"testnet_only": config.testnet_only if config else None, "disabled_by_default": config.feature_enabled is False if config else None},
        )

    def _expect(self, condition: bool, issues: list[BinanceFuturesTestnetProtectiveIssue], name: str, message: str) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message))

    def _issue(self, name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> BinanceFuturesTestnetProtectiveIssue:
        return BinanceFuturesTestnetProtectiveIssue(name, severity, message, details or {})

    def _resolve(self, path: str) -> Path:
        resolved = Path(path)
        return resolved if resolved.is_absolute() else self.repo_root / resolved

    def _now(self) -> str:
        if self.now_provider is not None:
            value = self.now_provider()
            if isinstance(value, datetime):
                return value.isoformat()
            return str(value)
        return datetime.now(UTC).isoformat()

    def _sanitize(self, text: str) -> str:
        for marker in ("signature=", "X-MBX-APIKEY", "BINANCE_FUTURES_TESTNET_API_KEY", "BINANCE_FUTURES_TESTNET_API_SECRET"):
            if marker in text:
                return "redacted authenticated protective-order error"
        return text[:180]

    def _sanitize_api_error(self, exc: Exception) -> str:
        if isinstance(exc, BinanceFuturesTestnetProtectiveAPIError):
            code = "" if exc.binance_code is None else f"{exc.binance_code} "
            return self._sanitize(f"{code}{exc.sanitized_message}")
        return self._sanitize(str(exc))

    def _position_details(self, position: BinanceFuturesTestnetProtectivePosition) -> dict[str, Any]:
        return {"direction": position.direction, "position_amount": str(position.position_amt), "entry_price": str(position.entry_price), "mark_price": str(position.mark_price)}

    def _algo_details(self, order: BinanceFuturesTestnetProtectiveAlgoSummary) -> dict[str, Any]:
        return {"client_algo_id": order.client_algo_id, "algo_id": order.algo_id, "status": order.algo_status}
