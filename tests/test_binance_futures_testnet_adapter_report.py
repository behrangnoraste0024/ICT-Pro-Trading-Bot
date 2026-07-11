from __future__ import annotations

from engine.diagnostics.binance_futures_testnet_adapter_engine import BinanceFuturesTestnetAdapterEngine
from reporting.binance_futures_testnet_adapter_report import (
    format_binance_futures_testnet_adapter_result,
    format_binance_futures_testnet_adapter_validation_report,
)


def test_validation_report_shows_disabled_safety_boundary() -> None:
    report = BinanceFuturesTestnetAdapterEngine(env={}).validate()

    text = format_binance_futures_testnet_adapter_validation_report(report)

    assert "BINANCE FUTURES TESTNET ADAPTER VALIDATION" in text
    assert "Adapter Enabled             : false" in text
    assert "Connection Mode             : disabled" in text
    assert "Order Submission            : false" in text
    assert "Production Endpoint         : false" in text


def test_result_report_redacts_signed_preview_payload() -> None:
    result = BinanceFuturesTestnetAdapterEngine(
        env={"BINANCE_FUTURES_TESTNET_API_KEY": "api-key-value", "BINANCE_FUTURES_TESTNET_API_SECRET": "secret-value"}
    ).signed_request_preview("/fapi/v2/account", {"timestamp": 123, "recvWindow": 5000})

    text = format_binance_futures_testnet_adapter_result(result)

    assert "BINANCE FUTURES TESTNET ADAPTER DIAGNOSTIC" in text
    assert "SIGNING_PREVIEW_BUILT" in text
    assert "REDACTED" in text
    assert "api-key-value" not in text
    assert "secret-value" not in text
    assert "Request Transmitted          : false" in text
    assert "Testnet Order Submitted      : false" in text
