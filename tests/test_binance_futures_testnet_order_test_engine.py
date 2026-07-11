from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from engine.diagnostics.binance_futures_testnet_order_test_engine import BinanceFuturesTestnetOrderTestEngine
from infrastructure.exchanges.binance_futures_testnet_order_test_client import BinanceOrderTestHTTPResponse
from models.binance_futures_testnet_order_test import BinanceFuturesTestnetOrderTestConfig


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


def _env() -> dict[str, str]:
    return {"BINANCE_FUTURES_TESTNET_API_KEY": "unit-test-key-token", "BINANCE_FUTURES_TESTNET_API_SECRET": "unit-test-private-token"}


def _http_get(url, timeout):
    if url.endswith("/fapi/v1/time"):
        return BinanceOrderTestHTTPResponse(200, url, {"serverTime": 123}, 18)
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
    assert "/fapi/v1/order/test" in calls[0][0]
    assert "/fapi/v1/order?" not in calls[0][0]


def test_hard_block_diagnostics_blocks_mutating_methods(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    result = _engine(tmp_path).hard_block_diagnostics(str(path))

    assert result.status == "PASS"
    assert result.payload["blocked_methods"]
    assert result.actual_order_submitted is False
