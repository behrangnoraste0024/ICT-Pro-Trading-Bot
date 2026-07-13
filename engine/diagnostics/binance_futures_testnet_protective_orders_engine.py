from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from infrastructure.exchanges.binance_futures_testnet_protective_orders_client import BinanceFuturesTestnetProtectiveAPIError, BinanceFuturesTestnetProtectiveOrdersClient
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
)


class ProtectiveAbort(RuntimeError):
    def __init__(self, decision: str, reason: str, recovery: bool = False, critical: bool = False) -> None:
        super().__init__(reason)
        self.decision = decision
        self.reason = reason
        self.recovery = recovery
        self.critical = critical


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
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.http_get = http_get
        self.authenticated_request = authenticated_request
        self.env = {} if env is None else env
        self.now_ms_provider = now_ms_provider
        self.now_provider = now_provider

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
            return self._result(config, "BUILD_PREVIEW", "PASS", "PROTECTIVE_PREVIEW_VALID", "Local protective preview is valid and non-executable.", preview=preview, position=position, exchange_filters=filters, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="CREATED_LOCALLY")
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
    ) -> BinanceFuturesTestnetProtectiveResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetProtectiveOrdersConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "FAIL", "OPERATION_BLOCKED", "Protective config failed validation.", issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        if confirmation != config.pair_confirmation_phrase:
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "WARNING", "CONFIRMATION_REQUIRED", "Explicit protective pair confirmation is required.", issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        client = self._client(config)
        metadata = client.inspect_credentials()
        if not metadata.credentials_complete:
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "WARNING", "CREDENTIALS_NOT_CONFIGURED", "Dedicated testnet credentials are incomplete or missing.", credential_metadata=metadata, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        lock_path = self._resolve(config.lock_path)
        lock_token = self._lock_token("run_protective_lifecycle", pair_id, stop_client_algo_id, take_profit_client_algo_id)
        lock_acquired = self._acquire_owned_lock(lock_path, lock_token)
        if not lock_acquired:
            issues.append(self._issue("protective_lock_exists", "FAIL", "An active protective-order lock already exists."))
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "FAIL", "RECOVERY_REQUIRED", "Existing protective lock blocks a new lifecycle.", credential_metadata=metadata, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, recovery_required=True)
        journal = BinanceFuturesTestnetProtectiveJournal(pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        filters = None
        position = final_position = None
        preview = None
        stop_order = take_order = final_stop = final_take = None
        create_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata] = []
        query_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata] = []
        cancel_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata] = []
        stop_create_started = take_create_started = cancel_started = False
        try:
            self._write_journal(config, journal, "PRECHECK_STARTED", {"pair_id": pair_id})
            filters = client.fetch_exchange_filters()
            self._server_time_or_issue(client, config, issues)
            if client.fetch_position_mode():
                raise ProtectiveAbort("POSITION_MODE_UNSUPPORTED", "Position mode is Hedge Mode; One-way Mode is required.")
            position = client.require_protectable_position(client.fetch_position_risk())
            self._write_journal(config, journal, "POSITION_VALIDATED", self._position_details(position))
            preview = client.build_preview(pair_id, stop_client_algo_id, take_profit_client_algo_id, position, filters, stop_offset_bps, take_profit_offset_bps)
            self._attach_journal_baseline(journal, position, preview)
            self._write_journal(config, journal, "STOP_CREATE_STARTED", {"client_algo_id": stop_client_algo_id})
            stop_create_started = True
            stop_order, meta = client.create_stop_order(preview)
            create_requests.append(meta)
            self._validate_algo_identity(stop_order, preview, "STOP")
            self._check_unexpected_trigger(stop_order)
            self._write_journal(config, journal, "STOP_CREATED", self._algo_details(stop_order))
            stop_order, meta = client.query_algo_order(stop_client_algo_id)
            query_requests.append(meta)
            self._validate_algo_identity(stop_order, preview, "STOP")
            self._require_new(stop_order, "STOP")
            self._write_journal(config, journal, "STOP_QUERY_COMPLETE", self._algo_details(stop_order))
            self._write_journal(config, journal, "TAKE_PROFIT_CREATE_STARTED", {"client_algo_id": take_profit_client_algo_id})
            take_create_started = True
            take_order, meta = client.create_take_profit_order(preview)
            create_requests.append(meta)
            self._validate_algo_identity(take_order, preview, "TAKE_PROFIT")
            self._check_unexpected_trigger(take_order)
            self._write_journal(config, journal, "TAKE_PROFIT_CREATED", self._algo_details(take_order))
            take_order, meta = client.query_algo_order(take_profit_client_algo_id)
            query_requests.append(meta)
            self._validate_algo_identity(take_order, preview, "TAKE_PROFIT")
            self._require_new(take_order, "TAKE_PROFIT")
            self._write_journal(config, journal, "TAKE_PROFIT_QUERY_COMPLETE", self._algo_details(take_order))
            self._require_same_position(position, client.require_protectable_position(client.fetch_position_risk()))
            self._write_journal(config, journal, "TAKE_PROFIT_CANCEL_STARTED", {"client_algo_id": take_profit_client_algo_id})
            cancel_started = True
            delete_take, meta = client.cancel_algo_order_exact(take_profit_client_algo_id)
            cancel_requests.append(meta)
            self._validate_delete_ack(delete_take, take_profit_client_algo_id)
            final_take, meta = client.query_algo_order(take_profit_client_algo_id)
            query_requests.append(meta)
            self._validate_algo_identity(final_take, preview, "TAKE_PROFIT")
            self._require_terminal_safe(final_take, "TAKE_PROFIT")
            self._write_journal(config, journal, "TAKE_PROFIT_CANCELED", self._algo_details(final_take))
            self._write_journal(config, journal, "STOP_CANCEL_STARTED", {"client_algo_id": stop_client_algo_id})
            delete_stop, meta = client.cancel_algo_order_exact(stop_client_algo_id)
            cancel_requests.append(meta)
            self._validate_delete_ack(delete_stop, stop_client_algo_id)
            final_stop, meta = client.query_algo_order(stop_client_algo_id)
            query_requests.append(meta)
            self._validate_algo_identity(final_stop, preview, "STOP")
            self._require_terminal_safe(final_stop, "STOP")
            self._write_journal(config, journal, "STOP_CANCELED", self._algo_details(final_stop))
            final_position = client.require_protectable_position(client.fetch_position_risk())
            self._require_same_position(position, final_position)
            journal.recovery_required = False
            self._write_journal(config, journal, "COMPLETE", {"stop_status": final_stop.algo_status, "take_profit_status": final_take.algo_status})
        except ProtectiveAbort as exc:
            issues.append(self._issue(exc.decision.lower(), "CRITICAL" if exc.critical else "FAIL", exc.reason))
            journal.recovery_required = bool(exc.recovery or exc.critical)
            self._write_journal(config, journal, "RECOVERY_REQUIRED" if exc.recovery or exc.critical else "FAILED", {"reason": exc.reason})
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "CRITICAL" if exc.critical else "FAIL", exc.decision, exc.reason, credential_metadata=metadata, exchange_filters=filters, position=position, final_position=final_position, preview=preview, stop_order=stop_order, take_profit_order=take_order, final_stop_order=final_stop, final_take_profit_order=final_take, create_requests=create_requests, query_requests=query_requests, cancel_requests=cancel_requests, journal=journal, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase=journal.phase, recovery_required=exc.recovery or exc.critical, unexpected_trigger=exc.critical, unexpected_position_change=exc.decision == "UNEXPECTED_POSITION_CHANGE")
        except Exception as exc:
            message = self._sanitize(str(exc))
            recovery = stop_create_started or take_create_started or cancel_started
            decision = "RECOVERY_REQUIRED" if recovery else "PROTECTIVE_PRECHECK_FAILED"
            issues.append(self._issue("protective_lifecycle_failed", "FAIL", message))
            journal.recovery_required = recovery
            self._write_journal(config, journal, "RECOVERY_REQUIRED" if recovery else "FAILED", {"reason": message})
            return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "FAIL", decision, "Protective lifecycle failed safely.", credential_metadata=metadata, exchange_filters=filters, position=position, final_position=final_position, preview=preview, stop_order=stop_order, take_profit_order=take_order, final_stop_order=final_stop, final_take_profit_order=final_take, create_requests=create_requests, query_requests=query_requests, cancel_requests=cancel_requests, journal=journal, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase=journal.phase, recovery_required=recovery)
        finally:
            self._release_owned_lock(lock_path, lock_token, lock_acquired)
        return self._result(config, "RUN_PROTECTIVE_LIFECYCLE", "PASS", "PROTECTIVE_LIFECYCLE_COMPLETE", "Protective STOP_MARKET and TAKE_PROFIT_MARKET lifecycle completed without changing the position.", credential_metadata=metadata, exchange_filters=filters, position=position, final_position=final_position, preview=preview, stop_order=stop_order, take_profit_order=take_order, final_stop_order=final_stop, final_take_profit_order=final_take, create_requests=create_requests, query_requests=query_requests, cancel_requests=cancel_requests, journal=journal, issues=issues, pair_id=pair_id, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="COMPLETE", lifecycle_complete=True)

    def query_protective_pair(self, stop_client_algo_id: str, take_profit_client_algo_id: str, config_path: str = "configs/binance_futures_testnet_protective_orders.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetProtectiveResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetProtectiveOrdersConfig()
        issues = list(report.issues)
        client = self._client(config)
        metadata = client.inspect_credentials()
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

    def recover_protective_pair(self, stop_client_algo_id: str, take_profit_client_algo_id: str, confirmation: str | None = None, config_path: str = "configs/binance_futures_testnet_protective_orders.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetProtectiveResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetProtectiveOrdersConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "FAIL", "OPERATION_BLOCKED", "Protective config failed validation.", issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        if confirmation != config.recovery_confirmation_phrase:
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "WARNING", "CONFIRMATION_REQUIRED", "Explicit protective recovery confirmation is required.", issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        client = self._client(config)
        metadata = client.inspect_credentials()
        if not metadata.credentials_complete:
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "WARNING", "CREDENTIALS_NOT_CONFIGURED", "Dedicated testnet credentials are incomplete or missing.", credential_metadata=metadata, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id)
        lock_path = self._resolve(config.lock_path)
        lock_token = self._lock_token("recover_protective_pair", "", stop_client_algo_id, take_profit_client_algo_id)
        lock_acquired = self._acquire_owned_lock(lock_path, lock_token)
        if not lock_acquired:
            issues.append(self._issue("protective_lock_exists", "FAIL", "An active protective-order lock already exists."))
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "FAIL", "RECOVERY_REQUIRED", "Existing protective lock blocks exact recovery.", credential_metadata=metadata, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, recovery_required=True)
        journal = self._load_or_new_journal(config, stop_client_algo_id, take_profit_client_algo_id)
        query_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata] = []
        cancel_requests: list[BinanceFuturesTestnetProtectiveRequestMetadata] = []
        stop = take = final_stop = final_take = None
        position = None
        try:
            self._write_journal(config, journal, "RECOVERY_STARTED", {"stop_client_algo_id": stop_client_algo_id, "take_profit_client_algo_id": take_profit_client_algo_id})
            self._server_time_or_issue(client, config, issues)
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
            if take is not None and take.algo_status == "NEW":
                delete_take, meta = client.cancel_algo_order_exact(take_profit_client_algo_id)
                cancel_requests.append(meta)
                self._validate_delete_ack(delete_take, take_profit_client_algo_id)
            final_take, meta = self._query_or_absent(client, take_profit_client_algo_id, journal, "TAKE_PROFIT", after_delete=take is not None and take.algo_status == "NEW")
            if meta is not None:
                query_requests.append(meta)
            if final_take is not None:
                self._validate_recovery_identity(final_take, journal, "TAKE_PROFIT", take_profit_client_algo_id)
                self._check_unexpected_trigger(final_take)
            if stop is not None and stop.algo_status == "NEW":
                delete_stop, meta = client.cancel_algo_order_exact(stop_client_algo_id)
                cancel_requests.append(meta)
                self._validate_delete_ack(delete_stop, stop_client_algo_id)
            final_stop, meta = self._query_or_absent(client, stop_client_algo_id, journal, "STOP", after_delete=stop is not None and stop.algo_status == "NEW")
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
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "PASS", "RECOVERY_COMPLETE", "Protective pair exact recovery completed.", credential_metadata=metadata, position=position, stop_order=stop, take_profit_order=take, final_stop_order=final_stop, final_take_profit_order=final_take, query_requests=query_requests, cancel_requests=cancel_requests, journal=journal, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="RECOVERY_COMPLETE", lifecycle_complete=True)
        except ProtectiveAbort as exc:
            issues.append(self._issue(exc.decision.lower(), "CRITICAL" if exc.critical else "FAIL", exc.reason))
            journal.recovery_required = True
            self._write_journal(config, journal, "RECOVERY_REQUIRED", {"reason": exc.reason})
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "CRITICAL" if exc.critical else "FAIL", exc.decision, exc.reason, credential_metadata=metadata, position=position, stop_order=stop, take_profit_order=take, final_stop_order=final_stop, final_take_profit_order=final_take, query_requests=query_requests, cancel_requests=cancel_requests, journal=journal, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="RECOVERY_REQUIRED", recovery_required=True, unexpected_trigger=exc.critical)
        except Exception as exc:
            message = self._sanitize(str(exc))
            issues.append(self._issue("protective_recovery_failed", "FAIL", message))
            journal.recovery_required = True
            self._write_journal(config, journal, "RECOVERY_REQUIRED", {"reason": message})
            return self._result(config, "RECOVER_PROTECTIVE_PAIR", "FAIL", "RECOVERY_REQUIRED", "Protective pair recovery failed safely.", credential_metadata=metadata, position=position, stop_order=stop, take_profit_order=take, final_stop_order=final_stop, final_take_profit_order=final_take, query_requests=query_requests, cancel_requests=cancel_requests, journal=journal, issues=issues, stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, phase="RECOVERY_REQUIRED", recovery_required=True)
        finally:
            self._release_owned_lock(lock_path, lock_token, lock_acquired)

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
        self._expect(config.request_timeout_seconds == 30 and config.recv_window_ms == 10000 and config.maximum_recv_window_ms == 10000 and config.maximum_clock_skew_ms <= 5000, issues, "timeout_recv_window", "Timeout, recvWindow and clock skew must remain hardened.")
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

    def _server_time_or_issue(self, client: BinanceFuturesTestnetProtectiveOrdersClient, config: BinanceFuturesTestnetProtectiveOrdersConfig, issues: list[BinanceFuturesTestnetProtectiveIssue]) -> None:
        server = client.fetch_server_time()
        if int(server["clock_skew_ms"]) > int(config.maximum_clock_skew_ms):
            raise ProtectiveAbort("PUBLIC_PREFLIGHT_FAILED", "Clock skew exceeds protective maximum.")
        client.set_server_time_offset(int(server["server_time"]), int(server["local_time"]))

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
                if self._journal_confirms_created(journal, label) and not after_delete:
                    raise ProtectiveAbort("RECOVERY_REQUIRED", f"{label} was journal-confirmed but exact query returned absent.", recovery=True) from exc
                return None, None
            raise

    def _journal_confirms_created(self, journal: BinanceFuturesTestnetProtectiveJournal, label: str) -> bool:
        phases = {"STOP": {"STOP_CREATED", "STOP_QUERY_COMPLETE"}, "TAKE_PROFIT": {"TAKE_PROFIT_CREATED", "TAKE_PROFIT_QUERY_COMPLETE"}}[label]
        return any(str(entry.get("phase")) in phases for entry in journal.entries)

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
        path = self._resolve(config.journal_path)
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("stop_client_algo_id") == stop_client_algo_id and payload.get("take_profit_client_algo_id") == take_profit_client_algo_id:
                    return BinanceFuturesTestnetProtectiveJournal(
                        pair_id=str(payload.get("pair_id") or ""),
                        stop_client_algo_id=stop_client_algo_id,
                        take_profit_client_algo_id=take_profit_client_algo_id,
                        phase=str(payload.get("phase") or "RECOVERY_REQUIRED"),
                        recovery_required=bool(payload.get("recovery_required", True)),
                        baseline_available=bool(payload.get("baseline_available", False)),
                        baseline_position_amount=None if payload.get("baseline_position_amount") is None else self._decimal(payload.get("baseline_position_amount")),
                        baseline_position_direction=payload.get("baseline_position_direction"),
                        stop_trigger=None if payload.get("stop_trigger") is None else self._decimal(payload.get("stop_trigger")),
                        take_profit_trigger=None if payload.get("take_profit_trigger") is None else self._decimal(payload.get("take_profit_trigger")),
                        entries=list(payload.get("entries") or []),
                    )
            except Exception:
                pass
        return BinanceFuturesTestnetProtectiveJournal(stop_client_algo_id=stop_client_algo_id, take_profit_client_algo_id=take_profit_client_algo_id, recovery_required=True, entries=[{"created_at": self._now(), "phase": "RECOVERY_STARTED", "details": {"baseline_available": False}}])

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

    def _write_journal(self, config: BinanceFuturesTestnetProtectiveOrdersConfig, journal: BinanceFuturesTestnetProtectiveJournal, phase: str, details: dict[str, Any]) -> None:
        if not config.allow_sanitized_local_journal:
            return
        journal.phase = phase
        journal.entries.append({"created_at": self._now(), "phase": phase, "details": details})
        path = self._resolve(config.journal_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(journal.to_dict(), indent=2), encoding="utf-8")
        temp.replace(path)

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
