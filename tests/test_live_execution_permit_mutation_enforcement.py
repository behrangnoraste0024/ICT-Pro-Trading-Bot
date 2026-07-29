from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.security.live_execution_permit_gate import LiveExecutionPermitGate
from models.live_execution_permit_enforcement import LiveExecutionPermitGateError, LiveExecutionPermitReference
from tests.test_binance_futures_testnet_order_lifecycle_engine import _engine as _lifecycle_engine, _env as _lifecycle_env, _http_get as _lifecycle_http_get, _write_config as _write_lifecycle_config
from tests.test_binance_futures_testnet_order_test_engine import _engine as _order_test_engine, _env as _order_test_env, _http_get as _order_test_http_get, _write_config as _write_order_test_config
from tests.test_binance_futures_testnet_protective_orders import _env as _protective_env, _http_get as _protective_http_get, _write_config as _write_protective_config
from engine.diagnostics.binance_futures_testnet_protective_orders_engine import BinanceFuturesTestnetProtectiveOrdersEngine


class RecordingPermitGate:
    def __init__(self, error: LiveExecutionPermitGateError | None = None) -> None:
        self.calls = []
        self.error = error

    def authorize_and_consume(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error


def _permit(suffix: str) -> LiveExecutionPermitReference:
    return LiveExecutionPermitReference("permit-" + suffix * 32, 1)


def test_lifecycle_create_missing_permit_blocks_before_authenticated_transport(tmp_path) -> None:
    path = _write_lifecycle_config(tmp_path)
    calls = []

    def forbidden_http_get(*args, **kwargs):
        raise AssertionError("structural permit failure must happen before public GET")

    def forbidden_transport(method, *args, **kwargs):
        calls.append(method)
        raise AssertionError("structural permit failure must happen before authenticated transport")

    result = _lifecycle_engine(
        tmp_path,
        env=_lifecycle_env(),
        http_get=forbidden_http_get,
        authenticated_request=forbidden_transport,
        now_ms_provider=lambda: 123,
    ).run_lifecycle(
        "lifecycle-001",
        "smcbot-lifecycle-001",
        "BUY",
        0.001,
        confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE",
        config_path=str(path),
    )

    assert result.status == "FAIL"
    assert result.decision == "PERMIT_REQUIRED"
    assert calls == []
    assert not (tmp_path / "data" / "runtime" / "binance_futures_testnet_order_lifecycle" / "lifecycle.json").exists()
    assert not (tmp_path / "data" / "runtime" / "binance_futures_testnet_order_lifecycle" / "lifecycle.lock").exists()


def test_protective_create_missing_permits_blocks_before_authenticated_transport(tmp_path) -> None:
    path = _write_protective_config(tmp_path)
    calls = []

    def forbidden_http_get(*args, **kwargs):
        raise AssertionError("structural permit failure must happen before public GET")

    def forbidden_transport(method, url, body, timeout, headers):
        calls.append(method)
        raise AssertionError("structural permit failure must happen before authenticated transport")

    result = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_protective_env(),
        http_get=forbidden_http_get,
        authenticated_request=forbidden_transport,
        now_ms_provider=lambda: 1000,
    ).run_protective_lifecycle(
        "pair-001",
        "smcbot-protect-sl-001",
        "smcbot-protect-tp-001",
        confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE",
        config_path=str(path),
    )

    assert result.status == "FAIL"
    assert result.decision == "PERMIT_REQUIRED"
    assert calls == []
    assert not (tmp_path / "data" / "runtime" / "binance_futures_testnet_protective_orders" / "protective.json").exists()
    assert not (tmp_path / "data" / "runtime" / "binance_futures_testnet_protective_orders" / "protective.lock").exists()


