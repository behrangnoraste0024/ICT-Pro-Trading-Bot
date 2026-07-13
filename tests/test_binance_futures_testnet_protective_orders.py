from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs

from engine.diagnostics.binance_futures_testnet_protective_orders_engine import BinanceFuturesTestnetProtectiveOrdersEngine
from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import BinanceLifecycleHTTPResponse
from infrastructure.exchanges.binance_futures_testnet_protective_orders_client import BinanceFuturesTestnetProtectiveAPIError, BinanceFuturesTestnetProtectiveOrdersClient
from models.binance_futures_testnet_protective_orders import BinanceFuturesTestnetProtectiveOrdersConfig


def _env() -> dict[str, str]:
    return {"BINANCE_FUTURES_TESTNET_API_KEY": "unit-test-key", "BINANCE_FUTURES_TESTNET_API_SECRET": "unit-test-secret"}


def _write_config(tmp_path: Path, **overrides) -> Path:
    data = BinanceFuturesTestnetProtectiveOrdersConfig().to_dict()
    data.update(overrides)
    path = tmp_path / "configs" / "binance_futures_testnet_protective_orders.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _exchange_info() -> dict:
    return {"symbols": [{"symbol": "BTCUSDT", "filters": [{"filterType": "PRICE_FILTER", "minPrice": "1", "maxPrice": "1000000", "tickSize": "0.10"}]}]}


def _http_get(url, timeout):
    if url.endswith("/fapi/v1/time"):
        return BinanceLifecycleHTTPResponse(200, url, {"serverTime": 1000}, 10)
    if "/fapi/v1/exchangeInfo" in url:
        return BinanceLifecycleHTTPResponse(200, url, _exchange_info(), 10)
    raise AssertionError(f"unexpected GET {url}")


class _Clock:
    def __init__(self, start: int = 1000, step: int = 1) -> None:
        self.value = start
        self.step = step

    def __call__(self) -> int:
        current = self.value
        self.value += self.step
        return current


def _position(amount: str = "0.001", mark: str = "50000", entry: str = "49000") -> list[dict]:
    return [{"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": amount, "entryPrice": entry, "markPrice": mark, "notional": str(abs(float(amount)) * float(mark))}]


def _runtime_file(tmp_path: Path, name: str) -> Path:
    return tmp_path / "data" / "runtime" / "binance_futures_testnet_protective_orders" / name


def _algo_response(client_id: str, order_type: str, status: str = "NEW", side: str = "SELL", trigger: str = "45000.00", **overrides) -> dict:
    payload = {
        "symbol": "BTCUSDT",
        "algoType": "CONDITIONAL",
        "clientAlgoId": client_id,
        "algoId": 1,
        "side": side,
        "positionSide": "BOTH",
        "orderType": order_type,
        "triggerPrice": trigger,
        "algoStatus": status,
        "actualQty": "0",
        "actualPrice": "0",
        "closePosition": True,
        "workingType": "MARK_PRICE",
        "priceProtect": True,
    }
    payload.update(overrides)
    return payload


def test_config_defaults_are_strict_and_validate(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    report = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path).validate(str(path))

    assert report.status == "PASS"
    assert report.config.request_timeout_seconds == 30
    assert report.config.recv_window_ms == 10000
    assert report.config.allowed_algo_type == "CONDITIONAL"
    assert report.config.allowed_order_types == ["STOP_MARKET", "TAKE_PROFIT_MARKET"]
    assert report.config.allowed_methods == ["POST", "GET", "DELETE"]
    assert report.config.feature_enabled is False
    assert report.config.allow_position_entry is False
    assert report.config.allow_position_close is False


def test_config_rejects_production_host_and_unsafe_paths(tmp_path: Path) -> None:
    path = _write_config(tmp_path, rest_base_url="https://fapi.binance.com", algo_order_path="/fapi/v1/order")

    report = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path).validate(str(path))

    assert report.status == "FAIL"
    assert {issue.name for issue in report.issues} >= {"rest_base_url", "algo_order_path"}


