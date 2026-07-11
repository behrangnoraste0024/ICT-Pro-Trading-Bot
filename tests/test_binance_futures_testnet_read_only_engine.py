from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path
from typing import Any

import pytest

from engine.diagnostics.binance_futures_testnet_read_only_engine import BinanceFuturesTestnetReadOnlyEngine
from infrastructure.exchanges.binance_futures_testnet_read_only_client import BinanceReadOnlyHTTPResponse
from models.binance_futures_testnet_read_only import BinanceFuturesTestnetReadOnlyConfig
from tests.test_binance_futures_testnet_adapter_engine import _write_adapter_configs
from tests.test_btc_futures_risk_model_engine import _write_json


def _read_only_config(**overrides: Any) -> dict[str, Any]:
    values = BinanceFuturesTestnetReadOnlyConfig().to_dict()
    values.update(overrides)
    return values


def _write_read_only_configs(tmp_path: Path, **overrides: Any) -> Path:
    _write_adapter_configs(tmp_path)
    path = tmp_path / "configs" / "binance_futures_testnet_read_only.json"
    _write_json(path, _read_only_config(**overrides))
    return path


def _write_read_only_config_only(tmp_path: Path, **overrides: Any) -> Path:
    path = tmp_path / "configs" / "binance_futures_testnet_read_only.json"
    _write_json(path, _read_only_config(**overrides))
    return path


class _FakeRuntimeEngine:
    def validate(self, *args, **kwargs):
        return SimpleNamespace(status="PASS", config=SimpleNamespace(kill_switch_enabled=True))


class _FakeRunnerEngine:
    def validate_config(self, *args, **kwargs):
        return None, [], None


class _FakeValidationEngine:
    def validate(self, *args, **kwargs):
        return SimpleNamespace(status="PASS", config=SimpleNamespace(kill_switch_enabled=True))


def _engine(tmp_path: Path, **kwargs: Any) -> BinanceFuturesTestnetReadOnlyEngine:
    return BinanceFuturesTestnetReadOnlyEngine(
        repo_root=tmp_path,
        runtime_config_engine=_FakeRuntimeEngine(),
        monitoring_engine=_FakeValidationEngine(),
        runner_engine=_FakeRunnerEngine(),
        testnet_adapter_engine=_FakeValidationEngine(),
        futures_feed_engine=_FakeValidationEngine(),
        futures_risk_model_engine=_FakeValidationEngine(),
        futures_paper_position_engine=_FakeValidationEngine(),
        **kwargs,
    )


def _env() -> dict[str, str]:
    return {"BINANCE_FUTURES_TESTNET_API_KEY": "unit-test-key-token", "BINANCE_FUTURES_TESTNET_API_SECRET": "unit-test-private-token"}


def _http_get(url: str, timeout: int):
    return BinanceReadOnlyHTTPResponse(200, "https://demo-fapi.binance.com/fapi/v1/time", {"serverTime": 1000}, 20)


def _auth_get(url: str, timeout: int, headers: dict[str, str]):
    if "/fapi/v3/account" in url:
        payload = {"totalWalletBalance": "100", "assets": [], "positions": [], "canTrade": True}
    elif "/fapi/v3/balance" in url:
        payload = [{"asset": "USDT", "balance": "100", "crossWalletBalance": "90", "crossUnPnl": "1", "availableBalance": "80", "maxWithdrawAmount": "70"}]
    else:
        payload = [{"symbol": "BTCUSDT", "positionAmt": "0", "entryPrice": "0", "markPrice": "60000", "unRealizedProfit": "0", "liquidationPrice": "0"}]
    return BinanceReadOnlyHTTPResponse(200, "https://demo-fapi.binance.com" + url.split("demo-fapi.binance.com", 1)[1].split("?", 1)[0], payload, 100)


