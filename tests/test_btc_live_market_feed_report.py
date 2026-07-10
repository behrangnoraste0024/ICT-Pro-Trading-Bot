from __future__ import annotations

from models.btc_live_market_feed import (
    BTCLiveMarketFeedConfig,
    BTCLiveMarketFeedResult,
    BTCLiveMarketFeedValidationReport,
    BTCLiveMarketObservationResult,
)
from reporting.btc_live_market_feed_report import (
    format_btc_live_market_feed_result,
    format_btc_live_market_feed_validation_report,
    format_btc_live_market_observation_result,
)


def test_validation_report_contains_safety_fields() -> None:
    rendered = format_btc_live_market_feed_validation_report(
        BTCLiveMarketFeedValidationReport(
            config_path="configs/btc_live_market_feed.json",
            status="PASS",
            config=BTCLiveMarketFeedConfig(),
            diagnostics={
                "runtime_config_status": "PASS",
                "monitoring_config_status": "PASS",
                "runner_config_status": "PASS",
                "signal_config_status": "PASS",
                "trade_candidate_config_status": "PASS",
                "candidate_journal_config_status": "PASS",
            },
        )
    )

    assert "BTC LIVE MARKET READ-ONLY FEED CONFIG VALIDATION" in rendered
    assert "Public Data Fetch : true" in rendered
    assert "Private API       : false" in rendered
    assert "Order Submission  : false" in rendered


def test_fetch_report_contains_market_data_and_safety() -> None:
    rendered = format_btc_live_market_feed_result(
        BTCLiveMarketFeedResult(
            status="PASS",
            primary_candles=100,
            confirmation_candles=100,
            public_market_data_fetch_used=True,
            private_api_used=False,
            api_key_used=False,
            trading_api_used=False,
            order_submitted=False,
        )
    )

    assert "BTC LIVE MARKET READ-ONLY FEED FETCH" in rendered
    assert "Primary Candles     : 100" in rendered
    assert "Private API Used    : false" in rendered
    assert "Trading Connection  : false" in rendered


def test_observation_report_contains_decision_and_non_execution_safety() -> None:
    rendered = format_btc_live_market_observation_result(
        BTCLiveMarketObservationResult(
            status="WARNING",
            decision="FEED_OK_SIGNAL_WARNING",
            signal_decision="WARNING_DRY_RUN",
            signal_score=0.2,
            signal_threshold=0.65,
            candidate_created=False,
            public_market_data_fetch_used=True,
        )
    )

    assert "BTC LIVE MARKET READ-ONLY OBSERVATION DRY-RUN" in rendered
    assert "Decision            : FEED_OK_SIGNAL_WARNING" in rendered
    assert "Executable Trade    : false" in rendered
    assert "Paper Persisted     : false" in rendered
    assert "State Mutated       : false" in rendered
