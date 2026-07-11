from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from engine.diagnostics.binance_futures_testnet_adapter_engine import BinanceFuturesTestnetAdapterEngine
from engine.diagnostics.btc_futures_paper_position_engine import BTCFuturesPaperPositionEngine
from engine.diagnostics.btc_futures_read_only_feed_engine import BTCFuturesReadOnlyFeedEngine
from engine.diagnostics.btc_futures_risk_model_engine import BTCFuturesRiskModelEngine
from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine
from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from infrastructure.exchanges.binance_futures_testnet_read_only_client import (
    BinanceFuturesTestnetReadOnlyClient,
    BinanceFuturesTestnetReadOnlyOperationBlocked,
)
from models.binance_futures_testnet_read_only import (
    BinanceFuturesTestnetAccountSummary,
    BinanceFuturesTestnetAuthenticatedRequestMetadata,
    BinanceFuturesTestnetBalanceSummary,
    BinanceFuturesTestnetCredentialMetadata,
    BinanceFuturesTestnetPositionSummary,
    BinanceFuturesTestnetReadOnlyAction,
    BinanceFuturesTestnetReadOnlyConfig,
    BinanceFuturesTestnetReadOnlyDecision,
    BinanceFuturesTestnetReadOnlyIssue,
    BinanceFuturesTestnetReadOnlyResult,
    BinanceFuturesTestnetReadOnlyValidationReport,
)


class BinanceFuturesTestnetReadOnlyEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        runtime_config_engine: BTCPaperRuntimeConfigEngine | None = None,
        monitoring_engine: BTCPaperMonitoringEngine | None = None,
        runner_engine: BTCPaperRunnerEngine | None = None,
        testnet_adapter_engine: BinanceFuturesTestnetAdapterEngine | None = None,
        futures_feed_engine: BTCFuturesReadOnlyFeedEngine | None = None,
        futures_risk_model_engine: BTCFuturesRiskModelEngine | None = None,
        futures_paper_position_engine: BTCFuturesPaperPositionEngine | None = None,
        http_get=None,
        authenticated_get=None,
        env: dict[str, str] | None = None,
        now_ms_provider=None,
        now_provider=None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.runtime_config_engine = runtime_config_engine or BTCPaperRuntimeConfigEngine(repo_root=self.repo_root)
        self.monitoring_engine = monitoring_engine or BTCPaperMonitoringEngine(repo_root=self.repo_root)
        self.runner_engine = runner_engine or BTCPaperRunnerEngine(repo_root=self.repo_root)
        self.testnet_adapter_engine = testnet_adapter_engine or BinanceFuturesTestnetAdapterEngine(repo_root=self.repo_root, env={})
        self.futures_feed_engine = futures_feed_engine or BTCFuturesReadOnlyFeedEngine(repo_root=self.repo_root)
        self.futures_risk_model_engine = futures_risk_model_engine or BTCFuturesRiskModelEngine(repo_root=self.repo_root)
        self.futures_paper_position_engine = futures_paper_position_engine or BTCFuturesPaperPositionEngine(repo_root=self.repo_root)
        self.http_get = http_get
        self.authenticated_get = authenticated_get
        self.env = {} if env is None else env
        self.now_ms_provider = now_ms_provider
        self.now_provider = now_provider

    def validate(self, config_path: str = "configs/binance_futures_testnet_read_only.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetReadOnlyValidationReport:
        issues: list[BinanceFuturesTestnetReadOnlyIssue] = []
        diagnostics: dict[str, Any] = {
            "runtime_config_status": "UNKNOWN",
            "monitoring_config_status": "UNKNOWN",
            "runner_config_status": "UNKNOWN",
            "testnet_adapter_config_status": "UNKNOWN",
            "futures_feed_config_status": "UNKNOWN",
            "futures_risk_model_config_status": "UNKNOWN",
            "futures_paper_position_config_status": "UNKNOWN",
            "kill_switch_enabled": None,
            "credentials_inspected": False,
            "network_used": False,
        }
        config = None
        try:
            config = self.load_config(config_path)
        except Exception as exc:
            issues.append(self._issue("config_invalid", "FAIL", f"Binance futures testnet read-only config could not be loaded: {exc}"))
            return self._report(config_path, config, issues, diagnostics)
        self._validate_config(config, expected_profile, issues, diagnostics)
        return self._report(config_path, config, issues, diagnostics)

    def check_credentials(self, config_path: str = "configs/binance_futures_testnet_read_only.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetReadOnlyResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetReadOnlyConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, BinanceFuturesTestnetReadOnlyAction.CHECK_CREDENTIALS.value, "FAIL", BinanceFuturesTestnetReadOnlyDecision.OPERATION_BLOCKED.value, "Read-only config failed validation.", issues=issues)
        metadata = self._client(config).inspect_credential_presence()
        if metadata.credentials_complete:
            status, decision, reason = "PASS", BinanceFuturesTestnetReadOnlyDecision.CREDENTIALS_PRESENT.value, "Dedicated testnet credentials are present."
        elif metadata.api_key_present or metadata.api_secret_present:
            status, decision, reason = "WARNING", BinanceFuturesTestnetReadOnlyDecision.CREDENTIALS_INCOMPLETE.value, "Dedicated testnet credentials are incomplete."
        else:
            status, decision, reason = "WARNING", BinanceFuturesTestnetReadOnlyDecision.CREDENTIALS_NOT_CONFIGURED.value, "Dedicated testnet credentials are not configured."
        return self._result(config, BinanceFuturesTestnetReadOnlyAction.CHECK_CREDENTIALS.value, status, decision, reason, credential_metadata=metadata, issues=issues, credentials_inspected=True)

    def fetch_account(self, confirmation: str | None = None, config_path: str = "configs/binance_futures_testnet_read_only.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetReadOnlyResult:
        return self._confirmed_read(
            BinanceFuturesTestnetReadOnlyAction.FETCH_ACCOUNT.value,
            BinanceFuturesTestnetReadOnlyDecision.ACCOUNT_READ_SUCCESS.value,
            "Authenticated read-only account summary fetched.",
            confirmation,
            config_path,
            expected_profile,
            lambda client, server_time: client.fetch_account(server_time),
            account_read=True,
        )

    def fetch_balance(self, asset: str = "USDT", confirmation: str | None = None, config_path: str = "configs/binance_futures_testnet_read_only.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetReadOnlyResult:
        return self._confirmed_read(
            BinanceFuturesTestnetReadOnlyAction.FETCH_BALANCE.value,
            BinanceFuturesTestnetReadOnlyDecision.BALANCE_READ_SUCCESS.value,
            "Authenticated read-only USDT balance fetched.",
            confirmation,
            config_path,
            expected_profile,
            lambda client, server_time: client.fetch_balance(asset, server_time),
            balance_read=True,
        )

    def fetch_position_risk(self, symbol: str = "BTCUSDT", confirmation: str | None = None, config_path: str = "configs/binance_futures_testnet_read_only.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetReadOnlyResult:
        return self._confirmed_read(
            BinanceFuturesTestnetReadOnlyAction.FETCH_POSITION_RISK.value,
            BinanceFuturesTestnetReadOnlyDecision.POSITION_READ_SUCCESS.value,
            "Authenticated read-only BTCUSDT position risk fetched.",
            confirmation,
            config_path,
            expected_profile,
            lambda client, server_time: client.fetch_position_risk(symbol, server_time),
            position_read=True,
        )

    def fetch_account_snapshot(self, confirmation: str | None = None, config_path: str = "configs/binance_futures_testnet_read_only.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetReadOnlyResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetReadOnlyConfig()
        issues = list(report.issues)
        guard = self._preflight(config, report, confirmation, BinanceFuturesTestnetReadOnlyAction.FETCH_ACCOUNT_SNAPSHOT.value, issues)
        if guard is not None:
            return guard
        client = self._client(config)
        metadata = client.inspect_credential_presence()
        try:
            server = self._server_time_or_issue(client, config, issues)
            account, account_meta = client.fetch_account(server)
            balance, balance_meta = client.fetch_balance(config.balance_asset_filter, server)
            position, position_meta = client.fetch_position_risk(config.position_symbol_filter, server)
        except Exception as exc:
            issues.append(self._issue("snapshot_failed", "FAIL", self._sanitize(str(exc))))
            return self._result(config, BinanceFuturesTestnetReadOnlyAction.FETCH_ACCOUNT_SNAPSHOT.value, "FAIL", BinanceFuturesTestnetReadOnlyDecision.AUTHORIZED_READ_ONLY_REQUEST_FAILED.value, "Combined account snapshot failed safely.", credential_metadata=metadata, issues=issues, public_server_time_request_used=True, credentials_inspected=True)
        request_metadata = self._merge_metadata(account_meta, balance_meta, position_meta)
        return self._result(
            config,
            BinanceFuturesTestnetReadOnlyAction.FETCH_ACCOUNT_SNAPSHOT.value,
            "PASS",
            BinanceFuturesTestnetReadOnlyDecision.ACCOUNT_SNAPSHOT_SUCCESS.value,
            "Combined authenticated read-only account snapshot fetched.",
            credential_metadata=metadata,
            request_metadata=request_metadata,
            account_summary=account,
            balance_summary=balance,
            position_summary=position,
            payload={"snapshot_complete": True},
            issues=issues,
            public_server_time_request_used=True,
            credentials_inspected=True,
            signature_generated=True,
            authenticated_transport_invoked=True,
            authenticated_testnet_request_used=True,
            authenticated_account_read_used=True,
            authenticated_balance_read_used=True,
            authenticated_position_read_used=True,
            request_transmitted=True,
            api_key_header_used=True,
        )

    def runner_validate(self, config_path: str = "configs/binance_futures_testnet_read_only.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetReadOnlyResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetReadOnlyConfig()
        status = "PASS" if report.status == "PASS" else "FAIL"
        decision = BinanceFuturesTestnetReadOnlyDecision.CONFIG_VALID.value if report.status == "PASS" else BinanceFuturesTestnetReadOnlyDecision.OPERATION_BLOCKED.value
        reason = "Read-only config validates for runner dry-run without credentials or network." if report.status == "PASS" else "Read-only config failed runner dry-run validation."
        return self._result(config, BinanceFuturesTestnetReadOnlyAction.RUNNER_VALIDATE.value, status, decision, reason, issues=list(report.issues))

    def hard_block_diagnostics(self, config_path: str = "configs/binance_futures_testnet_read_only.json") -> BinanceFuturesTestnetReadOnlyResult:
        config = self.load_config(config_path)
        client = self._client(config)
        methods = [
            "submit_order",
            "test_submit_order",
            "cancel_order",
            "modify_order",
            "fetch_open_orders",
            "fetch_all_orders",
            "fetch_trades",
            "fetch_income",
            "change_leverage",
            "change_margin_mode",
            "change_position_mode",
            "change_multi_assets_mode",
            "change_position_margin",
            "create_listen_key",
            "open_user_stream",
            "open_websocket",
        ]
        issues: list[BinanceFuturesTestnetReadOnlyIssue] = []
        blocked: dict[str, str] = {}
        for method in methods:
            try:
                getattr(client, method)()
            except BinanceFuturesTestnetReadOnlyOperationBlocked as exc:
                blocked[method] = str(exc)
            except Exception as exc:
                issues.append(self._issue(f"{method}_unexpected", "FAIL", str(exc)))
        status = "PASS" if len(blocked) == len(methods) and not issues else "FAIL"
        return self._result(config, BinanceFuturesTestnetReadOnlyAction.HARD_BLOCK.value, status, BinanceFuturesTestnetReadOnlyDecision.OPERATION_BLOCKED.value, "All order, trade, stream, leverage and mutation methods are blocked before transport.", payload={"blocked_methods": blocked}, issues=issues)

    def load_config(self, config_path: str = "configs/binance_futures_testnet_read_only.json") -> BinanceFuturesTestnetReadOnlyConfig:
        path = self._resolve(config_path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("config JSON must be an object")
        return BinanceFuturesTestnetReadOnlyConfig(**{**BinanceFuturesTestnetReadOnlyConfig().to_dict(), **loaded})

    def _confirmed_read(self, action: str, success_decision: str, success_reason: str, confirmation: str | None, config_path: str, expected_profile: str, callback, account_read: bool = False, balance_read: bool = False, position_read: bool = False) -> BinanceFuturesTestnetReadOnlyResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetReadOnlyConfig()
        issues = list(report.issues)
        guard = self._preflight(config, report, confirmation, action, issues)
        if guard is not None:
            return guard
        client = self._client(config)
        metadata = client.inspect_credential_presence()
        try:
            server = self._server_time_or_issue(client, config, issues)
            parsed, request_metadata = callback(client, server)
        except Exception as exc:
            issues.append(self._issue("authenticated_read_failed", "FAIL", self._sanitize(str(exc))))
            return self._result(config, action, "FAIL", BinanceFuturesTestnetReadOnlyDecision.AUTHORIZED_READ_ONLY_REQUEST_FAILED.value, "Authenticated read-only request failed safely.", credential_metadata=metadata, issues=issues, public_server_time_request_used=True, credentials_inspected=True)
        return self._result(
            config,
            action,
            "PASS",
            success_decision,
            success_reason,
            credential_metadata=metadata,
            request_metadata=request_metadata,
            account_summary=parsed if isinstance(parsed, BinanceFuturesTestnetAccountSummary) else None,
            balance_summary=parsed if isinstance(parsed, BinanceFuturesTestnetBalanceSummary) else None,
            position_summary=parsed if isinstance(parsed, BinanceFuturesTestnetPositionSummary) else None,
            issues=issues,
            public_server_time_request_used=True,
            credentials_inspected=True,
            signature_generated=True,
            authenticated_transport_invoked=True,
            authenticated_testnet_request_used=True,
            authenticated_account_read_used=account_read,
            authenticated_balance_read_used=balance_read,
            authenticated_position_read_used=position_read,
            request_transmitted=True,
            api_key_header_used=True,
        )

    def _preflight(self, config: BinanceFuturesTestnetReadOnlyConfig, report: BinanceFuturesTestnetReadOnlyValidationReport, confirmation: str | None, action: str, issues: list[BinanceFuturesTestnetReadOnlyIssue]) -> BinanceFuturesTestnetReadOnlyResult | None:
        if report.status == "FAIL":
            return self._result(config, action, "FAIL", BinanceFuturesTestnetReadOnlyDecision.OPERATION_BLOCKED.value, "Read-only config failed validation.", issues=issues)
        if config.require_explicit_network_confirmation and confirmation != config.network_confirmation_phrase:
            return self._result(config, action, "WARNING", BinanceFuturesTestnetReadOnlyDecision.NETWORK_CONFIRMATION_REQUIRED.value, "Explicit testnet read-only confirmation is required.", issues=issues)
        metadata = self._client(config).inspect_credential_presence()
        if not metadata.credentials_complete:
            decision = BinanceFuturesTestnetReadOnlyDecision.CREDENTIALS_INCOMPLETE.value if metadata.api_key_present or metadata.api_secret_present else BinanceFuturesTestnetReadOnlyDecision.CREDENTIALS_NOT_CONFIGURED.value
            return self._result(config, action, "WARNING", decision, "Dedicated testnet credentials are incomplete or missing.", credential_metadata=metadata, issues=issues, credentials_inspected=True)
        return None

    def _server_time_or_issue(self, client: BinanceFuturesTestnetReadOnlyClient, config: BinanceFuturesTestnetReadOnlyConfig, issues: list[BinanceFuturesTestnetReadOnlyIssue]) -> int:
        if not config.allow_public_server_time_fetch:
            raise RuntimeError("server time fetch is disabled")
        payload = client.fetch_server_time()
        skew = int(payload["clock_skew_ms"])
        if skew > int(config.maximum_clock_skew_ms):
            issues.append(self._issue("clock_skew_exceeded", "FAIL", "Testnet server-time skew exceeded safe maximum.", {"clock_skew_ms": skew}))
            raise RuntimeError("clock skew exceeded")
        return int(payload["server_time"])

    def _validate_config(self, config: BinanceFuturesTestnetReadOnlyConfig, expected_profile: str, issues: list[BinanceFuturesTestnetReadOnlyIssue], diagnostics: dict[str, Any]) -> None:
        expected = {"project_scope": "BTC_ONLY", "symbol": "BTC/USDT", "exchange_symbol": "BTCUSDT", "exchange": "binance", "market_type": "futures", "futures_contract_type": "USDT_PERPETUAL", "strategy_profile": expected_profile}
        for name, value in expected.items():
            self._expect(getattr(config, name) == value, issues, name, f"{name} must be {value}.")
        self._expect(not config.feature_enabled, issues, "feature_enabled", "feature_enabled must remain false.")
        self._expect(not config.automatic_execution_enabled, issues, "automatic_execution_enabled", "automatic execution must remain disabled.")
        self._expect(config.explicit_cli_only, issues, "explicit_cli_only", "authenticated read-only access must be explicit CLI only.")
        self._expect(config.authenticated_read_only_available, issues, "authenticated_read_only_available", "authenticated read-only availability must remain true for 2.78.")
        self._expect(config.dry_run_trading_only, issues, "dry_run_trading_only", "dry-run trading boundary must remain true.")
        self._expect(config.testnet_only, issues, "testnet_only", "testnet_only must remain true.")
        self._validate_url_and_hosts(config, issues)
        self._expect(config.api_key_env_var == "BINANCE_FUTURES_TESTNET_API_KEY", issues, "api_key_env_var", "Only BINANCE_FUTURES_TESTNET_API_KEY may be used.")
        self._expect(config.api_secret_env_var == "BINANCE_FUTURES_TESTNET_API_SECRET", issues, "api_secret_env_var", "Only BINANCE_FUTURES_TESTNET_API_SECRET may be used.")
        self._expect(config.allowed_http_methods == ["GET"], issues, "allowed_http_methods", "Only GET may be allowlisted.")
        allowed_paths = {"/fapi/v3/account", "/fapi/v3/balance", "/fapi/v3/positionRisk"}
        self._expect(set(config.allowed_authenticated_paths) == allowed_paths, issues, "allowed_authenticated_paths", "Authenticated paths must match the read-only allowlist exactly.")
        self._expect(config.account_path == "/fapi/v3/account", issues, "account_path", "account_path must be /fapi/v3/account.")
        self._expect(config.balance_path == "/fapi/v3/balance", issues, "balance_path", "balance_path must be /fapi/v3/balance.")
        self._expect(config.position_risk_path == "/fapi/v3/positionRisk", issues, "position_risk_path", "position_risk_path must be /fapi/v3/positionRisk.")
        self._expect(config.server_time_path == "/fapi/v1/time", issues, "server_time_path", "server_time_path must be /fapi/v1/time.")
        self._expect(config.require_explicit_network_confirmation, issues, "require_explicit_network_confirmation", "explicit confirmation is required.")
        self._expect(config.network_confirmation_phrase == "CONFIRM_TESTNET_READ_ONLY", issues, "network_confirmation_phrase", "confirmation phrase must match the safe fixed phrase.")
        self._expect(1 <= int(config.request_timeout_seconds) <= 30, issues, "request_timeout_seconds", "timeout must be between 1 and 30.")
        self._expect(int(config.max_authenticated_fetch_retries) == 0, issues, "max_authenticated_fetch_retries", "authenticated retries must remain zero.")
        self._expect(0 < int(config.recv_window_ms) <= int(config.maximum_recv_window_ms) <= 10000, issues, "recv_window_ms", "recvWindow must be positive and <= safe maximum.")
        self._expect(0 <= int(config.maximum_clock_skew_ms) <= 5000, issues, "maximum_clock_skew_ms", "clock-skew allowance must be <= 5000ms.")
        for name in ("allow_public_server_time_fetch", "allow_explicit_authenticated_account_read", "allow_explicit_authenticated_balance_read", "allow_explicit_authenticated_position_read", "allow_explicit_combined_account_snapshot"):
            self._expect(bool(getattr(config, name)), issues, name, f"{name} must remain true for explicit 2.78 diagnostics.")
        for name in self._must_be_false_fields():
            self._expect(not bool(getattr(config, name)), issues, name, f"{name} must remain false.")
        self._expect(config.balance_asset_filter == "USDT", issues, "balance_asset_filter", "Only USDT balance may be selected.")
        self._expect(config.position_symbol_filter == "BTCUSDT", issues, "position_symbol_filter", "Only BTCUSDT position risk may be selected.")
        self._validate_report_dir(config.report_export_dir, issues)
        self._validate_dependencies(config, expected_profile, issues, diagnostics)

    def _must_be_false_fields(self) -> tuple[str, ...]:
        return (
            "allow_automatic_authenticated_requests", "allow_background_authenticated_polling", "allow_runner_authenticated_requests", "allow_monitoring_authenticated_requests",
            "allow_order_query", "allow_trade_query", "allow_income_query", "allow_open_order_query",
            "allow_testnet_order_submission", "allow_testnet_order_test_submission", "allow_testnet_order_cancellation", "allow_testnet_order_modification",
            "allow_testnet_position_creation", "allow_testnet_position_close", "allow_testnet_leverage_change", "allow_testnet_margin_mode_change",
            "allow_testnet_position_mode_change", "allow_testnet_multi_assets_mode_change", "allow_testnet_position_margin_change",
            "allow_user_data_stream", "allow_listen_key", "allow_websocket_connection", "allow_production_endpoint", "allow_production_credentials", "allow_real_funds",
            "allow_raw_authenticated_response_print", "allow_raw_authenticated_response_persistence", "allow_authenticated_header_logging", "allow_signature_logging", "allow_signed_url_logging",
            "allow_futures_paper_state_mutation", "allow_spot_paper_account_state_mutation", "allow_runner_state_mutation", "allow_execution_state_mutation", "allow_exchange_state_mutation",
        )

    def _validate_url_and_hosts(self, config: BinanceFuturesTestnetReadOnlyConfig, issues: list[BinanceFuturesTestnetReadOnlyIssue]) -> None:
        try:
            BinanceFuturesTestnetReadOnlyClient(config, env={})
        except Exception as exc:
            issues.append(self._issue("rest_base_url", "FAIL", str(exc)))
        self._expect(config.allowed_hosts == ["demo-fapi.binance.com"], issues, "allowed_hosts", "allowed_hosts must contain only demo-fapi.binance.com.")
        host = urlparse(config.rest_base_url).hostname or ""
        self._expect(host == "demo-fapi.binance.com", issues, "rest_base_url_host", "REST host must be demo-fapi.binance.com.")

    def _validate_dependencies(self, config: BinanceFuturesTestnetReadOnlyConfig, expected_profile: str, issues: list[BinanceFuturesTestnetReadOnlyIssue], diagnostics: dict[str, Any]) -> None:
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
        feed = self.futures_feed_engine.validate(config.futures_read_only_feed_config_path, expected_profile=expected_profile)
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

    def _client(self, config: BinanceFuturesTestnetReadOnlyConfig) -> BinanceFuturesTestnetReadOnlyClient:
        return BinanceFuturesTestnetReadOnlyClient(config, http_get=self.http_get, authenticated_get=self.authenticated_get, env=self.env, now_ms_provider=self.now_ms_provider)

    def _result(
        self,
        config: BinanceFuturesTestnetReadOnlyConfig,
        action: str,
        status: str,
        decision: str,
        reason: str,
        credential_metadata: BinanceFuturesTestnetCredentialMetadata | None = None,
        request_metadata: BinanceFuturesTestnetAuthenticatedRequestMetadata | None = None,
        account_summary: BinanceFuturesTestnetAccountSummary | None = None,
        balance_summary: BinanceFuturesTestnetBalanceSummary | None = None,
        position_summary: BinanceFuturesTestnetPositionSummary | None = None,
        payload: dict[str, Any] | None = None,
        issues: list[BinanceFuturesTestnetReadOnlyIssue] | None = None,
        **flags,
    ) -> BinanceFuturesTestnetReadOnlyResult:
        safety = self._safety_summary(flags)
        return BinanceFuturesTestnetReadOnlyResult(
            created_at=self._now(),
            action=action,
            status=status,
            decision=decision,
            reason=reason,
            credential_metadata=credential_metadata,
            request_metadata=request_metadata,
            account_summary=account_summary,
            balance_summary=balance_summary,
            position_summary=position_summary,
            payload=payload or {},
            issues=issues or [],
            safety_summary=safety,
            **flags,
        )

    def _safety_summary(self, flags: dict[str, Any] | None = None) -> dict[str, Any]:
        flags = flags or {}
        safe = {name: False for name in (
            "order_query_used", "trade_query_used", "income_query_used", "open_order_query_used", "order_submitted", "test_order_submitted",
            "order_cancelled", "order_modified", "position_created", "position_closed", "leverage_changed", "margin_mode_changed", "position_mode_changed",
            "multi_assets_mode_changed", "position_margin_changed", "user_data_stream_opened", "listen_key_created", "websocket_opened", "production_endpoint_used",
            "production_credentials_used", "real_funds_used", "futures_paper_state_mutated", "spot_paper_account_state_mutated", "runner_state_mutated",
            "execution_state_mutated", "exchange_state_mutated", "api_key_exposed", "api_secret_exposed", "signature_exposed", "signed_url_exposed",
            "authenticated_headers_exposed", "raw_response_printed", "raw_response_persisted", "api_secret_transmitted",
        )}
        safe.update({
            "public_server_time_request_used": bool(flags.get("public_server_time_request_used", False)),
            "credentials_inspected": bool(flags.get("credentials_inspected", False)),
            "signature_generated": bool(flags.get("signature_generated", False)),
            "authenticated_transport_invoked": bool(flags.get("authenticated_transport_invoked", False)),
            "authenticated_testnet_request_used": bool(flags.get("authenticated_testnet_request_used", False)),
            "request_transmitted": bool(flags.get("request_transmitted", False)),
            "api_key_header_used": bool(flags.get("api_key_header_used", False)),
        })
        return safe

    def _merge_metadata(self, *items: BinanceFuturesTestnetAuthenticatedRequestMetadata) -> BinanceFuturesTestnetAuthenticatedRequestMetadata:
        latest = items[-1]
        return BinanceFuturesTestnetAuthenticatedRequestMetadata(
            method="GET",
            host=latest.host,
            path="ACCOUNT+BALANCE+POSITION",
            parameter_names=sorted({name for item in items for name in item.parameter_names}),
            timestamp=latest.timestamp,
            recv_window_ms=latest.recv_window_ms,
            signature_generated=all(item.signature_generated for item in items),
            signature_redacted=True,
            api_key_header_used=all(item.api_key_header_used for item in items),
            request_transmitted=all(item.request_transmitted for item in items),
            response_received=all(item.response_received for item in items),
            response_status_code=latest.response_status_code,
            final_host_validated=all(item.final_host_validated for item in items),
            response_bytes=sum(item.response_bytes or 0 for item in items),
            retry_count=sum(item.retry_count for item in items),
        )

    def _report(self, config_path: str, config: BinanceFuturesTestnetReadOnlyConfig | None, issues: list[BinanceFuturesTestnetReadOnlyIssue], diagnostics: dict[str, Any]) -> BinanceFuturesTestnetReadOnlyValidationReport:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        return BinanceFuturesTestnetReadOnlyValidationReport(config_path=config_path, created_at=self._now(), status="FAIL" if failures else "WARNING" if warnings else "PASS", issue_count=len(issues), warning_count=warnings, fail_count=failures, config=config, issues=issues, diagnostics=diagnostics)

    def _validate_report_dir(self, value: str, issues: list[BinanceFuturesTestnetReadOnlyIssue]) -> None:
        path = Path(value)
        self._expect(not path.is_absolute() and ".." not in path.parts and len(path.parts) >= 2 and path.parts[0] == "reports" and path.parts[1] == "binance_futures_testnet_read_only", issues, "report_export_dir", "report_export_dir must be under reports/binance_futures_testnet_read_only.")

    def _expect(self, condition: bool, issues: list[BinanceFuturesTestnetReadOnlyIssue], name: str, message: str) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message))

    def _issue(self, name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> BinanceFuturesTestnetReadOnlyIssue:
        return BinanceFuturesTestnetReadOnlyIssue(name=name, severity=severity, message=message, details=details or {})

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
                return "redacted authenticated read-only error"
        return text[:180]
