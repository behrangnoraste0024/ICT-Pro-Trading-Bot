from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from decimal import Decimal

from engine.diagnostics.binance_futures_testnet_order_test_engine import BinanceFuturesTestnetOrderTestEngine
from infrastructure.exchanges.binance_futures_testnet_order_test_client import BinanceOrderTestHTTPResponse
from infrastructure.persistence.live_execution_authorization_policy import LiveExecutionAuthorizationPolicy
from models.binance_futures_testnet_order_test import BinanceFuturesTestnetOrderTestConfig
from tests.kill_switch_test_support import durable_state_env


@dataclass
class _FakeReport:
    status: str = "PASS"
    config: object | None = None
    issues: list = None

    def __post_init__(self) -> None:
        if self.issues is None:
            self.issues = []
        if self.config is None:
            self.config = type("Config", (), {"kill_switch_enabled": True})()


@pytest.fixture(autouse=True)
def _allow_legacy_live_execution_permits(monkeypatch):
    def authorize_without_durable_permit(self, **kwargs):
        from models.live_execution_permit_enforcement import LiveExecutionPermitGateError

        decision = self.authorization_policy.authorize(
            kwargs["operation"],
            environment="TESTNET",
            symbol="BTCUSDT",
            confirmation_verified=kwargs.get("confirmation_verified", True),
            credentials_configured=kwargs.get("credentials_configured", True),
            runtime_config_path=kwargs.get("runtime_config_path"),
            current_pair_id=kwargs.get("current_pair_id"),
        )
        if not decision.allowed:
            raise LiveExecutionPermitGateError(decision.code)
        return None

    monkeypatch.setattr(
        "infrastructure.security.live_execution_permit_gate.LiveExecutionPermitGate.authorize_and_consume",
        authorize_without_durable_permit,
    )
    monkeypatch.setattr(
        "engine.diagnostics.binance_futures_testnet_order_test_engine.BinanceFuturesTestnetOrderTestEngine._require_present_permit_reference",
        staticmethod(lambda permit_reference: None),
    )

    class _LegacyPermitGate:
        def __init__(self, policy):
            self.authorization_policy = policy

        def authorize_and_consume(self, **kwargs):
            from models.live_execution_permit_enforcement import LiveExecutionPermitGateError

            decision = self.authorization_policy.authorize(
                kwargs["operation"],
                environment="TESTNET",
                symbol="BTCUSDT",
                confirmation_verified=kwargs.get("confirmation_verified", True),
                credentials_configured=kwargs.get("credentials_configured", True),
                runtime_config_path=kwargs.get("runtime_config_path"),
                current_pair_id=kwargs.get("current_pair_id"),
            )
            if not decision.allowed:
                raise LiveExecutionPermitGateError(decision.code)

    original_init = BinanceFuturesTestnetOrderTestEngine.__init__

    def legacy_init(self, *args, **kwargs):
        if kwargs.get("permit_gate") is None:
            kwargs["permit_gate"] = _LegacyPermitGate(kwargs.get("authorization_policy") or getattr(self, "authorization_policy", None))
        original_init(self, *args, **kwargs)
        if isinstance(self.permit_gate, _LegacyPermitGate):
            self.permit_gate.authorization_policy = self.authorization_policy

    monkeypatch.setattr(
        "engine.diagnostics.binance_futures_testnet_order_test_engine.BinanceFuturesTestnetOrderTestEngine.__init__",
        legacy_init,
    )



class _FakeEngine:
    def __init__(self, status: str = "PASS") -> None:
        self.status = status

    def validate(self, *args, **kwargs):
        return _FakeReport(self.status)


class _FakeRunnerEngine:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def validate_config(self, *args, **kwargs):
        issue = type("Issue", (), {"severity": "FAIL"})()
        return None, [issue] if self.fail else [], None


