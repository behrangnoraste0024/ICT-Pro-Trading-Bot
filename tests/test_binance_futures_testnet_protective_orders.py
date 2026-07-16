from __future__ import annotations

import json
import os

import pytest
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs

from engine.diagnostics.binance_futures_testnet_protective_orders_engine import BinanceFuturesTestnetProtectiveOrdersEngine
from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import BinanceLifecycleHTTPResponse
from infrastructure.exchanges.binance_futures_testnet_protective_orders_client import BinanceFuturesTestnetProtectiveAPIError, BinanceFuturesTestnetProtectiveOrdersClient
from models.binance_futures_testnet_protective_orders import BinanceFuturesTestnetProtectiveOrdersConfig
from reporting.binance_futures_testnet_protective_orders_report import format_binance_futures_testnet_protective_orders_result


class _LegacyProtectivePersistence:
    """Release 2.84 tests isolate exchange/journal behavior from the 2.88 write layer."""

    legacy_noop = True

    def __init__(self, **kwargs) -> None:
        pass

    def ensure_available(self) -> None:
        pass

    def close(self) -> None:
        pass

    def check_consistency(self, *args, **kwargs):
        from infrastructure.persistence.protective_lifecycle_persistence import ProtectiveConsistencyResult

        return ProtectiveConsistencyResult("FRESH")

    def prepare_lifecycle(self, *args, **kwargs):
        return None


@pytest.fixture(autouse=True)
def _isolate_legacy_protective_tests(monkeypatch) -> None:
    monkeypatch.setattr(
        "engine.diagnostics.binance_futures_testnet_protective_orders_engine.ProtectiveLifecyclePersistence",
        _LegacyProtectivePersistence,
    )


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
    created = set()
    deleted = set()

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
            deleted.add(client_id)
            return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": 1, "code": 200}, 10)
        order_type = params.get("type", ["STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"])[0]
        trigger = params.get("triggerPrice", ["45000.00" if order_type == "STOP_MARKET" else "55000.00"])[0]
        if method == "POST":
            created.add(client_id)
            return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)
        if client_id in deleted or client_id not in created:
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)

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
    created = set()
    deleted = set()

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = (params.get("clientAlgoId") or [""])[0]
        order_type = params.get("type", ["STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"])[0]
        trigger = params.get("triggerPrice", ["45000.00" if order_type == "STOP_MARKET" else "55000.00"])[0]
        if method == "POST":
            created.add(client_id)
            return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)
        if method == "DELETE":
            deleted.add(client_id)
            return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": 1, "code": 200}, 10)
        if client_id in deleted or client_id not in created:
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "PASS"
    assert result.lifecycle_complete is True
    algo_calls = [(method, (params.get("clientAlgoId") or [""])[0]) for method, url, params in calls if "algoOrder" in url]
    assert algo_calls[:5] == [("GET", "smcbot-protect-sl-001"), ("POST", "smcbot-protect-sl-001"), ("GET", "smcbot-protect-sl-001"), ("GET", "smcbot-protect-tp-001"), ("POST", "smcbot-protect-tp-001")]
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
        assert result.decision in ("ORDER_IDENTITY_MISMATCH", "RECOVERY_REQUIRED")


def test_delete_response_can_be_sparse_but_final_get_is_verified(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []
    statuses = {
        "smcbot-protect-sl-001": ["NEW", "CANCELED"],
        "smcbot-protect-tp-001": ["NEW", "CANCELED"],
    }
    created = set()
    deleted = set()

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        if method == "DELETE":
            deleted.add(client_id)
            return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": 1, "code": 200, "msg": "success"}, 10)
        order_type = params.get("type", ["STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"])[0]
        trigger = params.get("triggerPrice", ["45000.00" if order_type == "STOP_MARKET" else "55000.00"])[0]
        if method == "POST":
            created.add(client_id)
            return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)
        if client_id in deleted or client_id not in created:
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)

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
        if method == "GET":
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        if method == "POST":
            raise TimeoutError("timeout after POST transmission")
        raise AssertionError("no cancel after uncertain create")

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
        if method == "GET":
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        if method == "POST":
            raise BinanceFuturesTestnetProtectiveAPIError("timestamp outside recvWindow", http_status=400, binance_code=-1021, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        raise AssertionError("no cancel after timestamp-rejected POST")

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
        if method == "DELETE":
            statuses[client_id] = ["ABSENT"]
            return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": 1, "code": 200}, 10)
        if statuses[client_id][0] == "ABSENT":
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        status = statuses[client_id].pop(0)
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
        if method == "GET" and any(call[0] == "DELETE" and call[2]["clientAlgoId"][0] == client_id for call in calls):
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, "STOP_MARKET", status="NEW"), 10)

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
    journal.write_text(json.dumps({"schema_version": "1.0", "pair_id": "pair-001", "stop_client_algo_id": "smcbot-protect-sl-001", "take_profit_client_algo_id": "smcbot-protect-tp-001", "phase": "RECOVERY_REQUIRED", "recovery_required": True, "baseline_available": True, "baseline_position_amount": "0.001", "baseline_position_direction": "LONG", "stop_trigger": "45000.00", "take_profit_trigger": "55000.00", "mutation_intents": [], "entries": []}), encoding="utf-8")

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
    journal.write_text(json.dumps({"schema_version": "1.0", "pair_id": "pair-001", "stop_client_algo_id": "smcbot-protect-sl-001", "take_profit_client_algo_id": "smcbot-protect-tp-001", "phase": "RECOVERY_REQUIRED", "recovery_required": True, "baseline_available": True, "baseline_position_amount": "0.001", "baseline_position_direction": "LONG", "stop_trigger": "45000.00", "take_profit_trigger": "55000.00", "mutation_intents": [], "entries": [{"created_at": "2026-01-01T00:00:00+00:00", "phase": "OLD", "details": {"kept": True}}]}), encoding="utf-8")

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
    journal.write_text(json.dumps({"schema_version": "1.0", "pair_id": "other", "stop_client_algo_id": "smcbot-protect-other-sl", "take_profit_client_algo_id": "smcbot-protect-other-tp", "phase": "RECOVERY_REQUIRED", "recovery_required": True, "baseline_available": False, "baseline_position_amount": None, "baseline_position_direction": None, "stop_trigger": None, "take_profit_trigger": None, "mutation_intents": [], "entries": [{"created_at": "2026-01-01T00:00:00+00:00", "phase": "OLD", "details": {}}]}), encoding="utf-8")

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        order_type = "STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="CANCELED"), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "STALE_OR_MISMATCHED_JOURNAL"


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


