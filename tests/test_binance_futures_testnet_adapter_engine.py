from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.diagnostics.binance_futures_testnet_adapter_engine import BinanceFuturesTestnetAdapterEngine
from infrastructure.exchanges.binance_futures_testnet_adapter import BinancePublicResponse
from models.binance_futures_testnet_adapter import BinanceFuturesTestnetAdapterConfig
from tests.test_btc_futures_paper_position_engine import _write_configs as _write_position_configs
from tests.test_btc_futures_risk_model_engine import _write_json


def _adapter_config(**overrides: Any) -> dict[str, Any]:
    values = BinanceFuturesTestnetAdapterConfig().to_dict()
    values.update(overrides)
    return values


def _write_adapter_configs(tmp_path: Path, **overrides: Any) -> Path:
    _write_position_configs(tmp_path)
    path = tmp_path / "configs" / "binance_futures_testnet_adapter.json"
    _write_json(path, _adapter_config(**overrides))
    return path


def test_default_repo_config_validates_pass() -> None:
    report = BinanceFuturesTestnetAdapterEngine(env={}).validate()

    assert report.status == "PASS"
    assert report.config is not None
    assert report.config.adapter_enabled is False
    assert report.config.rest_base_url == "https://demo-fapi.binance.com"


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("adapter_enabled", True, "adapter_enabled"),
        ("connection_mode", "enabled", "connection_mode"),
        ("testnet_only", False, "testnet_only"),
        ("dry_run_only", False, "dry_run_only"),
        ("rest_base_url", "https://fapi.binance.com", "rest_base_url"),
        ("rest_base_url", "http://demo-fapi.binance.com", "rest_base_url"),
        ("rest_base_url", "https://demo-fapi.binance.com/fapi", "rest_base_url"),
        ("rest_base_url", "https://demo-fapi.binance.com?x=1", "rest_base_url"),
        ("rest_base_url", "https://127.0.0.1", "rest_base_url"),
        ("allowed_hosts", ["demo-fapi.binance.com", "fapi.binance.com"], "allowed_hosts"),
        ("api_key_env_var", "BINANCE_API_KEY", "api_key_env_var"),
        ("api_secret_env_var", "BINANCE_API_SECRET", "api_secret_env_var"),
        ("recv_window_ms", 20000, "recv_window_ms"),
        ("maximum_recv_window_ms", 20000, "recv_window_ms"),
        ("allowed_public_paths", ["/fapi/v1/order"], "allowed_public_paths"),
        ("allowed_signed_preview_paths", ["/fapi/v1/order"], "allowed_signed_preview_paths"),
        ("allow_authenticated_testnet_request", True, "allow_authenticated_testnet_request"),
        ("allow_authenticated_account_read", True, "allow_authenticated_account_read"),
        ("allow_authenticated_balance_read", True, "allow_authenticated_balance_read"),
        ("allow_authenticated_position_read", True, "allow_authenticated_position_read"),
        ("allow_testnet_order_submission", True, "allow_testnet_order_submission"),
        ("allow_testnet_order_cancellation", True, "allow_testnet_order_cancellation"),
        ("allow_testnet_leverage_change", True, "allow_testnet_leverage_change"),
        ("allow_testnet_margin_mode_change", True, "allow_testnet_margin_mode_change"),
        ("allow_user_data_stream", True, "allow_user_data_stream"),
        ("allow_websocket_connection", True, "allow_websocket_connection"),
        ("allow_production_endpoint", True, "allow_production_endpoint"),
        ("allow_production_credentials", True, "allow_production_credentials"),
        ("allow_real_funds", True, "allow_real_funds"),
        ("allow_futures_paper_state_mutation", True, "allow_futures_paper_state_mutation"),
        ("allow_runner_state_mutation", True, "allow_runner_state_mutation"),
        ("allow_execution_state_mutation", True, "allow_execution_state_mutation"),
        ("allow_exchange_state_mutation", True, "allow_exchange_state_mutation"),
        ("report_export_dir", "../reports", "report_export_dir"),
        ("symbol", "ETH/USDT", "symbol"),
        ("exchange_symbol", "ETHUSDT", "exchange_symbol"),
        ("market_type", "spot", "market_type"),
    ],
)
def test_config_validation_blocks_unsafe_values(tmp_path: Path, field: str, value: Any, issue: str) -> None:
    path = _write_adapter_configs(tmp_path, **{field: value})

    report = BinanceFuturesTestnetAdapterEngine(repo_root=tmp_path, env={}).validate(str(path))

    assert report.status == "FAIL"
    assert issue in {item.name for item in report.issues}


def test_public_ping_uses_injected_public_get_only(tmp_path: Path) -> None:
    path = _write_adapter_configs(tmp_path)
    calls: list[tuple[str, int]] = []

    def http_get(url: str, timeout: int) -> BinancePublicResponse:
        calls.append((url, timeout))
        return BinancePublicResponse(200, "https://demo-fapi.binance.com/fapi/v1/ping", {})

    result = BinanceFuturesTestnetAdapterEngine(repo_root=tmp_path, http_get=http_get, env={}).ping_testnet(str(path))

    assert result.status == "PASS"
    assert result.public_request_used is True
    assert result.credentials_inspected is False
    assert result.request_transmitted is False
    assert calls == [("https://demo-fapi.binance.com/fapi/v1/ping", 10)]


