from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from engine.diagnostics.btc_futures_paper_position_engine import BTCFuturesPaperPositionEngine
from engine.diagnostics.btc_futures_read_only_feed_engine import BTCFuturesReadOnlyFeedEngine
from engine.diagnostics.btc_futures_risk_model_engine import BTCFuturesRiskModelEngine
from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine
from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from infrastructure.exchanges.binance_futures_testnet_adapter import (
    BinanceFuturesTestnetAdapter,
    BinanceFuturesTestnetOperationBlocked,
)
from models.binance_futures_testnet_adapter import (
    BinanceFuturesTestnetAdapterAction,
    BinanceFuturesTestnetAdapterConfig,
    BinanceFuturesTestnetAdapterDecision,
    BinanceFuturesTestnetAdapterResult,
    BinanceFuturesTestnetAdapterStatus,
    BinanceFuturesTestnetAdapterValidationReport,
    BinanceFuturesTestnetIssue,
)


class BinanceFuturesTestnetAdapterEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        runtime_config_engine: BTCPaperRuntimeConfigEngine | None = None,
        monitoring_engine: BTCPaperMonitoringEngine | None = None,
        runner_engine: BTCPaperRunnerEngine | None = None,
        futures_feed_engine: BTCFuturesReadOnlyFeedEngine | None = None,
        futures_risk_model_engine: BTCFuturesRiskModelEngine | None = None,
        futures_paper_position_engine: BTCFuturesPaperPositionEngine | None = None,
        http_get=None,
        env: dict[str, str] | None = None,
        now_provider=None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.runtime_config_engine = runtime_config_engine or BTCPaperRuntimeConfigEngine(repo_root=self.repo_root)
        self.monitoring_engine = monitoring_engine or BTCPaperMonitoringEngine(repo_root=self.repo_root)
        self.runner_engine = runner_engine or BTCPaperRunnerEngine(repo_root=self.repo_root)
        self.futures_feed_engine = futures_feed_engine or BTCFuturesReadOnlyFeedEngine(repo_root=self.repo_root)
        self.futures_risk_model_engine = futures_risk_model_engine or BTCFuturesRiskModelEngine(repo_root=self.repo_root)
        self.futures_paper_position_engine = futures_paper_position_engine or BTCFuturesPaperPositionEngine(repo_root=self.repo_root)
        self.http_get = http_get
        self.env = {} if env is None else env
        self.now_provider = now_provider

    def validate(self, config_path: str = "configs/binance_futures_testnet_adapter.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetAdapterValidationReport:
        issues: list[BinanceFuturesTestnetIssue] = []
        diagnostics: dict[str, Any] = {
            "runtime_config_status": "UNKNOWN",
            "monitoring_config_status": "UNKNOWN",
            "runner_config_status": "UNKNOWN",
            "futures_feed_config_status": "UNKNOWN",
            "futures_risk_model_config_status": "UNKNOWN",
            "futures_paper_position_config_status": "UNKNOWN",
            "kill_switch_enabled": None,
        }
        config = None
        try:
            config = self.load_config(config_path)
        except Exception as exc:
            issues.append(self._issue("config_invalid", "FAIL", f"Binance futures testnet adapter config could not be loaded: {exc}", {"config_path": config_path}))
            return self._report(config_path, config, issues, diagnostics)
        self._validate_config(config, expected_profile, issues, diagnostics)
        return self._report(config_path, config, issues, diagnostics)

    def ping_testnet(self, config_path: str = "configs/binance_futures_testnet_adapter.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetAdapterResult:
        return self._public_action(BinanceFuturesTestnetAdapterAction.PING_TESTNET.value, "Public testnet ping completed.", lambda adapter: adapter.ping(), config_path, expected_profile)

    def fetch_server_time(self, config_path: str = "configs/binance_futures_testnet_adapter.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetAdapterResult:
        return self._public_action(BinanceFuturesTestnetAdapterAction.FETCH_SERVER_TIME.value, "Public testnet server time fetched.", lambda adapter: adapter.fetch_server_time(), config_path, expected_profile)

    def fetch_exchange_info(self, config_path: str = "configs/binance_futures_testnet_adapter.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetAdapterResult:
        return self._public_action(BinanceFuturesTestnetAdapterAction.FETCH_EXCHANGE_INFO.value, "Public testnet BTCUSDT exchange info fetched.", lambda adapter: adapter.fetch_exchange_info("BTCUSDT"), config_path, expected_profile)

    def check_credentials(self, config_path: str = "configs/binance_futures_testnet_adapter.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetAdapterResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetAdapterConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, BinanceFuturesTestnetAdapterAction.CHECK_CREDENTIALS.value, "FAIL", BinanceFuturesTestnetAdapterDecision.OPERATION_FAILED.value, "Adapter config failed validation.", {}, issues)
        payload = self._adapter(config).inspect_credential_presence()
        if payload["credentials_complete"]:
            status, decision, reason = "PASS", BinanceFuturesTestnetAdapterDecision.CREDENTIALS_PRESENT.value, "Dedicated testnet credentials are present."
        elif payload["api_key_present"] or payload["api_secret_present"]:
            status, decision, reason = "WARNING", BinanceFuturesTestnetAdapterDecision.CREDENTIALS_INCOMPLETE.value, "Dedicated testnet credentials are incomplete."
        else:
            status, decision, reason = "WARNING", BinanceFuturesTestnetAdapterDecision.CREDENTIALS_NOT_CONFIGURED.value, "Dedicated testnet credentials are not configured."
        return self._result(config, BinanceFuturesTestnetAdapterAction.CHECK_CREDENTIALS.value, status, decision, reason, payload, issues, credentials_inspected=True)

    def signed_request_preview(self, path: str, parameters: dict[str, Any] | None = None, config_path: str = "configs/binance_futures_testnet_adapter.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetAdapterResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetAdapterConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, BinanceFuturesTestnetAdapterAction.SIGNED_REQUEST_PREVIEW.value, "FAIL", BinanceFuturesTestnetAdapterDecision.OPERATION_FAILED.value, "Adapter config failed validation.", {}, issues)
        params = {"timestamp": int(time.time() * 1000), "recvWindow": config.recv_window_ms, **(parameters or {})}
        try:
            payload = self._adapter(config).build_signed_request_preview(path, params)
        except Exception as exc:
            issues.append(self._issue("signed_preview_rejected", "FAIL", str(exc)))
            return self._result(config, BinanceFuturesTestnetAdapterAction.SIGNED_REQUEST_PREVIEW.value, "FAIL", BinanceFuturesTestnetAdapterDecision.SIGNING_PREVIEW_REJECTED.value, "Signed request preview rejected safely.", {}, issues, credentials_inspected=True)
        status = "PASS" if payload.get("credentials_complete") else "WARNING"
        decision = BinanceFuturesTestnetAdapterDecision.SIGNING_PREVIEW_BUILT.value if payload.get("signature_generated") else BinanceFuturesTestnetAdapterDecision.CREDENTIALS_NOT_CONFIGURED.value
        reason = "Local redacted signing preview built." if payload.get("signature_generated") else "Dedicated testnet credentials are missing; no signature was generated."
        return self._result(config, BinanceFuturesTestnetAdapterAction.SIGNED_REQUEST_PREVIEW.value, status, decision, reason, payload, issues, credentials_inspected=True, signature_generated=bool(payload.get("signature_generated")), request_signed=False)

    def build_order_intent(self, intent_id: str, side: str, order_type: str, quantity: float, price: float | None = None, stop_price: float | None = None, time_in_force: str | None = None, reduce_only: bool = False, close_position: bool = False, config_path: str = "configs/binance_futures_testnet_adapter.json", expected_profile: str = "balanced_smc_decision_065") -> BinanceFuturesTestnetAdapterResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetAdapterConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, BinanceFuturesTestnetAdapterAction.BUILD_ORDER_INTENT.value, "FAIL", BinanceFuturesTestnetAdapterDecision.OPERATION_FAILED.value, "Adapter config failed validation.", {}, issues)
        try:
            payload = self._adapter(config).build_order_intent(intent_id, config.exchange_symbol, side, order_type, quantity, price, stop_price, time_in_force, reduce_only, close_position)
        except Exception as exc:
            issues.append(self._issue("order_intent_rejected", "FAIL", str(exc)))
            return self._result(config, BinanceFuturesTestnetAdapterAction.BUILD_ORDER_INTENT.value, "FAIL", BinanceFuturesTestnetAdapterDecision.ORDER_INTENT_REJECTED.value, "Local order intent rejected safely.", {}, issues)
        return self._result(config, BinanceFuturesTestnetAdapterAction.BUILD_ORDER_INTENT.value, "PASS", BinanceFuturesTestnetAdapterDecision.ORDER_INTENT_VALID.value, "Local non-executable order intent built.", payload, issues)

    def hard_block_diagnostics(self, config_path: str = "configs/binance_futures_testnet_adapter.json") -> BinanceFuturesTestnetAdapterResult:
        config = self.load_config(config_path)
        adapter = self._adapter(config)
        methods = ["submit_order", "cancel_order", "fetch_account", "fetch_balances", "fetch_positions", "change_leverage", "change_margin_mode"]
        blocked: dict[str, str] = {}
        issues: list[BinanceFuturesTestnetIssue] = []
        for name in methods:
            try:
                getattr(adapter, name)()
            except BinanceFuturesTestnetOperationBlocked as exc:
                blocked[name] = str(exc)
            except Exception as exc:
                issues.append(self._issue(f"{name}_unexpected", "FAIL", str(exc)))
        status = "FAIL" if issues or len(blocked) != len(methods) else "PASS"
        return self._result(config, BinanceFuturesTestnetAdapterAction.HARD_BLOCK.value, status, BinanceFuturesTestnetAdapterDecision.AUTHENTICATED_TESTNET_OPERATION_DISABLED.value, "Authenticated and mutating adapter methods are hard-blocked before transport.", {"blocked_methods": blocked, "authenticated_transport_available": False, "testnet_order_transport_available": False}, issues)

    def load_config(self, config_path: str = "configs/binance_futures_testnet_adapter.json") -> BinanceFuturesTestnetAdapterConfig:
        path = self._resolve(config_path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("config JSON must be an object")
        return BinanceFuturesTestnetAdapterConfig(**{**BinanceFuturesTestnetAdapterConfig().to_dict(), **loaded})

    def _public_action(self, action: str, success_reason: str, callback, config_path: str, expected_profile: str) -> BinanceFuturesTestnetAdapterResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetAdapterConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, action, "FAIL", BinanceFuturesTestnetAdapterDecision.OPERATION_FAILED.value, "Adapter config failed validation.", {}, issues)
        try:
            payload = callback(self._adapter(config))
            return self._result(config, action, "PASS", BinanceFuturesTestnetAdapterDecision.PUBLIC_TESTNET_OK.value, success_reason, payload, issues, public_request_used=True)
        except Exception as exc:
            issues.append(self._issue("public_testnet_request_failed", "FAIL", str(exc)))
            return self._result(config, action, "FAIL", BinanceFuturesTestnetAdapterDecision.PUBLIC_TESTNET_FAILED.value, "Public testnet diagnostic failed safely.", {}, issues, public_request_used=True)

    def _validate_config(self, config: BinanceFuturesTestnetAdapterConfig, expected_profile: str, issues: list[BinanceFuturesTestnetIssue], diagnostics: dict[str, Any]) -> None:
        expected = {"project_scope": "BTC_ONLY", "symbol": "BTC/USDT", "exchange_symbol": "BTCUSDT", "exchange": "binance", "market_type": "futures", "futures_contract_type": "USDT_PERPETUAL", "strategy_profile": expected_profile}
        for name, value in expected.items():
            self._expect(getattr(config, name) == value, issues, name, f"{name} must be {value}.")
        self._expect(not config.adapter_enabled, issues, "adapter_enabled", "adapter_enabled must remain false.")
        self._expect(config.connection_mode == "disabled", issues, "connection_mode", "connection_mode must be disabled.")
        self._expect(config.testnet_only, issues, "testnet_only", "testnet_only must be true.")
        self._expect(config.dry_run_only, issues, "dry_run_only", "dry_run_only must be true.")
        self._validate_url_and_hosts(config, issues)
        self._expect(config.api_key_env_var == "BINANCE_FUTURES_TESTNET_API_KEY", issues, "api_key_env_var", "Only BINANCE_FUTURES_TESTNET_API_KEY may be used.")
        self._expect(config.api_secret_env_var == "BINANCE_FUTURES_TESTNET_API_SECRET", issues, "api_secret_env_var", "Only BINANCE_FUTURES_TESTNET_API_SECRET may be used.")
        self._expect(1 <= int(config.request_timeout_seconds) <= 30, issues, "request_timeout_seconds", "request_timeout_seconds must be between 1 and 30.")
        self._expect(0 <= int(config.max_public_fetch_retries) <= 3, issues, "max_public_fetch_retries", "max_public_fetch_retries must be between 0 and 3.")
        self._expect(0 < int(config.recv_window_ms) <= int(config.maximum_recv_window_ms) <= 10000, issues, "recv_window_ms", "recvWindow must be positive and <= maximum safe value.")
        self._expect(set(config.allowed_public_paths) <= {"/fapi/v1/ping", "/fapi/v1/time", "/fapi/v1/exchangeInfo"}, issues, "allowed_public_paths", "Unknown public path is not allowed.")
        self._expect(set(config.allowed_signed_preview_paths) <= {"/fapi/v2/account", "/fapi/v2/balance", "/fapi/v2/positionRisk"}, issues, "allowed_signed_preview_paths", "Unknown signed preview path is not allowed.")
        for name in ("allow_public_testnet_ping", "allow_public_testnet_time_fetch", "allow_public_testnet_exchange_info_fetch", "allow_environment_credential_presence_check", "allow_local_hmac_signing_preview", "allow_local_signed_request_preview", "allow_local_order_intent_build"):
            self._expect(bool(getattr(config, name)), issues, name, f"{name} must be true for explicit diagnostics.")
        for name in (
            "allow_authenticated_testnet_request", "allow_authenticated_account_read", "allow_authenticated_balance_read", "allow_authenticated_position_read",
            "allow_testnet_order_submission", "allow_testnet_order_cancellation", "allow_testnet_leverage_change", "allow_testnet_margin_mode_change",
            "allow_testnet_position_creation", "allow_user_data_stream", "allow_websocket_connection", "allow_production_endpoint", "allow_production_credentials",
            "allow_real_funds", "allow_futures_paper_state_mutation", "allow_spot_paper_account_state_mutation", "allow_runner_state_mutation",
            "allow_execution_state_mutation", "allow_exchange_state_mutation",
        ):
            self._expect(not bool(getattr(config, name)), issues, name, f"{name} must remain false.")
        self._validate_report_dir(config.report_export_dir, issues)
        self._validate_dependencies(config, expected_profile, issues, diagnostics)

    def _validate_url_and_hosts(self, config: BinanceFuturesTestnetAdapterConfig, issues: list[BinanceFuturesTestnetIssue]) -> None:
        try:
            BinanceFuturesTestnetAdapter(config, env={})
        except Exception as exc:
            issues.append(self._issue("rest_base_url", "FAIL", str(exc)))
        self._expect(config.allowed_hosts == ["demo-fapi.binance.com"], issues, "allowed_hosts", "allowed_hosts must contain only demo-fapi.binance.com.")
        host = urlparse(config.rest_base_url).hostname or ""
        self._expect(host == "demo-fapi.binance.com", issues, "rest_base_url_host", "REST host must be demo-fapi.binance.com.")

    def _validate_dependencies(self, config: BinanceFuturesTestnetAdapterConfig, expected_profile: str, issues: list[BinanceFuturesTestnetIssue], diagnostics: dict[str, Any]) -> None:
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

    def _result(self, config: BinanceFuturesTestnetAdapterConfig, action: str, status: str, decision: str, reason: str, payload: dict[str, Any], issues: list[BinanceFuturesTestnetIssue], **flags) -> BinanceFuturesTestnetAdapterResult:
        safety = self._safety_summary(flags)
        return BinanceFuturesTestnetAdapterResult(created_at=self._now(), action=action, status=status, decision=decision, reason=reason, payload=payload, issues=issues, safety_summary=safety, **flags)

    def _safety_summary(self, flags: dict[str, Any] | None = None) -> dict[str, Any]:
        flags = flags or {}
        return {
            "public_request_used": bool(flags.get("public_request_used", False)),
            "credentials_inspected": bool(flags.get("credentials_inspected", False)),
            "signature_generated": bool(flags.get("signature_generated", False)),
            "request_transmitted": False,
            "authenticated_transport_invoked": False,
            "testnet_order_submitted": False,
            "testnet_order_cancelled": False,
            "exchange_leverage_changed": False,
            "exchange_margin_mode_changed": False,
            "futures_paper_state_mutated": False,
            "spot_paper_account_state_mutated": False,
            "runner_state_mutated": False,
            "execution_state_mutated": False,
            "exchange_state_mutated": False,
            "secrets_logged": False,
            "secrets_persisted": False,
        }

    def _adapter(self, config: BinanceFuturesTestnetAdapterConfig) -> BinanceFuturesTestnetAdapter:
        return BinanceFuturesTestnetAdapter(config, http_get=self.http_get, env=self.env)

    def _report(self, config_path: str, config: BinanceFuturesTestnetAdapterConfig | None, issues: list[BinanceFuturesTestnetIssue], diagnostics: dict[str, Any]) -> BinanceFuturesTestnetAdapterValidationReport:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        return BinanceFuturesTestnetAdapterValidationReport(config_path=config_path, created_at=self._now(), status="FAIL" if failures else "WARNING" if warnings else "PASS", issue_count=len(issues), warning_count=warnings, fail_count=failures, config=config, issues=issues, diagnostics=diagnostics)

    def _validate_report_dir(self, value: str, issues: list[BinanceFuturesTestnetIssue]) -> None:
        path = Path(value)
        self._expect(not path.is_absolute() and ".." not in path.parts and len(path.parts) >= 2 and path.parts[0] == "reports" and path.parts[1] == "binance_futures_testnet_adapter", issues, "report_export_dir", "report_export_dir must be under reports/binance_futures_testnet_adapter.")

    def _expect(self, condition: bool, issues: list[BinanceFuturesTestnetIssue], name: str, message: str) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message))

    def _issue(self, name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> BinanceFuturesTestnetIssue:
        return BinanceFuturesTestnetIssue(name=name, severity=severity, message=message, details=details or {})

    def _resolve(self, path_text: str) -> Path:
        path = Path(path_text)
        return path if path.is_absolute() else self.repo_root / path

    def _now(self) -> str:
        if self.now_provider is not None:
            return str(self.now_provider())
        return datetime.now(UTC).replace(microsecond=0).isoformat()