def test_deterministic_protective_client_algo_ids_are_stable_safe_and_unique(tmp_path: Path) -> None:
    client = BinanceFuturesTestnetProtectiveOrdersClient(BinanceFuturesTestnetProtectiveOrdersConfig(), env=_env())

    stop_id = client.derive_client_algo_id("pair-001", "STOP", "LONG", Decimal("50000"))
    take_id = client.derive_client_algo_id("pair-001", "TAKE_PROFIT", "LONG", Decimal("50000"))

    assert stop_id == client.derive_client_algo_id("pair-001", "STOP", "LONG", Decimal("50000"))
    assert stop_id != take_id
    assert stop_id != client.derive_client_algo_id("pair-002", "STOP", "LONG", Decimal("50000"))
    assert len(stop_id) <= 36
    assert len(take_id) <= 36
    assert stop_id.startswith("smcbot-protect-sl-")
    assert take_id.startswith("smcbot-protect-tp-")
    assert all(char.isalnum() or char in "-_" for char in stop_id + take_id)

    try:
        client.build_preview("pair-001", "bad id", "smcbot-protect-tp-001", client.require_protectable_position(_position()), client.parse_exchange_filters(_exchange_info()), 1000, 1000)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid explicit clientAlgoId must fail closed")


def test_intent_is_persisted_before_post_and_absent_reconciliation_stops(tmp_path: Path) -> None:
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
            journal_payload = json.loads(_runtime_file(tmp_path, "protective.json").read_text(encoding="utf-8"))
            assert journal_payload["mutation_intents"][0]["mutation_kind"] == "CREATE"
            raise TimeoutError("timeout after possible transmission")
        if method == "GET":
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        raise AssertionError("unexpected mutation")

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert len([call for call in calls if call[0] == "POST"]) == 1
    assert result.reconciliation_results[-1].reconciliation_state == "ABSENT"
    assert result.reconciliation_results[-1].interpreted_mutation_result == "CREATE_NOT_APPLIED"


def test_persistence_failure_prevents_protective_post(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        raise AssertionError("mutation must not be transmitted if intent persistence fails")

    engine = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000)
    original = engine._write_journal

    def failing_write(config, journal, phase, details):
        if phase.endswith("CREATE_INTENT_PERSISTED"):
            raise OSError("journal fsync failed")
        return original(config, journal, phase, details)

    engine._write_journal = failing_write
    result = engine.run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert not any(call[0] == "POST" for call in calls)


