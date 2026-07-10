from __future__ import annotations

import json
from pathlib import Path

import pytest

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
from scripts import run_btc_futures_read_only_feed
from tests.test_btc_futures_read_only_feed_engine import _write_futures_configs


def test_validate_default_action_prints_report(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_futures_configs(tmp_path)
    monkeypatch.setattr(run_btc_futures_read_only_feed, "ROOT_DIR", tmp_path)

    code = run_btc_futures_read_only_feed.main([])

    captured = capsys.readouterr()
    assert code == 0
    assert "BTC FUTURES READ-ONLY FEED CONFIG VALIDATION" in captured.out
    assert "Status            : PASS" in captured.out


def test_json_prints_serializable_validation(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_futures_configs(tmp_path)
    monkeypatch.setattr(run_btc_futures_read_only_feed, "ROOT_DIR", tmp_path)

    code = run_btc_futures_read_only_feed.main(["--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert payload["status"] == "PASS"
    assert payload["config"]["market_type"] == "futures"


def test_strict_exits_one_for_fail(tmp_path: Path, monkeypatch) -> None:
    _write_futures_configs(tmp_path, futures={"allow_private_api": True})
    monkeypatch.setattr(run_btc_futures_read_only_feed, "ROOT_DIR", tmp_path)

    code = run_btc_futures_read_only_feed.main(["--strict"])

    assert code == 1


class _FakeFuturesFeedEngine:
    def __init__(self, repo_root=None) -> None:
        self.repo_root = repo_root

    def validate(self, config_path: str = "configs/btc_futures_read_only_feed.json", expected_profile: str = "balanced_smc_decision_065") -> BTCFuturesReadOnlyValidationReport:
        return BTCFuturesReadOnlyValidationReport(config_path=config_path, status="PASS", config=BTCFuturesReadOnlyFeedConfig())

    def fetch_once(self, config_path: str = "configs/btc_futures_read_only_feed.json", expected_profile: str = "balanced_smc_decision_065") -> BTCFuturesReadOnlyFeedResult:
        return BTCFuturesReadOnlyFeedResult(
            status=BTCFuturesReadOnlyFeedStatus.PASS.value,
            primary_candles=100,
            confirmation_candles=100,
            mark_price=BTCFuturesMarkPrice(symbol="BTCUSDT", mark_price=100.0),
            funding_info=BTCFuturesFundingInfo(symbol="BTCUSDT", funding_rate=0.0001),
            public_futures_market_data_fetch_used=True,
            public_futures_mark_price_fetch_used=True,
            public_futures_funding_fetch_used=True,
        )

    def observe_once(self, config_path: str = "configs/btc_futures_read_only_feed.json", expected_profile: str = "balanced_smc_decision_065") -> BTCFuturesReadOnlyObservationResult:
        return BTCFuturesReadOnlyObservationResult(
            status=BTCFuturesReadOnlyFeedStatus.PASS.value,
            decision=BTCFuturesReadOnlyObservationDecision.FUTURES_FEED_OK_FUNDING_AVAILABLE.value,
            feed_status=BTCFuturesReadOnlyFeedStatus.PASS.value,
            public_futures_market_data_fetch_used=True,
            metadata={
                "leverage_model_available": False,
                "liquidation_model_available": False,
                "paper_futures_position_created": False,
                "futures_trade_pipeline_invoked": False,
            },
        )


def test_fetch_once_json_and_observe_once_use_engine_without_private_actions(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_futures_configs(tmp_path)
    monkeypatch.setattr(run_btc_futures_read_only_feed, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(run_btc_futures_read_only_feed, "BTCFuturesReadOnlyFeedEngine", _FakeFuturesFeedEngine)

    fetch_code = run_btc_futures_read_only_feed.main(["--fetch-once", "--json"])
    fetch_payload = json.loads(capsys.readouterr().out)
    observe_code = run_btc_futures_read_only_feed.main(["--observe-once"])
    observe_output = capsys.readouterr().out

    assert fetch_code == 0
    assert fetch_payload["order_submitted"] is False
    assert fetch_payload["paper_position_created"] is False
    assert fetch_payload["leverage_used"] is False
    assert observe_code == 0
    assert "Futures Pipeline    : false" in observe_output


def test_export_json_and_markdown(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_futures_configs(tmp_path)
    monkeypatch.setattr(run_btc_futures_read_only_feed, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(run_btc_futures_read_only_feed, "BTCFuturesReadOnlyFeedEngine", _FakeFuturesFeedEngine)
    json_path = tmp_path / "futures.json"
    md_path = tmp_path / "futures.md"

    code = run_btc_futures_read_only_feed.main(["--fetch-once", "--export-json", str(json_path), "--export-md", str(md_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert "[btc-futures-read-only-feed] wrote" in captured.out
    assert json_path.exists()
    assert md_path.exists()


def test_action_exclusivity_is_enforced() -> None:
    with pytest.raises(SystemExit):
        run_btc_futures_read_only_feed.main(["--fetch-once", "--observe-once"])
