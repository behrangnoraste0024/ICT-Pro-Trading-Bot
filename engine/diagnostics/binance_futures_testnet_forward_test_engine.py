from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from engine.diagnostics.btc_forward_test_loop_engine import BTCForwardTestLoopEngine
from engine.diagnostics.binance_futures_testnet_order_lifecycle_engine import BinanceFuturesTestnetOrderLifecycleEngine
from engine.diagnostics.binance_futures_testnet_order_test_engine import BinanceFuturesTestnetOrderTestEngine
from engine.diagnostics.binance_futures_testnet_protective_orders_engine import BinanceFuturesTestnetProtectiveOrdersEngine
from models.binance_futures_testnet_forward_test import (
    BinanceFuturesTestnetForwardTestConfig,
    BinanceFuturesTestnetForwardTestExecutionMode as ExecutionMode,
    BinanceFuturesTestnetForwardTestDecision,
    BinanceFuturesTestnetForwardTestEvidence,
    BinanceFuturesTestnetForwardTestIssue,
    BinanceFuturesTestnetForwardTestResult,
    BinanceFuturesTestnetForwardTestStatus,
    BinanceFuturesTestnetForwardTestValidationReport,
)
from infrastructure.security.live_execution_permit_gate import LiveExecutionPermitGate
from infrastructure.persistence.live_execution_permit_persistence import RUNTIME_EVIDENCE_ALLOWED_EVENTS
from models.live_execution_permit_enforcement import LiveExecutionPermitReference, PERMIT_GATE_CODES


SENSITIVE_MARKERS = (
    "apikey",
    "api_key",
    "api secret",
    "api_secret",
    "secret",
    "password",
    "token",
    "signature",
    "signed",
    "x-mbx-apikey",
    "authorization",
    "headers",
    "traceback",
    "sql",
    "rawresponse",
    "authenticatedurl",
)