def test_post_timeout_with_exact_order_present_confirms_create_and_does_not_retry(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        order_type = params.get("type", ["STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"])[0]
        trigger = params.get("triggerPrice", ["45000.00" if order_type == "STOP_MARKET" else "55000.00"])[0]
        if method == "POST" and client_id == "smcbot-protect-sl-001":
            raise TimeoutError("timeout after possible POST transmission")
        if method == "GET" and not any(call[0] == "POST" and call[2].get("clientAlgoId", [""])[0] == client_id for call in calls):
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        if method == "GET" and any(call[0] == "DELETE" and call[2].get("clientAlgoId", [""])[0] == client_id for call in calls):
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        if method == "DELETE":
            return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": 1, "code": 200}, 10)
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "PASS"
    stop_posts = [call for call in calls if call[0] == "POST" and call[2].get("clientAlgoId", [""])[0] == "smcbot-protect-sl-001"]
    assert len(stop_posts) == 1
    assert any(item.interpreted_mutation_result == "CREATE_CONFIRMED" for item in result.reconciliation_results)


def test_delete_timeout_absent_confirms_delete_without_retry(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        order_type = params.get("type", ["STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"])[0]
        trigger = params.get("triggerPrice", ["45000.00" if order_type == "STOP_MARKET" else "55000.00"])[0]
        if method == "DELETE" and client_id == "smcbot-protect-tp-001":
            raise TimeoutError("timeout after possible DELETE transmission")
        if method == "GET" and not any(call[0] == "POST" and call[2].get("clientAlgoId", [""])[0] == client_id for call in calls):
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        if method == "GET" and any(call[0] == "DELETE" and call[2].get("clientAlgoId", [""])[0] == client_id for call in calls):
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        if method == "DELETE":
            return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": 1, "code": 200}, 10)
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "PASS"
    deletes = [call for call in calls if call[0] == "DELETE" and call[2].get("clientAlgoId", [""])[0] == "smcbot-protect-tp-001"]
    assert len(deletes) == 1
    assert any(item.interpreted_mutation_result == "DELETE_CONFIRMED" for item in result.reconciliation_results)


def test_delete_timeout_present_requires_recovery_and_does_not_retry(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        order_type = params.get("type", ["STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"])[0]
        trigger = params.get("triggerPrice", ["45000.00" if order_type == "STOP_MARKET" else "55000.00"])[0]
        if method == "DELETE" and client_id == "smcbot-protect-tp-001":
            raise ConnectionResetError("reset after possible DELETE")
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    deletes = [call for call in calls if call[0] == "DELETE" and call[2].get("clientAlgoId", [""])[0] == "smcbot-protect-tp-001"]
    assert len(deletes) == 1
    assert result.reconciliation_results[-1].interpreted_mutation_result == "DELETE_NOT_APPLIED"


def test_ambiguous_lookup_failures_remain_recovery_required(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    for exc in (TimeoutError("lookup timeout"), OSError("TLS lookup failed"), ConnectionResetError("lookup reset"), BinanceFuturesTestnetProtectiveAPIError("temporary 5xx", http_status=503, binance_code=None, method="GET", path="/fapi/v1/algoOrder", request_transmitted=True, response_received=False)):
        calls = []

        def transport(method, url, body, timeout, headers, exc=exc):
            params = parse_qs(body.decode("utf-8"))
            calls.append((method, url, params))
            if "positionSide/dual" in url:
                return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
            if "positionRisk" in url:
                return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
            if method == "POST":
                raise TimeoutError("create maybe transmitted")
            if method == "GET":
                raise exc
            raise AssertionError("unexpected mutation")

        result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

        assert result.status == "FAIL"
        assert result.decision == "RECOVERY_REQUIRED"
        assert len([call for call in calls if call[0] == "POST"]) == 0
        assert result.reconciliation_results[-1].reconciliation_state == "AMBIGUOUS"


def test_reconciliation_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        if method == "POST":
            raise TimeoutError("create maybe transmitted")
        return BinanceLifecycleHTTPResponse(200, url, _algo_response("smcbot-protect-sl-001", "STOP_MARKET", side="BUY"), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert result.reconciliation_results[-1].reconciliation_state == "IDENTITY_MISMATCH"


def test_recovery_resolves_persisted_ambiguous_create_intent(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    journal = _runtime_file(tmp_path, "protective.json")
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps({
        "schema_version": "1.0",
        "pair_id": "pair-001",
        "stop_client_algo_id": "smcbot-protect-sl-001",
        "take_profit_client_algo_id": "smcbot-protect-tp-001",
        "phase": "RECOVERY_REQUIRED",
        "recovery_required": True,
        "baseline_available": True,
        "baseline_position_amount": "0.001",
        "baseline_position_direction": "LONG",
        "stop_trigger": "45000.00",
        "take_profit_trigger": "55000.00",
        "mutation_intents": [{
            "intent_version": "1.0",
            "pair_id": "pair-001",
            "symbol": "BTCUSDT",
            "label": "STOP",
            "mutation_kind": "CREATE",
            "client_algo_id": "smcbot-protect-sl-001",
            "expected_order_type": "STOP_MARKET",
            "expected_side": "SELL",
            "expected_trigger_price": "45000.00",
            "expected_close_position": True,
            "expected_working_type": "MARK_PRICE",
            "expected_price_protect": True,
            "baseline_position_amount": "0.001",
            "baseline_position_direction": "LONG",
            "created_at": "2026-01-01T00:00:00+00:00",
            "mutation_phase": "STOP_CREATE_STARTED",
            "resolved": False,
            "reconciliation_state": "AMBIGUOUS",
            "reconciliation_reason": "timeout"
        }],
        "entries": []
    }), encoding="utf-8")
    calls = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        if client_id == "smcbot-protect-tp-001":
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        if method == "GET" and any(call[0] == "DELETE" for call in calls):
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, "STOP_MARKET", status="NEW", trigger="45000.00"), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))

    assert result.status == "PASS"
    assert any(item.interpreted_mutation_result == "CREATE_CONFIRMED" for item in result.reconciliation_results)


def test_stale_or_malformed_persisted_intent_requires_recovery(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    journal = _runtime_file(tmp_path, "protective.json")
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps({
        "stop_client_algo_id": "smcbot-protect-sl-001",
        "take_profit_client_algo_id": "smcbot-protect-tp-001",
        "mutation_intents": [{"label": "STOP", "mutation_kind": "CREATE", "client_algo_id": "smcbot-protect-other", "symbol": "BTCUSDT"}],
        "entries": []
    }), encoding="utf-8")

    def transport(method, url, body, timeout, headers):
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        raise AssertionError("stale intent must fail before exact order lookup")

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"


def test_protective_reconciliation_report_is_sanitized(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        if method == "POST":
            raise TimeoutError("timeout signature=secret X-MBX-APIKEY")
        raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))
    rendered = format_binance_futures_testnet_protective_orders_result(result)

    assert "Mutation Reconciliation" in rendered
    assert "signature=" not in rendered
    assert "X-MBX-APIKEY" not in rendered
    assert "unit-test-secret" not in rendered


def _ambiguous_stop_create_journal(pair_id: str = "pair-001", symbol: str = "BTCUSDT", version: str = "1.0") -> dict:
    return {
        "schema_version": "1.0",
        "pair_id": pair_id,
        "stop_client_algo_id": "smcbot-protect-sl-001",
        "take_profit_client_algo_id": "smcbot-protect-tp-001",
        "phase": "RECOVERY_REQUIRED",
        "recovery_required": True,
        "baseline_available": True,
        "baseline_position_amount": "0.001",
        "baseline_position_direction": "LONG",
        "stop_trigger": "45000.00",
        "take_profit_trigger": "55000.00",
        "mutation_intents": [{
            "intent_version": version,
            "pair_id": pair_id,
            "symbol": symbol,
            "label": "STOP",
            "mutation_kind": "CREATE",
            "client_algo_id": "smcbot-protect-sl-001",
            "expected_order_type": "STOP_MARKET",
            "expected_side": "SELL",
            "expected_trigger_price": "45000.00",
            "expected_close_position": True,
            "expected_working_type": "MARK_PRICE",
            "expected_price_protect": True,
            "baseline_position_amount": "0.001",
            "baseline_position_direction": "LONG",
            "created_at": "2026-01-01T00:00:00+00:00",
            "mutation_phase": "STOP_CREATE_STARTED",
            "resolved": False,
            "reconciliation_state": "AMBIGUOUS",
            "reconciliation_reason": "timeout",
        }],
        "entries": [],
    }


def test_fresh_lifecycle_unresolved_journal_blocks_mutation_after_exact_reconcile(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    journal = _runtime_file(tmp_path, "protective.json")
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps(_ambiguous_stop_create_journal()), encoding="utf-8")
    calls = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        client_id = params["clientAlgoId"][0]
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, "STOP_MARKET", status="NEW", trigger="45000.00"), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert [call[0] for call in calls] == ["GET"]
    persisted = json.loads(journal.read_text(encoding="utf-8"))
    assert persisted["mutation_intents"][0]["resolved"] is True