def _engine(tmp_path: Path, **kwargs) -> BinanceFuturesTestnetOrderTestEngine:
    return BinanceFuturesTestnetOrderTestEngine(
        repo_root=tmp_path,
        runtime_config_engine=kwargs.pop("runtime_config_engine", _FakeEngine()),
        monitoring_engine=kwargs.pop("monitoring_engine", _FakeEngine()),
        runner_engine=kwargs.pop("runner_engine", _FakeRunnerEngine()),
        testnet_adapter_engine=kwargs.pop("testnet_adapter_engine", _FakeEngine()),
        testnet_read_only_engine=kwargs.pop("testnet_read_only_engine", _FakeEngine()),
        futures_feed_engine=kwargs.pop("futures_feed_engine", _FakeEngine()),
        futures_risk_model_engine=kwargs.pop("futures_risk_model_engine", _FakeEngine()),
        futures_paper_position_engine=kwargs.pop("futures_paper_position_engine", _FakeEngine()),
        **kwargs,
    )


def _write_config(tmp_path: Path, **overrides) -> Path:
    config = BinanceFuturesTestnetOrderTestConfig().to_dict()
    config.update(overrides)
    path = tmp_path / "configs" / "binance_futures_testnet_order_test.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _env(state: str = "RELEASED") -> dict[str, str]:
    return durable_state_env(state)


def _http_get(url, timeout):
    if url.endswith("/fapi/v1/time"):
        return BinanceOrderTestHTTPResponse(200, url, {"serverTime": 123}, 18)
    if "/fapi/v1/premiumIndex" in url:
        return BinanceOrderTestHTTPResponse(200, url, {"symbol": "BTCUSDT", "markPrice": "50000"}, 40)
    return BinanceOrderTestHTTPResponse(
        200,
        url,
        {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "filters": [
                        {"filterType": "PRICE_FILTER", "minPrice": "1", "maxPrice": "1000000", "tickSize": "0.10"},
                        {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "100", "stepSize": "0.001"},
                        {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "maxQty": "100", "stepSize": "0.001"},
                        {"filterType": "MIN_NOTIONAL", "notional": "5"},
                    ],
                }
            ]
        },
        100,
    )


def test_repo_safe_config_validates_pass() -> None:
    report = BinanceFuturesTestnetOrderTestEngine().validate()

    assert report.status == "PASS"
    assert report.diagnostics["credentials_inspected"] is False
    assert report.diagnostics["network_used"] is False


