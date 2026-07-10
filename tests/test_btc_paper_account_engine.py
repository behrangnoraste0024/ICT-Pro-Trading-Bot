from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.diagnostics.btc_paper_account_engine import BTCPaperAccountEngine
from models.btc_live_market_feed import BTCLiveMarketFeedResult, BTCLiveMarketObservationResult
from tests.test_btc_live_market_feed_engine import _write_live_configs
from tests.test_btc_paper_signal_evaluation_engine import _signal_config


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _account_config(**overrides) -> dict[str, Any]:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "quote_currency": "USDT",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "signal_evaluation_config_path": "configs/btc_paper_signal_evaluation.json",
        "trade_candidate_config_path": "configs/btc_paper_trade_candidate.json",
        "candidate_journal_config_path": "configs/btc_paper_candidate_journal.json",
        "forward_test_config_path": "configs/btc_forward_test_loop.json",
        "live_market_feed_config_path": "configs/btc_live_market_feed.json",
        "paper_account_enabled": False,
        "simulation_only": True,
        "dry_run_only": True,
        "initial_balance": 10000.0,
        "risk_per_trade_pct": 0.5,
        "max_risk_per_trade_pct": 1.0,
        "max_daily_loss_pct": 2.0,
        "max_drawdown_pct": 5.0,
        "max_open_virtual_positions": 1,
        "max_virtual_trades_per_day": 3,
        "min_risk_reward": 1.5,
        "require_stop_loss": True,
        "require_take_profit": True,
        "allow_local_paper_state_write": True,
        "allow_local_paper_ledger_write": True,
        "allow_virtual_order_creation": True,
        "allow_virtual_position_creation": True,
        "allow_virtual_pnl_calculation": True,
        "allow_public_market_data_fetch": True,
        "allow_private_api": False,
        "allow_api_key_usage": False,
        "allow_trading_api": False,
        "allow_account_data": False,
        "allow_balance_fetch": False,
        "allow_position_fetch": False,
        "allow_real_order_submission": False,
        "allow_order_cancellation": False,
        "allow_real_position_creation": False,
        "allow_exchange_connection_for_trading": False,
        "allow_executable_trade_creation": False,
        "allow_runner_state_mutation": False,
        "allow_execution_state_mutation": False,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_signal_config_pass": True,
        "require_trade_candidate_config_pass": True,
        "require_candidate_journal_config_pass": True,
        "require_forward_test_config_pass": True,
        "require_live_market_feed_config_pass": True,
        "require_kill_switch_enabled": True,
        "fill_model": "virtual_next_close",
        "slippage_rate": 0.0002,
        "fee_rate": 0.0004,
        "state_path": "reports/paper_account/btc_paper_account_state.json",
        "ledger_path": "reports/paper_account/btc_paper_account_ledger.jsonl",
        "report_export_dir": "reports/paper_account",
    }
    values.update(overrides)
    return values


def _write_account_configs(tmp_path: Path, *, account: dict[str, Any] | None = None, **kwargs) -> Path:
    _write_live_configs(tmp_path, **kwargs)
    path = tmp_path / "configs" / "btc_paper_account.json"
    _write_json(path, _account_config(**(account or {})))
    return path


class _FakeLiveFeedEngine:
    def __init__(self, observation: BTCLiveMarketObservationResult | None = None, fetch: BTCLiveMarketFeedResult | None = None, report_status: str = "PASS") -> None:
        self.observation = observation or _observation(candidate_created=False)
        self.fetch = fetch or BTCLiveMarketFeedResult(status="PASS", primary_latest_close=110.0)
        self.report_status = report_status

    def validate(self, config_path: str = "configs/btc_live_market_feed.json", expected_profile: str = "balanced_smc_decision_065"):
        from models.btc_live_market_feed import BTCLiveMarketFeedValidationReport

        return BTCLiveMarketFeedValidationReport(config_path=config_path, status=self.report_status, diagnostics={})

    def observe_once(self, config_path: str = "configs/btc_live_market_feed.json", expected_profile: str = "balanced_smc_decision_065", journal=None):
        return self.observation

    def fetch_once(self, config_path: str = "configs/btc_live_market_feed.json", expected_profile: str = "balanced_smc_decision_065"):
        return self.fetch