def test_fresh_lifecycle_malformed_or_stale_journal_blocks_without_mutation(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    cases = [
        "{not-json",
        json.dumps(["wrong"]),
        json.dumps(_ambiguous_stop_create_journal(version="9.9")),
        json.dumps(_ambiguous_stop_create_journal(pair_id="other-pair")),
        json.dumps(_ambiguous_stop_create_journal(symbol="ETHUSDT")),
    ]
    for payload in cases:
        journal = _runtime_file(tmp_path, "protective.json")
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text(payload, encoding="utf-8")
        calls = []

        def transport(method, url, body, timeout, headers):
            calls.append(method)
            raise AssertionError("journal validation failure must happen before authenticated mutation")

        result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

        assert result.status == "FAIL"
        assert result.recovery_required is True
        assert calls == []


def test_pre_create_lookup_present_reuses_order_and_sends_zero_post(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        order_type = "STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"
        trigger = "45000.00" if order_type == "STOP_MARKET" else "55000.00"
        if method == "DELETE":
            return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": 1, "code": 200}, 10)
        if method == "GET" and any(call[0] == "DELETE" and call[2].get("clientAlgoId", [""])[0] == client_id for call in calls):
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "PASS"
    assert not any(call[0] == "POST" for call in calls)


def test_pre_create_lookup_ambiguous_or_mismatch_sends_zero_post(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    for response in ("timeout", "mismatch"):
        calls = []

        def transport(method, url, body, timeout, headers, response=response):
            params = parse_qs(body.decode("utf-8"))
            calls.append((method, url, params))
            if "positionSide/dual" in url:
                return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
            if "positionRisk" in url:
                return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
            if response == "timeout":
                raise TimeoutError("pre-create lookup timeout")
            return BinanceLifecycleHTTPResponse(200, url, _algo_response("smcbot-protect-sl-001", "STOP_MARKET", side="BUY"), 10)

        result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

        assert result.status == "FAIL"
        assert result.decision == "RECOVERY_REQUIRED"
        assert not any(call[0] == "POST" for call in calls)


def test_resolved_compatible_journal_is_archived_before_new_lifecycle(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    journal = _runtime_file(tmp_path, "protective.json")
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps({"schema_version": "1.0", "pair_id": "pair-001", "stop_client_algo_id": "smcbot-protect-sl-001", "take_profit_client_algo_id": "smcbot-protect-tp-001", "phase": "COMPLETE", "recovery_required": False, "baseline_available": False, "baseline_position_amount": None, "baseline_position_direction": None, "stop_trigger": None, "take_profit_trigger": None, "mutation_intents": [], "entries": []}), encoding="utf-8")
    calls = []
    created = set()
    deleted = set()

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        order_type = params.get("type", ["STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"])[0]
        trigger = params.get("triggerPrice", ["45000.00" if order_type == "STOP_MARKET" else "55000.00"])[0]
        if method == "POST":
            created.add(client_id)
            return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)
        if method == "DELETE":
            deleted.add(client_id)
            return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": 1, "code": 200}, 10)
        if client_id in deleted or client_id not in created:
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "PASS"
    assert list(journal.parent.glob("protective.json.archived.*"))



def _write_runtime_journal(tmp_path: Path, payload: dict) -> Path:
    journal = _runtime_file(tmp_path, "protective.json")
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps(payload), encoding="utf-8")
    return journal


def _run_lifecycle_with_journal_payload(tmp_path: Path, payload: dict):
    path = _write_config(tmp_path)
    _write_runtime_journal(tmp_path, payload)
    calls = []

    def transport(method, url, body, timeout, headers):
        calls.append(method)
        raise AssertionError("invalid journal must fail before authenticated transport")

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))
    return result, calls


@pytest.mark.parametrize("field", [
    "intent_version",
    "pair_id",
    "symbol",
    "label",
    "mutation_kind",
    "client_algo_id",
    "expected_order_type",
    "expected_side",
    "expected_trigger_price",
    "expected_close_position",
    "expected_working_type",
    "expected_price_protect",
    "baseline_position_amount",
    "baseline_position_direction",
    "created_at",
    "mutation_phase",
    "resolved",
    "reconciliation_state",
    "reconciliation_reason",
])
def test_persisted_intent_missing_required_field_fails_before_transport(tmp_path: Path, field: str) -> None:
    payload = _ambiguous_stop_create_journal()
    payload["mutation_intents"][0].pop(field)

    result, calls = _run_lifecycle_with_journal_payload(tmp_path, payload)

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert calls == []


@pytest.mark.parametrize("field,value", [
    ("expected_close_position", "true"),
    ("expected_price_protect", 1),
    ("resolved", "false"),
    ("expected_trigger_price", "NaN"),
    ("expected_trigger_price", "Infinity"),
    ("expected_trigger_price", "0"),
    ("expected_trigger_price", "-1"),
    ("baseline_position_amount", "NaN"),
])
def test_persisted_intent_invalid_required_field_fails_before_transport(tmp_path: Path, field: str, value) -> None:
    payload = _ambiguous_stop_create_journal()
    payload["mutation_intents"][0][field] = value

    result, calls = _run_lifecycle_with_journal_payload(tmp_path, payload)

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert calls == []