class BinanceFuturesTestnetForwardTestEngine:
    ALLOWED_ENVIRONMENT = "BINANCE_FUTURES_TESTNET"
    ALLOWED_SYMBOL = "BTCUSDT"
    ALLOWED_HOST = "demo-fapi.binance.com"
    ALLOWED_RUNTIME_ENVIRONMENT_KEYS = (
        "BINANCE_FUTURES_TESTNET_API_KEY",
        "BINANCE_FUTURES_TESTNET_API_SECRET",
        "ICT_DATABASE_URL",
        "DATABASE_URL",
    )

    def __init__(
        self,
        repo_root: str | Path | None = None,
        forward_loop_engine: BTCForwardTestLoopEngine | None = None,
        order_test_engine: BinanceFuturesTestnetOrderTestEngine | None = None,
        order_lifecycle_engine: BinanceFuturesTestnetOrderLifecycleEngine | None = None,
        protective_orders_engine: BinanceFuturesTestnetProtectiveOrdersEngine | None = None,
        now_provider=None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.forward_loop_engine = forward_loop_engine or BTCForwardTestLoopEngine(repo_root=self.repo_root)
        self.order_test_engine = order_test_engine or BinanceFuturesTestnetOrderTestEngine(repo_root=self.repo_root)
        self.order_lifecycle_engine = order_lifecycle_engine or BinanceFuturesTestnetOrderLifecycleEngine(repo_root=self.repo_root)
        self.protective_orders_engine = protective_orders_engine or BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=self.repo_root)
        self.now_provider = now_provider

    def validate(
        self,
        config_path: str = "configs/binance_futures_testnet_forward_test.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BinanceFuturesTestnetForwardTestValidationReport:
        issues: list[BinanceFuturesTestnetForwardTestIssue] = []
        diagnostics = self._initial_diagnostics()
        config: BinanceFuturesTestnetForwardTestConfig | None = None
        try:
            config = self.load_config(config_path)
        except Exception:
            issues.append(self._issue("config_invalid", "FAIL", "Forward-test config could not be loaded."))
            return self._report(config_path, config, issues, diagnostics)
        try:
            self._validate_config(config, expected_profile, issues, diagnostics)
        except Exception:
            issues.append(self._issue("config_invalid", "FAIL", "Forward-test config failed safety validation."))
        return self._report(config_path, config, issues, diagnostics)

    def run(
        self,
        config_path: str = "configs/binance_futures_testnet_forward_test.json",
        expected_profile: str = "balanced_smc_decision_065",
        *,
        execution_authorized: bool = False,
        execution_mode: str | None = None,
        order_test_request: Mapping[str, Any] | None = None,
        confirmation: str | None = None,
        api_key_identifier: str | None = None,
        api_secret_identifier: str | None = None,
        permit_references: list[LiveExecutionPermitReference] | None = None,
        testnet_order_test_network_enabled: bool = False,
        runtime_environment: Mapping[str, str] | None = None,
        local_simulated_transport: bool = False,
        strategy_decision_count: int = 0,
        risk_denial_count: int = 0,
        kill_switch_denial_count: int = 0,
        restart_count: int = 0,
    ) -> BinanceFuturesTestnetForwardTestResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BinanceFuturesTestnetForwardTestConfig()
        issues = list(report.issues)
        evidence = self._empty_evidence(config, permit_references or [], strategy_decision_count, risk_denial_count, kill_switch_denial_count, restart_count)
        if report.status == BinanceFuturesTestnetForwardTestStatus.FAIL.value:
            return self._result("RUN", "FAIL", "CONFIG_INVALID", "Forward-test config failed safety validation.", config_path, evidence, issues, report.diagnostics)
        if execution_mode == ExecutionMode.SUPERVISED:
            return self._run_supervised(
                config, config_path, expected_profile, report, evidence,
                execution_authorized, permit_references or [], order_test_request,
                confirmation, api_key_identifier, api_secret_identifier,
                testnet_order_test_network_enabled, runtime_environment,
                local_simulated_transport,
            )
        if execution_mode not in (None, ExecutionMode.DISABLED, ExecutionMode.LOCAL) or execution_authorized is not False:
            return self._result("RUN", "FAIL", "EXECUTION_MODE_REQUIRED", "An explicit supervised ORDER_TEST mode is required.", config_path, evidence, issues, report.diagnostics)
        if execution_mode == ExecutionMode.LOCAL and not local_simulated_transport:
            return self._result("RUN", "FAIL", "EXECUTION_MODE_REQUIRED", "Local evidence requires explicit local simulation.", config_path, evidence, issues, report.diagnostics)
        if not local_simulated_transport:
            evidence.evidence_complete = False
            issues.append(self._issue("execution_not_authorized", "FAIL", "Actual Binance Demo execution is not authorized in this Pass."))
            return self._result("RUN", "FAIL", "EXECUTION_NOT_AUTHORIZED", "Forward-test execution is disabled by default and requires a later authorization Pass.", config_path, evidence, issues, report.diagnostics)
        evidence.evidence_complete = True
        evidence.execution_mode = ExecutionMode.LOCAL.value
        return self._result("RUN", "PASS", "LOCAL_SIMULATION_EVIDENCE", "Local simulated transport evidence only; no Binance Demo execution occurred.", config_path, evidence, issues, report.diagnostics)

    def _run_supervised(self, config, config_path, expected_profile, report, evidence,
                        authorized, references, request, confirmation,
                        key_identifier, secret_identifier, network_enabled,
                        runtime_environment, local_simulation):
        evidence.execution_mode = ExecutionMode.SUPERVISED.value
        evidence.order_test_requested_count = 1

        def denied(code):
            evidence.rejected_mutation_count = 1
            evidence.sanitized_error_count = 1
            return self._result("RUN", "FAIL", code, "Supervised ORDER_TEST was blocked.", config_path, evidence, [], report.diagnostics)

        if authorized is not True or confirmation != "CONFIRM_TESTNET_ORDER_TEST":
            return denied("EXECUTION_NOT_AUTHORIZED")
        if network_enabled is not True:
            return denied("TESTNET_ORDER_TEST_NETWORK_ENABLE_REQUIRED")
        runtime_env = self._validated_runtime_environment(runtime_environment)
        if runtime_env is None:
            return denied("TESTNET_RUNTIME_ENVIRONMENT_REQUIRED")
        if len(references) != 1 or not isinstance(references[0], LiveExecutionPermitReference):
            return denied("PERMIT_REFERENCE_REQUIRED")
        if (key_identifier, secret_identifier) != ("BINANCE_FUTURES_TESTNET_API_KEY", "BINANCE_FUTURES_TESTNET_API_SECRET"):
            return denied("TESTNET_CREDENTIAL_IDENTIFIERS_REQUIRED")
        if not isinstance(request, Mapping):
            return denied("ORDER_TEST_REQUEST_REQUIRED")
        request = dict(request)
        required = {"client_order_id", "side", "order_type", "quantity"}
        if not required <= request.keys() or request.keys() - (required | {"price", "time_in_force", "reduce_only"}):
            return denied("ORDER_TEST_REQUEST_INVALID")
        boundary = self.order_test_engine
        existing_local_transport = callable(getattr(boundary, "http_get", None)) and callable(getattr(boundary, "authenticated_post", None))
        if not local_simulation and not existing_local_transport:
            boundary = BinanceFuturesTestnetOrderTestEngine(repo_root=self.repo_root, env=runtime_env)
        if type(boundary) is not BinanceFuturesTestnetOrderTestEngine or type(boundary.permit_gate) is not LiveExecutionPermitGate:
            return denied("REAL_ORDER_TEST_BOUNDARY_REQUIRED")
        local = callable(boundary.http_get) and callable(boundary.authenticated_post)
        if local_simulation is not local or (not local and (boundary.http_get is not None or boundary.authenticated_post is not None)):
            return denied("TRANSPORT_MODE_INVALID")
        try:
            child = boundary.load_config(config.testnet_order_test_config_path)
            if (child.rest_base_url != "https://demo-fapi.binance.com"
                    or child.exchange_symbol != "BTCUSDT"
                    or child.api_key_env_var != key_identifier
                    or child.api_secret_env_var != secret_identifier):
                return denied("ORDER_TEST_CONFIG_INVALID")
            evidence.execution_authorized = True
            evidence.execution_enabled = True
            outcome = boundary.submit_test_order(
                **request, confirmation=confirmation,
                config_path=config.testnet_order_test_config_path,
                expected_profile=expected_profile, permit=references[0],
            )
        except Exception:
            outcome = None
        runtime_evidence = self._runtime_evidence_from_order_test_outcome(outcome)
        if runtime_evidence is not None:
            report.diagnostics.update(runtime_evidence)
        # The existing engine omits transport/consume state on some failure paths.
        # Unknown is deliberately not reported as zero or as completed evidence.
        metadata = None if outcome is None else outcome.request_metadata
        if metadata is not None and metadata.request_transmitted:
            evidence.permit_consumed_count = 1
            evidence.signing_count = 1
            evidence.post_count = 1
            evidence.final_persisted_state = "PERMIT_CONSUMED"
            evidence.actual_binance_demo_execution = not local
            evidence.transport_mode = "LOCAL_TEST_SIMULATED_TRANSPORT" if local else "ACTUAL_BINANCE_DEMO_ORDER_TEST"
            accepted = outcome.status == "PASS" and metadata.response_status_code is not None and 200 <= metadata.response_status_code < 300
            evidence.accepted_mutation_count = int(accepted)
            evidence.rejected_mutation_count = int(not accepted)
            evidence.sanitized_error_count = int(not accepted)
            evidence.evidence_complete = True
            code = "LOCAL_ORDER_TEST_ACCEPTED" if accepted and local else "ORDER_TEST_ACCEPTED" if accepted else "ORDER_TEST_REJECTED"
        else:
            evidence.permit_consumed_count = None
            evidence.signing_count = None
            evidence.post_count = None
            evidence.final_persisted_state = "UNKNOWN"
            evidence.evidence_complete = False
            evidence.sanitized_error_count = 1
            evidence.uncertain_mutation_count = 1
            accepted = False
            code = outcome.decision if outcome is not None and outcome.decision in PERMIT_GATE_CODES else "ORDER_TEST_EVIDENCE_INCOMPLETE"
            known_denials = PERMIT_GATE_CODES - {"PERMIT_GATE_UNAVAILABLE", "PERMIT_UNAVAILABLE", "PERMIT_CONSUMED_NO_TRANSPORT"}
            if code in known_denials:
                evidence.permit_consumed_count = 0
                evidence.signing_count = 0
                evidence.post_count = 0
                evidence.final_persisted_state = "NOT_MUTATED"
                evidence.uncertain_mutation_count = 0
                evidence.rejected_mutation_count = 1
                evidence.evidence_complete = True
            elif code == "PERMIT_CONSUMED_NO_TRANSPORT":
                evidence.permit_consumed_count = 1
                evidence.signing_count = 0
                evidence.post_count = 0
                evidence.final_persisted_state = "PERMIT_CONSUMED"
            if code == "KILL_SWITCH_ENGAGED":
                evidence.kill_switch_denial_count += 1
        evidence.end_timestamp = self._now()
        report.diagnostics["actual_demo_execution"] = evidence.actual_binance_demo_execution
        report.diagnostics["network_used"] = False if local else None
        report.diagnostics["credentials_inspected"] = bool(outcome and outcome.credentials_inspected)
        return self._result("RUN", "PASS" if accepted else "FAIL", code,
                            "Local ORDER_TEST boundary evidence; no Binance execution occurred." if local else "Supervised ORDER_TEST evidence recorded.",
                            config_path, evidence, [], report.diagnostics)

    @staticmethod
    def _runtime_evidence_from_order_test_outcome(outcome) -> dict[str, Any] | None:
        if outcome is None or not isinstance(getattr(outcome, "payload", None), Mapping):
            return None
        evidence = outcome.payload.get("runtime_evidence")
        if not isinstance(evidence, Mapping):
            return None
        events = evidence.get("mutation_boundary_events")
        if not isinstance(events, list) or any(event not in RUNTIME_EVIDENCE_ALLOWED_EVENTS for event in events):
            return None
        return {
            "policy_evaluation_count": int(evidence.get("policy_evaluation_count", 0)),
            "audit_record_count": int(evidence.get("audit_record_count", 0)),
            "recovery_required": evidence.get("recovery_required"),
            "mutation_boundary_events": list(events),
        }

    def _validated_runtime_environment(self, runtime_environment: Mapping[str, str] | None) -> dict[str, str] | None:
        if not isinstance(runtime_environment, Mapping):
            return None
        if any(key not in self.ALLOWED_RUNTIME_ENVIRONMENT_KEYS for key in runtime_environment):
            return None
        copied: dict[str, str] = {}
        for key, value in runtime_environment.items():
            if type(key) is not str or type(value) is not str or not value.strip():
                return None
            copied[key] = value
        required = {"BINANCE_FUTURES_TESTNET_API_KEY", "BINANCE_FUTURES_TESTNET_API_SECRET"}
        if not required <= copied.keys():
            return None
        if "ICT_DATABASE_URL" not in copied and "DATABASE_URL" not in copied:
            return None
        return copied

    def load_config(self, config_path: str) -> BinanceFuturesTestnetForwardTestConfig:
        path = self._resolve(config_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("config JSON must be an object")
        return BinanceFuturesTestnetForwardTestConfig(**{**BinanceFuturesTestnetForwardTestConfig().to_dict(), **payload})

    def _validate_config(
        self,
        config: BinanceFuturesTestnetForwardTestConfig,
        expected_profile: str,
        issues: list[BinanceFuturesTestnetForwardTestIssue],
        diagnostics: dict[str, Any],
    ) -> None:
        expected = {
            "schema_version": "1.0",
            "project_scope": "BTC_ONLY",
            "symbol": "BTC/USDT",
            "exchange_symbol": self.ALLOWED_SYMBOL,
            "environment": self.ALLOWED_ENVIRONMENT,
            "exchange": "binance",
            "market_type": "futures",
            "futures_contract_type": "USDT_PERPETUAL",
            "strategy_profile": expected_profile,
        }
        for field, value in expected.items():
            self._expect(getattr(config, field) == value, issues, field, f"{field} must be {value}.")
        self._expect(config.feature_enabled is False, issues, "feature_enabled", "feature_enabled must remain false.")
        self._expect(config.execution_enabled is False, issues, "execution_enabled", "execution_enabled must remain false.")
        self._expect(config.execution_mode == ExecutionMode.DISABLED, issues, "execution_mode", "Configuration cannot select execution mode.")
        self._expect(config.explicit_execution_authorization_required is True, issues, "explicit_execution_authorization_required", "explicit execution authorization is required.")
        self._expect(type(config.local_evidence_only) is bool, issues, "local_evidence_only", "local_evidence_only must be boolean.")
        self._expect(config.testnet_only is True, issues, "testnet_only", "Testnet/Demo isolation is required.")
        self._expect(config.btc_usdt_only is True, issues, "btc_usdt_only", "BTCUSDT-only scope is required.")
        self._validate_url_and_hosts(config, issues)
        for field in self._must_be_false_fields():
            self._expect(getattr(config, field) is False, issues, field, f"{field} must remain false.")
        for field in self._must_be_true_fields():
            self._expect(getattr(config, field) is True, issues, field, f"{field} must remain true.")
        self._expect(int(config.post_retry_count) == 0, issues, "post_retry_count", "POST retry count must be 0.")
        self._expect(int(config.delete_retry_count) == 0, issues, "delete_retry_count", "DELETE retry count must be 0.")
        self._validate_report_dir(config.report_export_dir, issues)
        self._validate_dependencies(config, expected_profile, issues, diagnostics)

    def _validate_dependencies(self, config: BinanceFuturesTestnetForwardTestConfig, expected_profile: str, issues: list[BinanceFuturesTestnetForwardTestIssue], diagnostics: dict[str, Any]) -> None:
        for name, callback in (
            ("forward_loop_status", lambda: self.forward_loop_engine.validate(config.forward_loop_config_path, expected_profile=expected_profile).status),
            ("order_test_status", lambda: self.order_test_engine.validate(config.testnet_order_test_config_path, expected_profile=expected_profile).status),
            ("order_lifecycle_status", lambda: self.order_lifecycle_engine.validate(config.testnet_order_lifecycle_config_path, expected_profile=expected_profile).status),
            ("protective_orders_status", lambda: self.protective_orders_engine.validate(config.testnet_protective_orders_config_path, expected_profile=expected_profile).status),
        ):
            try:
                status = callback()
            except Exception:
                status = "UNAVAILABLE"
            if status not in {"PASS", "FAIL", "WARNING"}:
                status = "UNAVAILABLE"
            diagnostics[name] = status
            if status != "PASS":
                issues.append(self._issue(name, "FAIL", f"{name} must validate PASS."))

    def _validate_url_and_hosts(self, config: BinanceFuturesTestnetForwardTestConfig, issues: list[BinanceFuturesTestnetForwardTestIssue]) -> None:
        parsed = urlparse(config.rest_base_url)
        self._expect(config.rest_base_url == "https://demo-fapi.binance.com", issues, "rest_base_url", "The exact Demo base URL is required.")
        self._expect(parsed.scheme == "https", issues, "rest_base_url", "REST base URL must use https.")
        self._expect(parsed.hostname == self.ALLOWED_HOST, issues, "rest_base_url", "REST base URL host must be demo-fapi.binance.com.")
        self._expect(not parsed.username and not parsed.password and parsed.path in ("", "/") and not parsed.query and not parsed.fragment, issues, "rest_base_url", "REST base URL must not include credentials, path, query, or fragment.")
        self._expect(config.allowed_hosts == [self.ALLOWED_HOST], issues, "allowed_hosts", "Allowed hosts must contain only demo-fapi.binance.com.")

    @staticmethod
    def _must_be_false_fields() -> tuple[str, ...]:
        return (
            "allow_unknown_environment",
            "allow_production_endpoint",
            "allow_production_credentials",
            "allow_real_funds",
            "allow_network_in_automated_tests",
            "allow_auto_permit_issue",
            "allow_permit_reuse",
            "allow_permit_refund",
        )

    @staticmethod
    def _must_be_true_fields() -> tuple[str, ...]:
        return (
            "require_supplied_permit_reference",
            "require_real_permit_gate",
            "require_existing_mutation_boundary",
            "require_existing_risk_authority",
            "require_existing_kill_switch_authority",
            "require_request_immutability",
            "require_reconciliation_on_uncertain",
            "require_restart_duplicate_protection",
        )

    def _empty_evidence(
        self,
        config: BinanceFuturesTestnetForwardTestConfig,
        permit_references: list[LiveExecutionPermitReference],
        strategy_decision_count: int,
        risk_denial_count: int,
        kill_switch_denial_count: int,
        restart_count: int,
    ) -> BinanceFuturesTestnetForwardTestEvidence:
        now = self._now()
        return BinanceFuturesTestnetForwardTestEvidence(
            run_id=f"binance-testnet-forward-{now}",
            start_timestamp=now,
            end_timestamp=now,
            environment=config.environment,
            symbol=config.exchange_symbol,
            production_disabled=not config.allow_production_endpoint and not config.allow_real_funds,
            execution_enabled=config.execution_enabled,
            strategy_decision_count=max(0, int(strategy_decision_count)),
            permit_reference_count=len(permit_references),
            permit_consumed_count=0,
            signing_count=0,
            post_count=0,
            delete_count=0,
            post_retry_count=int(config.post_retry_count),
            delete_retry_count=int(config.delete_retry_count),
            risk_denial_count=max(0, int(risk_denial_count)),
            kill_switch_denial_count=max(0, int(kill_switch_denial_count)),
            restart_count=max(0, int(restart_count)),
            final_position_state="NOT_INSPECTED",
            final_persisted_state="NOT_MUTATED",
        )

    def _report(
        self,
        config_path: str,
        config: BinanceFuturesTestnetForwardTestConfig | None,
        issues: list[BinanceFuturesTestnetForwardTestIssue],
        diagnostics: dict[str, Any],
    ) -> BinanceFuturesTestnetForwardTestValidationReport:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        status = "FAIL" if failures else "WARNING" if warnings else "PASS"
        decision = BinanceFuturesTestnetForwardTestDecision.CONFIG_INVALID.value if failures else BinanceFuturesTestnetForwardTestDecision.VALIDATION_PASS.value
        reason = "Forward-test config failed safety validation." if failures else "Forward-test orchestration config is safe and disabled by default."
        return BinanceFuturesTestnetForwardTestValidationReport(
            config_path="configs/binance_futures_testnet_forward_test.json",
            created_at=self._now(),
            status=status,
            decision=decision,
            reason=reason,
            issue_count=len(issues),
            warning_count=warnings,
            fail_count=failures,
            config=None if failures or config is None else replace(config, notes=None),
            issues=issues,
            diagnostics=diagnostics,
        )

    def _result(
        self,
        action: str,
        status: str,
        decision: str,
        reason: str,
        config_path: str,
        evidence: BinanceFuturesTestnetForwardTestEvidence,
        issues: list[BinanceFuturesTestnetForwardTestIssue],
        diagnostics: dict[str, Any],
    ) -> BinanceFuturesTestnetForwardTestResult:
        return BinanceFuturesTestnetForwardTestResult(
            action=action,
            status=status,
            decision=decision,
            reason=self._sanitize(reason),
            config_path="configs/binance_futures_testnet_forward_test.json",
            evidence=evidence,
            issues=issues,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _initial_diagnostics() -> dict[str, Any]:
        return {
            "network_used": False,
            "credentials_inspected": False,
            "permit_auto_issued": False,
            "permit_refunded": False,
            "actual_demo_execution": False,
            "production_endpoint_used": False,
            "forward_loop_status": "UNKNOWN",
            "order_test_status": "UNKNOWN",
            "order_lifecycle_status": "UNKNOWN",
            "protective_orders_status": "UNKNOWN",
        }

    def _validate_report_dir(self, value: str, issues: list[BinanceFuturesTestnetForwardTestIssue]) -> None:
        path = Path(value)
        self._expect(not path.is_absolute() and ".." not in path.parts and len(path.parts) >= 2 and path.parts[0] == "reports" and path.parts[1] == "binance_futures_testnet_forward_test", issues, "report_export_dir", "report_export_dir must stay under reports/binance_futures_testnet_forward_test.")

    @staticmethod
    def _expect(condition: bool, issues: list[BinanceFuturesTestnetForwardTestIssue], name: str, message: str) -> None:
        if not condition:
            issues.append(BinanceFuturesTestnetForwardTestIssue(name, "FAIL", message))

    @staticmethod
    def _issue(name: str, severity: str, message: str) -> BinanceFuturesTestnetForwardTestIssue:
        return BinanceFuturesTestnetForwardTestIssue(name, severity, message)

    def _resolve(self, path_text: str) -> Path:
        path = Path(path_text)
        return path if path.is_absolute() else self.repo_root / path

    def _now(self) -> str:
        if self.now_provider is not None:
            return str(self.now_provider())
        return datetime.now(UTC).replace(microsecond=0).isoformat()

    @staticmethod
    def _sanitize(text: str) -> str:
        lowered = text.lower().replace("-", "").replace("_", "")
        if any(marker.replace("-", "").replace("_", "") in lowered for marker in SENSITIVE_MARKERS):
            return "sanitized forward-test error"
        return text[:180]