@pytest.mark.parametrize(
    ("field", "value", "issue_name"),
    [
        ("feature_enabled", True, "feature_enabled"),
        ("automatic_execution_enabled", True, "automatic_execution_enabled"),
        ("explicit_cli_only", False, "explicit_cli_only"),
        ("testnet_only", False, "testnet_only"),
        ("test_order_only", False, "test_order_only"),
        ("rest_base_url", "https://fapi.binance.com", "rest_base_url"),
        ("allowed_hosts", ["demo-fapi.binance.com", "fapi.binance.com"], "allowed_hosts"),
        ("api_key_env_var", "BINANCE_API_KEY", "api_key_env_var"),
        ("api_secret_env_var", "BINANCE_API_SECRET", "api_secret_env_var"),
        ("allowed_http_methods", ["POST", "DELETE"], "allowed_http_methods"),
        ("test_order_path", "/fapi/v1/order", "test_order_path"),
        ("mark_price_path", "/fapi/v1/ticker/price", "mark_price_path"),
        ("market_reference_price_source", "TICKER_PRICE", "market_reference_price_source"),
        ("allowed_authenticated_paths", ["/fapi/v1/order"], "allowed_authenticated_paths"),
        ("require_explicit_network_confirmation", False, "require_explicit_network_confirmation"),
        ("network_confirmation_phrase", "CONFIRM", "network_confirmation_phrase"),
        ("max_authenticated_retries", 1, "max_authenticated_retries"),
        ("recv_window_ms", 20000, "recv_window_ms"),
        ("maximum_clock_skew_ms", 10000, "maximum_clock_skew_ms"),
        ("allowed_order_types", ["MARKET", "STOP"], "allowed_order_types"),
        ("maximum_quantity", 1.0, "maximum_quantity"),
        ("maximum_test_notional_usdt", 1000.0, "maximum_test_notional_usdt"),
        ("allow_actual_order_submission", True, "allow_actual_order_submission"),
        ("allow_order_cancellation", True, "allow_order_cancellation"),
        ("allow_order_modification", True, "allow_order_modification"),
        ("allow_order_query", True, "allow_order_query"),
        ("allow_trade_query", True, "allow_trade_query"),
        ("allow_conditional_order", True, "allow_conditional_order"),
        ("allow_algo_order", True, "allow_algo_order"),
        ("allow_position_creation", True, "allow_position_creation"),
        ("allow_leverage_change", True, "allow_leverage_change"),
        ("allow_raw_request_persistence", True, "allow_raw_request_persistence"),
        ("allow_raw_response_persistence", True, "allow_raw_response_persistence"),
        ("allow_authenticated_header_logging", True, "allow_authenticated_header_logging"),
        ("allow_signature_logging", True, "allow_signature_logging"),
        ("allow_exchange_state_mutation", True, "allow_exchange_state_mutation"),
        ("require_market_reference_price", False, "require_market_reference_price"),
        ("allow_zero_market_reference_price", True, "allow_zero_market_reference_price"),
        ("allow_unknown_market_notional", True, "allow_unknown_market_notional"),
        ("allow_unvalidated_exchange_filters_for_transmission", True, "allow_unvalidated_exchange_filters_for_transmission"),
        ("require_exchange_filters_before_transmission", False, "require_exchange_filters_before_transmission"),
        ("report_export_dir", "../reports", "report_export_dir"),
    ],
)
def test_dangerous_config_values_fail(tmp_path: Path, field: str, value, issue_name: str) -> None:
    path = _write_config(tmp_path, **{field: value})

    report = _engine(tmp_path).validate(str(path))

    assert report.status == "FAIL"
    assert any(issue.name == issue_name for issue in report.issues)