@pytest.mark.parametrize("mutation_intents", [None, {}, "[]"])
def test_journal_mutation_intents_must_be_explicit_list(tmp_path: Path, mutation_intents) -> None:
    payload = _ambiguous_stop_create_journal()
    if mutation_intents is None:
        payload.pop("mutation_intents")
    else:
        payload["mutation_intents"] = mutation_intents

    result, calls = _run_lifecycle_with_journal_payload(tmp_path, payload)

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert calls == []


def test_recovery_delete_persists_intent_before_transport_and_result_after_lookup(tmp_path: Path, monkeypatch) -> None:
    path = _write_config(tmp_path)
    events = []
    deleted = set()

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        if "positionRisk" in url:
            events.append("position_risk")
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        events.append(f"{method}:{client_id}")
        if method == "DELETE":
            deleted.add(client_id)
            return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": 1, "code": 200}, 10)
        if client_id in deleted:
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        order_type = "STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"
        trigger = "45000.00" if order_type == "STOP_MARKET" else "55000.00"
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)

    engine = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000)
    original_write = engine._write_journal

    def recording_write(config, journal, phase, details):
        events.append(f"persist:{phase}")
        return original_write(config, journal, phase, details)

    monkeypatch.setattr(engine, "_write_journal", recording_write)

    result = engine.recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))

    assert result.status == "PASS"
    assert events.index("persist:TAKE_PROFIT_DELETE_INTENT_PERSISTED") < events.index("DELETE:smcbot-protect-tp-001")
    tp_delete_index = events.index("DELETE:smcbot-protect-tp-001")
    assert any(index > tp_delete_index and event == "GET:smcbot-protect-tp-001" for index, event in enumerate(events))
    assert any(event.startswith("persist:TAKE_PROFIT_DELETE_DELETE_CONFIRMED") for event in events)
    assert events.index("persist:STOP_DELETE_INTENT_PERSISTED") < events.index("DELETE:smcbot-protect-sl-001")
    assert len([event for event in events if event.startswith("DELETE:")]) == 2


@pytest.mark.parametrize("failing_phase", ["TAKE_PROFIT_DELETE_INTENT_PERSISTED", "STOP_DELETE_INTENT_PERSISTED"])
def test_recovery_delete_persistence_failure_prevents_delete(tmp_path: Path, monkeypatch, failing_phase: str) -> None:
    path = _write_config(tmp_path)
    calls = []
    deleted = set()

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        calls.append((method, client_id))
        if method == "DELETE":
            if client_id == "smcbot-protect-tp-001":
                deleted.add(client_id)
                return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": 1, "code": 200}, 10)
            raise AssertionError("STOP DELETE must not transmit after persistence failure")
        if client_id in deleted:
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        order_type = "STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"
        trigger = "45000.00" if order_type == "STOP_MARKET" else "55000.00"
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)

    engine = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000)
    original_write = engine._write_journal

    def failing_write(config, journal, phase, details):
        if phase == failing_phase:
            raise OSError("forced persistence failure")
        return original_write(config, journal, phase, details)

    monkeypatch.setattr(engine, "_write_journal", failing_write)

    result = engine.recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    if failing_phase == "TAKE_PROFIT_DELETE_INTENT_PERSISTED":
        assert not any(call[0] == "DELETE" for call in calls)
    else:
        assert ("DELETE", "smcbot-protect-tp-001") in calls
        assert ("DELETE", "smcbot-protect-sl-001") not in calls


def test_recovery_delete_atomic_replace_failure_prevents_delete(tmp_path: Path, monkeypatch) -> None:
    path = _write_config(tmp_path)
    calls = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        calls.append((method, client_id))
        order_type = "STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"
        trigger = "45000.00" if order_type == "STOP_MARKET" else "55000.00"
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)

    import engine.diagnostics.binance_futures_testnet_protective_orders_engine as protective_engine_module

    original_replace = protective_engine_module.os.replace

    def failing_replace(src, dst):
        if str(src).endswith("protective.json.tmp"):
            raise OSError("forced replace failure")
        return original_replace(src, dst)

    monkeypatch.setattr(protective_engine_module.os, "replace", failing_replace)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert not any(call[0] == "DELETE" for call in calls)


def test_delete_ack_result_uses_pending_reconciliation_state(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    events = []
    deleted = set()

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        events.append((method, client_id))
        if method == "DELETE":
            deleted.add(client_id)
            return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": 1, "code": 200}, 10)
        if client_id in deleted or method == "GET" and not any(event[0] == "POST" and event[1] == client_id for event in events):
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        order_type = params.get("type", ["STOP_MARKET" if client_id.endswith("sl-001") else "TAKE_PROFIT_MARKET"])[0]
        trigger = params.get("triggerPrice", ["45000.00" if order_type == "STOP_MARKET" else "55000.00"])[0]
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "PASS"
    ack_results = [item for item in result.reconciliation_results if item.interpreted_mutation_result == "DELETE_ACKNOWLEDGED"]
    assert ack_results
    assert {item.reconciliation_state for item in ack_results} == {"PENDING"}



def test_protective_engine_has_no_direct_recovery_delete_bypass() -> None:
    source = Path("engine/diagnostics/binance_futures_testnet_protective_orders_engine.py").read_text(encoding="utf-8")
    assert source.count("client.cancel_algo_order_exact(") == 1
    assert "def _delete_with_reconciliation" in source



def _assert_untrusted_journal_preserved(tmp_path: Path, original: bytes, *, recovery: bool = False) -> None:
    path = _write_config(tmp_path)
    journal = _runtime_file(tmp_path, "protective.json")
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_bytes(original)
    calls = []

    def transport(method, url, body, timeout, headers):
        calls.append((method, url))
        raise AssertionError("untrusted journal must fail before authenticated transport")

    engine = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000)
    if recovery:
        result = engine.recover_protective_pair("smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY", config_path=str(path))
    else:
        result = engine.run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.recovery_required is True
    assert journal.read_bytes() == original
    assert not list(journal.parent.glob("protective.json.archived.*"))
    assert calls == []


