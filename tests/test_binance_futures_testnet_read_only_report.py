from __future__ import annotations

from engine.diagnostics.binance_futures_testnet_read_only_engine import BinanceFuturesTestnetReadOnlyEngine
from infrastructure.exchanges.binance_futures_testnet_read_only_client import BinanceReadOnlyHTTPResponse
from reporting.binance_futures_testnet_read_only_report import (
    format_binance_futures_testnet_read_only_result,
    format_binance_futures_testnet_read_only_validation_report,
)


def test_validation_report_shows_read_only_boundaries() -> None:
    report = BinanceFuturesTestnetReadOnlyEngine(env={}).validate()

    text = format_binance_futures_testnet_read_only_validation_report(report)

    assert "BINANCE FUTURES TESTNET READ-ONLY VALIDATION" in text
    assert "Feature Enabled              : false" in text
    assert "Allowed Methods              : ['GET']" in text
    assert "Order Submission             : false" in text
    assert "Raw Response Persistence     : false" in text


def test_result_report_hides_credentials_and_raw_payloads() -> None:
    def http_get(*args):
        return BinanceReadOnlyHTTPResponse(200, "https://demo-fapi.binance.com/fapi/v1/time", {"serverTime": 1000}, 10)

    def auth_get(*args):
        return BinanceReadOnlyHTTPResponse(200, "https://demo-fapi.binance.com/fapi/v3/balance", [{"asset": "USDT", "accountAlias": "hidden", "balance": "1", "crossWalletBalance": "1", "crossUnPnl": "0", "availableBalance": "1", "maxWithdrawAmount": "1"}], 100)

    result = BinanceFuturesTestnetReadOnlyEngine(
        http_get=http_get,
        authenticated_get=auth_get,
        env={"BINANCE_FUTURES_TESTNET_API_KEY": "unit-test-key-token", "BINANCE_FUTURES_TESTNET_API_SECRET": "unit-test-private-token"},
        now_ms_provider=lambda: 1000,
    ).fetch_balance("USDT", "CONFIRM_TESTNET_READ_ONLY")

    text = format_binance_futures_testnet_read_only_result(result)

    assert "BINANCE FUTURES TESTNET READ-ONLY DIAGNOSTIC" in text
    assert "BALANCE_READ_SUCCESS" in text
    assert "unit-test-key-token" not in text
    assert "unit-test-private-token" not in text
    assert "hidden" not in text
    assert "Signature Exposed            : false" in text
    assert "Raw Response Persisted       : false" in text
