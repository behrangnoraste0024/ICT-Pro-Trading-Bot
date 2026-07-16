from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs

import pytest

from engine.diagnostics.binance_futures_testnet_protective_orders_engine import (
    BinanceFuturesTestnetProtectiveOrdersEngine,
    ProtectiveAbort,
)
from infrastructure.exchanges.binance_futures_testnet_order_lifecycle_client import (
    BinanceLifecycleHTTPResponse,
)
from infrastructure.exchanges.binance_futures_testnet_protective_orders_client import (
    BinanceFuturesTestnetProtectiveAPIError,
    BinanceFuturesTestnetProtectiveOrdersClient,
)
from models.binance_futures_testnet_protective_orders import (
    BinanceFuturesTestnetProtectiveJournal,
    BinanceFuturesTestnetProtectiveOrdersConfig,
    ProtectiveMutationIntent,
    ProtectiveMutationKind,
    ProtectiveReconciliationResult,
    ProtectiveReconciliationState,
)


STOP_ID = "smcbot-protect-sl-terminal"
TAKE_ID = "smcbot-protect-tp-terminal"


class _LegacyProtectivePersistence:
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
def _isolate_terminal_reconciliation_tests(monkeypatch) -> None:
    monkeypatch.setattr(
        "engine.diagnostics.binance_futures_testnet_protective_orders_engine.ProtectiveLifecyclePersistence",
        _LegacyProtectivePersistence,
    )


def _env() -> dict[str, str]:
    return {
        "BINANCE_FUTURES_TESTNET_API_KEY": "unit-test-key",
        "BINANCE_FUTURES_TESTNET_API_SECRET": "unit-test-secret",
    }


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "configs" / "binance_futures_testnet_protective_orders.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(BinanceFuturesTestnetProtectiveOrdersConfig().to_dict()),
        encoding="utf-8",
    )
    return path


def _runtime_file(tmp_path: Path, name: str) -> Path:
    return (
        tmp_path
        / "data"
        / "runtime"
        / "binance_futures_testnet_protective_orders"
        / name
    )


def _http_get(url, timeout):
    if url.endswith("/fapi/v1/time"):
        return BinanceLifecycleHTTPResponse(
            200,
            url,
            {"serverTime": 1000},
            10,
        )
    raise AssertionError(f"unexpected public GET {url}")


def _position() -> list[dict]:
    return [
        {
            "symbol": "BTCUSDT",
            "positionSide": "BOTH",
            "positionAmt": "0.001",
            "entryPrice": "49000",
            "markPrice": "50000",
            "notional": "50",
        }
    ]


def _algo_response(
    client_id: str,
    order_type: str,
    status: str,
    *,
    trigger: str,
    actual_qty: str = "0",
    actual_order_id=None,
    actual_price: str = "0",
) -> dict:
    payload = {
        "symbol": "BTCUSDT",
        "algoType": "CONDITIONAL",
        "clientAlgoId": client_id,
        "algoId": 1,
        "side": "SELL",
        "positionSide": "BOTH",
        "orderType": order_type,
        "triggerPrice": trigger,
        "algoStatus": status,
        "actualQty": actual_qty,
        "actualPrice": actual_price,
        "closePosition": True,
        "workingType": "MARK_PRICE",
        "priceProtect": True,
    }
    if actual_order_id is not None:
        payload["actualOrderId"] = actual_order_id
    return payload


def _delete_intent() -> ProtectiveMutationIntent:
    return ProtectiveMutationIntent(
        pair_id="pair-terminal",
        symbol="BTCUSDT",
        label="STOP",
        mutation_kind=ProtectiveMutationKind.DELETE.value,
        client_algo_id=STOP_ID,
        expected_order_type="STOP_MARKET",
        expected_side="SELL",
        expected_trigger_price=Decimal("45000.00"),
        expected_close_position=True,
        expected_working_type="MARK_PRICE",
        expected_price_protect=True,
        baseline_position_amount=Decimal("0.001"),
        baseline_position_direction="LONG",
        created_at="2026-07-14T00:00:00+00:00",
        mutation_phase="STOP_DELETE_STARTED",
        resolved=False,
        reconciliation_state=ProtectiveReconciliationState.PRESENT.value,
        reconciliation_reason="DELETE ACK requires exact terminal reconciliation.",
    )


