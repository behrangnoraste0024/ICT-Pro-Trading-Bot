from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from engine.diagnostics.binance_futures_testnet_adapter_engine import BinanceFuturesTestnetAdapterEngine
from engine.diagnostics.binance_futures_testnet_read_only_engine import BinanceFuturesTestnetReadOnlyEngine
from engine.diagnostics.btc_futures_paper_position_engine import BTCFuturesPaperPositionEngine
from engine.diagnostics.btc_futures_read_only_feed_engine import BTCFuturesReadOnlyFeedEngine
from engine.diagnostics.btc_futures_risk_model_engine import BTCFuturesRiskModelEngine
from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine
from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from infrastructure.exchanges.binance_futures_testnet_order_test_client import (
    BinanceFuturesTestnetOrderOperationBlocked,
    BinanceFuturesTestnetOrderTestClient,
    BinanceFuturesTestnetOrderTestResponseShapeError,
)
from infrastructure.persistence.live_execution_authorization_policy import LiveExecutionAuthorizationPolicy
from infrastructure.security.live_execution_mutation_fingerprint_adapter import build_signed_order_test_create_from_final_request
from infrastructure.security.live_execution_permit_gate import LiveExecutionPermitGate
from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit_enforcement import LiveExecutionPermitGateError, LiveExecutionPermitReference
from models.binance_futures_testnet_order_test import (
    BinanceFuturesTestnetExchangeFilterSummary,
    BinanceFuturesTestnetOrderTestAction,
    BinanceFuturesTestnetOrderTestConfig,
    BinanceFuturesTestnetOrderTestCredentialMetadata,
    BinanceFuturesTestnetOrderTestDecision,
    BinanceFuturesTestnetOrderTestIssue,
    BinanceFuturesTestnetOrderTestPreview,
    BinanceFuturesTestnetOrderTestRequestMetadata,
    BinanceFuturesTestnetOrderTestResult,
    BinanceFuturesTestnetOrderTestValidationReport,
    OrderTestReferencePriceSource,
)


