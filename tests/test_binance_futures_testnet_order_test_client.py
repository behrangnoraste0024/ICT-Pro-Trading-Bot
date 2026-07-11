from __future__ import annotations

import pytest
from decimal import Decimal

from infrastructure.exchanges.binance_futures_testnet_order_test_client import (
    BinanceFuturesTestnetOrderOperationBlocked,
    BinanceFuturesTestnetOrderTestClient,
    BinanceOrderTestHTTPResponse,
)
from models.binance_futures_testnet_order_test import BinanceFuturesTestnetOrderTestConfig


def _env() -> dict[str, str]:
    return {"BINANCE_FUTURES_TESTNET_API_KEY": "unit-test-key-token", "BINANCE_FUTURES_TESTNET_API_SECRET": "unit-test-private-token"}


def _exchange_info() -> dict:
    return {
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
    }


def test_market_preview_is_local_and_non_executable() -> None:
    client = BinanceFuturesTestnetOrderTestClient(BinanceFuturesTestnetOrderTestConfig(), env={})

    preview = client.build_order_test_preview("smcbot-test-market-001", "BUY", "MARKET", 0.001)

    assert preview.order_type == "MARKET"
    assert preview.price is None
    assert preview.estimated_notional is None
    assert preview.exchange_filters_valid is None
    assert preview.notional_validation_status == "NOT_EVALUATED"
    assert preview.exchange_filter_validation_status == "NOT_EVALUATED"
    assert preview.transmission_ready is False
    assert preview.executable is False
    assert preview.actual_order_endpoint_used is False
    assert preview.exchange_order_created is False
    assert preview.position_created is False


def test_limit_preview_requires_price_and_time_in_force() -> None:
    client = BinanceFuturesTestnetOrderTestClient(BinanceFuturesTestnetOrderTestConfig(), env={})

    preview = client.build_order_test_preview("smcbot-test-limit-001", "BUY", "LIMIT", 0.001, price=50000, time_in_force="GTC")

    assert preview.order_type == "LIMIT"
    assert preview.price == Decimal("50000")
    assert preview.time_in_force == "GTC"
    assert preview.estimated_notional == Decimal("50.000")
    assert preview.exchange_filters_valid is None
    assert preview.exchange_filter_validation_status == "NOT_EVALUATED"
    assert preview.transmission_ready is False


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"side": "HOLD"}, "side"),
        ({"order_type": "STOP"}, "order_type"),
        ({"quantity": 0}, "quantity"),
        ({"quantity": 0.02}, "maximum"),
        ({"client_order_id": "bad-prefix-001"}, "prefix"),
        ({"client_order_id": "smcbot-test-unsafe!"}, "unsafe"),
        ({"order_type": "MARKET", "price": 50000}, "MARKET"),
        ({"order_type": "LIMIT", "price": None, "time_in_force": "GTC"}, "LIMIT"),
        ({"order_type": "LIMIT", "price": 50000, "time_in_force": None}, "LIMIT"),
    ],
)
def test_invalid_preview_parameters_are_rejected(kwargs: dict, message: str) -> None:
    client = BinanceFuturesTestnetOrderTestClient(BinanceFuturesTestnetOrderTestConfig(), env={})
    params = {"client_order_id": "smcbot-test-ok-001", "side": "BUY", "order_type": "MARKET", "quantity": 0.001}
    params.update(kwargs)

    with pytest.raises(ValueError, match=message):
        client.build_order_test_preview(**params)


def test_exchange_filters_are_parsed_and_used() -> None:
    client = BinanceFuturesTestnetOrderTestClient(BinanceFuturesTestnetOrderTestConfig(), env={})
    filters = client.parse_exchange_filters(_exchange_info())

    assert filters.symbol == "BTCUSDT"
    assert filters.price_tick_size == Decimal("0.10")
    assert filters.min_qty == Decimal("0.001")
    assert filters.market_min_qty == Decimal("0.001")
    assert filters.raw_response_included is False
    preview = client.build_order_test_preview("smcbot-test-filter-001", "BUY", "LIMIT", 0.001, price=50000, time_in_force="GTC", exchange_filters=filters)
    assert preview.exchange_filters_valid is True
    assert preview.exchange_filter_validation_status == "PASS"
    assert preview.notional_validation_status == "PASS"
    assert preview.transmission_ready is True