@pytest.mark.parametrize("payload", [
    b"{not-json",
    json.dumps(["wrong"]).encode("utf-8"),
    json.dumps({**_ambiguous_stop_create_journal(), "pair_id": "other-pair"}).encode("utf-8"),
    json.dumps({**_ambiguous_stop_create_journal(symbol="ETHUSDT")}).encode("utf-8"),
    json.dumps({**_ambiguous_stop_create_journal(), "mutation_intents": None}).encode("utf-8"),
])
def test_untrusted_lifecycle_journal_bytes_are_preserved(tmp_path: Path, payload: bytes) -> None:
    _assert_untrusted_journal_preserved(tmp_path, payload, recovery=False)


@pytest.mark.parametrize("field,value", [
    ("intent_version", "9.9"),
    ("client_algo_id", "bad-id"),
    ("mutation_kind", "UPDATE"),
    ("label", "UNKNOWN"),
    ("created_at", "not-a-time"),
])
def test_untrusted_intent_journal_bytes_are_preserved(tmp_path: Path, field: str, value: str) -> None:
    payload = _ambiguous_stop_create_journal()
    payload["mutation_intents"][0][field] = value
    _assert_untrusted_journal_preserved(tmp_path, json.dumps(payload).encode("utf-8"), recovery=False)


@pytest.mark.parametrize("payload", [
    b"{not-json",
    json.dumps(["wrong"]).encode("utf-8"),
    json.dumps({**_ambiguous_stop_create_journal(), "pair_id": "other-pair"}).encode("utf-8"),
    json.dumps({**_ambiguous_stop_create_journal(), "mutation_intents": None}).encode("utf-8"),
])
def test_untrusted_recovery_journal_bytes_are_preserved(tmp_path: Path, payload: bytes) -> None:
    _assert_untrusted_journal_preserved(tmp_path, payload, recovery=True)


@pytest.mark.parametrize("created_at", [
    "",
    "   ",
    "not-a-time",
    "2026-99-99T00:00:00Z",
    "2026-07-13T19:42:38",
    123,
    1.5,
    None,
])
def test_invalid_created_at_fails_closed_and_preserves_journal(tmp_path: Path, created_at) -> None:
    payload = _ambiguous_stop_create_journal()
    payload["mutation_intents"][0]["created_at"] = created_at
    _assert_untrusted_journal_preserved(tmp_path, json.dumps(payload).encode("utf-8"), recovery=False)


@pytest.mark.parametrize("created_at", ["2026-07-13T19:42:38Z", "2026-07-13T19:42:38+00:00", "2026-07-13T23:12:38+03:30"])
def test_valid_created_at_formats_are_accepted(tmp_path: Path, created_at: str) -> None:
    payload = _ambiguous_stop_create_journal()
    payload["mutation_intents"][0]["created_at"] = created_at
    path = _write_config(tmp_path)
    _write_runtime_journal(tmp_path, payload)
    calls = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, params["clientAlgoId"][0]))
        return BinanceLifecycleHTTPResponse(200, url, _algo_response("smcbot-protect-sl-001", "STOP_MARKET", status="NEW", trigger="45000.00"), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert calls == [("GET", "smcbot-protect-sl-001")]


def _assert_rejected_strict_journal_preserved(tmp_path: Path, payload: dict) -> None:
    _assert_untrusted_journal_preserved(tmp_path, json.dumps(payload, sort_keys=True).encode("utf-8"), recovery=False)


MISSING = object()


def _set_or_remove_journal_field(payload: dict, field: str, value) -> None:
    if value is MISSING:
        payload.pop(field)
    else:
        payload[field] = value


@pytest.mark.parametrize("value", [MISSING, None, "", 1, True, {"version": "1.0"}, "9.9"])
def test_journal_schema_version_rejects_invalid_values_and_preserves_bytes(tmp_path: Path, value) -> None:
    payload = _ambiguous_stop_create_journal()
    _set_or_remove_journal_field(payload, "schema_version", value)
    _assert_rejected_strict_journal_preserved(tmp_path, payload)


def test_journal_schema_version_supported_value_reloads_successfully(tmp_path: Path) -> None:
    engine = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=lambda *args: None, now_ms_provider=lambda: 1000)
    journal = engine._journal_from_payload_strict(_ambiguous_stop_create_journal(), "pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001")
    assert journal.schema_version == "1.0"


@pytest.mark.parametrize("field,value", [
    ("pair_id", MISSING),
    ("pair_id", None),
    ("pair_id", ""),
    ("pair_id", 1),
    ("pair_id", True),
    ("pair_id", "other-pair"),
])
def test_journal_pair_id_is_required_string_and_exact_match(tmp_path: Path, field: str, value) -> None:
    payload = _ambiguous_stop_create_journal()
    _set_or_remove_journal_field(payload, field, value)
    _assert_rejected_strict_journal_preserved(tmp_path, payload)