class OrderTestAuthorizationAbort(RuntimeError):
    def __init__(self, code: str, message: str, permit_consumed: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.permit_consumed = permit_consumed


class BinanceFuturesTestnetOrderTestEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        runtime_config_engine: BTCPaperRuntimeConfigEngine | None = None,
        monitoring_engine: BTCPaperMonitoringEngine | None = None,
        runner_engine: BTCPaperRunnerEngine | None = None,
        testnet_adapter_engine: BinanceFuturesTestnetAdapterEngine | None = None,
        testnet_read_only_engine: BinanceFuturesTestnetReadOnlyEngine | None = None,
        futures_feed_engine: BTCFuturesReadOnlyFeedEngine | None = None,
        futures_risk_model_engine: BTCFuturesRiskModelEngine | None = None,
        futures_paper_position_engine: BTCFuturesPaperPositionEngine | None = None,
        http_get=None,
        authenticated_post=None,
        env: dict[str, str] | None = None,
        now_ms_provider=None,
        now_provider=None,
        kill_switch_gate=None,
        authorization_policy=None,
        permit_gate=None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.runtime_config_engine = runtime_config_engine or BTCPaperRuntimeConfigEngine(repo_root=self.repo_root)
        self.monitoring_engine = monitoring_engine or BTCPaperMonitoringEngine(repo_root=self.repo_root)
        self.runner_engine = runner_engine or BTCPaperRunnerEngine(repo_root=self.repo_root)
        self.testnet_adapter_engine = testnet_adapter_engine or BinanceFuturesTestnetAdapterEngine(repo_root=self.repo_root, env={})
        self.testnet_read_only_engine = testnet_read_only_engine or BinanceFuturesTestnetReadOnlyEngine(repo_root=self.repo_root, env={})
        self.futures_feed_engine = futures_feed_engine or BTCFuturesReadOnlyFeedEngine(repo_root=self.repo_root)
        self.futures_risk_model_engine = futures_risk_model_engine or BTCFuturesRiskModelEngine(repo_root=self.repo_root)
        self.futures_paper_position_engine = futures_paper_position_engine or BTCFuturesPaperPositionEngine(repo_root=self.repo_root)
        self.http_get = http_get
        self.authenticated_post = authenticated_post
        self.env = {} if env is None else env
        self.now_ms_provider = now_ms_provider
        self.now_provider = now_provider
        self.authorization_policy = authorization_policy or LiveExecutionAuthorizationPolicy(
            repo_root=self.repo_root,
            env=self.env,
            kill_switch_gate=kill_switch_gate,
        )
        self.permit_gate = permit_gate or LiveExecutionPermitGate(
            authorization_policy=self.authorization_policy,
            env=self.env,
        )

    def _require_mutation_permission(self) -> None:
        decision = self.authorization_policy.authorize(
            LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE,
            environment="TESTNET",
            symbol="BTCUSDT",
            confirmation_verified=True,
            credentials_configured=True,
        )
        if not decision.allowed:
            raise OrderTestAuthorizationAbort(decision.code, decision.message)


    @staticmethod
    def _require_present_permit_reference(permit_reference: LiveExecutionPermitReference | None) -> None:
        if permit_reference is None:
            raise OrderTestAuthorizationAbort("PERMIT_REQUIRED", "A durable one-time live execution permit is required.")
        if not isinstance(permit_reference, LiveExecutionPermitReference):
            raise OrderTestAuthorizationAbort("PERMIT_REFERENCE_INVALID", "The live execution permit reference is invalid.")

    def _require_permit_for_mutation(
        self,
        *,
        fingerprint,
        permit_reference: LiveExecutionPermitReference | None,
        config: BinanceFuturesTestnetOrderTestConfig,
    ) -> None:
        try:
            self.permit_gate.authorize_and_consume(
                operation=LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE,
                fingerprint=fingerprint,
                permit_reference=permit_reference,
                confirmation_verified=True,
                credentials_configured=True,
                runtime_config_path=config.runtime_config_path,
            )
        except LiveExecutionPermitGateError as exc:
            raise OrderTestAuthorizationAbort(exc.code, exc.message, permit_consumed=exc.permit_consumed) from None

    def validate(self, config_path: str = "configs/binance_futures_testnet_order_test.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetOrderTestValidationReport:
        issues: list[BinanceFuturesTestnetOrderTestIssue] = []
        diagnostics: dict[str, Any] = {
            "runtime_config_status": "UNKNOWN",
            "monitoring_config_status": "UNKNOWN",
            "runner_config_status": "UNKNOWN",
            "testnet_adapter_config_status": "UNKNOWN",
            "testnet_read_only_config_status": "UNKNOWN",
            "futures_feed_config_status": "UNKNOWN",
            "futures_risk_model_config_status": "UNKNOWN",
            "futures_paper_position_config_status": "UNKNOWN",
            "kill_switch_enabled": None,
            "credentials_inspected": False,
            "network_used": False,
            "test_order_request_transmitted": False,
        }
        config = None
        try:
            config = self.load_config(config_path)
        except Exception as exc:
            issues.append(self._issue("config_invalid", "FAIL", f"Binance futures testnet order-test config could not be loaded: {exc}"))
            return self._report(config_path, config, issues, diagnostics)
        self._validate_config(config, expected_profile, issues, diagnostics)
        return self._report(config_path, config, issues, diagnostics)

    def check_credentials(self, config_path: str = "configs/binance_futures_testnet_order_test.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetOrderTestResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetOrderTestConfig()
        if report.status == "FAIL":
            return self._result(config, BinanceFuturesTestnetOrderTestAction.CHECK_CREDENTIALS.value, "FAIL", BinanceFuturesTestnetOrderTestDecision.ACTUAL_ORDER_OPERATION_BLOCKED.value, "Order-test config failed validation.", issues=list(report.issues))
        metadata = self._client(config).inspect_credentials()
        if metadata.credentials_complete:
            status, decision, reason = "PASS", BinanceFuturesTestnetOrderTestDecision.CREDENTIALS_PRESENT.value, "Dedicated testnet credentials are present."
        elif metadata.api_key_present or metadata.api_secret_present:
            status, decision, reason = "WARNING", BinanceFuturesTestnetOrderTestDecision.CREDENTIALS_INCOMPLETE.value, "Dedicated testnet credentials are incomplete."
        else:
            status, decision, reason = "WARNING", BinanceFuturesTestnetOrderTestDecision.CREDENTIALS_NOT_CONFIGURED.value, "Dedicated testnet credentials are not configured."
        return self._result(config, BinanceFuturesTestnetOrderTestAction.CHECK_CREDENTIALS.value, status, decision, reason, credential_metadata=metadata, issues=list(report.issues), credentials_inspected=True)

    def build_preview(
        self,
        client_order_id: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        time_in_force: str | None = None,
        reduce_only: bool = False,
        config_path: str = "configs/binance_futures_testnet_order_test.json",
        expected_profile: str = "balanced_smc_decision_065",
        exchange_filters: BinanceFuturesTestnetExchangeFilterSummary | None = None,
    ) -> BinanceFuturesTestnetOrderTestResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetOrderTestConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, BinanceFuturesTestnetOrderTestAction.BUILD_PREVIEW.value, "FAIL", BinanceFuturesTestnetOrderTestDecision.ORDER_TEST_PREVIEW_REJECTED.value, "Order-test config failed validation.", issues=issues)
        try:
            preview = self._client(config).build_order_test_preview(client_order_id, side, order_type, quantity, price, time_in_force, reduce_only, exchange_filters=exchange_filters)
        except Exception as exc:
            issues.append(self._issue("order_test_preview_rejected", "FAIL", self._sanitize(str(exc))))
            return self._result(config, BinanceFuturesTestnetOrderTestAction.BUILD_PREVIEW.value, "FAIL", BinanceFuturesTestnetOrderTestDecision.ORDER_TEST_PREVIEW_REJECTED.value, "Local order-test preview was rejected.", issues=issues)
        return self._result(config, BinanceFuturesTestnetOrderTestAction.BUILD_PREVIEW.value, "PASS", BinanceFuturesTestnetOrderTestDecision.ORDER_TEST_PREVIEW_VALID.value, "Local order-test preview is valid and non-executable.", preview=preview, issues=issues)

    def submit_test_order(
        self,
        client_order_id: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        time_in_force: str | None = None,
        reduce_only: bool = False,
        confirmation: str | None = None,
        config_path: str = "configs/binance_futures_testnet_order_test.json",
        expected_profile: str = "balanced_smc_decision_065",
        permit: LiveExecutionPermitReference | None = None,
    ) -> BinanceFuturesTestnetOrderTestResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetOrderTestConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, BinanceFuturesTestnetOrderTestAction.SUBMIT_TEST_ORDER.value, "FAIL", BinanceFuturesTestnetOrderTestDecision.ACTUAL_ORDER_OPERATION_BLOCKED.value, "Order-test config failed validation.", issues=issues)
        if config.require_explicit_network_confirmation and confirmation != config.network_confirmation_phrase:
            return self._result(config, BinanceFuturesTestnetOrderTestAction.SUBMIT_TEST_ORDER.value, "WARNING", BinanceFuturesTestnetOrderTestDecision.NETWORK_CONFIRMATION_REQUIRED.value, "Explicit testnet order-test confirmation is required.", issues=issues)
        try:
            self._require_present_permit_reference(permit)
        except OrderTestAuthorizationAbort as exc:
            issues.append(self._issue(exc.code.lower(), "FAIL", exc.message))
            return self._result(config, BinanceFuturesTestnetOrderTestAction.SUBMIT_TEST_ORDER.value, "FAIL", exc.code, exc.message, issues=issues)
        client = self._client(config)
        try:
            metadata = client.inspect_credentials()
        except Exception:
            return self._result(config, BinanceFuturesTestnetOrderTestAction.SUBMIT_TEST_ORDER.value, "FAIL", "CREDENTIALS_UNAVAILABLE", "Testnet credential readiness is unavailable.", issues=issues)
        if not metadata.credentials_complete:
            decision = BinanceFuturesTestnetOrderTestDecision.CREDENTIALS_INCOMPLETE.value if metadata.api_key_present or metadata.api_secret_present else BinanceFuturesTestnetOrderTestDecision.CREDENTIALS_NOT_CONFIGURED.value
            return self._result(config, BinanceFuturesTestnetOrderTestAction.SUBMIT_TEST_ORDER.value, "WARNING", decision, "Dedicated testnet credentials are incomplete or missing.", credential_metadata=metadata, issues=issues, credentials_inspected=True)
        try:
            self._require_mutation_permission()
            filters = client.fetch_exchange_filters()
            mark_price = client.fetch_mark_price(config.exchange_symbol) if str(order_type).upper() == "MARKET" else None
            preview = client.build_order_test_preview(client_order_id, side, order_type, quantity, price, time_in_force, reduce_only, exchange_filters=filters, mark_price=mark_price)
            server = self._server_time_or_issue(client, config, issues)
            unsigned_request = client.build_unsigned_business_request(preview)
            fingerprint = build_signed_order_test_create_from_final_request(unsigned_request)
            self._require_permit_for_mutation(fingerprint=fingerprint, permit_reference=permit, config=config)
            request_metadata = client.submit_test_order(preview, server, unsigned_business_request=unsigned_request)
        except OrderTestAuthorizationAbort as exc:
            issues.append(self._issue(exc.code.lower(), "FAIL", exc.message))
            return self._result(config, BinanceFuturesTestnetOrderTestAction.SUBMIT_TEST_ORDER.value, "FAIL", exc.code, exc.message, credential_metadata=metadata, issues=issues, credentials_inspected=True)
        except BinanceFuturesTestnetOrderTestResponseShapeError as exc:
            request_metadata = exc.metadata
            details = {
                "http_status_code": request_metadata.response_status_code,
                "http_method": request_metadata.method,
                "final_allowed_host": request_metadata.host if request_metadata.final_host_validated else None,
                "allowed_path": request_metadata.path,
                "request_transmitted": request_metadata.request_transmitted,
                "response_received": request_metadata.response_received,
                "retry_count": request_metadata.retry_count,
                "body_type": request_metadata.response_body_type,
                "byte_count_category": request_metadata.response_byte_count_category,
                "content_type_category": request_metadata.response_content_type_category,
                "binance_error_code": request_metadata.binance_error_code,
                "binance_error_message": request_metadata.binance_error_message,
            }
            issues.append(self._issue("order_test_response_shape_invalid", "FAIL", self._sanitize(str(exc)), details))
            return self._result(config, BinanceFuturesTestnetOrderTestAction.SUBMIT_TEST_ORDER.value, "FAIL", BinanceFuturesTestnetOrderTestDecision.ORDER_TEST_REJECTED.value, "Test Order request failed safely.", credential_metadata=metadata, request_metadata=request_metadata, issues=issues, credentials_inspected=True, public_server_time_request_used=True, public_exchange_info_request_used=True, signature_generated=True, authenticated_transport_invoked=True, test_order_request_transmitted=True, authenticated_test_request_used=True)
        except Exception as exc:
            issues.append(self._issue("order_test_request_failed", "FAIL", self._sanitize(str(exc))))
            return self._result(config, BinanceFuturesTestnetOrderTestAction.SUBMIT_TEST_ORDER.value, "FAIL", BinanceFuturesTestnetOrderTestDecision.ORDER_TEST_REJECTED.value, "Test Order request failed safely.", credential_metadata=metadata, issues=issues, credentials_inspected=True, public_exchange_info_request_used=True)
        return self._result(
            config,
            BinanceFuturesTestnetOrderTestAction.SUBMIT_TEST_ORDER.value,
            "PASS",
            BinanceFuturesTestnetOrderTestDecision.ORDER_TEST_ACCEPTED.value,
            "Test Order request accepted; parameters validated by Testnet Test Order endpoint.",
            credential_metadata=metadata,
            exchange_filter_summary=filters,
            preview=preview,
            request_metadata=request_metadata,
            issues=issues,
            credentials_inspected=True,
            public_server_time_request_used=True,
            public_exchange_info_request_used=True,
            signature_generated=True,
            authenticated_transport_invoked=True,
            test_order_request_transmitted=True,
            authenticated_test_request_used=True,
        )

    def runner_validate(self, config_path: str = "configs/binance_futures_testnet_order_test.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetOrderTestResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetOrderTestConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, BinanceFuturesTestnetOrderTestAction.RUNNER_VALIDATE.value, "FAIL", BinanceFuturesTestnetOrderTestDecision.ACTUAL_ORDER_OPERATION_BLOCKED.value, "Order-test config failed runner dry-run validation.", issues=issues)
        try:
            preview = self._client(config).build_order_test_preview("smcbot-test-runner-001", "BUY", "MARKET", 0.001)
        except Exception as exc:
            issues.append(self._issue("runner_preview_failed", "FAIL", self._sanitize(str(exc))))
            return self._result(config, BinanceFuturesTestnetOrderTestAction.RUNNER_VALIDATE.value, "FAIL", BinanceFuturesTestnetOrderTestDecision.ORDER_TEST_PREVIEW_REJECTED.value, "Runner local preview failed.", issues=issues)
        return self._result(config, BinanceFuturesTestnetOrderTestAction.RUNNER_VALIDATE.value, "PASS", BinanceFuturesTestnetOrderTestDecision.CONFIG_VALID.value, "Order-test config validates for runner dry-run without credentials or network.", preview=preview, issues=issues)

    def hard_block_diagnostics(self, config_path: str = "configs/binance_futures_testnet_order_test.json") -> BinanceFuturesTestnetOrderTestResult:
        config = self.load_config(config_path)
        client = self._client(config)
        methods = [
            "submit_actual_order",
            "submit_algo_order",
            "cancel_order",
            "modify_order",
            "fetch_order",
            "fetch_open_orders",
            "fetch_trades",
            "change_leverage",
            "change_margin_mode",
            "change_position_mode",
            "change_position_margin",
            "create_listen_key",
            "open_user_stream",
            "open_websocket",
        ]
        blocked: dict[str, str] = {}
        issues: list[BinanceFuturesTestnetOrderTestIssue] = []
        for method in methods:
            try:
                getattr(client, method)()
            except BinanceFuturesTestnetOrderOperationBlocked as exc:
                blocked[method] = str(exc)
            except Exception as exc:
                issues.append(self._issue(f"{method}_unexpected", "FAIL", self._sanitize(str(exc))))
        status = "PASS" if len(blocked) == len(methods) and not issues else "FAIL"
        return self._result(config, BinanceFuturesTestnetOrderTestAction.HARD_BLOCK.value, status, BinanceFuturesTestnetOrderTestDecision.ACTUAL_ORDER_OPERATION_BLOCKED.value, "All actual order, query, stream, leverage and mutation methods are blocked before transport.", payload={"blocked_methods": blocked}, issues=issues)

    def load_config(self, config_path: str = "configs/binance_futures_testnet_order_test.json") -> BinanceFuturesTestnetOrderTestConfig:
        path = self._resolve(config_path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("config JSON must be an object")
        return BinanceFuturesTestnetOrderTestConfig(**{**BinanceFuturesTestnetOrderTestConfig().to_dict(), **loaded})

    def _validate_config(self, config: BinanceFuturesTestnetOrderTestConfig, expected_profile: str, issues: list[BinanceFuturesTestnetOrderTestIssue], diagnostics: dict[str, Any]) -> None:
        expected = {"project_scope": "BTC_ONLY", "symbol": "BTC/USDT", "exchange_symbol": "BTCUSDT", "exchange": "binance", "market_type": "futures", "futures_contract_type": "USDT_PERPETUAL", "strategy_profile": expected_profile}
        for name, value in expected.items():
            self._expect(getattr(config, name) == value, issues, name, f"{name} must be {value}.")
        self._expect(not config.feature_enabled, issues, "feature_enabled", "feature_enabled must remain false.")
        self._expect(not config.automatic_execution_enabled, issues, "automatic_execution_enabled", "automatic execution must remain disabled.")
        self._expect(config.explicit_cli_only, issues, "explicit_cli_only", "order-test access must be explicit CLI only.")
        self._expect(config.testnet_only, issues, "testnet_only", "testnet_only must remain true.")
        self._expect(config.test_order_only, issues, "test_order_only", "only the Test Order endpoint may be used.")
        self._validate_url_and_hosts(config, issues)
        self._expect(config.api_key_env_var == "BINANCE_FUTURES_TESTNET_API_KEY", issues, "api_key_env_var", "Only BINANCE_FUTURES_TESTNET_API_KEY may be used.")
        self._expect(config.api_secret_env_var == "BINANCE_FUTURES_TESTNET_API_SECRET", issues, "api_secret_env_var", "Only BINANCE_FUTURES_TESTNET_API_SECRET may be used.")
        self._expect(config.allowed_http_methods == ["POST"], issues, "allowed_http_methods", "Only POST may be allowlisted.")
        self._expect(config.test_order_path == "/fapi/v1/order/test", issues, "test_order_path", "test_order_path must be /fapi/v1/order/test.")
        self._expect(config.mark_price_path == "/fapi/v1/premiumIndex", issues, "mark_price_path", "mark_price_path must be /fapi/v1/premiumIndex.")
        self._expect(config.market_reference_price_source == OrderTestReferencePriceSource.MARK_PRICE.value, issues, "market_reference_price_source", "MARKET reference price source must be MARK_PRICE.")
        self._expect(config.allowed_authenticated_paths == ["/fapi/v1/order/test"], issues, "allowed_authenticated_paths", "Only /fapi/v1/order/test may be authenticated.")
        forbidden_paths = {"/fapi/v1/order", "/fapi/v1/algoOrder", "/fapi/v1/openOrders", "/fapi/v1/allOrders", "/fapi/v1/userTrades"}
        self._expect(not any(path in forbidden_paths for path in config.allowed_authenticated_paths), issues, "forbidden_authenticated_paths", "Actual order, algo, query and trade paths are forbidden.")
        self._expect(config.require_explicit_network_confirmation, issues, "require_explicit_network_confirmation", "explicit confirmation is required.")
        self._expect(config.network_confirmation_phrase == "CONFIRM_TESTNET_ORDER_TEST", issues, "network_confirmation_phrase", "confirmation phrase must match the safe fixed phrase.")
        self._expect(1 <= int(config.request_timeout_seconds) <= 30, issues, "request_timeout_seconds", "timeout must be between 1 and 30.")
        self._expect(int(config.max_authenticated_retries) == 0, issues, "max_authenticated_retries", "authenticated retries must remain zero.")
        self._expect(0 < int(config.recv_window_ms) <= int(config.maximum_recv_window_ms) <= 10000, issues, "recv_window_ms", "recvWindow must be positive and <= safe maximum.")
        self._expect(0 <= int(config.maximum_clock_skew_ms) <= 5000, issues, "maximum_clock_skew_ms", "clock-skew allowance must be <= 5000ms.")
        self._expect(config.allow_public_server_time_fetch, issues, "allow_public_server_time_fetch", "public server time fetch must be available for explicit test order.")
        self._expect(config.allow_public_exchange_info_fetch, issues, "allow_public_exchange_info_fetch", "public exchangeInfo fetch must be available for filter validation.")
        self._expect(config.allow_local_order_test_preview, issues, "allow_local_order_test_preview", "local order-test preview must be allowed.")
        self._expect(config.allow_explicit_test_order_request, issues, "allow_explicit_test_order_request", "explicit test-order request must be allowed.")
        self._expect(config.require_market_reference_price, issues, "require_market_reference_price", "MARKET orders must require Mark Price reference.")
        self._expect(not config.allow_zero_market_reference_price, issues, "allow_zero_market_reference_price", "zero Mark Price must not be allowed.")
        self._expect(not config.allow_unknown_market_notional, issues, "allow_unknown_market_notional", "unknown MARKET notional must not be allowed.")
        self._expect(not config.allow_unvalidated_exchange_filters_for_transmission, issues, "allow_unvalidated_exchange_filters_for_transmission", "unvalidated filters must not be allowed for transmission.")
        self._expect(config.require_exchange_filters_before_transmission, issues, "require_exchange_filters_before_transmission", "exchange filters must be required before transmission.")
        self._expect(config.allowed_order_types == ["MARKET", "LIMIT"], issues, "allowed_order_types", "Only MARKET and LIMIT order types may be used.")
        self._expect(config.allowed_sides == ["BUY", "SELL"], issues, "allowed_sides", "Only BUY and SELL sides may be used.")
        self._expect(config.default_time_in_force == "GTC", issues, "default_time_in_force", "default time-in-force must remain GTC.")
        self._expect(config.allowed_time_in_force == ["GTC", "IOC", "FOK"], issues, "allowed_time_in_force", "Only GTC, IOC and FOK are allowed.")
        self._expect(0 < float(config.maximum_quantity) <= 0.01, issues, "maximum_quantity", "maximum quantity must be positive and <= 0.01.")
        self._expect(0 < float(config.maximum_test_notional_usdt) <= 100.0, issues, "maximum_test_notional_usdt", "maximum test notional must be positive and <= 100 USDT.")
        self._expect(config.require_exchange_filter_validation, issues, "require_exchange_filter_validation", "exchange filter validation must be required.")
        self._expect(config.require_unique_client_order_id, issues, "require_unique_client_order_id", "client order ID must be required.")
        self._expect(config.client_order_id_prefix == "smcbot-test-", issues, "client_order_id_prefix", "client order ID prefix must be smcbot-test-.")
        self._expect(1 <= int(config.maximum_client_order_id_length) <= 36, issues, "maximum_client_order_id_length", "client order ID maximum length must be <= 36.")
        self._expect(config.allow_reduce_only, issues, "allow_reduce_only", "reduceOnly may remain available for safe test order requests.")
        for name in self._must_be_false_fields():
            self._expect(not bool(getattr(config, name)), issues, name, f"{name} must remain false.")
        self._validate_report_dir(config.report_export_dir, issues)
        self._validate_dependencies(config, expected_profile, issues, diagnostics)

    def _must_be_false_fields(self) -> tuple[str, ...]:
        return (
            "allow_close_position", "allow_position_side", "allow_actual_order_submission", "allow_order_cancellation", "allow_order_modification",
            "allow_order_query", "allow_open_order_query", "allow_trade_query", "allow_income_query", "allow_conditional_order", "allow_algo_order",
            "allow_position_creation", "allow_position_close", "allow_leverage_change", "allow_margin_mode_change", "allow_position_mode_change",
            "allow_multi_assets_mode_change", "allow_position_margin_change", "allow_user_data_stream", "allow_listen_key", "allow_websocket_connection",
            "allow_production_endpoint", "allow_production_credentials", "allow_real_funds", "allow_raw_request_print", "allow_raw_response_print",
            "allow_raw_request_persistence", "allow_raw_response_persistence", "allow_authenticated_header_logging", "allow_signature_logging",
            "allow_signed_url_logging", "allow_futures_paper_state_mutation", "allow_spot_paper_account_state_mutation", "allow_runner_state_mutation",
            "allow_execution_state_mutation", "allow_exchange_state_mutation",
        )

    def _validate_url_and_hosts(self, config: BinanceFuturesTestnetOrderTestConfig, issues: list[BinanceFuturesTestnetOrderTestIssue]) -> None:
        try:
            BinanceFuturesTestnetOrderTestClient(config, env={})
        except Exception as exc:
            issues.append(self._issue("rest_base_url", "FAIL", str(exc)))
        self._expect(config.allowed_hosts == ["demo-fapi.binance.com"], issues, "allowed_hosts", "allowed_hosts must contain only demo-fapi.binance.com.")
        self._expect((urlparse(config.rest_base_url).hostname or "") == "demo-fapi.binance.com", issues, "rest_base_url_host", "REST host must be demo-fapi.binance.com.")

    def _validate_dependencies(self, config: BinanceFuturesTestnetOrderTestConfig, expected_profile: str, issues: list[BinanceFuturesTestnetOrderTestIssue], diagnostics: dict[str, Any]) -> None:
        runtime = self.runtime_config_engine.validate(config.runtime_config_path, expected_profile=expected_profile)
        diagnostics["runtime_config_status"] = runtime.status
        diagnostics["kill_switch_enabled"] = bool(getattr(runtime.config, "kill_switch_enabled", False))
        if config.require_runtime_config_pass and runtime.status != "PASS":
            issues.append(self._issue("runtime_config_validation", "FAIL", "Runtime config must validate PASS."))
        if runtime.config is not None and config.require_kill_switch_enabled:
            self._expect(runtime.config.kill_switch_enabled, issues, "kill_switch_enabled", "kill_switch_enabled must remain true.")
        monitoring = self.monitoring_engine.validate(config.monitoring_config_path, expected_profile=expected_profile)
        diagnostics["monitoring_config_status"] = monitoring.status
        if config.require_monitoring_config_pass and monitoring.status != "PASS":
            issues.append(self._issue("monitoring_config_validation", "FAIL", "Monitoring config must validate PASS."))
        _, runner_issues, _ = self.runner_engine.validate_config(config.runner_config_path, expected_profile=expected_profile)
        diagnostics["runner_config_status"] = "FAIL" if any(issue.severity == "FAIL" for issue in runner_issues) else "PASS"
        if config.require_runner_config_pass and diagnostics["runner_config_status"] != "PASS":
            issues.append(self._issue("runner_config_validation", "FAIL", "Runner config must validate PASS."))
        adapter = self.testnet_adapter_engine.validate(config.testnet_adapter_config_path, expected_profile=expected_profile)
        diagnostics["testnet_adapter_config_status"] = adapter.status
        if config.require_testnet_adapter_config_pass and adapter.status != "PASS":
            issues.append(self._issue("testnet_adapter_config_validation", "FAIL", "2.77 testnet adapter config must validate PASS."))
        read_only = self.testnet_read_only_engine.validate(config.testnet_read_only_config_path, expected_profile=expected_profile)
        diagnostics["testnet_read_only_config_status"] = read_only.status
        if config.require_testnet_read_only_config_pass and read_only.status != "PASS":
            issues.append(self._issue("testnet_read_only_config_validation", "FAIL", "2.78 read-only config must validate PASS."))
        feed = self.futures_feed_engine.validate(config.futures_feed_config_path, expected_profile=expected_profile)
        diagnostics["futures_feed_config_status"] = feed.status
        if config.require_futures_feed_config_pass and feed.status != "PASS":
            issues.append(self._issue("futures_feed_config_validation", "FAIL", "Futures read-only feed config must validate PASS."))
        risk = self.futures_risk_model_engine.validate(config.futures_risk_model_config_path, expected_profile=expected_profile)
        diagnostics["futures_risk_model_config_status"] = risk.status
        if config.require_futures_risk_model_config_pass and risk.status != "PASS":
            issues.append(self._issue("futures_risk_model_config_validation", "FAIL", "Futures risk model config must validate PASS."))
        paper = self.futures_paper_position_engine.validate(config.futures_paper_position_config_path, expected_profile=expected_profile)
        diagnostics["futures_paper_position_config_status"] = paper.status
        if config.require_futures_paper_position_config_pass and paper.status != "PASS":
            issues.append(self._issue("futures_paper_position_config_validation", "FAIL", "Futures paper position config must validate PASS."))

    def _server_time_or_issue(self, client: BinanceFuturesTestnetOrderTestClient, config: BinanceFuturesTestnetOrderTestConfig, issues: list[BinanceFuturesTestnetOrderTestIssue]) -> int:
        if not config.allow_public_server_time_fetch:
            raise RuntimeError("server time fetch is disabled")
        payload = client.fetch_server_time()
        skew = int(payload["clock_skew_ms"])
        if skew > int(config.maximum_clock_skew_ms):
            issues.append(self._issue("clock_skew_exceeded", "FAIL", "Testnet server-time skew exceeded safe maximum.", {"clock_skew_ms": skew}))
            raise RuntimeError("clock skew exceeded")
        return int(payload["server_time"])

    def _client(self, config: BinanceFuturesTestnetOrderTestConfig) -> BinanceFuturesTestnetOrderTestClient:
        return BinanceFuturesTestnetOrderTestClient(config, http_get=self.http_get, authenticated_post=self.authenticated_post, env=self.env, now_ms_provider=self.now_ms_provider)

    def _result(
        self,
        config: BinanceFuturesTestnetOrderTestConfig,
        action: str,
        status: str,
        decision: str,
        reason: str,
        credential_metadata: BinanceFuturesTestnetOrderTestCredentialMetadata | None = None,
        exchange_filter_summary: BinanceFuturesTestnetExchangeFilterSummary | None = None,
        preview: BinanceFuturesTestnetOrderTestPreview | None = None,
        request_metadata: BinanceFuturesTestnetOrderTestRequestMetadata | None = None,
        payload: dict[str, Any] | None = None,
        issues: list[BinanceFuturesTestnetOrderTestIssue] | None = None,
        **flags,
    ) -> BinanceFuturesTestnetOrderTestResult:
        safety = self._safety_summary(flags)
        return BinanceFuturesTestnetOrderTestResult(
            created_at=self._now(),
            action=action,
            status=status,
            decision=decision,
            reason=reason,
            credential_metadata=credential_metadata,
            exchange_filter_summary=exchange_filter_summary,
            preview=preview,
            request_metadata=request_metadata,
            payload=payload or {},
            issues=issues or [],
            safety_summary=safety,
            **flags,
        )

    def _safety_summary(self, flags: dict[str, Any] | None = None) -> dict[str, Any]:
        flags = flags or {}
        safe = {name: False for name in (
            "test_order_request_transmitted", "authenticated_test_request_used", "actual_order_submitted", "actual_order_endpoint_used",
            "matching_engine_submission", "exchange_order_created", "order_cancelled", "order_modified", "position_created", "position_closed",
            "leverage_changed", "margin_mode_changed", "conditional_order_created", "algo_order_created", "production_endpoint_used",
            "futures_paper_state_mutated", "spot_paper_account_state_mutated", "runner_state_mutated", "execution_state_mutated",
            "exchange_state_mutated", "api_key_exposed", "api_secret_exposed", "signature_exposed", "signed_url_exposed",
            "authenticated_headers_exposed", "raw_request_printed", "raw_response_printed", "raw_request_persisted", "raw_response_persisted",
        )}
        safe.update({
            "credentials_inspected": bool(flags.get("credentials_inspected", False)),
            "public_server_time_request_used": bool(flags.get("public_server_time_request_used", False)),
            "public_exchange_info_request_used": bool(flags.get("public_exchange_info_request_used", False)),
            "signature_generated": bool(flags.get("signature_generated", False)),
            "authenticated_transport_invoked": bool(flags.get("authenticated_transport_invoked", False)),
            "test_order_request_transmitted": bool(flags.get("test_order_request_transmitted", False)),
            "authenticated_test_request_used": bool(flags.get("authenticated_test_request_used", False)),
        })
        return safe

    def _report(self, config_path: str, config: BinanceFuturesTestnetOrderTestConfig | None, issues: list[BinanceFuturesTestnetOrderTestIssue], diagnostics: dict[str, Any]) -> BinanceFuturesTestnetOrderTestValidationReport:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        return BinanceFuturesTestnetOrderTestValidationReport(config_path=config_path, created_at=self._now(), status="FAIL" if failures else "WARNING" if warnings else "PASS", issue_count=len(issues), warning_count=warnings, fail_count=failures, config=config, issues=issues, diagnostics=diagnostics)

    def _validate_report_dir(self, value: str, issues: list[BinanceFuturesTestnetOrderTestIssue]) -> None:
        path = Path(value)
        self._expect(not path.is_absolute() and ".." not in path.parts and len(path.parts) >= 2 and path.parts[0] == "reports" and path.parts[1] == "binance_futures_testnet_order_test", issues, "report_export_dir", "report_export_dir must be under reports/binance_futures_testnet_order_test.")

    def _expect(self, condition: bool, issues: list[BinanceFuturesTestnetOrderTestIssue], name: str, message: str) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message))

    def _issue(self, name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> BinanceFuturesTestnetOrderTestIssue:
        return BinanceFuturesTestnetOrderTestIssue(name=name, severity=severity, message=message, details=details or {})

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
                return "redacted authenticated test order error"
        return text[:180]
