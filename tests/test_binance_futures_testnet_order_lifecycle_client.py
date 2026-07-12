from __future__ import annotations

from decimal import Decimal
from urllib.parse import parse_qs

import pytest

from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import (
    BinanceFuturesTestnetLifecycleOperationBlocked,
    BinanceFuturesTestnetOrderLifecycleClient,
    BinanceLifecycleHTTPResponse,
)
from models.binance_futures_testnet_order_lifecycle import BinanceFuturesTestnetOrderLifecycleConfig


def _exchange_info() -> dict:
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "filters": [
                    {"filterType": "PRICE_FILTER", "minPrice": "1", "maxPrice": "1000000", "tickSize": "0.10"},
                    {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "100", "stepSize": "0.001"},
                    {"filterType": "MIN_NOTIONAL", "notional": "5"},
                ],
            }
        ]
    }


def _ticker() -> dict:
    return {"symbol": "BTCUSDT", "bidPrice": "50000.10", "askPrice": "50001.20", "bidQty": "1", "askQty": "1"}


def _client(**overrides) -> BinanceFuturesTestnetOrderLifecycleClient:
    config = BinanceFuturesTestnetOrderLifecycleConfig(**{**BinanceFuturesTestnetOrderLifecycleConfig().to_dict(), **overrides})
    return BinanceFuturesTestnetOrderLifecycleClient(config, env={"BINANCE_FUTURES_TESTNET_API_KEY": "key", "BINANCE_FUTURES_TESTNET_API_SECRET": "secret"})


def test_buy_price_derives_below_best_bid_and_quantizes_down() -> None:
    client = _client()
    filters = client.parse_exchange_filters(_exchange_info())
    ticker = client.parse_book_ticker(_ticker())

    preview = client.build_lifecycle_preview("lifecycle-001", "smcbot-lifecycle-001", "BUY", "0.001", 100, filters, ticker)

    assert preview.derived_price == Decimal("49500.00")
    assert preview.derived_price < ticker.bid_price
    assert preview.exchange_filters_valid is True
    assert preview.non_marketable_price_valid is True
    assert preview.transmission_ready is True


def test_sell_price_derives_above_best_ask_and_quantizes_up() -> None:
    client = _client()
    filters = client.parse_exchange_filters(_exchange_info())
    ticker = client.parse_book_ticker(_ticker())

    preview = client.build_lifecycle_preview("lifecycle-002", "smcbot-lifecycle-002", "SELL", "0.001", 100, filters, ticker)

    assert preview.derived_price == Decimal("50501.30")
    assert preview.derived_price > ticker.ask_price


@pytest.mark.parametrize("payload", [{"symbol": "BTCUSDT", "bidPrice": "0", "askPrice": "1"}, {"symbol": "BTCUSDT", "bidPrice": "2", "askPrice": "1"}, {"symbol": "BTCUSDT", "bidPrice": "NaN", "askPrice": "1"}])
def test_invalid_book_ticker_rejected(payload: dict) -> None:
    with pytest.raises(ValueError):
        _client().parse_book_ticker(payload)


@pytest.mark.parametrize("offset", [49, 5001])
def test_unsafe_price_offset_rejected(offset: int) -> None:
    with pytest.raises(ValueError, match="offset"):
        _client().build_lifecycle_preview("lifecycle-003", "smcbot-lifecycle-003", "BUY", "0.001", offset)


def test_filter_notional_and_step_are_enforced() -> None:
    client = _client()
    filters = client.parse_exchange_filters(_exchange_info())

    with pytest.raises(ValueError, match="step"):
        client.validate_filters_and_notional(Decimal("0.0015"), Decimal("50000.00"), filters)
    with pytest.raises(ValueError, match="minimum"):
        client.validate_filters_and_notional(Decimal("0.001"), Decimal("1000.00"), filters)
    with pytest.raises(ValueError, match="maximum"):
        client.validate_filters_and_notional(Decimal("0.01"), Decimal("20000.00"), filters)