def test_default_repo_config_validates_pass() -> None:
    report = BinanceFuturesTestnetReadOnlyEngine(env={}).validate()

    assert report.status == "PASS"
    assert report.config is not None
    assert report.config.feature_enabled is False
    assert report.diagnostics["credentials_inspected"] is False
    assert report.diagnostics["network_used"] is False


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("feature_enabled", True, "feature_enabled"),
        ("automatic_execution_enabled", True, "automatic_execution_enabled"),
        ("explicit_cli_only", False, "explicit_cli_only"),
        ("authenticated_read_only_available", False, "authenticated_read_only_available"),
        ("dry_run_trading_only", False, "dry_run_trading_only"),
        ("testnet_only", False, "testnet_only"),
        ("rest_base_url", "https://fapi.binance.com", "rest_base_url"),
        ("rest_base_url", "http://demo-fapi.binance.com", "rest_base_url"),
        ("rest_base_url", "https://user:pass@demo-fapi.binance.com", "rest_base_url"),
        ("rest_base_url", "https://demo-fapi.binance.com/fapi", "rest_base_url"),
        ("rest_base_url", "https://demo-fapi.binance.com?x=1", "rest_base_url"),
        ("rest_base_url", "https://demo-fapi.binance.com#frag", "rest_base_url"),
        ("rest_base_url", "https://localhost", "rest_base_url"),
        ("rest_base_url", "https://127.0.0.1", "rest_base_url"),
        ("rest_base_url", "https://10.0.0.1", "rest_base_url"),
        ("allowed_hosts", ["demo-fapi.binance.com", "fapi.binance.com"], "allowed_hosts"),
        ("api_key_env_var", "BINANCE_API_KEY", "api_key_env_var"),
        ("api_secret_env_var", "BINANCE_API_SECRET", "api_secret_env_var"),
        ("allowed_http_methods", ["GET", "POST"], "allowed_http_methods"),
        ("allowed_authenticated_paths", ["/fapi/v3/account", "/fapi/v1/order"], "allowed_authenticated_paths"),
        ("account_path", "/fapi/v2/account", "account_path"),
        ("balance_path", "/fapi/v2/balance", "balance_path"),
        ("position_risk_path", "/fapi/v2/positionRisk", "position_risk_path"),
        ("server_time_path", "/api/v3/time", "server_time_path"),
        ("require_explicit_network_confirmation", False, "require_explicit_network_confirmation"),
        ("network_confirmation_phrase", "", "network_confirmation_phrase"),
        ("max_authenticated_fetch_retries", 1, "max_authenticated_fetch_retries"),
        ("request_timeout_seconds", 0, "request_timeout_seconds"),
        ("recv_window_ms", 20000, "recv_window_ms"),
        ("maximum_clock_skew_ms", 6000, "maximum_clock_skew_ms"),
        ("allow_automatic_authenticated_requests", True, "allow_automatic_authenticated_requests"),
        ("allow_background_authenticated_polling", True, "allow_background_authenticated_polling"),
        ("allow_runner_authenticated_requests", True, "allow_runner_authenticated_requests"),
        ("allow_monitoring_authenticated_requests", True, "allow_monitoring_authenticated_requests"),
        ("allow_order_query", True, "allow_order_query"),
        ("allow_trade_query", True, "allow_trade_query"),
        ("allow_income_query", True, "allow_income_query"),
        ("allow_open_order_query", True, "allow_open_order_query"),
        ("allow_testnet_order_submission", True, "allow_testnet_order_submission"),
        ("allow_testnet_order_test_submission", True, "allow_testnet_order_test_submission"),
        ("allow_testnet_order_cancellation", True, "allow_testnet_order_cancellation"),
        ("allow_testnet_order_modification", True, "allow_testnet_order_modification"),
        ("allow_testnet_position_creation", True, "allow_testnet_position_creation"),
        ("allow_testnet_position_close", True, "allow_testnet_position_close"),
        ("allow_testnet_leverage_change", True, "allow_testnet_leverage_change"),
        ("allow_testnet_margin_mode_change", True, "allow_testnet_margin_mode_change"),
        ("allow_testnet_position_mode_change", True, "allow_testnet_position_mode_change"),
        ("allow_testnet_multi_assets_mode_change", True, "allow_testnet_multi_assets_mode_change"),
        ("allow_testnet_position_margin_change", True, "allow_testnet_position_margin_change"),
        ("allow_user_data_stream", True, "allow_user_data_stream"),
        ("allow_listen_key", True, "allow_listen_key"),
        ("allow_websocket_connection", True, "allow_websocket_connection"),
        ("allow_production_endpoint", True, "allow_production_endpoint"),
        ("allow_production_credentials", True, "allow_production_credentials"),
        ("allow_real_funds", True, "allow_real_funds"),
        ("allow_raw_authenticated_response_print", True, "allow_raw_authenticated_response_print"),
        ("allow_raw_authenticated_response_persistence", True, "allow_raw_authenticated_response_persistence"),
        ("allow_authenticated_header_logging", True, "allow_authenticated_header_logging"),
        ("allow_signature_logging", True, "allow_signature_logging"),
        ("allow_signed_url_logging", True, "allow_signed_url_logging"),
        ("allow_futures_paper_state_mutation", True, "allow_futures_paper_state_mutation"),
        ("allow_spot_paper_account_state_mutation", True, "allow_spot_paper_account_state_mutation"),
        ("allow_runner_state_mutation", True, "allow_runner_state_mutation"),
        ("allow_execution_state_mutation", True, "allow_execution_state_mutation"),
        ("allow_exchange_state_mutation", True, "allow_exchange_state_mutation"),
        ("symbol", "ETH/USDT", "symbol"),
        ("exchange_symbol", "ETHUSDT", "exchange_symbol"),
        ("market_type", "spot", "market_type"),
        ("futures_contract_type", "COIN_PERP", "futures_contract_type"),
        ("report_export_dir", "../reports", "report_export_dir"),
    ],
)
def test_config_validation_blocks_unsafe_values(tmp_path: Path, field: str, value: Any, issue: str) -> None:
    path = _write_read_only_config_only(tmp_path, **{field: value})

    report = _engine(tmp_path, env={}).validate(str(path))

    assert report.status == "FAIL"
    assert issue in {item.name for item in report.issues}


