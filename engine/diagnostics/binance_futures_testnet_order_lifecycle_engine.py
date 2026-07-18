from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from engine.diagnostics.binance_futures_testnet_adapter_engine import BinanceFuturesTestnetAdapterEngine
from engine.diagnostics.binance_futures_testnet_order_test_engine import BinanceFuturesTestnetOrderTestEngine
from engine.diagnostics.binance_futures_testnet_read_only_engine import BinanceFuturesTestnetReadOnlyEngine
from engine.diagnostics.btc_futures_paper_position_engine import BTCFuturesPaperPositionEngine
from engine.diagnostics.btc_futures_read_only_feed_engine import BTCFuturesReadOnlyFeedEngine
from engine.diagnostics.btc_futures_risk_model_engine import BTCFuturesRiskModelEngine
from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine
from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import (
    BinanceFuturesTestnetLifecycleOperationBlocked,
    BinanceFuturesTestnetOrderLifecycleClient,
)
from infrastructure.persistence.live_execution_authorization_policy import LiveExecutionAuthorizationPolicy
from models.live_execution_authorization import LiveExecutionOperation
from models.binance_futures_testnet_order_lifecycle import (
    BinanceFuturesTestnetBookTicker,
    BinanceFuturesTestnetLifecycleCredentialMetadata,
    BinanceFuturesTestnetLifecycleExchangeFilters,
    BinanceFuturesTestnetLifecycleIssue,
    BinanceFuturesTestnetLifecycleJournal,
    BinanceFuturesTestnetLifecyclePreview,
    BinanceFuturesTestnetLifecycleRequestMetadata,
    BinanceFuturesTestnetLifecycleResult,
    BinanceFuturesTestnetLifecycleValidationReport,
    BinanceFuturesTestnetOrderLifecycleConfig,
    BinanceFuturesTestnetOrderSummary,
    LifecycleAction,
    LifecycleDecision,
    LifecyclePhase,
)


