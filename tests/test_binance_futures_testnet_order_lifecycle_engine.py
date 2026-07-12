from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs

import pytest

from engine.diagnostics.binance_futures_testnet_order_lifecycle_engine import BinanceFuturesTestnetOrderLifecycleEngine
from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import BinanceLifecycleHTTPResponse
from models.binance_futures_testnet_order_lifecycle import BinanceFuturesTestnetOrderLifecycleConfig


class _PassReport:
    status = "PASS"
    issues = []
    config = type("Config", (), {"kill_switch_enabled": True})()


class _PassEngine:
    def validate(self, *args, **kwargs):
        return _PassReport()


class _Runner:
    def validate_config(self, *args, **kwargs):
        return None, [], None


def _engine(tmp_path: Path, **kwargs) -> BinanceFuturesTestnetOrderLifecycleEngine:
    return BinanceFuturesTestnetOrderLifecycleEngine(
        repo_root=tmp_path,
        runtime_config_engine=_PassEngine(),
        monitoring_engine=_PassEngine(),
        runner_engine=_Runner(),
        testnet_adapter_engine=_PassEngine(),
        testnet_read_only_engine=_PassEngine(),
        testnet_order_test_engine=_PassEngine(),
        futures_feed_engine=_PassEngine(),
        futures_risk_model_engine=_PassEngine(),
        futures_paper_position_engine=_PassEngine(),
        **kwargs,
    )


def _write_config(tmp_path: Path, **overrides) -> Path:
    data = BinanceFuturesTestnetOrderLifecycleConfig().to_dict()
    data.update(overrides)
    path = tmp_path / "configs" / "binance_futures_testnet_order_lifecycle.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _runtime_file(tmp_path: Path, name: str) -> Path:
    return tmp_path / "data" / "runtime" / "binance_futures_testnet_order_lifecycle" / name


def _env() -> dict[str, str]:
    return {"BINANCE_FUTURES_TESTNET_API_KEY": "unit-test-key", "BINANCE_FUTURES_TESTNET_API_SECRET": "unit-test-secret"}


def _exchange_info() -> dict:
    return {"symbols": [{"symbol": "BTCUSDT", "filters": [{"filterType": "PRICE_FILTER", "minPrice": "1", "maxPrice": "1000000", "tickSize": "0.10"}, {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "100", "stepSize": "0.001"}, {"filterType": "MIN_NOTIONAL", "notional": "5"}]}]}


def _http_get(url, timeout):
    if url.endswith("/fapi/v1/time"):
        return BinanceLifecycleHTTPResponse(200, url, {"serverTime": 123}, 10)
    if "/fapi/v1/exchangeInfo" in url:
        return BinanceLifecycleHTTPResponse(200, url, _exchange_info(), 10)
    if "/fapi/v1/ticker/bookTicker" in url:
        return BinanceLifecycleHTTPResponse(200, url, {"symbol": "BTCUSDT", "bidPrice": "50000", "askPrice": "50001", "bidQty": "1", "askQty": "1"}, 10)
    raise AssertionError(f"unexpected GET {url}")


def _http_get_with_server_time(server_time: int):
    def http_get(url, timeout):
        if url.endswith("/fapi/v1/time"):
            return BinanceLifecycleHTTPResponse(200, url, {"serverTime": server_time}, 10)
        return _http_get(url, timeout)

    return http_get


def _transport(statuses: list[str] | None = None, executed_qty: str = "0"):
    calls = []
    statuses = list(statuses or ["NEW", "NEW", "CANCELED", "CANCELED"])

    def authenticated(method, url, body, timeout, headers):
        calls.append((method, url, body.decode("utf-8")))
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, [{"symbol": "BTCUSDT", "positionAmt": "0"}], 10)
        if method == "POST":
            return BinanceLifecycleHTTPResponse(200, url, {"symbol": "BTCUSDT", "clientOrderId": "smcbot-lifecycle-001", "orderId": 1, "side": "BUY", "type": "LIMIT", "timeInForce": "GTX", "price": "49500", "origQty": "0.001", "executedQty": executed_qty, "status": statuses.pop(0)}, 10)
        status = statuses.pop(0)
        return BinanceLifecycleHTTPResponse(200, url, {"symbol": "BTCUSDT", "clientOrderId": "smcbot-lifecycle-001", "orderId": 1, "side": "BUY", "type": "LIMIT", "timeInForce": "GTX", "price": "49500", "origQty": "0.001", "executedQty": executed_qty, "status": status}, 10)

    authenticated.calls = calls
    return authenticated