def test_auth_action_without_confirmation_uses_no_credentials_or_network(tmp_path: Path) -> None:
    path = _write_read_only_config_only(tmp_path)
    called = {"http": False, "auth": False}

    def http_get(*args):
        called["http"] = True
        raise AssertionError("public network should not run")

    def auth_get(*args):
        called["auth"] = True
        raise AssertionError("authenticated network should not run")

    result = _engine(tmp_path, http_get=http_get, authenticated_get=auth_get, env=_env()).fetch_account(config_path=str(path))

    assert result.status == "WARNING"
    assert result.decision == "NETWORK_CONFIRMATION_REQUIRED"
    assert result.credentials_inspected is False
    assert called == {"http": False, "auth": False}


def test_wrong_confirmation_is_rejected_before_credentials(tmp_path: Path) -> None:
    path = _write_read_only_config_only(tmp_path)

    result = _engine(tmp_path, env=_env()).fetch_account("WRONG", str(path))

    assert result.decision == "NETWORK_CONFIRMATION_REQUIRED"
    assert result.credentials_inspected is False


def test_missing_and_partial_credentials_warn_without_network(tmp_path: Path) -> None:
    path = _write_read_only_config_only(tmp_path)
    missing = _engine(tmp_path, env={}).fetch_account("CONFIRM_TESTNET_READ_ONLY", str(path))
    partial = _engine(tmp_path, env={"BINANCE_FUTURES_TESTNET_API_KEY": "key"}).fetch_account("CONFIRM_TESTNET_READ_ONLY", str(path))

    assert missing.decision == "CREDENTIALS_NOT_CONFIGURED"
    assert partial.decision == "CREDENTIALS_INCOMPLETE"
    assert missing.request_transmitted is False
    assert partial.request_transmitted is False


