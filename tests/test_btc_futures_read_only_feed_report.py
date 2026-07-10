from __future__ import annotations

from models.btc_futures_read_only_feed import (
    BTCFuturesFundingInfo,
    BTCFuturesMarkPrice,
    BTCFuturesReadOnlyFeedConfig,
    BTCFuturesReadOnlyFeedResult,
    BTCFuturesReadOnlyFeedStatus,
    BTCFuturesReadOnlyObservationDecision,
    BTCFuturesReadOnlyObservationResult,
    BTCFuturesReadOnlyValidationReport,
)
from reporting.btc_futures_read_only_feed_report import (
    format_btc_futures_read_only_feed_result,
    format_btc_futures_read_only_observation_result,
    format_btc_futures_read_only_validation_report,
)


def test_validation_report_displays_futures_safety_flags() -> None:
    report = BTCFuturesReadOnlyValidationReport(
        config_path="configs/btc_futures_read_only_feed.json",
        status=BTCFuturesReadOnlyFeedStatus.PASS.value,
        config=BTCFuturesReadOnlyFeedConfig(),
        diagnostics={"runtime_config_status": "PASS", "paper_account_config_status": "PASS"},
    )

    text = format_btc_futures_read_only_validation_report(report)

    assert "BTC FUTURES READ-ONLY FEED CONFIG VALIDATION" in text
    assert "Market Type       : futures" in text
    assert "Public Futures    : true" in text
    assert "Leverage          : false" in text
    assert "Paper Account     : PASS" in text


def test_fetch_report_displays_mark_funding_and_safety() -> None:
    result = BTCFuturesReadOnlyFeedResult(
        status=BTCFuturesReadOnlyFeedStatus.PASS.value,
        primary_candles=100,
        confirmation_candles=100,
        mark_price=BTCFuturesMarkPrice(symbol="BTCUSDT", mark_price=100.0, index_price=99.5),
        funding_info=BTCFuturesFundingInfo(symbol="BTCUSDT", funding_rate=0.0001),
        public_futures_market_data_fetch_used=True,
        public_futures_mark_price_fetch_used=True,
        public_futures_funding_fetch_used=True,
    )

    text = format_btc_futures_read_only_feed_result(result)

    assert "BTC FUTURES READ-ONLY FEED FETCH" in text
    assert "Mark Price          : 100.0" in text
    assert "Funding Rate        : 0.0001" in text
    assert "Order Submitted     : false" in text
    assert "Liquidation Model   : false" in text


def test_observation_report_displays_modeling_disabled() -> None:
    result = BTCFuturesReadOnlyObservationResult(
        status=BTCFuturesReadOnlyFeedStatus.PASS.value,
        decision=BTCFuturesReadOnlyObservationDecision.FUTURES_FEED_OK_FUNDING_AVAILABLE.value,
        feed_status=BTCFuturesReadOnlyFeedStatus.PASS.value,
        mark_price_value=100.0,
        funding_rate=0.0001,
        metadata={
            "leverage_model_available": False,
            "liquidation_model_available": False,
            "paper_futures_position_created": False,
            "futures_trade_pipeline_invoked": False,
        },
    )

    text = format_btc_futures_read_only_observation_result(result)

    assert "BTC FUTURES READ-ONLY OBSERVATION DRY-RUN" in text
    assert "Leverage Model      : false" in text
    assert "Futures Pipeline    : false" in text
    assert "Order Submitted     : false" in text