def test_create_order_transmits_limit_gtx_both_ack_only() -> None:
    calls = []

    def transport(method, url, body, timeout, headers):
        calls.append((method, url, body.decode("utf-8"), headers))
        return BinanceLifecycleHTTPResponse(200, url, {"symbol": "BTCUSDT", "clientOrderId": "smcbot-lifecycle-004", "orderId": 123, "side": "BUY", "type": "LIMIT", "timeInForce": "GTX", "price": "49500.00", "origQty": "0.001", "executedQty": "0", "status": "NEW"}, 2)

    client = _client()
    filters = client.parse_exchange_filters(_exchange_info())
    preview = client.build_lifecycle_preview("lifecycle-004", "smcbot-lifecycle-004", "BUY", "0.001", 100, filters, client.parse_book_ticker(_ticker()))
    summary, metadata = BinanceFuturesTestnetOrderLifecycleClient(client.config, authenticated_request=transport, env=client.env).create_order(preview, 123)

    assert summary.status == "NEW"
    assert metadata.request_transmitted is True
    body = calls[0][2]
    assert calls[0][0] == "POST"
    assert "/fapi/v1/order" in calls[0][1]
    assert "type=LIMIT" in body
    assert "timeInForce=GTX" in body
    assert "positionSide=BOTH" in body
    assert "newOrderRespType=ACK" in body
    assert "signature=" in body


def test_signed_request_uses_fresh_now_provider_timestamp_and_ignores_stale_input() -> None:
    calls = []
    timestamps = iter([1000, 7000])

    def transport(method, url, body, timeout, headers):
        calls.append(body.decode("utf-8"))
        return BinanceLifecycleHTTPResponse(200, url, {"symbol": "BTCUSDT", "clientOrderId": "smcbot-lifecycle-005", "orderId": 123, "side": "BUY", "type": "LIMIT", "timeInForce": "GTX", "price": "49500.00", "origQty": "0.001", "executedQty": "0", "status": "NEW"}, 2)

    client = _client()
    filters = client.parse_exchange_filters(_exchange_info())
    preview = client.build_lifecycle_preview("lifecycle-005", "smcbot-lifecycle-005", "BUY", "0.001", 100, filters, client.parse_book_ticker(_ticker()))
    lifecycle_client = BinanceFuturesTestnetOrderLifecycleClient(client.config, authenticated_request=transport, env=client.env, now_ms_provider=lambda: next(timestamps))

    _, first = lifecycle_client.create_order(preview, server_time=123)
    _, second = lifecycle_client.query_order("smcbot-lifecycle-005", server_time=123)

    assert first.timestamp == 1000
    assert second.timestamp == 7000
    assert "timestamp=123" not in "&".join(calls)
    assert parse_qs(calls[0])["timestamp"] == ["1000"]
    assert parse_qs(calls[1])["timestamp"] == ["7000"]


def test_signed_request_applies_validated_server_offset_to_fresh_local_time() -> None:
    calls = []
    timestamps = iter([5000])

    def transport(method, url, body, timeout, headers):
        calls.append(body.decode("utf-8"))
        return BinanceLifecycleHTTPResponse(200, url, {"symbol": "BTCUSDT", "clientOrderId": "smcbot-lifecycle-006", "orderId": 123, "side": "BUY", "type": "LIMIT", "timeInForce": "GTX", "price": "49500.00", "origQty": "0.001", "executedQty": "0", "status": "NEW"}, 2)

    client = _client()
    filters = client.parse_exchange_filters(_exchange_info())
    preview = client.build_lifecycle_preview("lifecycle-006", "smcbot-lifecycle-006", "BUY", "0.001", 100, filters, client.parse_book_ticker(_ticker()))
    lifecycle_client = BinanceFuturesTestnetOrderLifecycleClient(client.config, authenticated_request=transport, env=client.env, now_ms_provider=lambda: next(timestamps))

    lifecycle_client.set_server_time_offset(server_time=1100, local_time=1000)
    _, metadata = lifecycle_client.create_order(preview)

    assert metadata.timestamp == 5100
    assert parse_qs(calls[0])["timestamp"] == ["5100"]


def test_hard_blocked_operations_fail_before_transport() -> None:
    client = _client()
    for method in ("submit_market_order", "submit_conditional_order", "submit_algo_order", "submit_batch_orders", "modify_order", "cancel_all_orders", "fetch_open_orders", "fetch_all_orders", "fetch_trades", "change_leverage", "change_margin_mode", "change_position_mode", "change_multi_assets_mode", "change_position_margin", "close_position", "create_listen_key", "open_user_stream", "open_websocket"):
        with pytest.raises(BinanceFuturesTestnetLifecycleOperationBlocked):
            getattr(client, method)()