def test_strict_config_rejects_identity_and_limit_drift(tmp_path: Path) -> None:
    overrides = {
        "symbol": "ETH/USDT",
        "api_key_env_var": "BINANCE_KEY",
        "maximum_position_abs_quantity": 0.0021,
        "maximum_position_notional_usdt": 151,
        "request_timeout_seconds": 31,
        "recv_window_ms": 10001,
        "maximum_server_time_sync_age_ms": 5001,
        "pair_confirmation_phrase": "BAD",
        "recovery_confirmation_phrase": "BAD",
        "client_algo_id_prefix": "bad-",
    }
    path = _write_config(tmp_path, **overrides)

    report = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path).validate(str(path))

    assert report.status == "FAIL"
    names = {issue.name for issue in report.issues}
    assert {"symbol", "api_key_env_var", "maximum_position_abs_quantity", "maximum_position_notional_usdt", "timeout_recv_window", "pair_confirmation_phrase", "recovery_confirmation_phrase", "client_algo_id_policy"}.issubset(names)


def test_long_and_short_preview_side_trigger_order_and_rounding(tmp_path: Path) -> None:
    config = BinanceFuturesTestnetProtectiveOrdersConfig()
    client = BinanceFuturesTestnetProtectiveOrdersClient(config, env=_env())
    filters = client.parse_exchange_filters({"symbols": [{"symbol": "BTCUSDT", "filters": [{"filterType": "PRICE_FILTER", "minPrice": "1", "maxPrice": "1000000", "tickSize": "0.10"}]}]})
    long_position = client.require_protectable_position(_position("0.001", "50000.03"))
    short_position = client.require_protectable_position(_position("-0.001", "50000.03"))

    long_preview = client.build_preview("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", long_position, filters, 1000, 1000)
    short_preview = client.build_preview("pair-002", "smcbot-protect-sl-002", "smcbot-protect-tp-002", short_position, filters, 1000, 1000)

    assert long_preview.protective_side == "SELL"
    assert long_preview.stop_trigger == Decimal("45000.00")
    assert long_preview.take_profit_trigger == Decimal("55000.10")
    assert long_preview.stop_trigger < long_position.mark_price < long_preview.take_profit_trigger
    assert short_preview.protective_side == "BUY"
    assert short_preview.stop_trigger == Decimal("55000.10")
    assert short_preview.take_profit_trigger == Decimal("45000.00")
    assert short_preview.take_profit_trigger < short_position.mark_price < short_preview.stop_trigger


def test_invalid_positions_and_immediate_trigger_are_rejected(tmp_path: Path) -> None:
    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), env=_env())
    filters = client.parse_exchange_filters({"symbols": [{"symbol": "BTCUSDT", "filters": [{"filterType": "PRICE_FILTER", "minPrice": "1", "maxPrice": "1000000", "tickSize": "0.10"}]}]})

    for rows in ([_position("0")[0]], _position("0.0021"), _position("0.002", "80000")):
        try:
            client.require_protectable_position(rows)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid position should be rejected")
    position = client.require_protectable_position(_position("0.001", "50000"))
    try:
        client.build_preview("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", position, filters, 0, 1000)
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe offset should be rejected")


def test_protective_position_limits_accept_demo_minimum_sized_positions(tmp_path: Path) -> None:
    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), env=_env())

    position = client.require_protectable_position(_position("0.0016", "63099.66"))
    max_position = client.require_protectable_position(_position("0.002", "70000"))

    assert position.position_amt == Decimal("0.0016")
    assert position.notional < Decimal("150")
    assert max_position.position_amt == Decimal("0.002")
    assert max_position.notional < Decimal("150")


def test_protective_position_limits_reject_above_quantity_or_notional(tmp_path: Path) -> None:
    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), env=_env())

    for rows in (_position("0.0021", "63099.66"), _position("0.002", "80000")):
        try:
            client.require_protectable_position(rows)
        except ValueError:
            pass
        else:
            raise AssertionError("position above protective quantity/notional limit should be rejected")


def test_config_limits_accept_only_updated_position_ceiling(tmp_path: Path) -> None:
    valid_path = _write_config(tmp_path, maximum_position_abs_quantity=0.002, maximum_position_notional_usdt=150.0)
    invalid_quantity_path = _write_config(tmp_path / "quantity", maximum_position_abs_quantity=0.0021)
    invalid_notional_path = _write_config(tmp_path / "notional", maximum_position_notional_usdt=150.1)

    assert BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path).validate(str(valid_path)).status == "PASS"

    quantity_report = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path / "quantity").validate(str(invalid_quantity_path))
    notional_report = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path / "notional").validate(str(invalid_notional_path))

    assert quantity_report.status == "FAIL"
    assert any(issue.name == "maximum_position_abs_quantity" for issue in quantity_report.issues)
    assert notional_report.status == "FAIL"
    assert any(issue.name == "maximum_position_notional_usdt" for issue in notional_report.issues)