def test_dependency_failure_rejects_config(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    report = _engine(tmp_path, testnet_read_only_engine=_FakeEngine("FAIL")).validate(str(path))

    assert report.status == "FAIL"
    assert any(issue.name == "testnet_read_only_config_validation" for issue in report.issues)


def test_preview_uses_no_credentials_or_network(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    result = _engine(tmp_path, env=_env()).build_preview("smcbot-test-local-001", "BUY", "MARKET", 0.001, config_path=str(path))

    assert result.status == "PASS"
    assert result.decision == "ORDER_TEST_PREVIEW_VALID"
    assert result.credentials_inspected is False
    assert result.public_server_time_request_used is False
    assert result.test_order_request_transmitted is False
    assert result.actual_order_submitted is False
    assert result.preview.estimated_notional is None
    assert result.preview.exchange_filters_valid is None
    assert result.preview.notional_validation_status == "NOT_EVALUATED"
    assert result.preview.exchange_filter_validation_status == "NOT_EVALUATED"
    assert result.preview.transmission_ready is False


def test_submit_without_confirmation_blocks_before_credentials_or_network(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    result = _engine(tmp_path, env=_env()).submit_test_order("smcbot-test-submit-001", "BUY", "MARKET", 0.001, config_path=str(path))

    assert result.status == "WARNING"
    assert result.decision == "NETWORK_CONFIRMATION_REQUIRED"
    assert result.credentials_inspected is False
    assert result.public_server_time_request_used is False
    assert result.signature_generated is False
    assert result.test_order_request_transmitted is False


def test_submit_with_missing_credentials_warns_without_network(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    result = _engine(tmp_path, env={}).submit_test_order("smcbot-test-submit-002", "BUY", "MARKET", 0.001, confirmation="CONFIRM_TESTNET_ORDER_TEST", config_path=str(path))

    assert result.status == "WARNING"
    assert result.decision == "CREDENTIALS_NOT_CONFIGURED"
    assert result.credentials_inspected is True
    assert result.public_server_time_request_used is False
    assert result.test_order_request_transmitted is False


def test_engaged_durable_kill_switch_blocks_order_test_post_before_transport(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls: list[object] = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("engaged kill switch must block before Binance transport")

    result = _engine(
        tmp_path,
        env=_env("ENGAGED"),
        http_get=forbidden,
        authenticated_post=forbidden,
    ).submit_test_order(
        "smcbot-test-engaged-001",
        "BUY",
        "MARKET",
        0.001,
        confirmation="CONFIRM_TESTNET_ORDER_TEST",
        config_path=str(path),
    )

    assert result.status == "FAIL"
    assert result.test_order_request_transmitted is False
    assert calls == []


@pytest.mark.parametrize("transition_name", ["kill_switch", "runtime"])
def test_order_test_rechecks_authorization_immediately_before_signed_post(
    tmp_path: Path,
    transition_name: str,
) -> None:
    path = _write_config(tmp_path)
    env = _env()
    post_calls: list[object] = []

    def transitioning_get(url, timeout):
        if url.endswith("/fapi/v1/time"):
            if transition_name == "kill_switch":
                from infrastructure.persistence.kill_switch_persistence import KillSwitchPersistence

                persistence = KillSwitchPersistence(env=env)
                persistence.ensure_available()
                persistence.engage()
                persistence.close()
            else:
                Path(env["ICT_LIVE_EXECUTION_RUNTIME_CONFIG"]).write_text(
                    json.dumps({"live_trading_enabled": False, "dry_run": False}), encoding="utf-8"
                )
        return _http_get(url, timeout)

    def forbidden_post(*args, **kwargs):
        post_calls.append((args, kwargs))
        raise AssertionError("final authorization denial must precede signing and POST")

    result = _engine(
        tmp_path,
        env=env,
        http_get=transitioning_get,
        authenticated_post=forbidden_post,
        now_ms_provider=lambda: 123,
    ).submit_test_order(
        "smcbot-test-boundary-001",
        "BUY",
        "MARKET",
        0.001,
        confirmation="CONFIRM_TESTNET_ORDER_TEST",
        config_path=str(path),
    )

    expected = "KILL_SWITCH_ENGAGED" if transition_name == "kill_switch" else "LIVE_TRADING_DISABLED"
    assert result.status == "FAIL"
    assert result.decision == expected
    assert result.reason == LiveExecutionAuthorizationPolicy.SAFE_MESSAGES[expected]
    assert any(issue.name == expected.lower() and issue.message == result.reason for issue in result.issues)
    assert post_calls == []
    assert result.signature_generated is False
    assert result.test_order_request_transmitted is False
    assert result.signed_url_exposed is False
    assert result.api_key_exposed is False


def test_order_test_sanitizes_hostile_policy_provider_failure(tmp_path: Path) -> None:
    hostile = "postgresql://user:secret@ connectionString SELECT * FROM traceback X-MBX-APIKEY signed-url rawResponse Authorization secret-token"

    def hostile_factory(**kwargs):
        raise RuntimeError(hostile)

    path = _write_config(tmp_path)
    env = _env()
    policy = LiveExecutionAuthorizationPolicy(env=env, persistence_factory=hostile_factory)
    post_calls: list[object] = []
    result = _engine(
        tmp_path,
        env=env,
        authorization_policy=policy,
        authenticated_post=lambda *args, **kwargs: post_calls.append((args, kwargs)),
    ).submit_test_order(
        "smcbot-test-hostile-001",
        "BUY",
        "MARKET",
        0.001,
        confirmation="CONFIRM_TESTNET_ORDER_TEST",
        config_path=str(path),
    )
    rendered = str(result.to_dict())
    assert result.status == "FAIL"
    assert post_calls == []
    for marker in hostile.split():
        assert marker not in rendered


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("runtime", "EXECUTION_POLICY_UNAVAILABLE"),
        ("factory", "PERSISTENCE_UNAVAILABLE"),
        ("ensure", "PERSISTENCE_UNAVAILABLE"),
        ("kill_switch", "KILL_SWITCH_STATE_UNAVAILABLE"),
        ("recovery", "PERSISTENCE_UNAVAILABLE"),
        ("close", "PERSISTENCE_UNAVAILABLE"),
    ],
)
def test_actual_order_test_engine_sanitizes_policy_provider_failures(
    tmp_path: Path,
    caplog,
    source: str,
    expected: str,
) -> None:
    hostile = "postgresql://user:secret@ connectionString SELECT * FROM traceback X-MBX-APIKEY signed-url rawResponse Authorization secret-token"

    class RuntimeProvider:
        def load(self, config_path: str):
            if source == "runtime":
                raise RuntimeError(hostile)
            return True, False

    class Persistence:
        def __init__(self, **kwargs):
            if source == "factory":
                raise RuntimeError(hostile)

        def ensure_available(self):
            if source == "ensure":
                raise RuntimeError(hostile)

        def has_unresolved_recovery(self, current_pair_id=None):
            if source == "recovery":
                raise RuntimeError(hostile)
            return False

        def close(self):
            if source == "close":
                raise RuntimeError(hostile)

    class Gate:
        def require_released(self):
            if source == "kill_switch":
                raise RuntimeError(hostile)

    def factory(**kwargs):
        return Persistence(**kwargs)

    env = _env()
    policy = LiveExecutionAuthorizationPolicy(
        env=env,
        runtime_provider=RuntimeProvider(),
        kill_switch_gate=Gate(),
        persistence_factory=factory,
    )
    post_calls: list[object] = []
    result = _engine(
        tmp_path,
        env=env,
        authorization_policy=policy,
        authenticated_post=lambda *args, **kwargs: post_calls.append((args, kwargs)),
    ).submit_test_order(
        "smcbot-test-provider-001",
        "BUY",
        "MARKET",
        0.001,
        confirmation="CONFIRM_TESTNET_ORDER_TEST",
        config_path=str(_write_config(tmp_path)),
    )

    rendered = json.dumps(result.to_dict(), sort_keys=True)
    assert result.decision == expected
    assert result.reason == LiveExecutionAuthorizationPolicy.SAFE_MESSAGES[expected]
    assert post_calls == []
    assert result.signature_generated is False
    assert result.signed_url_exposed is False
    assert result.api_key_exposed is False
    assert hostile not in caplog.text
    for marker in hostile.split():
        assert marker not in rendered


def test_actual_order_test_engine_sanitizes_credential_readiness_failure(tmp_path: Path, caplog) -> None:
    hostile = "postgresql://user:secret@ connectionString SELECT * FROM traceback X-MBX-APIKEY signed-url rawResponse Authorization secret-token"

    class CredentialFailureClient:
        def inspect_credentials(self):
            raise RuntimeError(hostile)

    engine = _engine(tmp_path, env=_env(), authenticated_post=lambda *args, **kwargs: pytest.fail("POST forbidden"))
    engine._client = lambda config: CredentialFailureClient()

    result = engine.submit_test_order(
        "smcbot-test-credential-001",
        "BUY",
        "MARKET",
        0.001,
        confirmation="CONFIRM_TESTNET_ORDER_TEST",
        config_path=str(_write_config(tmp_path)),
    )

    rendered = json.dumps(result.to_dict(), sort_keys=True)
    assert result.decision == "CREDENTIALS_UNAVAILABLE"
    assert result.reason == "Testnet credential readiness is unavailable."
    assert hostile not in caplog.text
    for marker in hostile.split():
        assert marker not in rendered


def test_confirmed_mock_test_order_is_accepted_without_actual_order_flags(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def authenticated_post(url, body, timeout, headers):
        calls.append((url, body.decode("utf-8"), headers))
        return BinanceOrderTestHTTPResponse(200, "https://demo-fapi.binance.com/fapi/v1/order/test", {}, 2)

    result = _engine(tmp_path, env=_env(), http_get=_http_get, authenticated_post=authenticated_post, now_ms_provider=lambda: 123).submit_test_order(
        "smcbot-test-submit-003",
        "BUY",
        "MARKET",
        0.001,
        confirmation="CONFIRM_TESTNET_ORDER_TEST",
        config_path=str(path),
    )

    assert result.status == "PASS"
    assert result.decision == "ORDER_TEST_ACCEPTED"
    assert result.test_order_request_transmitted is True
    assert result.authenticated_test_request_used is True
    assert result.actual_order_submitted is False
    assert result.actual_order_endpoint_used is False
    assert result.matching_engine_submission is False
    assert result.exchange_order_created is False
    assert result.exchange_order_id is None
    assert result.position_created is False
    assert result.exchange_state_mutated is False
    assert result.public_exchange_info_request_used is True
    assert result.preview.reference_price == Decimal("50000")
    assert result.preview.reference_price_source == "MARK_PRICE"
    assert result.preview.estimated_notional == Decimal("50.000")
    assert result.preview.notional_validation_status == "PASS"
    assert result.preview.exchange_filter_validation_status == "PASS"
    assert result.preview.exchange_filters_valid is True
    assert result.preview.transmission_ready is True
    assert "/fapi/v1/order/test" in calls[0][0]
    assert "/fapi/v1/order?" not in calls[0][0]


def test_non_empty_order_test_response_preserves_sanitized_metadata_before_rejection(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def authenticated_post(url, body, timeout, headers):
        calls.append((url, body.decode("utf-8"), headers))
        return BinanceOrderTestHTTPResponse(
            400,
            "https://demo-fapi.binance.com/fapi/v1/order/test",
            {
                "code": "-1102",
                "msg": "Mandatory parameter was not sent.",
                "nested": {"rawResponse": "RAW_RESPONSE_SENTINEL"},
                "apiKey": "API_KEY_SENTINEL",
                "apiSecret": "API_SECRET_SENTINEL",
                "headers": "HEADER_SENTINEL",
                "signature": "SIGNATURE_SENTINEL",
                "signedQuery": "SIGNED_QUERY_SENTINEL",
                "authenticatedUrl": "AUTHENTICATED_URL_SENTINEL",
                "databaseUrl": "DATABASE_URL_SENTINEL",
                "sql": "SQL_SENTINEL",
                "traceback": "TRACEBACK_SENTINEL",
            },
            320,
            "application/json",
        )

    result = _engine(tmp_path, env=_env(), http_get=_http_get, authenticated_post=authenticated_post, now_ms_provider=lambda: 123).submit_test_order(
        "smcbot-test-submit-shape",
        "BUY",
        "MARKET",
        0.001,
        confirmation="CONFIRM_TESTNET_ORDER_TEST",
        config_path=str(path),
    )

    assert result.status == "FAIL"
    assert result.decision == "ORDER_TEST_REJECTED"
    assert result.request_metadata is not None
    assert result.request_metadata.method == "POST"
    assert result.request_metadata.host == "demo-fapi.binance.com"
    assert result.request_metadata.path == "/fapi/v1/order/test"
    assert result.request_metadata.request_transmitted is True
    assert result.request_metadata.response_received is True
    assert result.request_metadata.response_status_code == 400
    assert result.request_metadata.response_body_type == "object"
    assert result.request_metadata.response_byte_count_category == "small"
    assert result.request_metadata.response_content_type_category == "json"
    assert result.request_metadata.binance_error_code == "-1102"
    assert result.request_metadata.binance_error_message == "Mandatory parameter was not sent."
    assert result.request_metadata.retry_count == 0
    assert result.request_metadata.timestamp == 0
    assert result.signature_generated is True
    assert result.authenticated_transport_invoked is True
    assert result.test_order_request_transmitted is True
    assert result.authenticated_test_request_used is True
    assert result.actual_order_endpoint_used is False
    assert result.order_cancelled is False
    assert len(calls) == 1
    assert "/fapi/v1/order/test" in calls[0][0]
    issue = next(issue for issue in result.issues if issue.name == "order_test_response_shape_invalid")
    assert issue.details["http_status_code"] == 400
    assert issue.details["http_method"] == "POST"
    assert issue.details["final_allowed_host"] == "demo-fapi.binance.com"
    assert issue.details["allowed_path"] == "/fapi/v1/order/test"
    assert issue.details["request_transmitted"] is True
    assert issue.details["response_received"] is True
    assert issue.details["retry_count"] == 0
    assert issue.details["body_type"] == "object"
    assert issue.details["byte_count_category"] == "small"
    assert issue.details["content_type_category"] == "json"
    assert issue.details["binance_error_code"] == "-1102"
    assert issue.details["binance_error_message"] == "Mandatory parameter was not sent."
    serialized = json.dumps(result.to_dict(), sort_keys=True)
    for sentinel in (
        "RAW_RESPONSE_SENTINEL",
        "API_KEY_SENTINEL",
        "API_SECRET_SENTINEL",
        "HEADER_SENTINEL",
        "SIGNATURE_SENTINEL",
        "SIGNED_QUERY_SENTINEL",
        "AUTHENTICATED_URL_SENTINEL",
        "DATABASE_URL_SENTINEL",
        "SQL_SENTINEL",
        "TRACEBACK_SENTINEL",
    ):
        assert sentinel not in serialized


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"symbol": "BTCUSDT", "markPrice": "0"}, "mark price"),
        ({"symbol": "BTCUSDT", "markPrice": "-1"}, "mark price"),
        ({"symbol": "BTCUSDT", "markPrice": "NaN"}, "markPrice"),
        ({"symbol": "ETHUSDT", "markPrice": "50000"}, "symbol"),
    ],
)
def test_market_mark_price_failures_block_before_authenticated_transport(tmp_path: Path, payload: dict, message: str) -> None:
    path = _write_config(tmp_path)

    def http_get(url, timeout):
        if url.endswith("/fapi/v1/time"):
            return BinanceOrderTestHTTPResponse(200, url, {"serverTime": 123}, 18)
        if "/fapi/v1/premiumIndex" in url:
            return BinanceOrderTestHTTPResponse(200, url, payload, 40)
        return _http_get(url, timeout)

    result = _engine(tmp_path, env=_env(), http_get=http_get, authenticated_post=lambda *args: (_ for _ in ()).throw(AssertionError("authenticated transport used")), now_ms_provider=lambda: 123).submit_test_order(
        "smcbot-test-submit-004",
        "BUY",
        "MARKET",
        0.001,
        confirmation="CONFIRM_TESTNET_ORDER_TEST",
        config_path=str(path),
    )

    assert result.status == "FAIL"
    assert any(message in issue.message for issue in result.issues)
    assert result.signature_generated is False
    assert result.authenticated_test_request_used is False
    assert result.test_order_request_transmitted is False
    assert result.actual_order_submitted is False


def test_oversized_market_notional_blocks_before_signing(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    def http_get(url, timeout):
        if "/fapi/v1/premiumIndex" in url:
            return BinanceOrderTestHTTPResponse(200, url, {"symbol": "BTCUSDT", "markPrice": "200000"}, 40)
        return _http_get(url, timeout)

    result = _engine(tmp_path, env=_env(), http_get=http_get, authenticated_post=lambda *args: (_ for _ in ()).throw(AssertionError("authenticated transport used")), now_ms_provider=lambda: 123).submit_test_order(
        "smcbot-test-submit-005",
        "BUY",
        "MARKET",
        0.001,
        confirmation="CONFIRM_TESTNET_ORDER_TEST",
        config_path=str(path),
    )

    assert result.status == "FAIL"
    assert result.signature_generated is False
    assert result.test_order_request_transmitted is False
    assert any("maximum" in issue.message for issue in result.issues)


def test_hard_block_diagnostics_blocks_mutating_methods(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    result = _engine(tmp_path).hard_block_diagnostics(str(path))

    assert result.status == "PASS"
    assert result.payload["blocked_methods"]
    assert result.actual_order_submitted is False
