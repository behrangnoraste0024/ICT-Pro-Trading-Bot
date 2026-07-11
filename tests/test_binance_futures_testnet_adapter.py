from __future__ import annotations

import pytest

from infrastructure.exchanges.binance_futures_testnet_adapter import (
    BinanceFuturesTestnetAdapter,
    BinanceFuturesTestnetOperationBlocked,
    BinancePublicResponse,
)
from models.binance_futures_testnet_adapter import BinanceFuturesTestnetAdapterConfig


def test_public_ping_uses_exact_testnet_host_and_no_credentials() -> None:
    calls = []

    def http_get(url: str, timeout: int):
        calls.append((url, timeout))
        return BinancePublicResponse(200, "https://demo-fapi.binance.com/fapi/v1/ping", {})

    adapter = BinanceFuturesTestnetAdapter(BinanceFuturesTestnetAdapterConfig(), http_get=http_get, env={"BINANCE_FUTURES_TESTNET_API_KEY": "SECRET"})

    result = adapter.ping()

    assert result["ok"] is True
    assert calls == [("https://demo-fapi.binance.com/fapi/v1/ping", 10)]


def test_public_redirect_to_production_is_blocked() -> None:
    def http_get(url: str, timeout: int):
        return BinancePublicResponse(200, "https://fapi.binance.com/fapi/v1/ping", {})

    adapter = BinanceFuturesTestnetAdapter(BinanceFuturesTestnetAdapterConfig(), http_get=http_get)

    with pytest.raises(RuntimeError):
        adapter.ping()


def test_credentials_are_redacted_to_presence_and_lengths() -> None:
    adapter = BinanceFuturesTestnetAdapter(
        BinanceFuturesTestnetAdapterConfig(),
        env={"BINANCE_FUTURES_TESTNET_API_KEY": "abc123", "BINANCE_FUTURES_TESTNET_API_SECRET": "secret456"},
    )

    result = adapter.inspect_credential_presence()

    assert result == {
        "api_key_present": True,
        "api_secret_present": True,
        "api_key_length": 6,
        "api_secret_length": 9,
        "credentials_complete": True,
        "credential_source": "environment",
        "environment_names_valid": True,
    }
    assert "abc123" not in str(result)
    assert "secret456" not in str(result)


def test_signed_preview_redacts_signature_and_never_transmits() -> None:
    adapter = BinanceFuturesTestnetAdapter(
        BinanceFuturesTestnetAdapterConfig(),
        env={"BINANCE_FUTURES_TESTNET_API_SECRET": "secret"},
    )

    result = adapter.build_signed_request_preview("/fapi/v2/account", {"timestamp": 123, "recvWindow": 5000})

    assert result["signature_generated"] is True
    assert result["signature_redacted"].endswith("...REDACTED")
    assert result["request_transmitted"] is False
    assert "secret" not in str(result)


@pytest.mark.parametrize("path", ["/fapi/v1/order", "/fapi/v1/leverage", "/fapi/v1/marginType", "/fapi/v1/listenKey"])
def test_signed_preview_blocks_order_and_mutation_paths(path: str) -> None:
    adapter = BinanceFuturesTestnetAdapter(BinanceFuturesTestnetAdapterConfig())

    with pytest.raises(ValueError):
        adapter.build_signed_request_preview(path, {"timestamp": 123, "recvWindow": 5000})


def test_order_intent_is_non_executable() -> None:
    adapter = BinanceFuturesTestnetAdapter(BinanceFuturesTestnetAdapterConfig())

    result = adapter.build_order_intent("intent-1", "BTCUSDT", "BUY", "MARKET", 0.001)

    assert result["executable"] is False
    assert result["request_signed"] is False
    assert result["request_transmitted"] is False
    assert result["testnet_order_submitted"] is False
    assert result["exchange_order_id"] is None
    assert result["futures_paper_state_mutated"] is False


@pytest.mark.parametrize("method", ["submit_order", "cancel_order", "fetch_account", "fetch_balances", "fetch_positions", "change_leverage", "change_margin_mode"])
def test_authenticated_methods_are_hard_blocked(method: str) -> None:
    adapter = BinanceFuturesTestnetAdapter(BinanceFuturesTestnetAdapterConfig(), http_get=lambda *args: pytest.fail("HTTP should not be called"))

    with pytest.raises(BinanceFuturesTestnetOperationBlocked):
        getattr(adapter, method)()