def test_position_side_must_be_present_and_both(tmp_path: Path) -> None:
    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), env=_env())
    missing = _position()[0]
    missing.pop("positionSide")
    wrong = _position()[0]
    wrong["positionSide"] = "LONG"

    for rows in ([missing], [wrong]):
        try:
            client.require_protectable_position(rows)
        except ValueError:
            pass
        else:
            raise AssertionError("positionSide must be present and BOTH")


def test_algo_summary_parses_current_binance_fields_and_trigger_detection(tmp_path: Path) -> None:
    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), env=_env())
    order = client.sanitize_algo_summary(_algo_response("smcbot-protect-sl-001", "STOP_MARKET", actualQty="0.001", actualOrderId=99, actualPrice="45000.00"), "smcbot-protect-sl-001")

    assert order.algo_type == "CONDITIONAL"
    assert order.order_type == "STOP_MARKET"
    assert order.executed_quantity == Decimal("0.001")
    assert order.actual_order_id == "99"
    assert order.actual_price == Decimal("45000.00")
    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path)
    try:
        result._check_unexpected_trigger(order)
    except Exception as exc:
        assert getattr(exc, "critical", False) is True
    else:
        raise AssertionError("actualQty/actualOrderId must be critical")


def test_create_parameters_are_exact_close_position_and_freshly_signed(tmp_path: Path) -> None:
    bodies = []
    now_values = iter([1000, 2000])

    def transport(method, url, body, timeout, headers):
        bodies.append(body.decode("utf-8"))
        return BinanceLifecycleHTTPResponse(200, url, _algo_response("smcbot-protect-sl-001", "STOP_MARKET"), 10)

    config = BinanceFuturesTestnetProtectiveOrdersConfig()
    client = BinanceFuturesTestnetProtectiveOrdersClient(config, authenticated_request=transport, env=_env(), now_ms_provider=lambda: next(now_values))
    client.server_time_offset_ms = 100
    filters = client.parse_exchange_filters(_exchange_info())
    position = client.require_protectable_position(_position())
    preview = client.build_preview("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", position, filters)

    _, metadata = client.create_stop_order(preview)

    params = parse_qs(bodies[0])
    assert metadata.timestamp == 1100
    assert params["algoType"] == ["CONDITIONAL"]
    assert params["type"] == ["STOP_MARKET"]
    assert params["closePosition"] == ["true"]
    assert params["positionSide"] == ["BOTH"]
    assert params["workingType"] == ["MARK_PRICE"]
    assert params["priceProtect"] == ["true"]
    assert "quantity" not in params
    assert "reduceOnly" not in params
    assert "price" not in params


def test_lifecycle_refreshes_server_time_before_each_mutation_boundary(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    server_time_calls = []
    auth_calls = []
    statuses = {
        "smcbot-protect-sl-001": ["NEW", "CANCELED"],
        "smcbot-protect-tp-001": ["NEW", "CANCELED"],
    }

    def http_get(url, timeout):
        if url.endswith("/fapi/v1/time"):
            server_time_calls.append(url)
            return BinanceLifecycleHTTPResponse(200, url, {"serverTime": 1000}, 10)
        if "/fapi/v1/exchangeInfo" in url:
            return BinanceLifecycleHTTPResponse(200, url, _exchange_info(), 10)
        raise AssertionError(f"unexpected GET {url}")

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        auth_calls.append((method, url, params))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        if method == "DELETE":
            return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": 1, "code": 200}, 10)
        order_type = params.get("type", ["STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"])[0]
        trigger = params.get("triggerPrice", ["45000.00" if order_type == "STOP_MARKET" else "55000.00"])[0]
        status = statuses[client_id].pop(0) if method == "GET" and statuses[client_id] else statuses[client_id][0] if statuses[client_id] else "CANCELED"
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status=status, trigger=trigger), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "PASS"
    assert len(server_time_calls) == 5
    assert [item.server_time_resync_count for item in result.create_requests] == [2, 3]
    assert [item.server_time_resync_count for item in result.cancel_requests] == [4, 5]
    assert all(item.server_time_sync_used for item in result.create_requests + result.cancel_requests)


