from __future__ import annotations

import json
from pathlib import Path

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


@pytest.mark.parametrize(("field", "value"), [("feature_enabled", True), ("manual_lifecycle_only", False), ("single_order_only", False), ("rest_base_url", "https://fapi.binance.com"), ("allowed_order_types", ["LIMIT", "MARKET"]), ("allowed_time_in_force", ["GTX", "GTC"]), ("allow_standalone_create", True), ("allow_cancel_all", True), ("allow_leverage_change", True), ("maximum_lifecycle_notional_usdt", 101), ("minimum_price_offset_bps", 1), ("lifecycle_journal_path", "../bad.json")])
def test_dangerous_config_values_fail(tmp_path: Path, field: str, value) -> None:
    path = _write_config(tmp_path, **{field: value})

    report = _engine(tmp_path).validate(str(path))

    assert report.status == "FAIL"
    assert any(issue.name == field or field in issue.name for issue in report.issues)


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


def test_expired_order_completes_without_delete(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    transport = _transport(["EXPIRED", "EXPIRED", "EXPIRED"])

    result = _engine(tmp_path, env=_env(), http_get=_http_get, authenticated_request=transport, now_ms_provider=lambda: 123).run_lifecycle("lifecycle-001", "smcbot-lifecycle-001", "BUY", 0.001, confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE", config_path=str(path))

    assert result.status == "PASS"
    assert [call[0] for call in transport.calls].count("DELETE") == 0


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


def test_hard_block_diagnostics_pass(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    result = _engine(tmp_path).hard_block_diagnostics(str(path))

    assert result.status == "PASS"
    assert result.payload["blocked_methods"]
