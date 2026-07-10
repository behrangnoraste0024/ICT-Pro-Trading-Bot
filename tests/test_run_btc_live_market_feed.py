from __future__ import annotations

import json

from models.btc_live_market_feed import (
    BTCLiveMarketFeedConfig,
    BTCLiveMarketFeedResult,
    BTCLiveMarketFeedValidationReport,
    BTCLiveMarketObservationResult,
)
from scripts import run_btc_live_market_feed
from tests.test_btc_live_market_feed_engine import _write_live_configs


class _FakeEngine:
    def __init__(self, repo_root=None) -> None:
        self.repo_root = repo_root

    def validate(self, config_path: str = "configs/btc_live_market_feed.json", expected_profile: str = "balanced_smc_decision_065") -> BTCLiveMarketFeedValidationReport:
        return BTCLiveMarketFeedValidationReport(config_path=config_path, status="PASS", config=BTCLiveMarketFeedConfig())

    def fetch_once(self, config_path: str = "configs/btc_live_market_feed.json", expected_profile: str = "balanced_smc_decision_065") -> BTCLiveMarketFeedResult:
        return BTCLiveMarketFeedResult(status="PASS", primary_candles=100, confirmation_candles=100, public_market_data_fetch_used=True)

    def observe_once(self, config_path: str = "configs/btc_live_market_feed.json", expected_profile: str = "balanced_smc_decision_065", journal=None) -> BTCLiveMarketObservationResult:
        return BTCLiveMarketObservationResult(status="WARNING", decision="FEED_OK_SIGNAL_WARNING", public_market_data_fetch_used=True, journal_entry_written=bool(journal))


class _FailEngine(_FakeEngine):
    def validate(self, config_path: str = "configs/btc_live_market_feed.json", expected_profile: str = "balanced_smc_decision_065") -> BTCLiveMarketFeedValidationReport:
        return BTCLiveMarketFeedValidationReport(config_path=config_path, status="FAIL", config=BTCLiveMarketFeedConfig(dry_run_only=False))


def test_default_runner_prints_validation(capsys, monkeypatch, tmp_path) -> None:
    _write_live_configs(tmp_path)
    monkeypatch.setattr(run_btc_live_market_feed, "ROOT_DIR", tmp_path)

    code = run_btc_live_market_feed.main([])

    captured = capsys.readouterr()
    assert code == 0
    assert "BTC LIVE MARKET READ-ONLY FEED CONFIG VALIDATION" in captured.out


def test_json_prints_serializable_validation(capsys, monkeypatch, tmp_path) -> None:
    _write_live_configs(tmp_path)
    monkeypatch.setattr(run_btc_live_market_feed, "ROOT_DIR", tmp_path)

    code = run_btc_live_market_feed.main(["--json"])

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["status"] == "PASS"


def test_strict_exits_zero_for_pass(capsys, monkeypatch, tmp_path) -> None:
    _write_live_configs(tmp_path)
    monkeypatch.setattr(run_btc_live_market_feed, "ROOT_DIR", tmp_path)

    code = run_btc_live_market_feed.main(["--strict"])

    capsys.readouterr()
    assert code == 0


def test_strict_exits_one_for_fail(capsys, monkeypatch) -> None:
    monkeypatch.setattr(run_btc_live_market_feed, "BTCLiveMarketFeedEngine", _FailEngine)

    code = run_btc_live_market_feed.main(["--strict"])

    capsys.readouterr()
    assert code == 1


def test_fetch_once_json_uses_engine_and_prints_safe_payload(capsys, monkeypatch) -> None:
    monkeypatch.setattr(run_btc_live_market_feed, "BTCLiveMarketFeedEngine", _FakeEngine)

    code = run_btc_live_market_feed.main(["--fetch-once", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["primary_candles"] == 100
    assert payload["private_api_used"] is False


def test_observe_once_json_and_no_journal(capsys, monkeypatch) -> None:
    monkeypatch.setattr(run_btc_live_market_feed, "BTCLiveMarketFeedEngine", _FakeEngine)

    code = run_btc_live_market_feed.main(["--observe-once", "--no-journal", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "WARNING"
    assert payload["journal_entry_written"] is False
    assert payload["order_submitted"] is False


def test_exports_write_requested_files(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(run_btc_live_market_feed, "BTCLiveMarketFeedEngine", _FakeEngine)
    json_path = tmp_path / "out.json"
    md_path = tmp_path / "out.md"

    code = run_btc_live_market_feed.main(["--fetch-once", "--export-json", str(json_path), "--export-md", str(md_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert "[btc-live-market-feed] wrote" in captured.out
    assert json_path.exists()
    assert md_path.exists()