def test_stale_server_time_sync_refreshes_before_signing(tmp_path: Path) -> None:
    calls = []

    def http_get(url, timeout):
        calls.append(url)
        return BinanceLifecycleHTTPResponse(200, url, {"serverTime": 7001}, 10)

    def transport(method, url, body, timeout, headers):
        return BinanceLifecycleHTTPResponse(200, url, _algo_response("smcbot-protect-sl-001", "STOP_MARKET"), 10)

    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), http_get=http_get, authenticated_request=transport, env=_env(), now_ms_provider=lambda: 6001)
    client.server_time_offset_ms = 0
    client.server_time_synced_at_ms = 0

    _, metadata = client.query_algo_order("smcbot-protect-sl-001")

    assert len(calls) == 1
    assert metadata.server_time_sync_used is True
    assert metadata.server_time_resync_count == 1
    assert metadata.timestamp == 7001


def test_get_timestamp_error_resyncs_and_retries_once(tmp_path: Path) -> None:
    auth_calls = []
    server_time_calls = []
    clock = _Clock(1000)

    def http_get(url, timeout):
        server_time_calls.append(url)
        return BinanceLifecycleHTTPResponse(200, url, {"serverTime": clock.value + 100}, 10)

    def transport(method, url, body, timeout, headers):
        auth_calls.append(parse_qs(body.decode("utf-8")))
        if len(auth_calls) == 1:
            raise BinanceFuturesTestnetProtectiveAPIError("timestamp outside recvWindow", http_status=400, binance_code=-1021, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        return BinanceLifecycleHTTPResponse(200, url, _algo_response("smcbot-protect-sl-001", "STOP_MARKET"), 10)

    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), http_get=http_get, authenticated_request=transport, env=_env(), now_ms_provider=clock)

    _, metadata = client.query_algo_order("smcbot-protect-sl-001")

    assert len(auth_calls) == 2
    assert len(server_time_calls) == 2
    assert metadata.retry_count == 1
    assert metadata.timestamp_retry_count == 1
    assert metadata.timestamp_error_detected is True
    assert auth_calls[0]["timestamp"] != auth_calls[1]["timestamp"]
    assert auth_calls[0]["signature"] != auth_calls[1]["signature"]


def test_get_timestamp_error_retries_once_then_fails(tmp_path: Path) -> None:
    auth_calls = []
    clock = _Clock(1000)

    def http_get(url, timeout):
        return BinanceLifecycleHTTPResponse(200, url, {"serverTime": clock.value + 100}, 10)

    def transport(method, url, body, timeout, headers):
        auth_calls.append(body)
        raise BinanceFuturesTestnetProtectiveAPIError("timestamp outside recvWindow", http_status=400, binance_code=-1021, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)

    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), http_get=http_get, authenticated_request=transport, env=_env(), now_ms_provider=clock)

    try:
        client.query_algo_order("smcbot-protect-sl-001")
    except BinanceFuturesTestnetProtectiveAPIError as exc:
        assert exc.binance_code == -1021
    else:
        raise AssertionError("second timestamp rejection should fail safely")
    assert len(auth_calls) == 2


def test_get_does_not_retry_other_binance_errors(tmp_path: Path) -> None:
    calls = []

    def transport(method, url, body, timeout, headers):
        calls.append(body)
        raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)

    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), http_get=_http_get, authenticated_request=transport, env=_env(), now_ms_provider=lambda: 1000)

    try:
        client.query_algo_order("smcbot-protect-sl-001")
    except BinanceFuturesTestnetProtectiveAPIError as exc:
        assert exc.binance_code == -2013
    else:
        raise AssertionError("non-timestamp Binance errors must not retry")
    assert len(calls) == 1


def test_post_and_delete_timestamp_errors_are_not_retried(tmp_path: Path) -> None:
    calls = []

    def transport(method, url, body, timeout, headers):
        calls.append(method)
        raise BinanceFuturesTestnetProtectiveAPIError("timestamp outside recvWindow", http_status=400, binance_code=-1021, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)

    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), http_get=_http_get, authenticated_request=transport, env=_env(), now_ms_provider=lambda: 1000)
    filters = client.parse_exchange_filters(_exchange_info())
    position = client.require_protectable_position(_position())
    preview = client.build_preview("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", position, filters)

    for action in (lambda: client.create_stop_order(preview), lambda: client.cancel_algo_order_exact("smcbot-protect-sl-001")):
        try:
            action()
        except BinanceFuturesTestnetProtectiveAPIError as exc:
            assert exc.binance_code == -1021
        else:
            raise AssertionError("mutation timestamp errors must fail without retry")

    assert calls == ["POST", "DELETE"]