@pytest.mark.parametrize(
    "status",
    ["CANCELED", "EXPIRED", "REJECTED"],
)
def test_delete_interpretation_accepts_terminal_safe_present(status: str) -> None:
    client = BinanceFuturesTestnetProtectiveOrdersClient(
        BinanceFuturesTestnetProtectiveOrdersConfig(),
        env=_env(),
    )
    order = client.sanitize_algo_summary(
        _algo_response(
            STOP_ID,
            "STOP_MARKET",
            status,
            trigger="45000.00",
        ),
        STOP_ID,
    )
    result = ProtectiveReconciliationResult(
        label="STOP",
        mutation_kind=ProtectiveMutationKind.DELETE.value,
        client_algo_id=STOP_ID,
        reconciliation_state=ProtectiveReconciliationState.PRESENT.value,
        order=order,
    )

    interpreted = BinanceFuturesTestnetProtectiveOrdersEngine()._interpret_mutation(
        _delete_intent(),
        result,
    )

    assert interpreted == "DELETE_CONFIRMED_TERMINAL"


def test_delete_interpretation_keeps_new_present_unresolved() -> None:
    client = BinanceFuturesTestnetProtectiveOrdersClient(
        BinanceFuturesTestnetProtectiveOrdersConfig(),
        env=_env(),
    )
    order = client.sanitize_algo_summary(
        _algo_response(
            STOP_ID,
            "STOP_MARKET",
            "NEW",
            trigger="45000.00",
        ),
        STOP_ID,
    )
    result = ProtectiveReconciliationResult(
        label="STOP",
        mutation_kind=ProtectiveMutationKind.DELETE.value,
        client_algo_id=STOP_ID,
        reconciliation_state=ProtectiveReconciliationState.PRESENT.value,
        order=order,
    )

    interpreted = BinanceFuturesTestnetProtectiveOrdersEngine()._interpret_mutation(
        _delete_intent(),
        result,
    )

    assert interpreted == "DELETE_NOT_APPLIED"


def test_delete_terminal_status_with_execution_evidence_is_critical() -> None:
    client = BinanceFuturesTestnetProtectiveOrdersClient(
        BinanceFuturesTestnetProtectiveOrdersConfig(),
        env=_env(),
    )
    order = client.sanitize_algo_summary(
        _algo_response(
            STOP_ID,
            "STOP_MARKET",
            "CANCELED",
            trigger="45000.00",
            actual_qty="0.001",
        ),
        STOP_ID,
    )
    result = ProtectiveReconciliationResult(
        label="STOP",
        mutation_kind=ProtectiveMutationKind.DELETE.value,
        client_algo_id=STOP_ID,
        reconciliation_state=ProtectiveReconciliationState.PRESENT.value,
        order=order,
    )

    with pytest.raises(ProtectiveAbort) as exc_info:
        BinanceFuturesTestnetProtectiveOrdersEngine()._interpret_mutation(
            _delete_intent(),
            result,
        )

    assert exc_info.value.decision == "UNEXPECTED_TRIGGER_DETECTED"
    assert exc_info.value.critical is True


def test_recovery_accepts_canceled_lookup_after_single_delete(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path)
    calls: list[tuple[str, str]] = []
    deleted = False

    def transport(method, url, body, timeout, headers):
        nonlocal deleted
        params = parse_qs(body.decode("utf-8"))

        if "positionRisk" in url:
            calls.append((method, "POSITION"))
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)

        client_id = params["clientAlgoId"][0]
        calls.append((method, client_id))

        if client_id == TAKE_ID:
            raise BinanceFuturesTestnetProtectiveAPIError(
                "NO_SUCH_ORDER",
                http_status=400,
                binance_code=-2013,
                method=method,
                path="/fapi/v1/algoOrder",
                request_transmitted=True,
                response_received=True,
            )

        if method == "DELETE":
            deleted = True
            return BinanceLifecycleHTTPResponse(
                200,
                url,
                {
                    "clientAlgoId": STOP_ID,
                    "algoId": 1,
                    "code": 200,
                    "msg": "success",
                },
                10,
            )

        status = "CANCELED" if deleted else "NEW"
        return BinanceLifecycleHTTPResponse(
            200,
            url,
            _algo_response(
                STOP_ID,
                "STOP_MARKET",
                status,
                trigger="45000.00",
            ),
            10,
        )

    result = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(),
        http_get=_http_get,
        authenticated_request=transport,
        now_ms_provider=lambda: 1000,
    ).recover_protective_pair(
        STOP_ID,
        TAKE_ID,
        confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY",
        config_path=str(config_path),
    )

    deletes = [call for call in calls if call[0] == "DELETE"]
    delete_results = [
        item
        for item in result.reconciliation_results
        if item.mutation_kind == ProtectiveMutationKind.DELETE.value
    ]

    assert result.status == "PASS"
    assert result.decision == "RECOVERY_COMPLETE"
    assert result.lifecycle_complete is True
    assert result.recovery_required is False
    assert len(deletes) == 1
    assert deletes[0] == ("DELETE", STOP_ID)
    assert len(result.cancel_requests) == 1
    assert result.cancel_requests[0].retry_count == 0
    assert delete_results[-1].reconciliation_state == "PRESENT"
    assert (
        delete_results[-1].interpreted_mutation_result
        == "DELETE_CONFIRMED_TERMINAL"
    )
    assert delete_results[-1].resolved is True
    assert delete_results[-1].recovery_required is False
    assert result.final_stop_order is not None
    assert result.final_stop_order.algo_status == "CANCELED"
    assert result.journal is not None
    assert result.journal.phase == "RECOVERY_COMPLETE"
    assert result.journal.recovery_required is False
    assert result.journal.mutation_intents[-1].resolved is True
    assert result.unexpected_trigger is False
    assert result.unexpected_position_change is False


