from __future__ import annotations

import json

import pytest

from infrastructure.exchanges.binance_futures_testnet_read_only_client import (
    BinanceFuturesTestnetReadOnlyClient,
    BinanceFuturesTestnetReadOnlyOperationBlocked,
    BinanceReadOnlyHTTPResponse,
)
from models.binance_futures_testnet_read_only import BinanceFuturesTestnetReadOnlyConfig


def _env() -> dict[str, str]:
    return {"BINANCE_FUTURES_TESTNET_API_KEY": "unit-test-key-token", "BINANCE_FUTURES_TESTNET_API_SECRET": "unit-test-private-token"}


def _account_payload() -> dict:
    return {
        "feeTier": 0,
        "canTrade": True,
        "canDeposit": True,
        "canWithdraw": False,
        "updateTime": 123,
        "multiAssetsMargin": False,
        "totalInitialMargin": "1.1",
        "totalMaintMargin": "2.2",
        "totalWalletBalance": "100.0",
        "totalUnrealizedProfit": "3.0",
        "totalMarginBalance": "103.0",
        "totalPositionInitialMargin": "1.0",
        "totalOpenOrderInitialMargin": "0.0",
        "totalCrossWalletBalance": "100.0",
        "totalCrossUnPnl": "3.0",
        "availableBalance": "99.0",
        "maxWithdrawAmount": "98.0",
        "assets": [{"asset": "USDT", "accountAlias": "hidden"}],
        "positions": [{"symbol": "BTCUSDT"}],
    }


def _balance_payload() -> list[dict]:
    return [
        {"asset": "BTC", "balance": "99"},
        {
            "asset": "USDT",
            "accountAlias": "hidden",
            "balance": "100.0",
            "crossWalletBalance": "90.0",
            "crossUnPnl": "1.0",
            "availableBalance": "80.0",
            "maxWithdrawAmount": "70.0",
            "marginAvailable": True,
            "updateTime": 456,
        },
    ]


def _position_payload(amount: str = "0.1") -> list[dict]:
    return [
        {
            "symbol": "BTCUSDT",
            "positionSide": "BOTH",
            "positionAmt": amount,
            "entryPrice": "60000",
            "breakEvenPrice": "60100",
            "markPrice": "61000",
            "unRealizedProfit": "100",
            "liquidationPrice": "40000",
            "isolatedMargin": "10",
            "notional": "6100",
            "marginAsset": "USDT",
            "isolatedWallet": "20",
            "initialMargin": "100",
            "maintMargin": "5",
            "positionInitialMargin": "100",
            "openOrderInitialMargin": "0",
            "adl": 1,
            "updateTime": 789,
        }
    ]


def test_server_time_uses_public_get_without_credentials() -> None:
    calls = []

    def http_get(url: str, timeout: int):
        calls.append((url, timeout))
        return BinanceReadOnlyHTTPResponse(200, "https://demo-fapi.binance.com/fapi/v1/time", {"serverTime": 1000})

    client = BinanceFuturesTestnetReadOnlyClient(BinanceFuturesTestnetReadOnlyConfig(), http_get=http_get, env=_env(), now_ms_provider=lambda: 1001)

    result = client.fetch_server_time()

    assert result["server_time"] == 1000
    assert result["clock_skew_ms"] == 1
    assert calls == [("https://demo-fapi.binance.com/fapi/v1/time", 10)]


def test_authenticated_account_get_is_signed_get_and_sanitized() -> None:
    calls = []

    def auth_get(url: str, timeout: int, headers: dict[str, str]):
        calls.append((url, timeout, headers))
        return BinanceReadOnlyHTTPResponse(200, "https://demo-fapi.binance.com/fapi/v3/account", _account_payload(), 100)

    client = BinanceFuturesTestnetReadOnlyClient(BinanceFuturesTestnetReadOnlyConfig(), authenticated_get=auth_get, env=_env())

    summary, metadata = client.fetch_account(123)

    assert summary.total_wallet_balance == 100.0
    assert summary.asset_count == 1
    assert summary.position_count == 1
    assert summary.raw_response_included is False
    assert metadata.method == "GET"
    assert metadata.path == "/fapi/v3/account"
    assert metadata.api_key_header_used is True
    assert metadata.raw_url_exposed is False
    assert "signature=" in calls[0][0]
    assert calls[0][2] == {"X-MBX-APIKEY": "unit-test-key-token"}
    assert "unit-test-private-token" not in json.dumps(summary.to_dict())