def test_exact_get_and_delete_algo_contract_uses_client_algo_id_only(tmp_path: Path) -> None:
    calls = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, params))
        return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": "smcbot-protect-sl-001", "algoId": 1, "code": 200}, 10)

    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), authenticated_request=transport, env=_env(), now_ms_provider=lambda: 1000)
    client.server_time_offset_ms = 0
    client.server_time_synced_at_ms = 1000

    client.query_algo_order("smcbot-protect-sl-001")
    client.cancel_algo_order_exact("smcbot-protect-sl-001")

    for method, params in calls:
        assert set(params) == {"clientAlgoId", "timestamp", "recvWindow", "signature"}
        assert params["clientAlgoId"] == ["smcbot-protect-sl-001"]
        assert "symbol" not in params
    assert calls[0][0] == "GET"
    assert calls[1][0] == "DELETE"


def test_parser_does_not_synthesize_missing_identity(tmp_path: Path) -> None:
    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), env=_env())

    order = client.sanitize_algo_summary({"algoId": 1}, "smcbot-protect-sl-001")

    assert order.client_algo_id is None
    assert order.symbol is None


def test_missing_mandatory_response_identity_fails_closed(tmp_path: Path) -> None:
    engine = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path)
    base = _algo_response("smcbot-protect-sl-001", "STOP_MARKET")

    for field in ("clientAlgoId", "symbol", "side", "positionSide", "triggerPrice", "algoId", "algoType", "orderType", "algoStatus", "closePosition", "workingType", "priceProtect"):
        payload = dict(base)
        payload.pop(field)
        order = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), env=_env()).sanitize_algo_summary(payload, "smcbot-protect-sl-001")
        try:
            engine._validate_algo_identity(order, None, "STOP", stop_client_algo_id="smcbot-protect-sl-001")
        except Exception as exc:
            assert getattr(exc, "decision", "") == "ORDER_IDENTITY_MISMATCH"
        else:
            raise AssertionError(f"{field} should be mandatory")


def test_delete_minimal_success_and_mismatch_validation(tmp_path: Path) -> None:
    engine = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path)
    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), env=_env())

    ok = client.sanitize_algo_summary({"clientAlgoId": "smcbot-protect-sl-001", "algoId": 1, "code": 200, "msg": "success"}, "smcbot-protect-sl-001")
    engine._validate_delete_ack(ok, "smcbot-protect-sl-001")

    bad = client.sanitize_algo_summary({"clientAlgoId": "smcbot-protect-other", "algoId": 1, "code": 200}, "smcbot-protect-sl-001")
    try:
        engine._validate_delete_ack(bad, "smcbot-protect-sl-001")
    except Exception as exc:
        assert getattr(exc, "decision", "") == "ORDER_IDENTITY_MISMATCH"
    else:
        raise AssertionError("mismatched DELETE clientAlgoId must fail")


def test_structured_api_error_preserves_sanitized_code_without_secrets(tmp_path: Path) -> None:
    error = BinanceFuturesTestnetProtectiveAPIError(
        "UNKNOWN_PARAM signature=secret X-MBX-APIKEY key",
        http_status=400,
        binance_code=-1103,
        method="GET",
        path="/fapi/v1/algoOrder",
        request_transmitted=True,
        response_received=True,
    )

    assert error.binance_code == -1103
    assert error.http_status == 400
    assert error.method == "GET"
    assert "signature=" not in error.sanitized_message
    assert "X-MBX-APIKEY" not in error.sanitized_message