@pytest.mark.parametrize(("field", "value"), [("feature_enabled", True), ("manual_lifecycle_only", False), ("single_order_only", False), ("rest_base_url", "https://fapi.binance.com"), ("allowed_order_types", ["LIMIT", "MARKET"]), ("allowed_time_in_force", ["GTX", "GTC"]), ("allow_standalone_create", True), ("allow_cancel_all", True), ("allow_leverage_change", True), ("maximum_lifecycle_notional_usdt", 101), ("minimum_price_offset_bps", 1), ("request_timeout_seconds", 31), ("recv_window_ms", 10001), ("lifecycle_journal_path", "../bad.json")])
def test_dangerous_config_values_fail(tmp_path: Path, field: str, value) -> None:
    path = _write_config(tmp_path, **{field: value})

    report = _engine(tmp_path).validate(str(path))

    assert report.status == "FAIL"
    assert any(issue.name == field or field in issue.name for issue in report.issues)


def test_default_timeout_and_recv_window_are_hardened(tmp_path: Path) -> None:
    config = BinanceFuturesTestnetOrderLifecycleConfig()

    assert config.request_timeout_seconds == 30
    assert config.recv_window_ms == 10000


def test_timeout_30_seconds_is_valid_but_maximum_remains_30(tmp_path: Path) -> None:
    path = _write_config(tmp_path, request_timeout_seconds=30, recv_window_ms=10000)

    report = _engine(tmp_path).validate(str(path))

    assert report.status == "PASS"


