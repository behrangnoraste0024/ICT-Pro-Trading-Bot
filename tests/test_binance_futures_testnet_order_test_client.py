from __future__ import annotations

import pytest
from decimal import Decimal
from urllib.parse import parse_qs

from infrastructure.exchanges.binance_futures_testnet_order_test_client import (
    BinanceFuturesTestnetOrderOperationBlocked,
    BinanceFuturesTestnetOrderTestClient,
    BinanceOrderTestHTTPResponse,
)
from models.binance_futures_testnet_order_test import BinanceFuturesTestnetOrderTestConfig
from models.live_execution_permit_enforcement import LiveExecutionUnsignedMutationRequest


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


def test_submit_test_order_omitted_unsigned_request_copies_business_params_before_signing() -> None:
    calls = []

    def authenticated_post(url, body, timeout, headers):
        calls.append((url, body.decode("utf-8"), timeout, headers))
        return BinanceOrderTestHTTPResponse(200, "https://demo-fapi.binance.com/fapi/v1/order/test", {}, 2)

    class RecordingClient(BinanceFuturesTestnetOrderTestClient):
        built_request: LiveExecutionUnsignedMutationRequest | None = None

        def build_unsigned_business_request(self, preview):
            self.built_request = super().build_unsigned_business_request(preview)
            return self.built_request

    client = RecordingClient(BinanceFuturesTestnetOrderTestConfig(), env=_env(), authenticated_post=authenticated_post)
    filters = client.parse_exchange_filters(_exchange_info())
    preview = client.build_order_test_preview("smcbot-test-post-002", "BUY", "MARKET", 0.001, exchange_filters=filters, mark_price="50000")

    metadata = client.submit_test_order(preview, server_time=123)

    assert isinstance(client.built_request, LiveExecutionUnsignedMutationRequest)
    assert "timestamp" not in client.built_request.transport_business_parameters
    assert "recvWindow" not in client.built_request.transport_business_parameters
    assert "signature" not in client.built_request.transport_business_parameters
    assert "timestamp" not in client.built_request.fingerprint_context
    assert "recvWindow" not in client.built_request.fingerprint_context
    assert "signature" not in client.built_request.fingerprint_context
    transmitted = parse_qs(calls[0][1])
    for key, value in client.built_request.transport_business_parameters.items():
        assert transmitted[key] == [str(value)]
    assert transmitted["timestamp"] == ["123"]
    assert transmitted["recvWindow"] == [str(BinanceFuturesTestnetOrderTestConfig().recv_window_ms)]
    assert "signature" in transmitted
    assert len(calls) == 1
    assert metadata.retry_count == 0


def test_submit_test_order_copies_supplied_unsigned_request_before_auth_fields() -> None:
    calls = []

    def authenticated_post(url, body, timeout, headers):
        calls.append((url, body.decode("utf-8"), timeout, headers))
        return BinanceOrderTestHTTPResponse(200, "https://demo-fapi.binance.com/fapi/v1/order/test", {}, 2)

    client = BinanceFuturesTestnetOrderTestClient(BinanceFuturesTestnetOrderTestConfig(), env=_env(), authenticated_post=authenticated_post)
    filters = client.parse_exchange_filters(_exchange_info())
    preview = client.build_order_test_preview("smcbot-test-post-003", "BUY", "LIMIT", 0.001, price=50000, time_in_force="GTC", exchange_filters=filters)
    unsigned = client.build_unsigned_business_request(preview)
    original_fingerprint = dict(unsigned.fingerprint_context)
    original_transport = dict(unsigned.transport_business_parameters)

    metadata = client.submit_test_order(preview, server_time=456, unsigned_business_request=unsigned)

    assert dict(unsigned.fingerprint_context) == original_fingerprint
    assert dict(unsigned.transport_business_parameters) == original_transport
    assert not {"timestamp", "recvWindow", "signature"} & set(unsigned.fingerprint_context)
    assert not {"timestamp", "recvWindow", "signature"} & set(unsigned.transport_business_parameters)
    transmitted = parse_qs(calls[0][1])
    for key, value in original_transport.items():
        assert transmitted[key] == [str(value)]
    assert transmitted["timestamp"] == ["456"]
    assert transmitted["recvWindow"] == [str(BinanceFuturesTestnetOrderTestConfig().recv_window_ms)]
    assert "signature" in transmitted
    assert len(calls) == 1
    assert metadata.retry_count == 0


def test_submit_test_order_copies_supplied_mapping_before_auth_fields() -> None:
    calls = []

    def authenticated_post(url, body, timeout, headers):
        calls.append((url, body.decode("utf-8"), timeout, headers))
        return BinanceOrderTestHTTPResponse(200, "https://demo-fapi.binance.com/fapi/v1/order/test", {}, 2)

    client = BinanceFuturesTestnetOrderTestClient(BinanceFuturesTestnetOrderTestConfig(), env=_env(), authenticated_post=authenticated_post)
    filters = client.parse_exchange_filters(_exchange_info())
    preview = client.build_order_test_preview("smcbot-test-post-004", "SELL", "MARKET", 0.001, exchange_filters=filters, mark_price="50000")
    caller_mapping = dict(client.build_unsigned_business_request(preview).transport_business_parameters)
    original_mapping = dict(caller_mapping)

    metadata = client.submit_test_order(preview, server_time=789, unsigned_business_request=caller_mapping)

    assert caller_mapping == original_mapping
    transmitted = parse_qs(calls[0][1])
    for key, value in original_mapping.items():
        assert transmitted[key] == [str(value)]
    assert transmitted["timestamp"] == ["789"]
    assert transmitted["recvWindow"] == [str(BinanceFuturesTestnetOrderTestConfig().recv_window_ms)]
    assert "signature" in transmitted
    assert len(calls) == 1
    assert metadata.retry_count == 0


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