def test_lifecycle_sequence_cancel_order_and_position_unchanged(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []
    statuses = {
        "smcbot-protect-sl-001": ["NEW", "CANCELED"],
        "smcbot-protect-tp-001": ["NEW", "CANCELED"],
    }

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = (params.get("clientAlgoId") or [""])[0]
        if method == "POST":
            status = statuses[client_id][0]
        else:
            status = statuses[client_id].pop(0) if statuses[client_id] else "CANCELED"
        order_type = params.get("type", ["STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"])[0]
        trigger = params.get("triggerPrice", ["45000.00" if order_type == "STOP_MARKET" else "55000.00"])[0]
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status=status, trigger=trigger), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "PASS"
    assert result.lifecycle_complete is True
    algo_calls = [(method, (params.get("clientAlgoId") or [""])[0]) for method, url, params in calls if "algoOrder" in url]
    assert algo_calls[:4] == [("POST", "smcbot-protect-sl-001"), ("GET", "smcbot-protect-sl-001"), ("POST", "smcbot-protect-tp-001"), ("GET", "smcbot-protect-tp-001")]
    assert ("DELETE", "smcbot-protect-tp-001") in algo_calls
    assert algo_calls.index(("DELETE", "smcbot-protect-tp-001")) < algo_calls.index(("DELETE", "smcbot-protect-sl-001"))
    assert not _runtime_file(tmp_path, "protective.lock").exists()
    journal = _runtime_file(tmp_path, "protective.json").read_text(encoding="utf-8")
    assert "signature=" not in journal
    assert "unit-test-secret" not in journal


def test_exact_algo_response_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    mismatches = [
        {"clientAlgoId": "smcbot-protect-other"},
        {"symbol": "ETHUSDT"},
        {"algoType": "BAD"},
        {"orderType": "TAKE_PROFIT_MARKET"},
        {"side": "BUY"},
        {"positionSide": "LONG"},
        {"triggerPrice": "45000.10"},
    ]

    for mismatch in mismatches:
        def transport(method, url, body, timeout, headers, mismatch=mismatch):
            params = parse_qs(body.decode("utf-8"))
            if "positionSide/dual" in url:
                return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
            if "positionRisk" in url:
                return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
            client_id = (params.get("clientAlgoId") or ["smcbot-protect-sl-001"])[0]
            return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, "STOP_MARKET", **mismatch), 10)

        result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

        assert result.status == "FAIL"
        assert result.decision == "ORDER_IDENTITY_MISMATCH"


def test_delete_response_can_be_sparse_but_final_get_is_verified(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []
    statuses = {
        "smcbot-protect-sl-001": ["NEW", "CANCELED"],
        "smcbot-protect-tp-001": ["NEW", "CANCELED"],
    }

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        if method == "DELETE":
            return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": 1, "code": 200, "msg": "success"}, 10)
        order_type = params.get("type", ["STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"])[0]
        trigger = params.get("triggerPrice", ["45000.00" if order_type == "STOP_MARKET" else "55000.00"])[0]
        status = statuses[client_id].pop(0) if method == "GET" and statuses[client_id] else statuses[client_id][0] if statuses[client_id] else "CANCELED"
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status=status, trigger=trigger), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "PASS"
    assert [call[0] for call in calls if "algoOrder" in call[1]].count("DELETE") == 2


def test_lock_blocks_lifecycle_without_network_or_journal_mutation(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    lock = _runtime_file(tmp_path, "protective.lock")
    journal = _runtime_file(tmp_path, "protective.json")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("foreign-owner", encoding="utf-8")
    journal.write_text("existing", encoding="utf-8")
    calls = []

    def transport(method, url, body, timeout, headers):
        calls.append(url)
        raise AssertionError("network should not run")

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=lambda url, timeout: transport("GET", url, b"", timeout, {}), authenticated_request=transport).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert calls == []
    assert lock.read_text(encoding="utf-8") == "foreign-owner"
    assert journal.read_text(encoding="utf-8") == "existing"