@pytest.mark.parametrize("field,value", [
    ("stop_client_algo_id", MISSING),
    ("stop_client_algo_id", None),
    ("stop_client_algo_id", 1),
    ("stop_client_algo_id", ""),
    ("stop_client_algo_id", "smcbot-protect-other"),
    ("take_profit_client_algo_id", MISSING),
    ("take_profit_client_algo_id", None),
    ("take_profit_client_algo_id", False),
    ("take_profit_client_algo_id", ""),
    ("take_profit_client_algo_id", "smcbot-protect-other"),
])
def test_journal_protective_ids_are_required_strings_and_exact_match(tmp_path: Path, field: str, value) -> None:
    payload = _ambiguous_stop_create_journal()
    _set_or_remove_journal_field(payload, field, value)
    _assert_rejected_strict_journal_preserved(tmp_path, payload)


def test_journal_stop_and_take_profit_ids_must_be_distinct(tmp_path: Path) -> None:
    payload = _ambiguous_stop_create_journal()
    payload["take_profit_client_algo_id"] = payload["stop_client_algo_id"]
    payload["mutation_intents"][0]["client_algo_id"] = payload["stop_client_algo_id"]
    _assert_rejected_strict_journal_preserved(tmp_path, payload)


@pytest.mark.parametrize("field,value", [
    ("recovery_required", "false"),
    ("recovery_required", 0),
    ("recovery_required", None),
    ("baseline_available", "true"),
    ("baseline_available", 1),
    ("baseline_available", None),
])
def test_journal_booleans_reject_coerced_values(tmp_path: Path, field: str, value) -> None:
    payload = _ambiguous_stop_create_journal()
    payload[field] = value
    _assert_rejected_strict_journal_preserved(tmp_path, payload)


@pytest.mark.parametrize("value", [MISSING, None, "[]", {}, ["bad-entry"]])
def test_journal_entries_must_be_explicit_sanitized_list(tmp_path: Path, value) -> None:
    payload = _ambiguous_stop_create_journal()
    _set_or_remove_journal_field(payload, "entries", value)
    _assert_rejected_strict_journal_preserved(tmp_path, payload)


@pytest.mark.parametrize("value", [MISSING, None, "", 1, "UNKNOWN_PHASE"])
def test_journal_phase_must_be_known_string(tmp_path: Path, value) -> None:
    payload = _ambiguous_stop_create_journal()
    _set_or_remove_journal_field(payload, "phase", value)
    _assert_rejected_strict_journal_preserved(tmp_path, payload)


def test_journal_serialization_writes_schema_and_reloads_exact_top_level_types(tmp_path: Path) -> None:
    engine = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=lambda *args: None, now_ms_provider=lambda: 1000)
    original = engine._journal_from_payload_strict(_ambiguous_stop_create_journal(), "pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001")
    payload = original.to_dict()
    assert payload["schema_version"] == "1.0"
    assert isinstance(payload["schema_version"], str)
    assert isinstance(payload["pair_id"], str)
    assert isinstance(payload["stop_client_algo_id"], str)
    assert isinstance(payload["take_profit_client_algo_id"], str)
    assert isinstance(payload["phase"], str)
    assert isinstance(payload["recovery_required"], bool)
    assert isinstance(payload["baseline_available"], bool)
    assert isinstance(payload["entries"], list)
    assert isinstance(payload["mutation_intents"], list)
    reloaded = engine._journal_from_payload_strict(payload, "pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001")
    assert reloaded.schema_version == original.schema_version
    assert reloaded.pair_id == original.pair_id
    assert reloaded.stop_client_algo_id == original.stop_client_algo_id
    assert reloaded.take_profit_client_algo_id == original.take_profit_client_algo_id
    assert reloaded.recovery_required is original.recovery_required
    assert reloaded.baseline_available is original.baseline_available


def _terminal_journal_payload(marker: str = "original") -> dict:
    return {
        "schema_version": "1.0",
        "pair_id": "pair-001",
        "stop_client_algo_id": "smcbot-protect-sl-001",
        "take_profit_client_algo_id": "smcbot-protect-tp-001",
        "phase": "COMPLETE",
        "recovery_required": False,
        "baseline_available": False,
        "baseline_position_amount": None,
        "baseline_position_direction": None,
        "stop_trigger": None,
        "take_profit_trigger": None,
        "mutation_intents": [],
        "entries": [{"created_at": "2026-01-01T00:00:00+00:00", "phase": "COMPLETE", "details": {"marker": marker}}],
    }


def _successful_lifecycle_transport(calls: list):
    created = set()
    deleted = set()

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, url, params))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        client_id = params["clientAlgoId"][0]
        order_type = params.get("type", ["STOP_MARKET" if "sl-" in client_id else "TAKE_PROFIT_MARKET"])[0]
        trigger = params.get("triggerPrice", ["45000.00" if order_type == "STOP_MARKET" else "55000.00"])[0]
        if method == "POST":
            created.add(client_id)
            return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)
        if method == "DELETE":
            deleted.add(client_id)
            return BinanceLifecycleHTTPResponse(200, url, {"clientAlgoId": client_id, "algoId": 1, "code": 200}, 10)
        if client_id in deleted or client_id not in created:
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        return BinanceLifecycleHTTPResponse(200, url, _algo_response(client_id, order_type, status="NEW", trigger=trigger), 10)

    return transport


