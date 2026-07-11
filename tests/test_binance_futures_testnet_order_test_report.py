from __future__ import annotations

from decimal import Decimal

from models.binance_futures_testnet_order_test import (
    BinanceFuturesTestnetOrderTestPreview,
    BinanceFuturesTestnetOrderTestRequestMetadata,
    BinanceFuturesTestnetOrderTestResult,
    BinanceFuturesTestnetOrderTestValidationReport,
)
from reporting.binance_futures_testnet_order_test_report import (
    format_binance_futures_testnet_order_test_result,
    format_binance_futures_testnet_order_test_validation_report,
)


def test_validation_report_displays_safe_boundaries() -> None:
    rendered = format_binance_futures_testnet_order_test_validation_report(BinanceFuturesTestnetOrderTestValidationReport(status="PASS"))

    assert "BINANCE FUTURES TESTNET TEST ORDER VALIDATION" in rendered
    assert "Actual Order Submission" in rendered
    assert "Raw Response Persistence" in rendered


def test_success_report_distinguishes_test_request_from_actual_order() -> None:
    result = BinanceFuturesTestnetOrderTestResult(
        action="SUBMIT_TEST_ORDER",
        status="PASS",
        decision="ORDER_TEST_ACCEPTED",
        reason="Test Order request accepted.",
        preview=BinanceFuturesTestnetOrderTestPreview(
            client_order_id="smcbot-test-001",
            quantity=Decimal("0.001"),
            reference_price=Decimal("50000"),
            reference_price_source="MARK_PRICE",
            estimated_notional=Decimal("50.000"),
            configured_max_notional_valid=True,
            exchange_min_notional_valid=True,
            notional_validation_status="PASS",
            exchange_filter_validation_status="PASS",
            exchange_filters_valid=True,
            local_rules_valid=True,
            transmission_ready=True,
        ),
        request_metadata=BinanceFuturesTestnetOrderTestRequestMetadata(request_transmitted=True, response_empty_object=True),
        test_order_request_transmitted=True,
        authenticated_test_request_used=True,
        actual_order_submitted=False,
        matching_engine_submission=False,
        exchange_order_created=False,
        position_created=False,
    )

    rendered = format_binance_futures_testnet_order_test_result(result)

    assert "BINANCE FUTURES TESTNET TEST ORDER RESULT" in rendered
    assert "Test Request Transmitted  : true" in rendered
    assert "Authenticated Request     : true" in rendered
    assert "Reference Price           : 50000" in rendered
    assert "Reference Price Source    : MARK_PRICE" in rendered
    assert "Estimated Notional        : 50.000" in rendered
    assert "Notional Validation       : PASS" in rendered
    assert "Exchange Filter Validation: PASS" in rendered
    assert "Transmission Ready        : true" in rendered
    assert "Actual Order Submitted    : false" in rendered
    assert "Matching Engine Submission: false" in rendered
    assert "Exchange Order Created    : false" in rendered
    assert "Position Created          : false" in rendered
    assert "Secrets Exposed           : false" in rendered


def test_local_market_preview_report_shows_not_evaluated_not_ready() -> None:
    result = BinanceFuturesTestnetOrderTestResult(
        action="BUILD_PREVIEW",
        status="PASS",
        decision="ORDER_TEST_PREVIEW_VALID",
        reason="Local preview only.",
        preview=BinanceFuturesTestnetOrderTestPreview(client_order_id="smcbot-test-001", quantity=Decimal("0.001")),
    )

    rendered = format_binance_futures_testnet_order_test_result(result)

    assert "Reference Price           : None" in rendered
    assert "Estimated Notional        : NOT_EVALUATED" in rendered
    assert "Exchange Filters Valid    : None" in rendered
    assert "Transmission Ready        : false" in rendered