def test_complete_credentials_allow_mocked_account_balance_position_and_snapshot(tmp_path: Path) -> None:
    path = _write_read_only_config_only(tmp_path)
    engine = _engine(tmp_path, http_get=_http_get, authenticated_get=_auth_get, env=_env(), now_ms_provider=lambda: 1001)

    account = engine.fetch_account("CONFIRM_TESTNET_READ_ONLY", str(path))
    balance = engine.fetch_balance("USDT", "CONFIRM_TESTNET_READ_ONLY", str(path))
    position = engine.fetch_position_risk("BTCUSDT", "CONFIRM_TESTNET_READ_ONLY", str(path))
    snapshot = engine.fetch_account_snapshot("CONFIRM_TESTNET_READ_ONLY", str(path))

    assert account.status == "PASS"
    assert balance.status == "PASS"
    assert position.status == "PASS"
    assert snapshot.status == "PASS"
    assert account.account_summary is not None
    assert balance.balance_summary is not None
    assert position.position_summary is not None
    assert snapshot.account_summary is not None
    assert snapshot.payload["snapshot_complete"] is True
    for result in (account, balance, position, snapshot):
        text = json.dumps(result.to_dict())
        assert "unit-test-key-token" not in text
        assert "unit-test-private-token" not in text
        assert "X-MBX-APIKEY" not in text
        assert result.raw_response_persisted is False
        assert result.order_submitted is False
        assert result.leverage_changed is False
        assert result.futures_paper_state_mutated is False


def test_generic_production_credentials_are_ignored(tmp_path: Path) -> None:
    path = _write_read_only_config_only(tmp_path)
    env = {"BINANCE_API_KEY": "generic-key-token", "BINANCE_API_SECRET": "generic-private-token"}

    result = _engine(tmp_path, env=env).check_credentials(str(path))

    assert result.decision == "CREDENTIALS_NOT_CONFIGURED"
    assert "generic-key-token" not in json.dumps(result.to_dict())
    assert "generic-private-token" not in json.dumps(result.to_dict())


def test_server_time_failure_blocks_authenticated_request(tmp_path: Path) -> None:
    path = _write_read_only_config_only(tmp_path)
    called = False

    def auth_get(*args):
        nonlocal called
        called = True
        raise AssertionError("authenticated network should not run")

    result = _engine(
        tmp_path,
        http_get=lambda *args: BinanceReadOnlyHTTPResponse(200, "https://demo-fapi.binance.com/fapi/v1/time", {"bad": 1}),
        authenticated_get=auth_get,
        env=_env(),
    ).fetch_account("CONFIRM_TESTNET_READ_ONLY", str(path))

    assert result.status == "FAIL"
    assert called is False


def test_clock_skew_blocks_authenticated_request(tmp_path: Path) -> None:
    path = _write_read_only_config_only(tmp_path)
    result = _engine(tmp_path, http_get=_http_get, authenticated_get=_auth_get, env=_env(), now_ms_provider=lambda: 100000).fetch_account("CONFIRM_TESTNET_READ_ONLY", str(path))

    assert result.status == "FAIL"
    assert "clock_skew_exceeded" in {issue.name for issue in result.issues}


def test_hard_block_diagnostics_keeps_all_mutations_false(tmp_path: Path) -> None:
    path = _write_read_only_config_only(tmp_path)

    result = _engine(tmp_path, env={}).hard_block_diagnostics(str(path))

    assert result.status == "PASS"
    assert len(result.payload["blocked_methods"]) == 16
    assert result.order_submitted is False
    assert result.order_cancelled is False
    assert result.websocket_opened is False