def test_unresolved_delete_intent_reconciles_canceled_without_second_delete(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path)
    journal_path = _runtime_file(tmp_path, "protective.json")
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    journal = BinanceFuturesTestnetProtectiveJournal(
        pair_id="pair-terminal",
        stop_client_algo_id=STOP_ID,
        take_profit_client_algo_id=TAKE_ID,
        phase="RECOVERY_REQUIRED",
        recovery_required=True,
        baseline_available=True,
        baseline_position_amount=Decimal("0.001"),
        baseline_position_direction="LONG",
        stop_trigger=Decimal("45000.00"),
        take_profit_trigger=Decimal("55000.00"),
        entries=[],
        mutation_intents=[_delete_intent()],
    )
    journal_path.write_text(
        json.dumps(journal.to_dict()),
        encoding="utf-8",
    )

    calls: list[tuple[str, str]] = []

    def transport(method, url, body, timeout, headers):
        params = parse_qs(body.decode("utf-8"))

        if "positionRisk" in url:
            calls.append((method, "POSITION"))
            return BinanceLifecycleHTTPResponse(200, url, _position(), 10)

        client_id = params["clientAlgoId"][0]
        calls.append((method, client_id))

        if method == "DELETE":
            raise AssertionError("resolved terminal DELETE must not be retransmitted")

        if client_id == TAKE_ID:
            raise BinanceFuturesTestnetProtectiveAPIError(
                "NO_SUCH_ORDER",
                http_status=400,
                binance_code=-2013,
                method=method,
                path="/fapi/v1/algoOrder",
                request_transmitted=True,
                response_received=True,
            )

        return BinanceLifecycleHTTPResponse(
            200,
            url,
            _algo_response(
                STOP_ID,
                "STOP_MARKET",
                "CANCELED",
                trigger="45000.00",
            ),
            10,
        )

    result = BinanceFuturesTestnetProtectiveOrdersEngine(
        repo_root=tmp_path,
        env=_env(),
        http_get=_http_get,
        authenticated_request=transport,
        now_ms_provider=lambda: 1000,
    ).recover_protective_pair(
        STOP_ID,
        TAKE_ID,
        confirmation="CONFIRM_TESTNET_PROTECTIVE_PAIR_RECOVERY",
        config_path=str(config_path),
    )

    terminal_results = [
        item
        for item in result.reconciliation_results
        if item.interpreted_mutation_result == "DELETE_CONFIRMED_TERMINAL"
    ]

    assert result.status == "PASS"
    assert result.decision == "RECOVERY_COMPLETE"
    assert result.lifecycle_complete is True
    assert not any(method == "DELETE" for method, _ in calls)
    assert terminal_results
    assert terminal_results[0].resolved is True
    assert result.final_stop_order is not None
    assert result.final_stop_order.algo_status == "CANCELED"
    assert result.journal is not None
    assert result.journal.phase == "RECOVERY_COMPLETE"
    assert result.journal.recovery_required is False
    assert result.journal.mutation_intents[0].resolved is True