class BinanceFuturesTestnetOrderLifecycleEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        runtime_config_engine: BTCPaperRuntimeConfigEngine | None = None,
        monitoring_engine: BTCPaperMonitoringEngine | None = None,
        runner_engine: BTCPaperRunnerEngine | None = None,
        testnet_adapter_engine: BinanceFuturesTestnetAdapterEngine | None = None,
        testnet_read_only_engine: BinanceFuturesTestnetReadOnlyEngine | None = None,
        testnet_order_test_engine: BinanceFuturesTestnetOrderTestEngine | None = None,
        futures_feed_engine: BTCFuturesReadOnlyFeedEngine | None = None,
        futures_risk_model_engine: BTCFuturesRiskModelEngine | None = None,
        futures_paper_position_engine: BTCFuturesPaperPositionEngine | None = None,
        http_get=None,
        authenticated_request=None,
        env: dict[str, str] | None = None,
        now_ms_provider=None,
        now_provider=None,
        kill_switch_gate=None,
        authorization_policy=None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.runtime_config_engine = runtime_config_engine or BTCPaperRuntimeConfigEngine(repo_root=self.repo_root)
        self.monitoring_engine = monitoring_engine or BTCPaperMonitoringEngine(repo_root=self.repo_root)
        self.runner_engine = runner_engine or BTCPaperRunnerEngine(repo_root=self.repo_root)
        self.testnet_adapter_engine = testnet_adapter_engine or BinanceFuturesTestnetAdapterEngine(repo_root=self.repo_root, env={})
        self.testnet_read_only_engine = testnet_read_only_engine or BinanceFuturesTestnetReadOnlyEngine(repo_root=self.repo_root, env={})
        self.testnet_order_test_engine = testnet_order_test_engine or BinanceFuturesTestnetOrderTestEngine(repo_root=self.repo_root, env={})
        self.futures_feed_engine = futures_feed_engine or BTCFuturesReadOnlyFeedEngine(repo_root=self.repo_root)
        self.futures_risk_model_engine = futures_risk_model_engine or BTCFuturesRiskModelEngine(repo_root=self.repo_root)
        self.futures_paper_position_engine = futures_paper_position_engine or BTCFuturesPaperPositionEngine(repo_root=self.repo_root)
        self.http_get = http_get
        self.authenticated_request = authenticated_request
        self.env = {} if env is None else env
        self.now_ms_provider = now_ms_provider
        self.now_provider = now_provider
        self.authorization_policy = authorization_policy or LiveExecutionAuthorizationPolicy(
            repo_root=self.repo_root,
            env=self.env,
            kill_switch_gate=kill_switch_gate,
        )

    def _require_mutation_permission(self, operation: LiveExecutionOperation) -> None:
        decision = self.authorization_policy.authorize(
            operation,
            environment="TESTNET",
            symbol="BTCUSDT",
            confirmation_verified=True,
            credentials_configured=True,
        )
        if not decision.allowed:
            raise LifecycleAbort(
                decision.code,
                decision.message,
            )

    def validate(self, config_path: str = "configs/binance_futures_testnet_order_lifecycle.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetLifecycleValidationReport:
        issues: list[BinanceFuturesTestnetLifecycleIssue] = []
        diagnostics = self._initial_diagnostics()
        config = None
        try:
            config = self.load_config(config_path)
        except Exception as exc:
            issues.append(self._issue("config_invalid", "FAIL", f"Binance futures testnet lifecycle config could not be loaded: {exc}"))
            return self._report(config_path, config, issues, diagnostics)
        self._validate_config(config, expected_profile, issues, diagnostics)
        return self._report(config_path, config, issues, diagnostics)

    def check_credentials(self, config_path: str = "configs/binance_futures_testnet_order_lifecycle.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetLifecycleResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetOrderLifecycleConfig()
        if report.status == "FAIL":
            return self._result(config, LifecycleAction.CHECK_CREDENTIALS.value, "FAIL", LifecycleDecision.OPERATION_BLOCKED.value, "Lifecycle config failed validation.", issues=list(report.issues))
        metadata = self._client(config).inspect_credentials()
        if metadata.credentials_complete:
            status, decision, reason = "PASS", LifecycleDecision.CREDENTIALS_PRESENT.value, "Dedicated testnet credentials are present."
        elif metadata.api_key_present or metadata.api_secret_present:
            status, decision, reason = "WARNING", LifecycleDecision.CREDENTIALS_INCOMPLETE.value, "Dedicated testnet credentials are incomplete."
        else:
            status, decision, reason = "WARNING", LifecycleDecision.CREDENTIALS_NOT_CONFIGURED.value, "Dedicated testnet credentials are not configured."
        return self._result(config, LifecycleAction.CHECK_CREDENTIALS.value, status, decision, reason, credential_metadata=metadata, issues=list(report.issues), credentials_inspected=True)

    def build_preview(
        self,
        lifecycle_id: str,
        client_order_id: str,
        side: str,
        quantity: float,
        price_offset_bps: int | None = None,
        config_path: str = "configs/binance_futures_testnet_order_lifecycle.json",
        expected_profile: str = "balanced_smc_decision_065",
        exchange_filters: BinanceFuturesTestnetLifecycleExchangeFilters | None = None,
        book_ticker: BinanceFuturesTestnetBookTicker | None = None,
    ) -> BinanceFuturesTestnetLifecycleResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetOrderLifecycleConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, LifecycleAction.BUILD_PREVIEW.value, "FAIL", LifecycleDecision.OPERATION_BLOCKED.value, "Lifecycle config failed validation.", issues=issues, lifecycle_id=lifecycle_id, client_order_id=client_order_id)
        try:
            preview = self._client(config).build_lifecycle_preview(lifecycle_id, client_order_id, side, quantity, price_offset_bps, exchange_filters, book_ticker)
        except Exception as exc:
            issues.append(self._issue("lifecycle_preview_rejected", "FAIL", self._sanitize(str(exc))))
            return self._result(config, LifecycleAction.BUILD_PREVIEW.value, "FAIL", LifecycleDecision.OPERATION_BLOCKED.value, "Local lifecycle preview was rejected.", issues=issues, lifecycle_id=lifecycle_id, client_order_id=client_order_id)
        return self._result(config, LifecycleAction.BUILD_PREVIEW.value, "PASS", LifecycleDecision.LIFECYCLE_PREVIEW_VALID.value, "Local lifecycle preview is valid and non-executable.", preview=preview, issues=issues, lifecycle_id=lifecycle_id, client_order_id=client_order_id, phase=LifecyclePhase.CREATED_LOCALLY.value)

    def run_lifecycle(
        self,
        lifecycle_id: str,
        client_order_id: str,
        side: str,
        quantity: float,
        price_offset_bps: int | None = None,
        confirmation: str | None = None,
        config_path: str = "configs/binance_futures_testnet_order_lifecycle.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BinanceFuturesTestnetLifecycleResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetOrderLifecycleConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, LifecycleAction.RUN_LIFECYCLE.value, "FAIL", LifecycleDecision.OPERATION_BLOCKED.value, "Lifecycle config failed validation.", issues=issues, lifecycle_id=lifecycle_id, client_order_id=client_order_id)
        if config.require_explicit_lifecycle_confirmation and confirmation != config.lifecycle_confirmation_phrase:
            return self._result(config, LifecycleAction.RUN_LIFECYCLE.value, "WARNING", LifecycleDecision.CONFIRMATION_REQUIRED.value, "Explicit testnet lifecycle confirmation is required.", issues=issues, lifecycle_id=lifecycle_id, client_order_id=client_order_id)
        client = self._client(config)
        try:
            metadata = client.inspect_credentials()
        except Exception:
            return self._result(config, LifecycleAction.RUN_LIFECYCLE.value, "FAIL", "CREDENTIALS_UNAVAILABLE", "Testnet credential readiness is unavailable.", issues=issues, lifecycle_id=lifecycle_id, client_order_id=client_order_id)
        if not metadata.credentials_complete:
            decision = LifecycleDecision.CREDENTIALS_INCOMPLETE.value if metadata.api_key_present or metadata.api_secret_present else LifecycleDecision.CREDENTIALS_NOT_CONFIGURED.value
            return self._result(config, LifecycleAction.RUN_LIFECYCLE.value, "WARNING", decision, "Dedicated testnet credentials are incomplete or missing.", credential_metadata=metadata, issues=issues, lifecycle_id=lifecycle_id, client_order_id=client_order_id, credentials_inspected=True)
        try:
            self._require_mutation_permission(LiveExecutionOperation.ORDER_LIFECYCLE_CREATE)
        except LifecycleAbort as exc:
            issues.append(self._issue(exc.decision.lower(), "FAIL", exc.reason))
            return self._result(config, LifecycleAction.RUN_LIFECYCLE.value, "FAIL", exc.decision, exc.reason, credential_metadata=metadata, issues=issues, lifecycle_id=lifecycle_id, client_order_id=client_order_id, credentials_inspected=True)
        lock_path = self._resolve(config.lifecycle_lock_path)
        lock_token = self._lock_token("run_lifecycle", lifecycle_id, client_order_id)
        lock_acquired = self._acquire_owned_lock(lock_path, lock_token)
        if not lock_acquired:
            issues.append(self._issue("lifecycle_lock_exists", "FAIL", "An active lifecycle lock already exists."))
            return self._result(config, LifecycleAction.RUN_LIFECYCLE.value, "FAIL", LifecycleDecision.RECOVERY_REQUIRED.value, "Existing lifecycle lock blocks a new lifecycle.", credential_metadata=metadata, issues=issues, lifecycle_id=lifecycle_id, client_order_id=client_order_id, recovery_required=True)
        filters = None
        ticker = None
        preview = None
        created = queried = cancelled = final = None
        create_meta = query_meta = cancel_meta = None
        create_started = False
        cancel_started = False
        authenticated_precheck_started = False
        journal = BinanceFuturesTestnetLifecycleJournal(lifecycle_id=lifecycle_id, client_order_id=client_order_id)
        try:
            self._ensure_no_unfinished_lifecycle(config, client_order_id)
            self._write_journal(config, journal, LifecyclePhase.PRECHECK_STARTED.value, {"client_order_id": client_order_id})
            filters = client.fetch_exchange_filters()
            ticker = client.fetch_book_ticker()
            preview = client.build_lifecycle_preview(lifecycle_id, client_order_id, side, quantity, price_offset_bps, filters, ticker)
            self._server_time_or_issue(client, config, issues)
            authenticated_precheck_started = True
            hedge_mode = client.fetch_position_mode()
            preview.position_mode_valid = not hedge_mode
            if hedge_mode:
                raise LifecycleAbort(LifecycleDecision.POSITION_MODE_UNSUPPORTED.value, "Position mode is Hedge Mode; One-way Mode is required.")
            before_rows = client.fetch_position_risk()
            client.require_zero_position(before_rows)
            preview.zero_position_precheck_valid = True
            self._write_journal(config, journal, LifecyclePhase.CREATE_REQUEST_STARTED.value, {"client_order_id": client_order_id})
            create_started = True
            self._require_mutation_permission(LiveExecutionOperation.ORDER_LIFECYCLE_CREATE)
            created, create_meta = client.create_order(preview)
            self._check_unexpected_fill(created)
            self._write_journal(config, journal, LifecyclePhase.ORDER_CREATED.value, created.to_dict())
            queried, query_meta = client.query_order(client_order_id)
            self._check_unexpected_fill(queried)
            self._write_journal(config, journal, LifecyclePhase.ORDER_QUERIED.value, queried.to_dict())
            if queried.status == "NEW":
                self._write_journal(config, journal, LifecyclePhase.CANCEL_REQUEST_STARTED.value, {"client_order_id": client_order_id})
                cancel_started = True
                self._require_mutation_permission(LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL)
                cancelled, cancel_meta = client.cancel_order_exact(client_order_id)
                self._write_journal(config, journal, LifecyclePhase.ORDER_CANCELLED.value, cancelled.to_dict())
            elif queried.status not in ("EXPIRED", "REJECTED"):
                self._check_unexpected_fill(queried)
                raise LifecycleAbort(LifecycleDecision.ORDER_STATE_UNKNOWN.value, f"Unexpected initial order status: {queried.status}", recovery=True)
            final, query_meta = client.query_order(client_order_id)
            self._check_unexpected_fill(final)
            if final.status not in ("CANCELED", "EXPIRED", "REJECTED"):
                raise LifecycleAbort(LifecycleDecision.ORDER_STATE_UNKNOWN.value, f"Unexpected final order status: {final.status}", recovery=True)
            after_rows = client.fetch_position_risk()
            client.require_zero_position(after_rows)
            self._write_journal(config, journal, LifecyclePhase.COMPLETE.value, {"final_status": final.status})
        except LifecycleAbort as exc:
            severity = "CRITICAL" if exc.decision in (LifecycleDecision.UNEXPECTED_FILL_DETECTED.value, LifecycleDecision.UNEXPECTED_POSITION_DETECTED.value) else "FAIL"
            issues.append(self._issue(exc.decision.lower(), severity, exc.reason))
            recovery = bool(exc.recovery or create_started or cancel_started)
            if recovery:
                journal.recovery_required = True
                self._write_journal(config, journal, LifecyclePhase.RECOVERY_REQUIRED.value, {"reason": exc.reason})
            else:
                self._write_journal(config, journal, LifecyclePhase.FAILED.value, {"reason": exc.reason})
            return self._result(config, LifecycleAction.RUN_LIFECYCLE.value, "CRITICAL" if severity == "CRITICAL" else "FAIL", exc.decision, exc.reason, credential_metadata=metadata, book_ticker=ticker, exchange_filters=filters, preview=preview, create_request=create_meta, query_request=query_meta, cancel_request=cancel_meta, created_order=created, queried_order=queried, cancel_order=cancelled, final_order=final, journal=journal, issues=issues, lifecycle_id=lifecycle_id, client_order_id=client_order_id, phase=LifecyclePhase.RECOVERY_REQUIRED.value if recovery else LifecyclePhase.FAILED.value, **self._lifecycle_flags(create_meta, query_meta, cancel_meta, recovery_required=recovery, unexpected_fill_detected=severity == "CRITICAL"))
        except Exception as exc:
            message = self._sanitize(str(exc))
            unknown_transport = any(token in message.lower() for token in ("timeout", "timed out", "connection reset", "connection aborted"))
            recovery = (unknown_transport and (create_started or cancel_started)) or (create_meta is not None and final is None)
            decision = LifecycleDecision.RECOVERY_REQUIRED.value if recovery else LifecycleDecision.ORDER_CREATE_REJECTED.value if create_started else LifecycleDecision.AUTHENTICATED_PRECHECK_FAILED.value if authenticated_precheck_started else LifecycleDecision.PUBLIC_PREFLIGHT_FAILED.value
            issues.append(self._issue("lifecycle_failed", "FAIL", message))
            if recovery:
                journal.recovery_required = True
                self._write_journal(config, journal, LifecyclePhase.RECOVERY_REQUIRED.value, {"reason": message})
            else:
                self._write_journal(config, journal, LifecyclePhase.FAILED.value, {"reason": message})
            return self._result(config, LifecycleAction.RUN_LIFECYCLE.value, "FAIL", decision, "Lifecycle failed safely.", credential_metadata=metadata, book_ticker=ticker, exchange_filters=filters, preview=preview, create_request=create_meta, query_request=query_meta, cancel_request=cancel_meta, created_order=created, queried_order=queried, cancel_order=cancelled, final_order=final, journal=journal, issues=issues, lifecycle_id=lifecycle_id, client_order_id=client_order_id, phase=LifecyclePhase.RECOVERY_REQUIRED.value if recovery else LifecyclePhase.FAILED.value, **self._lifecycle_flags(create_meta, query_meta, cancel_meta, recovery_required=recovery))
        finally:
            self._release_owned_lock(lock_path, lock_token, lock_acquired)
        return self._result(config, LifecycleAction.RUN_LIFECYCLE.value, "PASS", LifecycleDecision.LIFECYCLE_COMPLETE.value, "Lifecycle completed: one LIMIT GTX order was created, queried, cancelled or expired, final status verified, and zero position confirmed.", credential_metadata=metadata, book_ticker=ticker, exchange_filters=filters, preview=preview, create_request=create_meta, query_request=query_meta, cancel_request=cancel_meta, created_order=created, queried_order=queried, cancel_order=cancelled, final_order=final, journal=journal, issues=issues, lifecycle_id=lifecycle_id, client_order_id=client_order_id, phase=LifecyclePhase.COMPLETE.value, **self._lifecycle_flags(create_meta, query_meta, cancel_meta, lifecycle_complete=True))

    def query_order(self, client_order_id: str, confirmation: str | None = None, config_path: str = "configs/binance_futures_testnet_order_lifecycle.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetLifecycleResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetOrderLifecycleConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, LifecycleAction.QUERY_ORDER.value, "FAIL", LifecycleDecision.OPERATION_BLOCKED.value, "Lifecycle config failed validation.", issues=issues, client_order_id=client_order_id)
        if config.require_explicit_query_confirmation and confirmation != config.query_confirmation_phrase:
            return self._result(config, LifecycleAction.QUERY_ORDER.value, "WARNING", LifecycleDecision.CONFIRMATION_REQUIRED.value, "Explicit query confirmation is required.", issues=issues, client_order_id=client_order_id)
        client = self._client(config)
        try:
            metadata = client.inspect_credentials()
        except Exception:
            return self._result(config, LifecycleAction.QUERY_ORDER.value, "FAIL", "CREDENTIALS_UNAVAILABLE", "Testnet credential readiness is unavailable.", issues=issues, client_order_id=client_order_id)
        if not metadata.credentials_complete:
            return self._result(config, LifecycleAction.QUERY_ORDER.value, "WARNING", LifecycleDecision.CREDENTIALS_NOT_CONFIGURED.value, "Dedicated testnet credentials are incomplete or missing.", credential_metadata=metadata, issues=issues, client_order_id=client_order_id, credentials_inspected=True)
        self._server_time_or_issue(client, config, issues)
        order, meta = client.query_order(client_order_id)
        return self._result(config, LifecycleAction.QUERY_ORDER.value, "PASS", LifecycleDecision.ORDER_QUERY_SUCCESS.value, "Exact lifecycle order query succeeded.", credential_metadata=metadata, final_order=order, query_request=meta, issues=issues, client_order_id=client_order_id, phase=LifecyclePhase.QUERY_COMPLETE.value, credentials_inspected=True, public_server_time_request_used=True, authenticated_transport_invoked=True, query_request_transmitted=True, signature_generated=True)

    def recovery_cancel(self, client_order_id: str, confirmation: str | None = None, config_path: str = "configs/binance_futures_testnet_order_lifecycle.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetLifecycleResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetOrderLifecycleConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, LifecycleAction.RECOVERY_CANCEL.value, "FAIL", LifecycleDecision.OPERATION_BLOCKED.value, "Lifecycle config failed validation.", issues=issues, client_order_id=client_order_id)
        if config.require_explicit_cancel_confirmation and confirmation != config.cancel_confirmation_phrase:
            return self._result(config, LifecycleAction.RECOVERY_CANCEL.value, "WARNING", LifecycleDecision.CONFIRMATION_REQUIRED.value, "Explicit recovery cancel confirmation is required.", issues=issues, client_order_id=client_order_id)
        client = self._client(config)
        try:
            metadata = client.inspect_credentials()
        except Exception:
            return self._result(config, LifecycleAction.RECOVERY_CANCEL.value, "FAIL", "CREDENTIALS_UNAVAILABLE", "Testnet credential readiness is unavailable.", issues=issues, client_order_id=client_order_id)
        if not metadata.credentials_complete:
            return self._result(config, LifecycleAction.RECOVERY_CANCEL.value, "WARNING", LifecycleDecision.CREDENTIALS_NOT_CONFIGURED.value, "Dedicated testnet credentials are incomplete or missing.", credential_metadata=metadata, issues=issues, client_order_id=client_order_id, credentials_inspected=True)
        try:
            self._require_mutation_permission(LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL)
        except LifecycleAbort as exc:
            issues.append(self._issue(exc.decision.lower(), "FAIL", exc.reason))
            return self._result(config, LifecycleAction.RECOVERY_CANCEL.value, "FAIL", exc.decision, exc.reason, credential_metadata=metadata, issues=issues, client_order_id=client_order_id, credentials_inspected=True)
        self._server_time_or_issue(client, config, issues)
        try:
            self._require_mutation_permission(LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL)
        except LifecycleAbort as exc:
            issues.append(self._issue(exc.decision.lower(), "FAIL", exc.reason))
            return self._result(
                config,
                LifecycleAction.RECOVERY_CANCEL.value,
                "FAIL",
                exc.decision,
                exc.reason,
                credential_metadata=metadata,
                issues=issues,
                client_order_id=client_order_id,
                credentials_inspected=True,
                public_server_time_request_used=True,
            )
        order, meta = client.cancel_order_exact(client_order_id)
        return self._result(config, LifecycleAction.RECOVERY_CANCEL.value, "PASS", LifecycleDecision.ORDER_CANCEL_SUCCESS.value, "Exact lifecycle order recovery cancellation succeeded.", credential_metadata=metadata, cancel_order=order, cancel_request=meta, issues=issues, client_order_id=client_order_id, phase=LifecyclePhase.RECOVERY_CANCEL_COMPLETE.value, credentials_inspected=True, public_server_time_request_used=True, authenticated_transport_invoked=True, cancel_request_transmitted=True, signature_generated=True, order_cancelled=True)

    def recover_lifecycle(self, client_order_id: str, confirmation: str | None = None, config_path: str = "configs/binance_futures_testnet_order_lifecycle.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetLifecycleResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetOrderLifecycleConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, LifecycleAction.RECOVER_LIFECYCLE.value, "FAIL", LifecycleDecision.OPERATION_BLOCKED.value, "Lifecycle config failed validation.", issues=issues, client_order_id=client_order_id)
        if confirmation != config.recovery_confirmation_phrase:
            return self._result(config, LifecycleAction.RECOVER_LIFECYCLE.value, "WARNING", LifecycleDecision.CONFIRMATION_REQUIRED.value, "Explicit exact recovery confirmation is required.", issues=issues, client_order_id=client_order_id)
        client = self._client(config)
        try:
            metadata = client.inspect_credentials()
        except Exception:
            return self._result(config, LifecycleAction.RECOVER_LIFECYCLE.value, "FAIL", "CREDENTIALS_UNAVAILABLE", "Testnet credential readiness is unavailable.", issues=issues, client_order_id=client_order_id)
        if not metadata.credentials_complete:
            return self._result(config, LifecycleAction.RECOVER_LIFECYCLE.value, "WARNING", LifecycleDecision.CREDENTIALS_NOT_CONFIGURED.value, "Dedicated testnet credentials are incomplete or missing.", credential_metadata=metadata, issues=issues, client_order_id=client_order_id, credentials_inspected=True)
        try:
            self._require_mutation_permission(LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL)
        except LifecycleAbort as exc:
            issues.append(self._issue(exc.decision.lower(), "FAIL", exc.reason))
            return self._result(config, LifecycleAction.RECOVER_LIFECYCLE.value, "FAIL", exc.decision, exc.reason, credential_metadata=metadata, issues=issues, client_order_id=client_order_id, credentials_inspected=True)
        lock_path = self._resolve(config.lifecycle_lock_path)
        lock_token = self._lock_token("recover_lifecycle", "", client_order_id)
        lock_acquired = self._acquire_owned_lock(lock_path, lock_token)
        if not lock_acquired:
            issues.append(self._issue("lifecycle_lock_exists", "FAIL", "An active lifecycle lock already exists."))
            return self._result(config, LifecycleAction.RECOVER_LIFECYCLE.value, "FAIL", LifecycleDecision.RECOVERY_REQUIRED.value, "Existing lifecycle lock blocks exact recovery.", credential_metadata=metadata, issues=issues, client_order_id=client_order_id, recovery_required=True)
        journal = self._load_or_new_journal(config, client_order_id)
        query_meta = cancel_meta = None
        queried = cancelled = final = None
        try:
            self._write_journal(config, journal, LifecyclePhase.RECOVERY_REQUIRED.value, {"client_order_id": client_order_id, "recovery_started": True})
            self._server_time_or_issue(client, config, issues)
            queried, query_meta = client.query_order(client_order_id)
            self._check_unexpected_fill(queried)
            if queried.status == "NEW":
                self._require_mutation_permission(LiveExecutionOperation.ORDER_LIFECYCLE_CANCEL)
                cancelled, cancel_meta = client.cancel_order_exact(client_order_id)
                self._check_unexpected_fill(cancelled)
            elif queried.status not in ("CANCELED", "EXPIRED", "REJECTED"):
                raise LifecycleAbort(LifecycleDecision.ORDER_STATE_UNKNOWN.value, f"Unexpected recovery order status: {queried.status}", recovery=True)
            final, query_meta = client.query_order(client_order_id)
            self._check_unexpected_fill(final)
            if final.status not in ("CANCELED", "EXPIRED", "REJECTED"):
                raise LifecycleAbort(LifecycleDecision.ORDER_STATE_UNKNOWN.value, f"Unexpected final recovery status: {final.status}", recovery=True)
            rows = client.fetch_position_risk()
            client.require_zero_position(rows)
            journal.recovery_required = False
            self._write_journal(config, journal, LifecyclePhase.RECOVERY_COMPLETE.value, {"final_status": final.status})
            return self._result(config, LifecycleAction.RECOVER_LIFECYCLE.value, "PASS", LifecycleDecision.RECOVERY_COMPLETE.value, "Exact lifecycle recovery completed.", credential_metadata=metadata, queried_order=queried, cancel_order=cancelled, final_order=final, query_request=query_meta, cancel_request=cancel_meta, journal=journal, issues=issues, client_order_id=client_order_id, phase=LifecyclePhase.RECOVERY_COMPLETE.value, **self._lifecycle_flags(None, query_meta, cancel_meta, lifecycle_complete=True))
        except LifecycleAbort as exc:
            severity = "CRITICAL" if exc.decision == LifecycleDecision.UNEXPECTED_FILL_DETECTED.value else "FAIL"
            issues.append(self._issue(exc.decision.lower(), severity, exc.reason))
            journal.recovery_required = True
            self._write_journal(config, journal, LifecyclePhase.RECOVERY_REQUIRED.value, {"reason": exc.reason})
            return self._result(config, LifecycleAction.RECOVER_LIFECYCLE.value, "CRITICAL" if severity == "CRITICAL" else "FAIL", exc.decision, exc.reason, credential_metadata=metadata, queried_order=queried, cancel_order=cancelled, final_order=final, query_request=query_meta, cancel_request=cancel_meta, journal=journal, issues=issues, client_order_id=client_order_id, phase=LifecyclePhase.RECOVERY_REQUIRED.value, **self._lifecycle_flags(None, query_meta, cancel_meta, recovery_required=True, unexpected_fill_detected=severity == "CRITICAL"))
        except Exception as exc:
            message = self._sanitize(str(exc))
            issues.append(self._issue("recovery_failed", "FAIL", message))
            journal.recovery_required = True
            self._write_journal(config, journal, LifecyclePhase.RECOVERY_REQUIRED.value, {"reason": message})
            return self._result(config, LifecycleAction.RECOVER_LIFECYCLE.value, "FAIL", LifecycleDecision.RECOVERY_REQUIRED.value, "Exact lifecycle recovery failed safely.", credential_metadata=metadata, queried_order=queried, cancel_order=cancelled, final_order=final, query_request=query_meta, cancel_request=cancel_meta, journal=journal, issues=issues, client_order_id=client_order_id, phase=LifecyclePhase.RECOVERY_REQUIRED.value, **self._lifecycle_flags(None, query_meta, cancel_meta, recovery_required=True))
        finally:
            self._release_owned_lock(lock_path, lock_token, lock_acquired)

    def runner_validate(self, config_path: str = "configs/binance_futures_testnet_order_lifecycle.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetLifecycleResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetOrderLifecycleConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, LifecycleAction.RUNNER_VALIDATE.value, "FAIL", LifecycleDecision.OPERATION_BLOCKED.value, "Lifecycle config failed runner dry-run validation.", issues=issues)
        preview = self._client(config).build_lifecycle_preview("lifecycle-runner-001", "smcbot-lifecycle-runner-001", "BUY", 0.001, config.default_price_offset_bps)
        return self._result(config, LifecycleAction.RUNNER_VALIDATE.value, "PASS", LifecycleDecision.CONFIG_VALID.value, "Lifecycle config validates for runner dry-run without credentials or network.", preview=preview, issues=issues, lifecycle_id=preview.lifecycle_id, client_order_id=preview.client_order_id)

    def hard_block_diagnostics(self, config_path: str = "configs/binance_futures_testnet_order_lifecycle.json") -> BinanceFuturesTestnetLifecycleResult:
        config = self.load_config(config_path)
        client = self._client(config)
        methods = ["submit_market_order", "submit_conditional_order", "submit_algo_order", "submit_batch_orders", "modify_order", "cancel_all_orders", "fetch_open_orders", "fetch_all_orders", "fetch_trades", "change_leverage", "change_margin_mode", "change_position_mode", "change_multi_assets_mode", "change_position_margin", "close_position", "create_listen_key", "open_user_stream", "open_websocket"]
        blocked: dict[str, str] = {}
        issues: list[BinanceFuturesTestnetLifecycleIssue] = []
        for method in methods:
            try:
                getattr(client, method)()
            except BinanceFuturesTestnetLifecycleOperationBlocked as exc:
                blocked[method] = str(exc)
            except Exception as exc:
                issues.append(self._issue(f"{method}_unexpected", "FAIL", self._sanitize(str(exc))))
        status = "PASS" if len(blocked) == len(methods) and not issues else "FAIL"
        return self._result(config, LifecycleAction.HARD_BLOCK.value, status, LifecycleDecision.OPERATION_BLOCKED.value, "Forbidden lifecycle operations are blocked before transport.", payload={"blocked_methods": blocked}, issues=issues)

    def load_config(self, config_path: str = "configs/binance_futures_testnet_order_lifecycle.json") -> BinanceFuturesTestnetOrderLifecycleConfig:
        path = self._resolve(config_path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("config JSON must be an object")
        return BinanceFuturesTestnetOrderLifecycleConfig(**{**BinanceFuturesTestnetOrderLifecycleConfig().to_dict(), **loaded})

    def _validate_config(self, config: BinanceFuturesTestnetOrderLifecycleConfig, expected_profile: str, issues: list[BinanceFuturesTestnetLifecycleIssue], diagnostics: dict[str, Any]) -> None:
        expected = {"project_scope": "BTC_ONLY", "symbol": "BTC/USDT", "exchange_symbol": "BTCUSDT", "exchange": "binance", "market_type": "futures", "futures_contract_type": "USDT_PERPETUAL", "strategy_profile": expected_profile}
        for name, value in expected.items():
            self._expect(getattr(config, name) == value, issues, name, f"{name} must be {value}.")
        true_fields = ("explicit_cli_only", "manual_lifecycle_only", "testnet_only", "single_order_only", "require_zero_position_before_create", "require_zero_position_after_cancel", "require_explicit_lifecycle_confirmation", "require_explicit_cancel_confirmation", "require_explicit_query_confirmation", "require_exchange_filter_validation", "require_book_ticker_validation", "require_non_marketable_price", "require_gtx_post_only", "allow_lifecycle_create_query_cancel", "allow_exact_order_query", "allow_exact_order_recovery_cancel", "allow_sanitized_local_lifecycle_journal")
        for name in true_fields:
            self._expect(bool(getattr(config, name)), issues, name, f"{name} must be true.")
        self._expect(not config.feature_enabled, issues, "feature_enabled", "feature_enabled must remain false.")
        self._expect(not config.automatic_execution_enabled, issues, "automatic_execution_enabled", "automatic execution must remain disabled.")
        self._validate_url_and_hosts(config, issues)
        self._expect(config.api_key_env_var == "BINANCE_FUTURES_TESTNET_API_KEY", issues, "api_key_env_var", "Only dedicated futures testnet API key env var may be used.")
        self._expect(config.api_secret_env_var == "BINANCE_FUTURES_TESTNET_API_SECRET", issues, "api_secret_env_var", "Only dedicated futures testnet API secret env var may be used.")
        self._expect(config.server_time_path == "/fapi/v1/time", issues, "server_time_path", "server time path is fixed.")
        self._expect(config.exchange_info_path == "/fapi/v1/exchangeInfo", issues, "exchange_info_path", "exchangeInfo path is fixed.")
        self._expect(config.book_ticker_path == "/fapi/v1/ticker/bookTicker", issues, "book_ticker_path", "bookTicker path is fixed.")
        self._expect(config.position_mode_path == "/fapi/v1/positionSide/dual", issues, "position_mode_path", "position mode path is fixed.")
        self._expect(config.position_risk_path == "/fapi/v3/positionRisk", issues, "position_risk_path", "position risk path is fixed.")
        self._expect(config.order_path == "/fapi/v1/order", issues, "order_path", "order path must be /fapi/v1/order.")
        self._expect(config.allowed_order_methods == ["POST", "GET", "DELETE"], issues, "allowed_order_methods", "Only POST/GET/DELETE order methods are allowed.")
        self._expect(config.allowed_order_types == ["LIMIT"], issues, "allowed_order_types", "Only LIMIT order type is allowed.")
        self._expect(config.allowed_time_in_force == ["GTX"], issues, "allowed_time_in_force", "Only GTX time-in-force is allowed.")
        self._expect(config.allowed_sides == ["BUY", "SELL"], issues, "allowed_sides", "Only BUY and SELL sides are allowed.")
        self._expect(config.required_position_mode == "ONE_WAY", issues, "required_position_mode", "One-way Mode is required.")
        self._expect(config.required_position_side == "BOTH", issues, "required_position_side", "positionSide must be BOTH.")
        self._expect(config.lifecycle_confirmation_phrase == "CONFIRM_TESTNET_POST_ONLY_LIFECYCLE", issues, "lifecycle_confirmation_phrase", "lifecycle confirmation phrase is fixed.")
        self._expect(config.cancel_confirmation_phrase == "CONFIRM_TESTNET_CANCEL_ORDER", issues, "cancel_confirmation_phrase", "cancel confirmation phrase is fixed.")
        self._expect(config.query_confirmation_phrase == "CONFIRM_TESTNET_READ_ONLY", issues, "query_confirmation_phrase", "query confirmation phrase is fixed.")
        self._expect(config.recovery_confirmation_phrase == "CONFIRM_TESTNET_EXACT_RECOVERY", issues, "recovery_confirmation_phrase", "recovery confirmation phrase is fixed.")
        self._expect(1 <= int(config.request_timeout_seconds) <= 30, issues, "request_timeout_seconds", "timeout must be between 1 and 30.")
        self._expect(int(config.max_create_retries) == 0, issues, "max_create_retries", "create retries must remain zero.")
        self._expect(int(config.max_cancel_retries) == 0, issues, "max_cancel_retries", "cancel retries must remain zero.")
        self._expect(0 <= int(config.max_query_retries) <= 1, issues, "max_query_retries", "query retries must be at most one.")
        self._expect(0 < int(config.recv_window_ms) <= int(config.maximum_recv_window_ms) <= 10000, issues, "recv_window_ms", "recvWindow must be <= 10000.")
        self._expect(0 <= int(config.maximum_clock_skew_ms) <= 5000, issues, "maximum_clock_skew_ms", "clock skew allowance must be <= 5000ms.")
        self._expect(int(config.minimum_price_offset_bps) >= 50, issues, "minimum_price_offset_bps", "minimum offset must be at least 50 bps.")
        self._expect(int(config.maximum_price_offset_bps) <= 5000, issues, "maximum_price_offset_bps", "maximum offset must be <= 5000 bps.")
        self._expect(int(config.minimum_price_offset_bps) <= int(config.default_price_offset_bps) <= int(config.maximum_price_offset_bps), issues, "default_price_offset_bps", "default offset must be in safe range.")
        self._expect(0 < float(config.maximum_quantity) <= 0.01, issues, "maximum_quantity", "maximum quantity must be <= 0.01.")
        self._expect(0 < float(config.maximum_lifecycle_notional_usdt) <= 100.0, issues, "maximum_lifecycle_notional_usdt", "maximum lifecycle notional must be <= 100 USDT.")
        self._expect(config.new_order_response_type == "ACK", issues, "new_order_response_type", "new order response type must be ACK.")
        self._expect(config.client_order_id_prefix == "smcbot-lifecycle-", issues, "client_order_id_prefix", "client order ID prefix must be smcbot-lifecycle-.")
        self._expect(1 <= int(config.maximum_client_order_id_length) <= 36, issues, "maximum_client_order_id_length", "client order ID length must be <= 36.")
        for name in self._must_be_false_fields():
            self._expect(not bool(getattr(config, name)), issues, name, f"{name} must remain false.")
        self._validate_paths(config, issues)
        self._validate_dependencies(config, expected_profile, issues, diagnostics)

    def _must_be_false_fields(self) -> tuple[str, ...]:
        return (
            "allow_standalone_create", "allow_market_order", "allow_conditional_order", "allow_algo_order", "allow_batch_order",
            "allow_order_modification", "allow_cancel_all", "allow_open_order_list_query", "allow_all_order_history_query",
            "allow_trade_history_query", "allow_position_creation", "allow_position_close", "allow_leverage_change", "allow_margin_mode_change",
            "allow_position_mode_change", "allow_multi_assets_mode_change", "allow_position_margin_change", "allow_user_data_stream",
            "allow_listen_key", "allow_websocket_connection", "allow_production_endpoint", "allow_production_credentials", "allow_real_funds",
            "allow_runner_order_creation", "allow_monitoring_order_creation", "allow_strategy_order_creation", "allow_background_order_creation",
            "allow_futures_paper_state_mutation", "allow_spot_paper_account_state_mutation", "allow_runner_state_mutation", "allow_execution_state_mutation",
            "allow_raw_request_print", "allow_raw_response_print", "allow_raw_request_persistence", "allow_raw_response_persistence",
            "allow_authenticated_header_logging", "allow_signature_logging", "allow_signed_url_logging",
        )

    def _validate_url_and_hosts(self, config: BinanceFuturesTestnetOrderLifecycleConfig, issues: list[BinanceFuturesTestnetLifecycleIssue]) -> None:
        try:
            BinanceFuturesTestnetOrderLifecycleClient(config, env={})
        except Exception as exc:
            issues.append(self._issue("rest_base_url", "FAIL", str(exc)))
        self._expect(config.allowed_hosts == ["demo-fapi.binance.com"], issues, "allowed_hosts", "allowed_hosts must contain only demo-fapi.binance.com.")
        self._expect((urlparse(config.rest_base_url).hostname or "") == "demo-fapi.binance.com", issues, "rest_base_url_host", "REST host must be demo-fapi.binance.com.")

    def _validate_paths(self, config: BinanceFuturesTestnetOrderLifecycleConfig, issues: list[BinanceFuturesTestnetLifecycleIssue]) -> None:
        journal = Path(config.lifecycle_journal_path)
        lock = Path(config.lifecycle_lock_path)
        for name, path in (("lifecycle_journal_path", journal), ("lifecycle_lock_path", lock)):
            self._expect(not path.is_absolute() and ".." not in path.parts and len(path.parts) >= 3 and path.parts[0] == "data" and path.parts[1] == "runtime" and path.parts[2] == "binance_futures_testnet_order_lifecycle", issues, name, f"{name} must stay under data/runtime/binance_futures_testnet_order_lifecycle.")
        report_dir = Path(config.report_export_dir)
        self._expect(not report_dir.is_absolute() and ".." not in report_dir.parts and len(report_dir.parts) >= 2 and report_dir.parts[0] == "reports" and report_dir.parts[1] == "binance_futures_testnet_order_lifecycle", issues, "report_export_dir", "report_export_dir must stay under reports/binance_futures_testnet_order_lifecycle.")

    def _validate_dependencies(self, config: BinanceFuturesTestnetOrderLifecycleConfig, expected_profile: str, issues: list[BinanceFuturesTestnetLifecycleIssue], diagnostics: dict[str, Any]) -> None:
        runtime = self.runtime_config_engine.validate(config.runtime_config_path, expected_profile=expected_profile)
        diagnostics["runtime_config_status"] = runtime.status
        diagnostics["kill_switch_enabled"] = bool(getattr(runtime.config, "kill_switch_enabled", False))
        if config.require_runtime_config_pass and runtime.status != "PASS":
            issues.append(self._issue("runtime_config_validation", "FAIL", "Runtime config must validate PASS."))
        if runtime.config is not None and config.require_kill_switch_enabled:
            self._expect(runtime.config.kill_switch_enabled, issues, "kill_switch_enabled", "kill_switch_enabled must remain true.")
        checks = [
            ("monitoring_config_status", config.require_monitoring_config_pass, self.monitoring_engine.validate(config.monitoring_config_path, expected_profile=expected_profile), "monitoring_config_validation"),
            ("testnet_adapter_config_status", config.require_testnet_adapter_config_pass, self.testnet_adapter_engine.validate(config.testnet_adapter_config_path, expected_profile=expected_profile), "testnet_adapter_config_validation"),
            ("testnet_read_only_config_status", config.require_testnet_read_only_config_pass, self.testnet_read_only_engine.validate(config.testnet_read_only_config_path, expected_profile=expected_profile), "testnet_read_only_config_validation"),
            ("testnet_order_test_config_status", config.require_testnet_order_test_config_pass, self.testnet_order_test_engine.validate(config.testnet_order_test_config_path, expected_profile=expected_profile), "testnet_order_test_config_validation"),
            ("futures_feed_config_status", config.require_futures_feed_config_pass, self.futures_feed_engine.validate(config.futures_feed_config_path, expected_profile=expected_profile), "futures_feed_config_validation"),
            ("futures_risk_model_config_status", config.require_futures_risk_model_config_pass, self.futures_risk_model_engine.validate(config.futures_risk_model_config_path, expected_profile=expected_profile), "futures_risk_model_config_validation"),
            ("futures_paper_position_config_status", config.require_futures_paper_position_config_pass, self.futures_paper_position_engine.validate(config.futures_paper_position_config_path, expected_profile=expected_profile), "futures_paper_position_config_validation"),
        ]
        _, runner_issues, _ = self.runner_engine.validate_config(config.runner_config_path, expected_profile=expected_profile)
        diagnostics["runner_config_status"] = "FAIL" if any(issue.severity == "FAIL" for issue in runner_issues) else "PASS"
        if config.require_runner_config_pass and diagnostics["runner_config_status"] != "PASS":
            issues.append(self._issue("runner_config_validation", "FAIL", "Runner config must validate PASS."))
        for diagnostic_name, required, report, issue_name in checks:
            diagnostics[diagnostic_name] = report.status
            if required and report.status != "PASS":
                issues.append(self._issue(issue_name, "FAIL", f"{issue_name} must validate PASS."))

    def _server_time_or_issue(self, client: BinanceFuturesTestnetOrderLifecycleClient, config: BinanceFuturesTestnetOrderLifecycleConfig, issues: list[BinanceFuturesTestnetLifecycleIssue]) -> int:
        payload = client.fetch_server_time()
        skew = int(payload["clock_skew_ms"])
        if skew > int(config.maximum_clock_skew_ms):
            issues.append(self._issue("clock_skew_exceeded", "FAIL", "Testnet server-time skew exceeded safe maximum.", {"clock_skew_ms": skew}))
            raise RuntimeError("clock skew exceeded")
        client.set_server_time_offset(int(payload["server_time"]), int(payload["local_time"]))
        return int(payload["server_time"])

    def _check_unexpected_fill(self, order: BinanceFuturesTestnetOrderSummary | None) -> None:
        if order is None:
            return
        if order.executed_quantity is not None and order.executed_quantity > 0:
            raise LifecycleAbort(LifecycleDecision.UNEXPECTED_FILL_DETECTED.value, "Unexpected executed quantity detected.", recovery=True)
        if order.status in ("FILLED", "PARTIALLY_FILLED"):
            raise LifecycleAbort(LifecycleDecision.UNEXPECTED_FILL_DETECTED.value, f"Unexpected fill status detected: {order.status}", recovery=True)

    def _ensure_no_unfinished_lifecycle(self, config: BinanceFuturesTestnetOrderLifecycleConfig, client_order_id: str) -> None:
        path = self._resolve(config.lifecycle_journal_path)
        if not path.exists():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("client_order_id") == client_order_id and payload.get("phase") not in (LifecyclePhase.COMPLETE.value, LifecyclePhase.FAILED.value):
            raise LifecycleAbort(LifecycleDecision.RECOVERY_REQUIRED.value, "Unfinished lifecycle exists for this client order ID.", recovery=True)

    def _write_journal(self, config: BinanceFuturesTestnetOrderLifecycleConfig, journal: BinanceFuturesTestnetLifecycleJournal, phase: str, details: dict[str, Any]) -> None:
        if not config.allow_sanitized_local_lifecycle_journal:
            return
        journal.phase = phase
        journal.entries.append({"created_at": self._now(), "phase": phase, "details": details})
        path = self._resolve(config.lifecycle_journal_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(journal.to_dict(), indent=2), encoding="utf-8")
        temp.replace(path)

    def _lock_token(self, operation: str, lifecycle_id: str, client_order_id: str) -> str:
        return f"{self._lock_token_part(operation)}|lifecycle_id={self._lock_token_part(lifecycle_id)}|client_order_id={self._lock_token_part(client_order_id)}|token={uuid.uuid4().hex}"

    def _lock_token_part(self, value: str) -> str:
        cleaned = "".join(char if char.isalnum() or char in ("-", "_", ".") else "_" for char in str(value))
        return cleaned[:120]

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

    def _load_or_new_journal(self, config: BinanceFuturesTestnetOrderLifecycleConfig, client_order_id: str) -> BinanceFuturesTestnetLifecycleJournal:
        path = self._resolve(config.lifecycle_journal_path)
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("client_order_id") == client_order_id:
                    return BinanceFuturesTestnetLifecycleJournal(
                        lifecycle_id=str(payload.get("lifecycle_id") or ""),
                        client_order_id=client_order_id,
                        phase=str(payload.get("phase") or LifecyclePhase.RECOVERY_REQUIRED.value),
                        recovery_required=bool(payload.get("recovery_required", True)),
                        entries=[entry for entry in payload.get("entries", []) if isinstance(entry, dict)],
                    )
            except Exception:
                pass
        return BinanceFuturesTestnetLifecycleJournal(client_order_id=client_order_id, phase=LifecyclePhase.RECOVERY_REQUIRED.value, recovery_required=True)

    def _client(self, config: BinanceFuturesTestnetOrderLifecycleConfig) -> BinanceFuturesTestnetOrderLifecycleClient:
        return BinanceFuturesTestnetOrderLifecycleClient(config, http_get=self.http_get, authenticated_request=self.authenticated_request, env=self.env, now_ms_provider=self.now_ms_provider)

    def _result(self, config: BinanceFuturesTestnetOrderLifecycleConfig, action: str, status: str, decision: str, reason: str, **kwargs) -> BinanceFuturesTestnetLifecycleResult:
        flags = {key: value for key, value in kwargs.items() if key in BinanceFuturesTestnetLifecycleResult.__dataclass_fields__}
        flags.setdefault("safety_summary", self._safety_summary(flags))
        return BinanceFuturesTestnetLifecycleResult(created_at=self._now(), action=action, status=status, decision=decision, reason=reason, **flags)

    def _lifecycle_flags(self, create_meta, query_meta, cancel_meta, lifecycle_complete: bool = False, recovery_required: bool = False, unexpected_fill_detected: bool = False) -> dict[str, Any]:
        return {
            "credentials_inspected": True,
            "public_server_time_request_used": True,
            "public_exchange_info_request_used": True,
            "public_book_ticker_request_used": True,
            "position_mode_request_used": True,
            "position_risk_request_used": True,
            "signature_generated": any(meta is not None and meta.signature_generated for meta in (create_meta, query_meta, cancel_meta)),
            "authenticated_transport_invoked": any(meta is not None and meta.request_transmitted for meta in (create_meta, query_meta, cancel_meta)),
            "create_request_transmitted": bool(create_meta and create_meta.request_transmitted),
            "query_request_transmitted": bool(query_meta and query_meta.request_transmitted),
            "cancel_request_transmitted": bool(cancel_meta and cancel_meta.request_transmitted),
            "order_created": bool(create_meta and create_meta.request_transmitted),
            "order_cancelled": bool(cancel_meta and cancel_meta.request_transmitted),
            "actual_order_endpoint_used": bool(create_meta and create_meta.request_transmitted),
            "lifecycle_complete": lifecycle_complete,
            "recovery_required": recovery_required,
            "unexpected_fill_detected": unexpected_fill_detected,
        }

    def _safety_summary(self, flags: dict[str, Any] | None = None) -> dict[str, Any]:
        flags = flags or {}
        names = ("credentials_inspected", "public_server_time_request_used", "public_exchange_info_request_used", "public_book_ticker_request_used", "position_mode_request_used", "position_risk_request_used", "signature_generated", "authenticated_transport_invoked", "create_request_transmitted", "query_request_transmitted", "cancel_request_transmitted", "order_created", "order_cancelled", "lifecycle_complete", "recovery_required", "unexpected_fill_detected", "unexpected_position_detected", "actual_order_endpoint_used", "market_order_used", "conditional_order_created", "algo_order_created", "batch_order_created", "order_modified", "cancel_all_used", "leverage_changed", "margin_mode_changed", "position_mode_changed", "production_endpoint_used", "futures_paper_state_mutated", "spot_paper_account_state_mutated", "runner_state_mutated", "execution_state_mutated", "exchange_state_mutated", "api_key_exposed", "api_secret_exposed", "signature_exposed", "signed_url_exposed", "authenticated_headers_exposed", "raw_request_persisted", "raw_response_persisted")
        return {name: bool(flags.get(name, False)) for name in names}

    def _initial_diagnostics(self) -> dict[str, Any]:
        return {"runtime_config_status": "UNKNOWN", "monitoring_config_status": "UNKNOWN", "runner_config_status": "UNKNOWN", "testnet_adapter_config_status": "UNKNOWN", "testnet_read_only_config_status": "UNKNOWN", "testnet_order_test_config_status": "UNKNOWN", "futures_feed_config_status": "UNKNOWN", "futures_risk_model_config_status": "UNKNOWN", "futures_paper_position_config_status": "UNKNOWN", "kill_switch_enabled": None, "credentials_inspected": False, "network_used": False, "order_created": False}

    def _report(self, config_path: str, config: BinanceFuturesTestnetOrderLifecycleConfig | None, issues: list[BinanceFuturesTestnetLifecycleIssue], diagnostics: dict[str, Any]) -> BinanceFuturesTestnetLifecycleValidationReport:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        return BinanceFuturesTestnetLifecycleValidationReport(config_path=config_path, created_at=self._now(), status="FAIL" if failures else "WARNING" if warnings else "PASS", issue_count=len(issues), warning_count=warnings, fail_count=failures, config=config, issues=issues, diagnostics=diagnostics)

    def _expect(self, condition: bool, issues: list[BinanceFuturesTestnetLifecycleIssue], name: str, message: str) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message))

    def _issue(self, name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> BinanceFuturesTestnetLifecycleIssue:
        return BinanceFuturesTestnetLifecycleIssue(name=name, severity=severity, message=message, details=details or {})

    def _resolve(self, path_text: str) -> Path:
        path = Path(path_text)
        return path if path.is_absolute() else self.repo_root / path

    def _now(self) -> str:
        if self.now_provider is not None:
            return str(self.now_provider())
        return datetime.now(UTC).replace(microsecond=0).isoformat()

    def _sanitize(self, text: str) -> str:
        for marker in ("signature=", "X-MBX-APIKEY", self.env.get("BINANCE_FUTURES_TESTNET_API_KEY", ""), self.env.get("BINANCE_FUTURES_TESTNET_API_SECRET", "")):
            if marker and marker in text:
                return "redacted authenticated lifecycle error"
        return text[:180]


class LifecycleAbort(RuntimeError):
    def __init__(self, decision: str, reason: str, recovery: bool = False) -> None:
        super().__init__(reason)
        self.decision = decision
        self.reason = reason
        self.recovery = recovery