def test_market_preview_with_filters_requires_mark_price_for_transmission() -> None:
    client = BinanceFuturesTestnetOrderTestClient(BinanceFuturesTestnetOrderTestConfig(), env={})
    filters = client.parse_exchange_filters(_exchange_info())

    with pytest.raises(ValueError, match="notional"):
        client.build_order_test_preview("smcbot-test-filter-002", "BUY", "MARKET", 0.001, exchange_filters=filters)

    preview = client.build_order_test_preview("smcbot-test-filter-003", "BUY", "MARKET", 0.001, exchange_filters=filters, mark_price="50000")
    assert preview.reference_price == Decimal("50000")
    assert preview.reference_price_source == "MARK_PRICE"
    assert preview.estimated_notional == Decimal("50.000")
    assert preview.exchange_filters_valid is True
    assert preview.transmission_ready is True


def test_submit_test_order_uses_only_order_test_post_and_redacts_metadata() -> None:
    calls = []

    def authenticated_post(url, body, timeout, headers):
        calls.append((url, body.decode("utf-8"), timeout, headers))
        return BinanceOrderTestHTTPResponse(200, "https://demo-fapi.binance.com/fapi/v1/order/test", {}, 2)

    client = BinanceFuturesTestnetOrderTestClient(BinanceFuturesTestnetOrderTestConfig(), env=_env(), authenticated_post=authenticated_post, now_ms_provider=lambda: 123)
    filters = client.parse_exchange_filters(_exchange_info())
    preview = client.build_order_test_preview("smcbot-test-post-001", "BUY", "MARKET", 0.001, exchange_filters=filters, mark_price="50000")

    metadata = client.submit_test_order(preview, server_time=123)

    assert metadata.request_transmitted is True
    assert metadata.path == "/fapi/v1/order/test"
    assert metadata.signature_generated is True
    assert metadata.signature_redacted is True
    assert metadata.raw_headers_exposed is False
    assert metadata.raw_request_included is False
    assert "/fapi/v1/order/test" in calls[0][0]
    assert "/fapi/v1/order?" not in calls[0][0]
    assert "signature=" in calls[0][1]
    assert calls[0][3]["X-MBX-APIKEY"] == "unit-test-key-token"


def test_final_host_is_validated() -> None:
    def authenticated_post(url, body, timeout, headers):
        return BinanceOrderTestHTTPResponse(200, "https://fapi.binance.com/fapi/v1/order/test", {}, 2)

    client = BinanceFuturesTestnetOrderTestClient(BinanceFuturesTestnetOrderTestConfig(), env=_env(), authenticated_post=authenticated_post)
    filters = client.parse_exchange_filters(_exchange_info())
    preview = client.build_order_test_preview("smcbot-test-host-001", "BUY", "MARKET", 0.001, exchange_filters=filters, mark_price="50000")

    with pytest.raises(ValueError, match="host"):
        client.submit_test_order(preview, server_time=123)


def test_hard_blocked_methods_fail_before_transport() -> None:
    client = BinanceFuturesTestnetOrderTestClient(BinanceFuturesTestnetOrderTestConfig(), env={})

    for method in (
        "submit_actual_order",
        "submit_algo_order",
        "cancel_order",
        "modify_order",
        "fetch_order",
        "fetch_open_orders",
        "fetch_trades",
        "change_leverage",
        "change_margin_mode",
        "change_position_mode",
        "change_position_margin",
        "create_listen_key",
        "open_user_stream",
        "open_websocket",
    ):
        with pytest.raises(BinanceFuturesTestnetOrderOperationBlocked):
            getattr(client, method)()