def test_missing_confirmation_blocks_before_credentials_or_network(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    result = _engine(tmp_path, env=_env()).run_lifecycle("lifecycle-001", "smcbot-lifecycle-001", "BUY", 0.001, config_path=str(path))

    assert result.status == "WARNING"
    assert result.decision == "CONFIRMATION_REQUIRED"
    assert result.credentials_inspected is False
    assert result.create_request_transmitted is False


def test_missing_credentials_warns_without_network(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    result = _engine(tmp_path, env={}).run_lifecycle("lifecycle-001", "smcbot-lifecycle-001", "BUY", 0.001, confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE", config_path=str(path))

    assert result.status == "WARNING"
    assert result.decision == "CREDENTIALS_NOT_CONFIGURED"
    assert result.credentials_inspected is True
    assert result.create_request_transmitted is False


def test_run_lifecycle_existing_lock_blocks_without_network_or_journal_mutation(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    lock_path = _runtime_file(tmp_path, "lifecycle.lock")
    journal_path = _runtime_file(tmp_path, "lifecycle.json")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("other-owner", encoding="utf-8")
    journal_path.write_text("existing-journal", encoding="utf-8")
    calls = []

    def http_get(url, timeout):
        calls.append(("public", url))
        raise AssertionError("public network should not run when lifecycle lock exists")

    def transport(method, url, body, timeout, headers):
        calls.append(("auth", url))
        raise AssertionError("authenticated network should not run when lifecycle lock exists")

    result = _engine(tmp_path, env=_env(), http_get=http_get, authenticated_request=transport).run_lifecycle("lifecycle-001", "smcbot-lifecycle-001", "BUY", 0.001, confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert result.recovery_required is True
    assert calls == []
    assert lock_path.read_text(encoding="utf-8") == "other-owner"
    assert journal_path.read_text(encoding="utf-8") == "existing-journal"


def test_recover_lifecycle_existing_lock_blocks_without_network_or_journal_mutation(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    lock_path = _runtime_file(tmp_path, "lifecycle.lock")
    journal_path = _runtime_file(tmp_path, "lifecycle.json")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("other-owner", encoding="utf-8")
    journal_path.write_text("existing-journal", encoding="utf-8")
    calls = []

    def http_get(url, timeout):
        calls.append(("public", url))
        raise AssertionError("public network should not run when lifecycle lock exists")

    def transport(method, url, body, timeout, headers):
        calls.append(("auth", url))
        raise AssertionError("authenticated network should not run when lifecycle lock exists")

    result = _engine(tmp_path, env=_env(), http_get=http_get, authenticated_request=transport).recover_lifecycle("smcbot-lifecycle-001", confirmation="CONFIRM_TESTNET_EXACT_RECOVERY", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert result.recovery_required is True
    assert calls == []
    assert lock_path.read_text(encoding="utf-8") == "other-owner"
    assert journal_path.read_text(encoding="utf-8") == "existing-journal"


def test_owned_lock_acquisition_is_atomic(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    lock_path = _runtime_file(tmp_path, "lifecycle.lock")

    first = engine._acquire_owned_lock(lock_path, "first-token")
    second = engine._acquire_owned_lock(lock_path, "second-token")

    assert first is True
    assert second is False
    assert lock_path.read_text(encoding="utf-8") == "first-token"
    engine._release_owned_lock(lock_path, "first-token", first)
    assert not lock_path.exists()


def test_lock_token_is_sanitized_and_contains_no_secret_material(tmp_path: Path) -> None:
    engine = _engine(tmp_path)

    token = engine._lock_token("run_lifecycle", "life/cycle:001", "client order?001")

    assert "run_lifecycle" in token
    assert "life_cycle_001" in token
    assert "client_order_001" in token
    assert "unit-test-key" not in token
    assert "unit-test-secret" not in token
    assert "signature" not in token.lower()
    assert "http" not in token.lower()


def test_mocked_new_order_is_queried_cancelled_and_completed(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    transport = _transport(["NEW", "NEW", "CANCELED", "CANCELED"])

    result = _engine(tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 123).run_lifecycle("lifecycle-001", "smcbot-lifecycle-001", "BUY", 0.001, confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE", config_path=str(path))

    assert result.status == "PASS"
    assert result.decision == "LIFECYCLE_COMPLETE"
    assert result.order_created is True
    assert result.order_cancelled is True
    assert result.lifecycle_complete is True
    assert [call[0] for call in transport.calls].count("POST") == 1
    assert [call[0] for call in transport.calls].count("DELETE") == 1
    assert "signature=" not in (tmp_path / "data" / "runtime" / "binance_futures_testnet_order_lifecycle" / "lifecycle.json").read_text(encoding="utf-8")
    assert not _runtime_file(tmp_path, "lifecycle.lock").exists()


def test_lifecycle_signed_requests_use_fresh_monotonic_timestamps(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    transport = _transport(["NEW", "NEW", "CANCELED", "CANCELED"])
    now_values = iter([100000, 101000, 102000, 108000, 114000, 120000, 126000, 132000])

    result = _engine(tmp_path, env=_env(), http_get=_http_get_with_server_time(102050), authenticated_request=transport, now_ms_provider=lambda: next(now_values)).run_lifecycle("lifecycle-001", "smcbot-lifecycle-001", "BUY", 0.001, confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE", config_path=str(path))

    timestamps = [int(parse_qs(call[2])["timestamp"][0]) for call in transport.calls]
    paths = [call[1] for call in transport.calls]

    assert result.status == "PASS"
    assert ["/fapi/v1/positionSide/dual" in path for path in paths].count(True) == 1
    assert ["/fapi/v3/positionRisk" in path for path in paths].count(True) == 2
    assert ["/fapi/v1/order" in path for path in paths].count(True) == 4
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == len(timestamps)
    assert timestamps == [103050, 104050, 110050, 116050, 122050, 128050, 134050]
    assert max(timestamps) - min(timestamps) > BinanceFuturesTestnetOrderLifecycleConfig().recv_window_ms


def test_expired_order_completes_without_delete(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    transport = _transport(["EXPIRED", "EXPIRED", "EXPIRED"])

    result = _engine(tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 123).run_lifecycle("lifecycle-001", "smcbot-lifecycle-001", "BUY", 0.001, confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE", config_path=str(path))

    assert result.status == "PASS"
    assert [call[0] for call in transport.calls].count("DELETE") == 0


def test_clock_skew_still_fails_closed_before_create(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []
    now_values = iter([100000, 101000, 500000])

    def transport(method, url, body, timeout, headers):
        calls.append(method)
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, [{"symbol": "BTCUSDT", "positionAmt": "0"}], 10)
        raise AssertionError("order create should not run after clock skew failure")

    result = _engine(tmp_path, env=_env(), http_get=_http_get_with_server_time(1000), authenticated_request=transport, now_ms_provider=lambda: next(now_values)).run_lifecycle("lifecycle-001", "smcbot-lifecycle-001", "BUY", 0.001, confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "PUBLIC_PREFLIGHT_FAILED"
    assert result.order_created is False
    assert calls == []


def test_unexpected_fill_returns_critical(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    result = _engine(tmp_path, env=_env(), http_get=_http_get, authenticated_request=_transport(["PARTIALLY_FILLED"], executed_qty="0.001"), now_ms_provider=lambda: 123).run_lifecycle("lifecycle-001", "smcbot-lifecycle-001", "BUY", 0.001, confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE", config_path=str(path))

    assert result.status == "CRITICAL"
    assert result.decision == "UNEXPECTED_FILL_DETECTED"
    assert result.recovery_required is True


def test_create_timeout_returns_unknown_state_recovery(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def transport(method, url, body, timeout, headers):
        calls.append(method)
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, [{"symbol": "BTCUSDT", "positionAmt": "0"}], 10)
        if method == "POST":
            raise TimeoutError("timeout after POST transmission")
        raise AssertionError("no query or cancel should run after create timeout")

    result = _engine(tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 123).run_lifecycle("lifecycle-001", "smcbot-lifecycle-001", "BUY", 0.001, confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert result.recovery_required is True
    assert calls.count("POST") == 1
    assert calls.count("DELETE") == 0
    assert not _runtime_file(tmp_path, "lifecycle.lock").exists()


def test_replaced_lock_token_is_not_deleted_on_lifecycle_failure(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    lock_path = _runtime_file(tmp_path, "lifecycle.lock")

    def transport(method, url, body, timeout, headers):
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, [{"symbol": "BTCUSDT", "positionAmt": "0"}], 10)
        if method == "POST":
            lock_path.write_text("replacement-owner", encoding="utf-8")
            raise TimeoutError("timeout after POST transmission")
        raise AssertionError("no query or cancel should run after create timeout")

    result = _engine(tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 123).run_lifecycle("lifecycle-001", "smcbot-lifecycle-001", "BUY", 0.001, confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert lock_path.read_text(encoding="utf-8") == "replacement-owner"


def test_timeout_before_create_start_does_not_report_created_or_recovery(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def transport(method, url, body, timeout, headers):
        calls.append(method)
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            raise TimeoutError("timeout before create start")
        raise AssertionError("POST should not be used")

    result = _engine(tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 123).run_lifecycle("lifecycle-001", "smcbot-lifecycle-001", "BUY", 0.001, confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "AUTHENTICATED_PRECHECK_FAILED"
    assert result.order_created is False
    assert result.recovery_required is False
    assert calls.count("POST") == 0
    assert not _runtime_file(tmp_path, "lifecycle.lock").exists()


def test_cancel_timeout_returns_unknown_state_recovery(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def transport(method, url, body, timeout, headers):
        calls.append(method)
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, [{"symbol": "BTCUSDT", "positionAmt": "0"}], 10)
        if method == "POST":
            return BinanceLifecycleHTTPResponse(200, url, {"symbol": "BTCUSDT", "clientOrderId": "smcbot-lifecycle-001", "orderId": 1, "side": "BUY", "type": "LIMIT", "timeInForce": "GTX", "price": "49500", "origQty": "0.001", "executedQty": "0", "status": "NEW"}, 10)
        if method == "GET":
            return BinanceLifecycleHTTPResponse(200, url, {"symbol": "BTCUSDT", "clientOrderId": "smcbot-lifecycle-001", "orderId": 1, "side": "BUY", "type": "LIMIT", "timeInForce": "GTX", "price": "49500", "origQty": "0.001", "executedQty": "0", "status": "NEW"}, 10)
        if method == "DELETE":
            raise TimeoutError("timeout after DELETE transmission")
        raise AssertionError(f"unexpected method {method}")

    result = _engine(tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 123).run_lifecycle("lifecycle-001", "smcbot-lifecycle-001", "BUY", 0.001, confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert result.recovery_required is True
    assert calls.count("POST") == 1
    assert calls.count("DELETE") == 1
    assert not _runtime_file(tmp_path, "lifecycle.lock").exists()


def test_hedge_mode_blocks_before_post(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    def transport(method, url, body, timeout, headers):
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": True}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, [{"symbol": "BTCUSDT", "positionAmt": "0"}], 10)
        raise AssertionError("POST should not be used")

    result = _engine(tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 123).run_lifecycle("lifecycle-001", "smcbot-lifecycle-001", "BUY", 0.001, confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE", config_path=str(path))

    assert result.decision == "POSITION_MODE_UNSUPPORTED"
    assert result.create_request_transmitted is False


def test_recovery_query_and_cancel_require_confirmation(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    engine = _engine(tmp_path, env=_env())

    assert engine.query_order("smcbot-lifecycle-001", config_path=str(path)).decision == "CONFIRMATION_REQUIRED"
    assert engine.recovery_cancel("smcbot-lifecycle-001", config_path=str(path)).decision == "CONFIRMATION_REQUIRED"


def test_exact_query_and_recovery_cancel_use_fresh_timestamp_after_preflight(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []
    server_times = iter([1100, 12100])
    now_values = iter([1000, 7000, 12000, 18000])

    def http_get(url, timeout):
        if url.endswith("/fapi/v1/time"):
            return BinanceLifecycleHTTPResponse(200, url, {"serverTime": next(server_times)}, 10)
        return _http_get(url, timeout)

    def transport(method, url, body, timeout, headers):
        calls.append((method, body.decode("utf-8")))
        if method == "GET":
            return BinanceLifecycleHTTPResponse(200, url, {"symbol": "BTCUSDT", "clientOrderId": "smcbot-lifecycle-001", "orderId": 1, "side": "BUY", "type": "LIMIT", "timeInForce": "GTX", "price": "49500", "origQty": "0.001", "executedQty": "0", "status": "NEW"}, 10)
        if method == "DELETE":
            return BinanceLifecycleHTTPResponse(200, url, {"symbol": "BTCUSDT", "clientOrderId": "smcbot-lifecycle-001", "orderId": 1, "side": "BUY", "type": "LIMIT", "timeInForce": "GTX", "price": "49500", "origQty": "0.001", "executedQty": "0", "status": "CANCELED"}, 10)
        raise AssertionError(f"unexpected method {method}")

    engine = _engine(tmp_path, env=_env(), http_get=http_get, authenticated_request=transport, now_ms_provider=lambda: next(now_values))

    query = engine.query_order("smcbot-lifecycle-001", confirmation="CONFIRM_TESTNET_READ_ONLY", config_path=str(path))
    cancel = engine.recovery_cancel("smcbot-lifecycle-001", confirmation="CONFIRM_TESTNET_CANCEL_ORDER", config_path=str(path))

    assert query.decision == "ORDER_QUERY_SUCCESS"
    assert cancel.decision == "ORDER_CANCEL_SUCCESS"
    assert query.phase == "QUERY_COMPLETE"
    assert cancel.phase == "RECOVERY_CANCEL_COMPLETE"
    assert [int(parse_qs(call[1])["timestamp"][0]) for call in calls] == [7100, 18100]


def test_recover_lifecycle_queries_cancels_final_queries_and_verifies_position(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []
    statuses = iter(["NEW", "CANCELED", "CANCELED"])

    def transport(method, url, body, timeout, headers):
        calls.append((method, url, body.decode("utf-8")))
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, [{"symbol": "BTCUSDT", "positionAmt": "0"}], 10)
        status = next(statuses)
        return BinanceLifecycleHTTPResponse(200, url, {"symbol": "BTCUSDT", "clientOrderId": "smcbot-lifecycle-001", "orderId": 1, "side": "BUY", "type": "LIMIT", "timeInForce": "GTX", "price": "49500", "origQty": "0.001", "executedQty": "0", "status": status}, 10)

    result = _engine(tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 123).recover_lifecycle("smcbot-lifecycle-001", confirmation="CONFIRM_TESTNET_EXACT_RECOVERY", config_path=str(path))

    assert result.status == "PASS"
    assert result.decision == "RECOVERY_COMPLETE"
    assert result.phase == "RECOVERY_COMPLETE"
    assert result.final_order.status == "CANCELED"
    assert [call[0] for call in calls if "/fapi/v1/order" in call[1]] == ["GET", "DELETE", "GET"]
    assert [call[0] for call in calls if "positionRisk" in call[1]] == ["GET"]
    journal = json.loads((tmp_path / "data" / "runtime" / "binance_futures_testnet_order_lifecycle" / "lifecycle.json").read_text(encoding="utf-8"))
    assert journal["phase"] == "RECOVERY_COMPLETE"
    assert journal["recovery_required"] is False
    assert not _runtime_file(tmp_path, "lifecycle.lock").exists()


def test_recover_lifecycle_does_not_cancel_terminal_order(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def transport(method, url, body, timeout, headers):
        calls.append((method, url, body.decode("utf-8")))
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, [{"symbol": "BTCUSDT", "positionAmt": "0"}], 10)
        return BinanceLifecycleHTTPResponse(200, url, {"symbol": "BTCUSDT", "clientOrderId": "smcbot-lifecycle-001", "orderId": 1, "side": "BUY", "type": "LIMIT", "timeInForce": "GTX", "price": "49500", "origQty": "0.001", "executedQty": "0", "status": "CANCELED"}, 10)

    result = _engine(tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 123).recover_lifecycle("smcbot-lifecycle-001", confirmation="CONFIRM_TESTNET_EXACT_RECOVERY", config_path=str(path))

    assert result.status == "PASS"
    assert [call[0] for call in calls if "/fapi/v1/order" in call[1]] == ["GET", "GET"]


def test_recover_lifecycle_unexpected_fill_is_critical_and_does_not_cancel(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def transport(method, url, body, timeout, headers):
        calls.append((method, url, body.decode("utf-8")))
        return BinanceLifecycleHTTPResponse(200, url, {"symbol": "BTCUSDT", "clientOrderId": "smcbot-lifecycle-001", "orderId": 1, "side": "BUY", "type": "LIMIT", "timeInForce": "GTX", "price": "49500", "origQty": "0.001", "executedQty": "0.001", "status": "FILLED"}, 10)

    result = _engine(tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 123).recover_lifecycle("smcbot-lifecycle-001", confirmation="CONFIRM_TESTNET_EXACT_RECOVERY", config_path=str(path))

    assert result.status == "CRITICAL"
    assert result.decision == "UNEXPECTED_FILL_DETECTED"
    assert result.unexpected_fill_detected is True
    assert [call[0] for call in calls] == ["GET"]
    assert not _runtime_file(tmp_path, "lifecycle.lock").exists()


def test_recover_lifecycle_failure_releases_owned_lock(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    calls = []

    def transport(method, url, body, timeout, headers):
        calls.append(method)
        if method == "GET":
            raise TimeoutError("recovery query timeout")
        raise AssertionError("cancel should not run after query timeout")

    result = _engine(tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 123).recover_lifecycle("smcbot-lifecycle-001", confirmation="CONFIRM_TESTNET_EXACT_RECOVERY", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert calls
    assert set(calls) == {"GET"}
    assert not _runtime_file(tmp_path, "lifecycle.lock").exists()


def test_replaced_lock_token_is_not_deleted_on_recovery_failure(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    lock_path = _runtime_file(tmp_path, "lifecycle.lock")

    def transport(method, url, body, timeout, headers):
        lock_path.write_text("replacement-owner", encoding="utf-8")
        raise TimeoutError("recovery query timeout")

    result = _engine(tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 123).recover_lifecycle("smcbot-lifecycle-001", confirmation="CONFIRM_TESTNET_EXACT_RECOVERY", config_path=str(path))

    assert result.status == "FAIL"
    assert result.decision == "RECOVERY_REQUIRED"
    assert lock_path.read_text(encoding="utf-8") == "replacement-owner"


def test_hard_block_diagnostics_pass(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    result = _engine(tmp_path).hard_block_diagnostics(str(path))

    assert result.status == "PASS"
    assert result.payload["blocked_methods"]