def test_mutation_uncertainty_returns_recovery_required_and_does_not_retry_post(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        if method == "POST":
            raise TimeoutError("timeout after POST transmission")
        raise AssertionError("no query/cancel after uncertain create")

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert len([call for call in calls if call[0] == "POST"]) == 1
    assert not _runtime_file(tmp_path, "protective.lock").exists()


def test_lifecycle_post_timestamp_error_requires_recovery_without_retry(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        if method == "POST":
            raise BinanceFuturesTestnetProtectiveAPIError("timestamp outside recvWindow", http_status=400, binance_code=-1021, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        raise AssertionError("no query/cancel after timestamp-rejected POST")

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "TIMESTAMP_OUTSIDE_RECV_WINDOW"
    assert result.recovery_required is True
    assert len([call for call in calls if call[0] == "POST"]) == 1


def test_recovery_queries_both_ids_cancels_new_take_profit_before_stop(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []
    statuses = {
        "smcbot-protect-sl-001": ["NEW", "CANCELED"],
        "smcbot-protect-tp-001": ["NEW", "CANCELED"],
    }

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        status = statuses[client_id][0] if method == "DELETE" else statuses[client_id].pop(0)
        order_type = "STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status=status), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))

    assert result.status == "PASS"
    algo_calls = [(method, params["clientAlgoId"][0]) for method, url, params in calls if "algoOrder" in url]
    assert algo_calls[:2] == [("GET", "smcbot-protect-sl-001"), ("GET", "smcbot-protect-tp-001")]
    assert algo_calls.index(("DELETE", "smcbot-protect-tp-001")) < algo_calls.index(("DELETE", "smcbot-protect-sl-001"))
    assert not any("openOrders" in url or "allOrders" in url for _, url, _ in calls)


def test_recovery_absent_absent_sends_no_delete_and_checks_position(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position("0"), 10)
        raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))

    assert result.status == "PASS"
    assert not any(call[0] == "DELETE" for call in calls)
    assert any("positionRisk" in call[1] for call in calls)


def test_recovery_timeout_tls_and_auth_errors_do_not_become_absent(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    for exc in (
        TimeoutError("timeout"),
        OSError("TLS failed"),
        BinanceFuturesTestnetProtectiveAPIError("INVALID_SIGNATURE", http_status=400, binance_code=-1022, method="GET", path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True),
    ):
        def transport(method, url, body, timeout, headers, exc=exc):
            raise exc

        result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))

        assert result.status == "FAIL"
        assert result.decision == "RECOVERY_REQUIRED"


def test_recovery_stop_new_take_profit_absent_cancels_stop_once(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        if client_id == "smcbot-protect-tp-001":
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        status = "CANCELED" if method == "GET" and any(call[0] == "DELETE" and call[2]["clientAlgoId"][0] == client_id for call in calls) else "NEW"
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, "STOP_MARKET", status=status), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))

    assert result.status == "PASS"
    deletes = [call for call in calls if call[0] == "DELETE"]
    assert len(deletes) == 1
    assert deletes[0][2]["clientAlgoId"] == ["smcbot-protect-sl-001"]


def test_journal_confirmed_order_returning_absent_requires_recovery(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    journal = _runtime_file(tmp_path, "protective.json")
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps({"pair_id": "pair-001", "stop_client_algo_id": "smcbot-protect-sl-001", "take_profit_client_algo_id": "smcbot-protect-tp-001", "phase": "RECOVERY_REQUIRED", "recovery_required": True, "entries": [{"phase": "STOP_CREATED"}]}), encoding="utf-8")

    def transport(method, url, body, timeout, headers):
        raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"


def test_query_retry_policy_for_transient_only_and_fresh_signature(tmp_path: Path) -> None:
    calls = []
    now_values = iter([1000, 1001, 1002, 1003])

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append(params)
        if len(calls) == 1:
            raise TimeoutError("transient")
        return BinanceLifecycleHTTPResponse(200, url, _algo_response("smcbot-protect-sl-001", "STOP_MARKET"), 10)

    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), authenticated_request=transport, env=_env(), now_ms_provider=lambda: next(now_values))
    client.server_time_offset_ms = 0
    client.server_time_synced_at_ms = 1000
    client.query_algo_order("smcbot-protect-sl-001")

    assert len(calls) == 2
    assert calls[0]["clientAlgoId"] == calls[1]["clientAlgoId"]
    assert calls[0]["timestamp"] != calls[1]["timestamp"]
    assert calls[0]["signature"] != calls[1]["signature"]

    deterministic_calls = []

    def deterministic(method, url, body, timeout, headers):
        deterministic_calls.append(body)
        raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)

    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), authenticated_request=deterministic, env=_env(), now_ms_provider=lambda: 1000)
    client.server_time_offset_ms = 0
    client.server_time_synced_at_ms = 1000
    try:
        client.query_algo_order("smcbot-protect-sl-001")
    except BinanceFuturesTestnetProtectiveAPIError:
        pass
    else:
        raise AssertionError("deterministic API errors must not be retried")
    assert len(deterministic_calls) == 1