def test_archive_preserves_exact_content_and_new_journal_is_separate(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    journal = _runtime_file(tmp_path, "protective.json")
    journal.parent.mkdir(parents=True, exist_ok=True)
    original = json.dumps(_terminal_journal_payload("archive-me"), sort_keys=True).encode("utf-8")
    journal.write_bytes(original)
    calls = []

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=_successful_lifecycle_transport(calls), now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    archives = list(journal.parent.glob("protective.json.archived.*"))
    assert result.status == "PASS"
    assert len(archives) == 1
    assert archives[0].read_bytes() == original
    assert journal.exists()
    assert journal.read_bytes() != original


def test_archive_collision_uses_unique_destination_without_overwrite(tmp_path: Path, monkeypatch) -> None:
    path = _write_config(tmp_path)
    journal = _runtime_file(tmp_path, "protective.json")
    journal.parent.mkdir(parents=True, exist_ok=True)
    first_uuid = "a" * 32
    second_uuid = "b" * 32
    timestamp = "2026-07-13T19:42:38+00:00"
    original = json.dumps(_terminal_journal_payload("collision"), sort_keys=True).encode("utf-8")
    journal.write_bytes(original)
    context = "pair-001-smcbot-protect-sl-001-smcbot-protect-tp-001"
    existing_archive = journal.with_name(f"protective.json.archived.{context}.{timestamp.replace(':', '').replace('-', '').replace('.', '').replace('+', '')}.{first_uuid}")
    existing_archive.write_bytes(b"existing archive bytes")
    uuid_values = iter([type("U", (), {"hex": first_uuid})(), type("U", (), {"hex": second_uuid})()])
    monkeypatch.setattr("engine.diagnostics.binance_futures_testnet_protective_orders_engine.uuid.uuid4", lambda: next(uuid_values))
    calls = []

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=_successful_lifecycle_transport(calls), now_ms_provider=lambda: 1000, now_provider=lambda: timestamp).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "PASS"
    assert existing_archive.read_bytes() == b"existing archive bytes"
    archives = list(journal.parent.glob("protective.json.archived.*"))
    assert len(archives) == 2
    assert any(archive.read_bytes() == original for archive in archives)


def test_archive_move_failure_preserves_journal_and_blocks_preflight(tmp_path: Path, monkeypatch) -> None:
    path = _write_config(tmp_path)
    journal = _runtime_file(tmp_path, "protective.json")
    journal.parent.mkdir(parents=True, exist_ok=True)
    original = json.dumps(_terminal_journal_payload("move-fail"), sort_keys=True).encode("utf-8")
    journal.write_bytes(original)
    calls = []

    def failing_rename(self, target):
        raise OSError("forced archive move failure")

    monkeypatch.setattr(Path, "rename", failing_rename)

    def transport(method, url, body, timeout, headers):
        calls.append((method, url))
        raise AssertionError("archive failure must happen before preflight")

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=lambda url, timeout: (_ for _ in ()).throw(AssertionError("no public preflight after archive failure")), authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.recovery_required is True
    assert journal.read_bytes() == original
    assert calls == []
    assert not list(journal.parent.glob("protective.json.archived.*"))


def test_unresolved_or_incompatible_journal_is_not_archived(tmp_path: Path) -> None:
    cases = [
        _ambiguous_stop_create_journal(),
        {**_terminal_journal_payload("bad-phase"), "phase": "RECOVERY_REQUIRED", "recovery_required": True},
        {**_terminal_journal_payload("stale"), "pair_id": "other-pair"},
    ]
    for index, payload in enumerate(cases):
        case_root = tmp_path / f"case-{index}"
        path = _write_config(case_root)
        journal = _runtime_file(case_root, "protective.json")
        journal.parent.mkdir(parents=True, exist_ok=True)
        original = json.dumps(payload, sort_keys=True).encode("utf-8")
        journal.write_bytes(original)
        calls = []

        def transport(method, url, body, timeout, headers):
            calls.append((method, url))
            return BinanceLifecycleHTTPResponse(200, url, _algo_response("smcbot-protect-sl-001", "STOP_MARKET", status="NEW", trigger="45000.00"), 10)

        result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=case_root, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

        assert result.status == "FAIL"
        assert not list(journal.parent.glob("protective.json.archived.*"))
        assert journal.read_bytes() == original or payload.get("pair_id") == "pair-001"
        assert not any(call[0] in ("POST", "DELETE") for call in calls)


def test_unresolved_delete_startup_reconciles_without_new_mutation(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    payload = _ambiguous_stop_create_journal()
    payload["mutation_intents"][0].update({
        "mutation_kind": "DELETE",
        "mutation_phase": "STOP_DELETE_STARTED",
        "reconciliation_state": "AMBIGUOUS",
    })
    _write_runtime_journal(tmp_path, payload)
    calls = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, params["clientAlgoId"][0]))
        if method == "GET":
            raise BinanceFuturesTestnetProtectiveAPIError("NO_SUCH_ORDER", http_status=400, binance_code=-2013, method=method, path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True)
        raise AssertionError("unresolved DELETE startup must not mutate")

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert calls == [("GET", "smcbot-protect-sl-001")]
    persisted = json.loads(_runtime_file(tmp_path, "protective.json").read_text(encoding="utf-8"))
    assert persisted["mutation_intents"][0]["resolved"] is True
    assert persisted["mutation_intents"][0]["reconciliation_state"] == "ABSENT"


@pytest.mark.parametrize("outcome", ["present", "ambiguous"])
def test_unresolved_delete_startup_present_or_ambiguous_stops_without_mutation(tmp_path: Path, outcome: str) -> None:
    path = _write_config(tmp_path)
    payload = _ambiguous_stop_create_journal()
    payload["mutation_intents"][0].update({"mutation_kind": "DELETE", "mutation_phase": "STOP_DELETE_STARTED"})
    _write_runtime_journal(tmp_path, payload)
    calls = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))
        calls.append((method, params["clientAlgoId"][0]))
        if outcome == "ambiguous":
            raise TimeoutError("lookup ambiguous")
        return BinanceLifecycleHTTPResponse(200, url, _algo_response("smcbot-protect-sl-001", "STOP_MARKET", status="NEW", trigger="45000.00"), 10)

    result = BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 1000).run_protective_lifecycle("pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001", confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    expected_gets = 2 if outcome == "ambiguous" else 1
    assert calls == [("GET", "smcbot-protect-sl-001")] * expected_gets
    assert not any(method in ("POST", "DELETE") for method, _ in calls)
