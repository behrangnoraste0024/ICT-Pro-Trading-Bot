from __future__ import annotations

from decimal import Decimal

from models.binance_futures_testnet_order_lifecycle import BinanceFuturesTestnetLifecyclePreview, BinanceFuturesTestnetLifecycleResult, BinanceFuturesTestnetLifecycleValidationReport
from reporting.binance_futures_testnet_order_lifecycle_report import format_binance_futures_testnet_order_lifecycle_result, format_binance_futures_testnet_order_lifecycle_validation_report


def test_validation_report_displays_manual_boundaries() -> None:
    rendered = format_binance_futures_testnet_order_lifecycle_validation_report(BinanceFuturesTestnetLifecycleValidationReport(status="PASS"))

    assert "BINANCE FUTURES TESTNET MANUAL ORDER LIFECYCLE VALIDATION" in rendered
    assert "Standalone Create" in rendered
    assert "MARKET Orders" in rendered
    assert "Raw Persistence" in rendered


def test_lifecycle_report_displays_safety_fields() -> None:
    result = BinanceFuturesTestnetLifecycleResult(
        action="RUN_LIFECYCLE",
        status="PASS",
        decision="LIFECYCLE_COMPLETE",
        reason="Done.",
        lifecycle_id="lifecycle-001",
        client_order_id="smcbot-lifecycle-001",
        preview=BinanceFuturesTestnetLifecyclePreview(derived_price=Decimal("49500"), estimated_notional=Decimal("49.5"), exchange_filters_valid=True, non_marketable_price_valid=True, transmission_ready=True),
        order_created=True,
        order_cancelled=True,
        lifecycle_complete=True,
    )

    rendered = format_binance_futures_testnet_order_lifecycle_result(result)

    assert "BINANCE FUTURES TESTNET POST-ONLY LIMIT LIFECYCLE" in rendered
    assert "Derived Price             : 49500" in rendered
    assert "Lifecycle Complete        : true" in rendered
    assert "MARKET Order Used         : false" in rendered