def test_recovery_matching_journal_validates_side_and_triggers(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    journal = _runtime_file(tmp_path, "protective.json")
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps({"pair_id": "pair-001", "stop_client_algo_id": "smcbot-protect-sl-001", "take_profit_client_algo_id": "smcbot-protect-tp-001", "baseline_available": True, "baseline_position_amount": "0.001", "baseline_position_direction": "LONG", "stop_trigger": "45000.00", "take_profit_trigger": "55000.00", "entries": []}), encoding="utf-8")

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        order_type = "STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"
        trigger = "45000.10" if client_id.endswith("sl-001") else "55000.00"
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="CANCELED", side="SELL", trigger=trigger), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "ORDER_IDENTITY_MISMATCH"


def test_recovery_generic_transport_errors_return_recovery_required_and_release_lock(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    for exc in (TimeoutError("timeout"), OSError("TLS failed"), ConnectionResetError("connection reset")):
        calls = []

        def transport(method, url, body, timeout, headers, exc=exc):
            calls.append(method)
            raise exc

        result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))

        assert result.status == "FAIL"
        assert result.decision == "RECOVERY_REQUIRED"
        assert result.recovery_required is True
        assert set(calls) == {"GET"}
        assert not _runtime_file(tmp_path, "protective.lock").exists()


def test_recovery_preserves_matching_journal_and_compares_baseline(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    journal = _runtime_file(tmp_path, "protective.json")
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps({"pair_id": "pair-001", "stop_client_algo_id": "smcbot-protect-sl-001", "take_profit_client_algo_id": "smcbot-protect-tp-001", "phase": "RECOVERY_REQUIRED", "recovery_required": True, "baseline_available": True, "baseline_position_amount": "0.001", "baseline_position_direction": "LONG", "stop_trigger": "45000.00", "take_profit_trigger": "55000.00", "entries": [{"phase": "OLD", "details": {"kept": True}}]}), encoding="utf-8")

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position("0.0005"), 10)
        client_id = params["clientAlgoId"][0]
        order_type = "STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"
        trigger = "45000.00" if order_type == "STOP_MARKET" else "55000.00"
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="CANCELED", trigger=trigger), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))

    assert result.status == "CRITICAL"
    assert result.decision == "UNEXPECTED_POSITION_CHANGE"
    assert result.journal.pair_id == "pair-001"
    assert any(entry.get("phase") == "OLD" for entry in result.journal.entries)


def test_recovery_does_not_reuse_unrelated_journal(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    journal = _runtime_file(tmp_path, "protective.json")
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps({"pair_id": "other", "stop_client_algo_id": "other-sl", "take_profit_client_algo_id": "other-tp", "entries": [{"phase": "OLD"}]}), encoding="utf-8")

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        order_type = "STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="CANCELED"), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))

    assert result.status == "PASS"
    assert result.journal.pair_id == ""
    assert result.journal.baseline_available is False
    assert not any(entry.get("phase") == "OLD" for entry in result.journal.entries)


def test_query_pair_detects_triggered_state_as_critical(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        client_id = params["clientAlgoId"][0]
        order_type = "STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="TRIGGERED", actualQty="0.001"), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).query_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", config_path=str(path))

    assert result.status == "CRITICAL"
    assert result.unexpected_trigger is True


def test_query_pair_side_mismatch_and_timeout_fail_without_mutation(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    def mismatched(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        client_id = params["clientAlgoId"][0]
        if client_id.endswith("sl-001"):
            return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, "STOP_MARKET", side="SELL"), 10)
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, "TAKE_PROFIT_MARKET", side="BUY"), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=mismatched, now_ms_provider=lambda: 1000).query_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "ORDER_IDENTITY_MISMATCH"
    assert result.cancel_request_transmitted is False

    def timeout(method, url, body, timeout, headers):
        raise TimeoutError("timeout")

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=timeout, now_ms_provider=lambda: 1000).query_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "QUERY_FAILED"
    assert result.cancel_request_transmitted is False


def test_triggered_order_in_recovery_is_critical(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        client_id = params["clientAlgoId"][0]
        order_type = "STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="TRIGGERED", actualOrderId=9, actualQty="0.001"), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))

    assert result.status == "CRITICAL"
    assert result.unexpected_trigger is True