def test_signed_order_test_missing_permit_blocks_before_transport(tmp_path) -> None:
    path = _write_order_test_config(tmp_path)
    calls = []

    def forbidden_http_get(*args, **kwargs):
        raise AssertionError("structural permit failure must happen before public GET")

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("network must not run without a permit")

    result = _order_test_engine(
        tmp_path,
        env=_order_test_env(),
        http_get=forbidden_http_get,
        authenticated_post=forbidden,
        now_ms_provider=lambda: 123,
    ).submit_test_order(
        "smcbot-test-submit-001",
        "BUY",
        "MARKET",
        0.001,
        confirmation="CONFIRM_TESTNET_ORDER_TEST",
        config_path=str(path),
    )

    assert result.status == "FAIL"
    assert result.decision == "PERMIT_REQUIRED"
    assert calls == []


def test_signed_order_test_consumes_permit_immediately_before_post(tmp_path) -> None:
    path = _write_order_test_config(tmp_path)
    permit_gate = RecordingPermitGate()
    post_calls = []

    def authenticated_post(url, body, timeout, headers):
        assert len(permit_gate.calls) == 1
        post_calls.append((url, body.decode("utf-8")))
        from infrastructure.exchanges.binance_futures_testnet_order_test_client import BinanceOrderTestHTTPResponse

        return BinanceOrderTestHTTPResponse(200, url, {}, 12)

    result = _order_test_engine(
        tmp_path,
        env=_order_test_env(),
        http_get=_order_test_http_get,
        authenticated_post=authenticated_post,
        permit_gate=permit_gate,
        now_ms_provider=lambda: 123,
    ).submit_test_order(
        "smcbot-test-submit-001",
        "BUY",
        "MARKET",
        0.001,
        confirmation="CONFIRM_TESTNET_ORDER_TEST",
        config_path=str(path),
        permit=_permit("a"),
    )

    assert result.status == "PASS"
    assert len(permit_gate.calls) == 1
    assert permit_gate.calls[0]["operation"].value == "SIGNED_ORDER_TEST_CREATE"
    assert post_calls


def test_real_enforcement_module_uses_actual_permit_gate_method() -> None:
    assert LiveExecutionPermitGate.authorize_and_consume.__module__ == "infrastructure.security.live_execution_permit_gate"


def test_lifecycle_journal_failure_happens_before_permit_gate_and_post(tmp_path, monkeypatch) -> None:
    path = _write_lifecycle_config(tmp_path)
    permit_gate = RecordingPermitGate()
    calls = []

    def transport(method, *args, **kwargs):
        calls.append(method)
        from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import BinanceLifecycleHTTPResponse
        url = args[0] if args else ""
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, [{"symbol": "BTCUSDT", "positionAmt": "0"}], 10)
        raise AssertionError("POST/DELETE must not run after journal failure")

    engine = _lifecycle_engine(
        tmp_path,
        env=_lifecycle_env(),
        http_get=_lifecycle_http_get,
        authenticated_request=transport,
        permit_gate=permit_gate,
        now_ms_provider=lambda: 123,
    )
    original_write = engine._write_journal

    def fail_create_started(config, journal, phase, details):
        if phase == "CREATE_REQUEST_STARTED":
            raise OSError("journal unavailable")
        return original_write(config, journal, phase, details)

    monkeypatch.setattr(engine, "_write_journal", fail_create_started)
    result = engine.run_lifecycle(
        "lifecycle-001",
        "smcbot-lifecycle-001",
        "BUY",
        0.001,
        confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE",
        config_path=str(path),
        create_permit=_permit("a"),
        cancel_permit=_permit("b"),
    )

    assert result.status == "FAIL"
    assert result.decision != "PERMIT_CONSUMED_NO_TRANSPORT"
    assert permit_gate.calls == []
    assert "POST" not in calls
    assert "DELETE" not in calls