def test_fetch_server_time_and_exchange_info_are_public_only(tmp_path: Path) -> None:
    path = _write_adapter_configs(tmp_path)

    def http_get(url: str, timeout: int) -> BinancePublicResponse:
        if url.endswith("/fapi/v1/time"):
            return BinancePublicResponse(200, url, {"serverTime": 123})
        return BinancePublicResponse(200, url, {"symbols": [{"symbol": "BTCUSDT"}]})

    engine = BinanceFuturesTestnetAdapterEngine(repo_root=tmp_path, http_get=http_get, env={})

    server_time = engine.fetch_server_time(str(path))
    exchange_info = engine.fetch_exchange_info(str(path))

    assert server_time.status == "PASS"
    assert exchange_info.status == "PASS"
    assert server_time.authenticated_transport_invoked is False
    assert exchange_info.testnet_order_submitted is False


def test_check_credentials_redacts_values(tmp_path: Path) -> None:
    path = _write_adapter_configs(tmp_path)
    env = {"BINANCE_FUTURES_TESTNET_API_KEY": "key-secret-value", "BINANCE_FUTURES_TESTNET_API_SECRET": "secret-value"}

    result = BinanceFuturesTestnetAdapterEngine(repo_root=tmp_path, env=env).check_credentials(str(path))

    assert result.status == "PASS"
    assert result.credentials_inspected is True
    assert result.payload["api_key_length"] == len("key-secret-value")
    assert result.payload["api_secret_length"] == len("secret-value")
    assert "key-secret-value" not in json.dumps(result.to_dict())
    assert "secret-value" not in json.dumps(result.to_dict())


def test_signed_preview_is_local_redacted_and_not_transmitted(tmp_path: Path) -> None:
    path = _write_adapter_configs(tmp_path)
    env = {"BINANCE_FUTURES_TESTNET_API_KEY": "testnet-key-value", "BINANCE_FUTURES_TESTNET_API_SECRET": "super-private-token"}

    result = BinanceFuturesTestnetAdapterEngine(repo_root=tmp_path, env=env).signed_request_preview(
        "/fapi/v2/account",
        {"timestamp": 123, "recvWindow": 5000},
        str(path),
    )

    assert result.status == "PASS"
    assert result.signature_generated is True
    assert result.request_signed is False
    assert result.request_transmitted is False
    assert result.authenticated_transport_invoked is False
    assert result.payload["signature_redacted"].endswith("...REDACTED")
    assert "testnet-key-value" not in json.dumps(result.to_dict())
    assert "super-private-token" not in json.dumps(result.to_dict())


def test_signed_preview_rejects_order_path(tmp_path: Path) -> None:
    path = _write_adapter_configs(tmp_path)

    result = BinanceFuturesTestnetAdapterEngine(repo_root=tmp_path, env={}).signed_request_preview("/fapi/v1/order", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "SIGNING_PREVIEW_REJECTED"
    assert result.request_transmitted is False


def test_order_intent_is_valid_non_executable_and_local(tmp_path: Path) -> None:
    path = _write_adapter_configs(tmp_path)

    result = BinanceFuturesTestnetAdapterEngine(repo_root=tmp_path, env={}).build_order_intent("intent-1", "BUY", "MARKET", 0.001, config_path=str(path))

    assert result.status == "PASS"
    assert result.decision == "ORDER_INTENT_VALID"
    assert result.payload["executable"] is False
    assert result.payload["request_signed"] is False
    assert result.payload["request_transmitted"] is False
    assert result.testnet_order_submitted is False
    assert result.futures_paper_state_mutated is False


@pytest.mark.parametrize(
    ("kwargs", "issue"),
    [
        ({"quantity": 0}, "order_intent_rejected"),
        ({"quantity": 2.0}, "order_intent_rejected"),
        ({"order_type": "LIMIT"}, "order_intent_rejected"),
        ({"order_type": "STOP_MARKET"}, "order_intent_rejected"),
    ],
)
def test_order_intent_invalid_values_fail_safely(tmp_path: Path, kwargs: dict[str, Any], issue: str) -> None:
    path = _write_adapter_configs(tmp_path)
    values = {"intent_id": "intent-1", "side": "BUY", "order_type": "MARKET", "quantity": 0.001, **kwargs}

    result = BinanceFuturesTestnetAdapterEngine(repo_root=tmp_path, env={}).build_order_intent(config_path=str(path), **values)

    assert result.status == "FAIL"
    assert issue in {item.name for item in result.issues}
    assert result.testnet_order_submitted is False


def test_hard_block_diagnostics_keep_authenticated_transport_unavailable(tmp_path: Path) -> None:
    path = _write_adapter_configs(tmp_path)

    result = BinanceFuturesTestnetAdapterEngine(repo_root=tmp_path, env={}).hard_block_diagnostics(str(path))

    assert result.status == "PASS"
    assert result.payload["authenticated_transport_available"] is False
    assert result.payload["testnet_order_transport_available"] is False
    assert set(result.payload["blocked_methods"]) == {
        "submit_order",
        "cancel_order",
        "fetch_account",
        "fetch_balances",
        "fetch_positions",
        "change_leverage",
        "change_margin_mode",
    }