def _observation(candidate_created: bool, *, candidate: dict[str, Any] | None = None, status: str = "WARNING") -> BTCLiveMarketObservationResult:
    return BTCLiveMarketObservationResult(
        status="PASS" if candidate_created else status,
        decision="FEED_OK_CANDIDATE_CREATED_DRY_RUN" if candidate_created else "FEED_OK_SIGNAL_WARNING",
        signal_decision="APPROVED_DRY_RUN" if candidate_created else "WARNING_DRY_RUN",
        signal_score=0.9 if candidate_created else 0.1,
        signal_threshold=0.65,
        candidate_created=candidate_created,
        reason="approved" if candidate_created else "score below threshold",
        public_market_data_fetch_used=True,
        metadata={"candidate": candidate or _candidate()} if candidate_created else {},
    )


def _candidate(**overrides) -> dict[str, Any]:
    values = {"candidate_id": "C1", "direction": "LONG", "entry_price": 100.0, "stop_loss": 99.0, "take_profit": 101.5}
    values.update(overrides)
    return values


def _engine(tmp_path: Path, live: _FakeLiveFeedEngine | None = None) -> BTCPaperAccountEngine:
    return BTCPaperAccountEngine(repo_root=tmp_path, live_market_feed_engine=live or _FakeLiveFeedEngine(), now_provider=lambda: "2026-01-01T00:00:00+00:00")


def test_default_repo_paper_account_config_validates_pass() -> None:
    report = BTCPaperAccountEngine().validate()

    assert report.status == "PASS"
    assert report.config is not None
    assert report.config.paper_account_enabled is False


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("simulation_only", False, "simulation_only"),
        ("dry_run_only", False, "dry_run_only"),
        ("allow_private_api", True, "allow_private_api"),
        ("allow_api_key_usage", True, "allow_api_key_usage"),
        ("allow_trading_api", True, "allow_trading_api"),
        ("allow_account_data", True, "allow_account_data"),
        ("allow_balance_fetch", True, "allow_balance_fetch"),
        ("allow_position_fetch", True, "allow_position_fetch"),
        ("allow_real_order_submission", True, "allow_real_order_submission"),
        ("allow_order_cancellation", True, "allow_order_cancellation"),
        ("allow_real_position_creation", True, "allow_real_position_creation"),
        ("allow_exchange_connection_for_trading", True, "allow_exchange_connection_for_trading"),
        ("allow_executable_trade_creation", True, "allow_executable_trade_creation"),
        ("allow_runner_state_mutation", True, "allow_runner_state_mutation"),
        ("allow_execution_state_mutation", True, "allow_execution_state_mutation"),
        ("symbol", "ETH/USDT", "symbol"),
        ("strategy_profile", "research_baseline", "strategy_profile"),
        ("state_path", "../state.json", "state_path"),
        ("ledger_path", "../ledger.jsonl", "ledger_path"),
        ("report_export_dir", "../reports", "report_export_dir"),
        ("risk_per_trade_pct", 2.0, "risk_per_trade_pct"),
        ("max_risk_per_trade_pct", 2.0, "max_risk_per_trade_pct_runtime"),
        ("require_stop_loss", False, "require_stop_loss"),
        ("require_take_profit", False, "require_take_profit"),
    ],
)
def test_dangerous_paper_account_config_fails(tmp_path: Path, field: str, value: Any, issue: str) -> None:
    path = _write_account_configs(tmp_path, account={field: value})

    report = _engine(tmp_path).validate(str(path))

    assert report.status == "FAIL"
    assert issue in {item.name for item in report.issues}