def test_balance_selects_usdt_and_hides_other_assets() -> None:
    client = BinanceFuturesTestnetReadOnlyClient(
        BinanceFuturesTestnetReadOnlyConfig(),
        authenticated_get=lambda *args: BinanceReadOnlyHTTPResponse(200, "https://demo-fapi.binance.com/fapi/v3/balance", _balance_payload(), 100),
        env=_env(),
    )

    summary, _ = client.fetch_balance("USDT", 123)

    assert summary.asset == "USDT"
    assert summary.wallet_balance == 100.0
    assert summary.account_alias_present is True
    assert "BTC" not in json.dumps(summary.to_dict())


def test_missing_usdt_balance_can_return_zero_summary() -> None:
    client = BinanceFuturesTestnetReadOnlyClient(
        BinanceFuturesTestnetReadOnlyConfig(),
        authenticated_get=lambda *args: BinanceReadOnlyHTTPResponse(200, "https://demo-fapi.binance.com/fapi/v3/balance", [], 2),
        env=_env(),
    )

    summary, _ = client.fetch_balance("USDT", 123)

    assert summary.asset == "USDT"
    assert summary.wallet_balance == 0.0


def test_position_risk_is_btcusdt_only_and_parses_position() -> None:
    client = BinanceFuturesTestnetReadOnlyClient(
        BinanceFuturesTestnetReadOnlyConfig(),
        authenticated_get=lambda *args: BinanceReadOnlyHTTPResponse(200, "https://demo-fapi.binance.com/fapi/v3/positionRisk", _position_payload("-0.2"), 100),
        env=_env(),
    )

    summary, metadata = client.fetch_position_risk("BTCUSDT", 123)

    assert summary.symbol == "BTCUSDT"
    assert summary.position_amount == -0.2
    assert summary.has_open_position is True
    assert metadata.parameter_names == ["recvWindow", "symbol", "timestamp"]


def test_other_position_symbol_is_rejected_before_transport() -> None:
    called = False

    def auth_get(*args):
        nonlocal called
        called = True
        raise AssertionError("transport should not run")

    client = BinanceFuturesTestnetReadOnlyClient(BinanceFuturesTestnetReadOnlyConfig(), authenticated_get=auth_get, env=_env())

    with pytest.raises(ValueError):
        client.fetch_position_risk("ETHUSDT", 123)
    assert called is False


def test_redirect_to_production_is_blocked() -> None:
    client = BinanceFuturesTestnetReadOnlyClient(
        BinanceFuturesTestnetReadOnlyConfig(),
        authenticated_get=lambda *args: BinanceReadOnlyHTTPResponse(200, "https://fapi.binance.com/fapi/v3/account", _account_payload(), 100),
        env=_env(),
    )

    with pytest.raises(RuntimeError):
        client.fetch_account(123)


@pytest.mark.parametrize("method", ["submit_order", "test_submit_order", "cancel_order", "modify_order", "fetch_open_orders", "fetch_all_orders", "fetch_trades", "fetch_income", "change_leverage", "change_margin_mode", "change_position_mode", "change_multi_assets_mode", "change_position_margin", "create_listen_key", "open_user_stream", "open_websocket"])
def test_mutation_and_order_methods_are_hard_blocked(method: str) -> None:
    client = BinanceFuturesTestnetReadOnlyClient(BinanceFuturesTestnetReadOnlyConfig(), authenticated_get=lambda *args: pytest.fail("transport should not run"), env=_env())

    with pytest.raises(BinanceFuturesTestnetReadOnlyOperationBlocked):
        getattr(client, method)()