def test_lifecycle_post_consume_gate_failure_preserves_consumed_no_transport(tmp_path) -> None:
    path = _write_lifecycle_config(tmp_path)
    permit_gate = RecordingPermitGate(LiveExecutionPermitGateError("PERMIT_CONSUMED_NO_TRANSPORT", permit_consumed=True))
    calls = []

    def transport(method, *args, **kwargs):
        calls.append(method)
        from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import BinanceLifecycleHTTPResponse
        url = args[0] if args else ""
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, [{"symbol": "BTCUSDT", "positionAmt": "0"}], 10)
        raise AssertionError("POST/DELETE must not run after consumed-no-transport")

    result = _lifecycle_engine(
        tmp_path,
        env=_lifecycle_env(),
        http_get=_lifecycle_http_get,
        authenticated_request=transport,
        permit_gate=permit_gate,
        now_ms_provider=lambda: 123,
    ).run_lifecycle(
        "lifecycle-001",
        "smcbot-lifecycle-001",
        "BUY",
        0.001,
        confirmation="CONFIRM_TESTNET_POST_ONLY_LIFECYCLE",
        config_path=str(path),
        create_permit=_permit("a"),
        cancel_permit=_permit("b"),
    )

    assert result.status == "FAIL"
    assert result.decision == "PERMIT_CONSUMED_NO_TRANSPORT"
    assert result.recovery_required is True
    assert len(permit_gate.calls) == 1
    assert "POST" not in calls
    assert "DELETE" not in calls


def test_fresh_protective_gate_denial_does_not_create_false_recovery(tmp_path) -> None:
    """A pair id alone is not proof that a STOP create reached Binance."""
    from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import BinanceLifecycleHTTPResponse
    from infrastructure.exchanges.binance_futures_testnet_protective_orders_client import BinanceFuturesTestnetProtectiveAPIError
    from tests.test_binance_futures_testnet_protective_orders import _exchange_info, _position

    class Persistence:
        def __init__(self, **kwargs):
            pass

        def ensure_available(self):
            pass

        def close(self):
            pass

        def check_consistency(self, *args, **kwargs):
            from infrastructure.persistence.protective_lifecycle_persistence import ProtectiveConsistencyResult
            return ProtectiveConsistencyResult("FRESH")

        def prepare_lifecycle(self, *args, **kwargs):
            return object()

        def mark_failed_safe(self, *args, **kwargs):
            pass

    calls = []

    def transport(method, url, body, timeout, headers):
        calls.append(method)
        if "positionSide/dual" in url:
            return BinanceLifecycleHTTPResponse(200, url, {"dualSidePosition": False}, 10)
        if "positionRisk" in url:
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)
        if method == "GET":
            raise BinanceFuturesTestnetProtectiveAPIError(
                "NO_SUCH_ORDER", http_status=400, binance_code=-2013,
                method="GET", path="/fapi/v1/algoOrder", request_transmitted=True, response_received=True,
            )
        raise AssertionError("a denied fresh create must not mutate")

    def http_get(url, timeout):
        if url.endswith("/fapi/v1/time"):
            return BinanceLifecycleHTTPResponse(200, url, {"serverTime": 1000}, 10)
        if "/fapi/v1/exchangeInfo" in url:
            return BinanceLifecycleHTTPResponse(200, url, _exchange_info(), 10)
        raise AssertionError("unexpected public request")

    result = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_protective_env(),
        http_get=http_get,
        authenticated_request=transport,
        permit_gate=RecordingPermitGate(LiveExecutionPermitGateError("PERMIT_REQUIRED")),
        persistence_factory=Persistence,
        now_ms_provider=lambda: 1000,
    ).run_protective_lifecycle(
        "pair-001", "smcbot-protect-sl-001", "smcbot-protect-tp-001",
        confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_LIFECYCLE",
        config_path=str(_write_protective_config(tmp_path)),
        stop_create_permit=_permit("a"), take_profit_create_permit=_permit("b"),
        take_profit_cancel_permit=_permit("c"), stop_cancel_permit=_permit("d"),
    )

    assert result.decision == "PERMIT_REQUIRED"
    assert result.recovery_required is False
    assert "POST" not in calls and "DELETE" not in calls
    assert result.journal is not None
    assert result.journal.recovery_required is False