def test_dependency_failures_block_paper_account_config(tmp_path: Path) -> None:
    cases = [
        ("runtime", {"runtime": {"live_trading_enabled": True}}, "runtime_config_validation"),
        ("monitoring", {"monitoring": {"live_trading_expected": True}}, "monitoring_config_validation"),
        ("runner", {"runner": {"allow_order_submission": True}}, "runner_config_validation"),
        ("signal", {"signal": _signal_config(tmp_path / "signal", allow_order_submission=True)}, "signal_config_validation"),
        ("candidate", {"candidate": {"allow_order_submission": True}}, "trade_candidate_config_validation"),
        ("journal", {"journal": {"allow_order_submission": True}}, "candidate_journal_config_validation"),
        ("forward", {"forward": {"allow_order_submission": True}}, "forward_test_config_validation"),
        ("live", {"live": {"allow_order_submission": True}}, "live_market_feed_config_validation"),
        ("kill", {"runtime": {"kill_switch_enabled": False}}, "kill_switch_enabled"),
    ]
    for name, kwargs, expected_issue in cases:
        root = tmp_path / name
        path = _write_account_configs(root, **kwargs)
        engine = _engine(root, _FakeLiveFeedEngine(report_status="FAIL")) if name == "live" else _engine(root)
        report = engine.validate(str(path))
        assert expected_issue in {issue.name for issue in report.issues}


def test_status_missing_state_returns_warning(tmp_path: Path) -> None:
    path = _write_account_configs(tmp_path)

    result = _engine(tmp_path).status(str(path))

    assert result.status == "WARNING"
    assert result.decision == "STATE_MISSING"
    assert result.safety_summary["real_order_submitted"] is False


def test_initialize_writes_state_and_ledger(tmp_path: Path) -> None:
    path = _write_account_configs(tmp_path)

    result = _engine(tmp_path).initialize(str(path))

    assert result.status == "PASS"
    assert (tmp_path / "reports" / "paper_account" / "btc_paper_account_state.json").exists()
    assert (tmp_path / "reports" / "paper_account" / "btc_paper_account_ledger.jsonl").exists()
    assert result.safety_summary["trading_api_used"] is False


def test_initialize_existing_state_warns_unless_forced(tmp_path: Path) -> None:
    path = _write_account_configs(tmp_path)
    engine = _engine(tmp_path)

    assert engine.initialize(str(path)).status == "PASS"
    assert engine.initialize(str(path)).status == "WARNING"
    assert engine.initialize(str(path), force=True).status == "PASS"


def test_reset_without_force_does_not_delete_files(tmp_path: Path) -> None:
    path = _write_account_configs(tmp_path)
    engine = _engine(tmp_path)
    engine.initialize(str(path))

    result = engine.reset(str(path))

    assert result.status == "WARNING"
    assert (tmp_path / "reports" / "paper_account" / "btc_paper_account_state.json").exists()


def test_reset_with_force_resets_safe_local_files(tmp_path: Path) -> None:
    path = _write_account_configs(tmp_path)
    engine = _engine(tmp_path)
    engine.initialize(str(path))

    result = engine.reset(str(path), force=True)

    assert result.status == "PASS"
    assert result.account_state is not None
    assert result.account_state.total_virtual_orders == 0


def test_ledger_summary_missing_and_present(tmp_path: Path) -> None:
    path = _write_account_configs(tmp_path)
    engine = _engine(tmp_path)

    missing = engine.ledger_summary(str(path))
    engine.initialize(str(path))
    present = engine.ledger_summary(str(path))

    assert missing.status == "WARNING"
    assert present.status == "PASS"
    assert present.account_initialized == 1


def test_simulate_live_observation_missing_state_warns(tmp_path: Path) -> None:
    path = _write_account_configs(tmp_path)

    result = _engine(tmp_path).simulate_live_observation(str(path))

    assert result.status == "WARNING"
    assert result.decision == "STATE_MISSING"


def test_low_score_observation_records_no_action(tmp_path: Path) -> None:
    path = _write_account_configs(tmp_path)

    result = _engine(tmp_path, _FakeLiveFeedEngine(_observation(False))).simulate_live_observation(str(path), initialize_if_missing=True)

    assert result.status == "WARNING"
    assert result.no_action_recorded is True
    assert result.virtual_order_created is False
    assert result.account_state is not None
    assert result.account_state.total_no_action_events == 1
    assert result.safety_summary["real_order_submitted"] is False


def test_approved_observation_creates_virtual_order_and_position_only(tmp_path: Path) -> None:
    path = _write_account_configs(tmp_path)

    result = _engine(tmp_path, _FakeLiveFeedEngine(_observation(True))).simulate_live_observation(str(path), initialize_if_missing=True)

    assert result.status == "PASS"
    assert result.virtual_order_created is True
    assert result.virtual_position_created is True
    assert result.account_state is not None
    assert len(result.account_state.open_positions) == 1
    assert result.safety_summary["real_position_created"] is False
    assert result.safety_summary["executable_trade_created"] is False


@pytest.mark.parametrize(
    "candidate",
    [
        _candidate(stop_loss=None),
        _candidate(take_profit=100.5),
    ],
)
def test_risk_rejection_creates_no_virtual_position(tmp_path: Path, candidate: dict[str, Any]) -> None:
    path = _write_account_configs(tmp_path)

    result = _engine(tmp_path, _FakeLiveFeedEngine(_observation(True, candidate=candidate))).simulate_live_observation(str(path), initialize_if_missing=True)

    assert result.status == "WARNING"
    assert result.virtual_position_created is False
    assert result.account_state is not None
    assert result.account_state.total_risk_rejections == 1


def test_max_open_positions_blocks_new_virtual_position(tmp_path: Path) -> None:
    path = _write_account_configs(tmp_path)
    engine = _engine(tmp_path, _FakeLiveFeedEngine(_observation(True)))
    assert engine.simulate_live_observation(str(path), initialize_if_missing=True).status == "PASS"

    result = engine.simulate_live_observation(str(path))

    assert result.status == "WARNING"
    assert result.decision == "VIRTUAL_TRADE_REJECTED_LIMIT"


def test_max_virtual_trades_per_day_blocks_new_virtual_trade(tmp_path: Path) -> None:
    path = _write_account_configs(tmp_path, account={"max_open_virtual_positions": 1, "max_virtual_trades_per_day": 1})
    engine = _engine(tmp_path, _FakeLiveFeedEngine(_observation(True)))
    first = engine.simulate_live_observation(str(path), initialize_if_missing=True)
    first.account_state.open_positions.clear()
    engine._write_state(engine.load_config(str(path)), first.account_state)

    result = engine.simulate_live_observation(str(path))

    assert result.status == "WARNING"
    assert result.decision == "VIRTUAL_TRADE_REJECTED_LIMIT"


def test_mark_to_market_no_positions_and_open_position(tmp_path: Path) -> None:
    path = _write_account_configs(tmp_path)
    engine = _engine(tmp_path, _FakeLiveFeedEngine(_observation(True), BTCLiveMarketFeedResult(status="PASS", primary_latest_close=110.0)))
    engine.initialize(str(path))
    no_position = engine.mark_to_market(str(path))
    engine.simulate_live_observation(str(path))
    marked = engine.mark_to_market(str(path))

    assert no_position.status == "WARNING"
    assert marked.status == "PASS"
    assert marked.mark_to_market_updated is True
    assert marked.account_state.unrealized_pnl > 0


def test_all_action_safety_flags_remain_false(tmp_path: Path) -> None:
    path = _write_account_configs(tmp_path)
    result = _engine(tmp_path).initialize(str(path))

    for name in ("private_api_used", "api_key_used", "trading_api_used", "account_data_used", "balance_fetch_used", "position_fetch_used", "real_order_submitted", "order_cancelled", "real_position_created", "exchange_connected_for_trading", "executable_trade_created", "runner_state_mutated", "execution_state_mutated"):
        assert result.safety_summary[name] is False
