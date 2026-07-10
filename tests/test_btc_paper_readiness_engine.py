from __future__ import annotations

import json
from pathlib import Path

from engine.diagnostics.btc_paper_readiness_engine import BTCPaperReadinessEngine


def _write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _candles(count: int = 1000) -> list[dict]:
    return [{"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1} for _ in range(count)]


def _registry(root: Path, *, btc_15m: bool = True, btc_1h: bool = True, eth_required: bool = False) -> Path:
    if btc_15m:
        _write_json(root / "data" / "historical" / "btcusdt_15m_1000.json", _candles())
    if btc_1h:
        _write_json(root / "data" / "historical" / "btcusdt_1h_1000.json", _candles())
    registry = root / "configs" / "historical_sample_registry.json"
    _write_json(
        registry,
        {
            "schema_version": "1.0",
            "samples": [
                _sample("btcusdt_15m_1000", "BTC/USDT", "15m", True, True),
                _sample("btcusdt_1h_1000", "BTC/USDT", "1h", True, False),
                _sample("ethusdt_15m_1000", "ETH/USDT", "15m", eth_required, False),
                _sample("ethusdt_1h_1000", "ETH/USDT", "1h", eth_required, False),
            ],
        },
    )
    return registry


def _sample(name: str, symbol: str, timeframe: str, full: bool, ci: bool) -> dict:
    return {
        "sample_name": name,
        "symbol": symbol,
        "timeframe": timeframe,
        "fixture_path": f"data/historical/{name}.json",
        "expected_min_candles": 1000,
        "required_for_full_gate": full,
        "required_for_ci_gate": ci,
    }


def _baseline(root: Path, *, profile: str = "balanced_smc_decision_065", snapshot: dict | None = None, missing_snapshot: bool = False) -> Path:
    snapshot_path = root / "reports" / "validation_snapshots" / "baseline.json"
    if not missing_snapshot:
        _write_json(snapshot_path, snapshot or _snapshot())
    config = root / "configs" / "validation_baseline.json"
    _write_json(
        config,
        {
            "schema_version": "1.0",
            "baseline_snapshot_path": str(snapshot_path.relative_to(root)),
            "recommended_profile": profile,
        },
    )
    return config


def _snapshot(*, eth_status: str = "SKIPPED_OUT_OF_SCOPE", scope: str = "required_full") -> dict:
    return {
        "metadata": {"recommended_profile": "balanced_smc_decision_065"},
        "multi_sample_result": {
            "sample_scope": scope,
            "rows": [
                _row("btcusdt_15m_1000", "BTC/USDT", "15m", "PASSED", "PASS"),
                _row("btcusdt_1h_1000", "BTC/USDT", "1h", "PASSED", "PASS"),
                _row("ethusdt_15m_1000", "ETH/USDT", "15m", eth_status, "FAIL" if eth_status == "FAILED" else None),
            ],
        },
    }


def _row(sample: str, symbol: str, timeframe: str, status: str, wf: str | None) -> dict:
    return {
        "sample_name": sample,
        "symbol": symbol,
        "timeframe": timeframe,
        "status": status,
        "validation_status": wf,
        "cache_status": "HIT",
    }


def _ready_files(root: Path) -> None:
    _write_json(root / "configs" / "btc_paper_runtime.json", _runtime_config())
    _write_json(root / "configs" / "btc_paper_monitoring.json", _monitoring_config())
    _write_json(root / "configs" / "btc_paper_runner.json", _runner_config())
    _write_json(root / "configs" / "btc_paper_signal_evaluation.json", _signal_evaluation_config())
    _write_json(root / "configs" / "btc_paper_trade_candidate.json", _trade_candidate_config())
    _write_json(root / "configs" / "btc_paper_candidate_journal.json", _candidate_journal_config())
    _write_json(root / "configs" / "btc_forward_test_loop.json", _forward_test_config())
    trade_plan = root / "engine" / "trade_plan" / "trade_plan_engine.py"
    trade_plan.parent.mkdir(parents=True, exist_ok=True)
    trade_plan.write_text("class TradePlanEngine: pass\n", encoding="utf-8")


def _runtime_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "exchange": "binance",
        "strategy_profile": "balanced_smc_decision_065",
        "sample_scope": "required_full",
        "primary_timeframe": "15m",
        "confirmation_timeframe": "1h",
        "enabled": False,
        "paper_execution_enabled": False,
        "live_trading_enabled": False,
        "order_submission_enabled": False,
        "dry_run": True,
        "kill_switch_enabled": True,
        "account_currency": "USDT",
        "starting_equity": 10000.0,
        "risk_per_trade_pct": 0.005,
        "max_risk_per_trade_pct": 0.01,
        "max_daily_loss_pct": 0.02,
        "max_total_drawdown_pct": 0.05,
        "max_open_positions": 1,
        "max_trades_per_day": 3,
        "min_trade_interval_minutes": 15,
        "max_position_notional_pct": 0.25,
        "min_risk_reward": 1.5,
        "require_stop_loss": True,
        "require_take_profit": True,
        "allow_long": True,
        "allow_short": True,
    }
    values.update(overrides)
    return values


def _monitoring_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "enabled": True,
        "monitoring_only": True,
        "paper_execution_expected": False,
        "live_trading_expected": False,
        "order_submission_expected": False,
        "heartbeat_stale_after_seconds": 120,
        "signal_stale_after_minutes": 60,
        "validation_gate_stale_after_hours": 24,
        "runtime_config_stale_after_hours": 24,
        "max_consecutive_errors": 3,
        "require_kill_switch_visible": True,
        "require_execution_state_visible": True,
        "require_runtime_config_visible": True,
        "require_validation_gate_status_visible": True,
        "require_last_signal_visible": False,
        "status_export_dir": "reports/paper_monitoring",
    }
    values.update(overrides)
    return values


def _runner_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_enabled": False,
        "dry_run_only": True,
        "allow_signal_generation": False,
        "allow_paper_trade_creation": False,
        "allow_order_submission": False,
        "allow_exchange_connection": False,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_kill_switch_enabled": True,
        "heartbeat_interval_seconds": 30,
        "state_export_dir": "reports/paper_runner",
    }
    values.update(overrides)
    return values


def _signal_evaluation_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "sample_name": "btcusdt_15m_1000",
        "fixture_path": "data/historical/btcusdt_15m_1000.json",
        "confirmation_sample_name": "btcusdt_1h_1000",
        "confirmation_fixture_path": "data/historical/btcusdt_1h_1000.json",
        "evaluation_mode": "latest_closed_candle",
        "dry_run_only": True,
        "allow_trade_creation": False,
        "allow_order_submission": False,
        "allow_exchange_connection": False,
        "allow_state_mutation": False,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_validation_baseline": True,
        "require_kill_switch_enabled": True,
        "min_candles": 1000,
        "max_evaluation_window": 500,
        "decision_threshold": 0.65,
        "status_export_dir": "reports/paper_signal_evaluation",
    }
    values.update(overrides)
    return values


def _trade_candidate_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "signal_evaluation_config_path": "configs/btc_paper_signal_evaluation.json",
        "dry_run_only": True,
        "allow_candidate_creation": True,
        "allow_executable_trade_creation": False,
        "allow_paper_trade_persistence": False,
        "allow_position_creation": False,
        "allow_order_submission": False,
        "allow_exchange_connection": False,
        "allow_state_mutation": False,
        "require_signal_approved": True,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_signal_config_pass": True,
        "require_kill_switch_enabled": True,
        "min_signal_score": 0.65,
        "min_risk_reward": 1.5,
        "entry_price_source": "latest_close",
        "stop_loss_mode": "diagnostic_atr_like",
        "take_profit_mode": "fixed_rr",
        "diagnostic_stop_loss_pct": 0.01,
        "max_candidate_notional_pct": 0.25,
        "status_export_dir": "reports/paper_trade_candidates",
    }
    values.update(overrides)
    return values


def _candidate_journal_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "signal_evaluation_config_path": "configs/btc_paper_signal_evaluation.json",
        "trade_candidate_config_path": "configs/btc_paper_trade_candidate.json",
        "dry_run_only": True,
        "allow_journal_write": True,
        "allow_executable_trade_creation": False,
        "allow_paper_trade_persistence": False,
        "allow_position_creation": False,
        "allow_order_submission": False,
        "allow_exchange_connection": False,
        "allow_state_mutation": False,
        "journal_format": "jsonl",
        "journal_dir": "reports/paper_candidate_journal",
        "journal_file_name": "btc_paper_candidate_journal.jsonl",
        "max_entries_to_read": 50,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_signal_config_pass": True,
        "require_trade_candidate_config_pass": True,
        "require_kill_switch_enabled": True,
    }
    values.update(overrides)
    return values


def _forward_test_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "signal_evaluation_config_path": "configs/btc_paper_signal_evaluation.json",
        "trade_candidate_config_path": "configs/btc_paper_trade_candidate.json",
        "candidate_journal_config_path": "configs/btc_paper_candidate_journal.json",
        "fixture_path": "data/historical/btcusdt_15m_1000.json",
        "confirmation_fixture_path": "data/historical/btcusdt_1h_1000.json",
        "dry_run_only": True,
        "allow_forward_loop": True,
        "allow_journal_write": True,
        "allow_live_market_data": False,
        "allow_exchange_connection": False,
        "allow_order_submission": False,
        "allow_position_creation": False,
        "allow_paper_trade_persistence": False,
        "allow_executable_trade_creation": False,
        "allow_state_mutation": False,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_signal_config_pass": True,
        "require_trade_candidate_config_pass": True,
        "require_candidate_journal_config_pass": True,
        "require_kill_switch_enabled": True,
        "cycle_mode": "historical_cursor",
        "start_index": 500,
        "max_cycles": 5,
        "min_candles": 1000,
        "evaluation_window": 500,
        "cycle_interval_seconds": 0,
        "max_run_seconds": 60,
        "state_export_dir": "reports/forward_test",
        "report_export_dir": "reports/forward_test",
    }
    values.update(overrides)
    return values


def _report(root: Path, **kwargs):
    registry = kwargs.pop("registry", None)
    if registry is None:
        registry = _registry(root)
    baseline = kwargs.pop("baseline", None)
    if baseline is None:
        baseline = _baseline(root)
    return BTCPaperReadinessEngine(repo_root=root, env=kwargs.pop("env", {}), gate_runner=kwargs.pop("gate_runner", None)).build_report(
        registry_path=str(registry),
        baseline_config=str(baseline),
        **kwargs,
    )


def _check(report, name: str):
    return next(check for check in report.checks if check.name == name)


def test_ready_when_btc_samples_baseline_and_placeholders_exist(tmp_path) -> None:
    _ready_files(tmp_path)

    report = _report(tmp_path)

    assert report.readiness_status == "READY"
    assert _check(report, "btcusdt_15m_1000").status == "PASS"
    assert _check(report, "btcusdt_1h_1000").status == "PASS"
    assert _check(report, "eth_optional_scope").status == "PASS"
    assert _check(report, "risk_runtime_config").status == "PASS"
    assert _check(report, "paper_monitoring").status == "PASS"
    assert _check(report, "btc_paper_runner_dry_run_state_machine").status == "PASS"
    assert _check(report, "btc_paper_signal_evaluation_dry_run").status == "PASS"
    assert _check(report, "btc_paper_trade_candidate_dry_run").status == "PASS"
    assert _check(report, "btc_paper_candidate_journal_dry_run").status == "PASS"
    assert _check(report, "btc_forward_test_loop_dry_run").status == "PASS"


def test_missing_btc_15m_required_sample_blocks(tmp_path) -> None:
    report = _report(tmp_path, registry=_registry(tmp_path, btc_15m=False))

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "btcusdt_15m_1000").status == "FAIL"


def test_missing_btc_1h_required_sample_blocks(tmp_path) -> None:
    report = _report(tmp_path, registry=_registry(tmp_path, btc_1h=False))

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "btcusdt_1h_1000").status == "FAIL"


def test_missing_baseline_config_blocks(tmp_path) -> None:
    registry = _registry(tmp_path)

    report = BTCPaperReadinessEngine(repo_root=tmp_path, env={}).build_report(
        registry_path=str(registry),
        baseline_config=str(tmp_path / "configs" / "missing.json"),
    )

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "validation_baseline_config").status == "FAIL"


def test_missing_baseline_snapshot_non_strict_warns(tmp_path) -> None:
    report = _report(tmp_path, baseline=_baseline(tmp_path, missing_snapshot=True))

    assert _check(report, "baseline_snapshot").status == "WARNING"


def test_missing_baseline_snapshot_strict_blocks(tmp_path) -> None:
    report = _report(tmp_path, baseline=_baseline(tmp_path, missing_snapshot=True), strict=True)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "baseline_snapshot").status == "FAIL"


def test_wrong_profile_blocks(tmp_path) -> None:
    report = _report(tmp_path, baseline=_baseline(tmp_path, profile="research_baseline"))

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "baseline_profile").status == "FAIL"


def test_eth_failed_under_all_available_warns_not_btc_blocks(tmp_path) -> None:
    report = _report(tmp_path, baseline=_baseline(tmp_path, snapshot=_snapshot(eth_status="FAILED", scope="all_available")))

    assert _check(report, "eth_optional_scope").status == "WARNING"


def test_live_trading_enabled_blocks(tmp_path) -> None:
    report = _report(tmp_path, env={"LIVE_TRADING_ENABLED": "true"})

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "live_trading_disabled").status == "FAIL"


def test_paper_execution_disabled_safety_passes(tmp_path) -> None:
    report = _report(tmp_path)

    assert _check(report, "paper_execution_disabled").status == "PASS"


def test_risk_and_monitoring_placeholders_warn_when_missing(tmp_path) -> None:
    report = _report(tmp_path)

    assert _check(report, "risk_runtime_config").status == "WARNING"
    assert _check(report, "paper_monitoring").status == "WARNING"


def test_readiness_risk_runtime_config_passes_when_valid_config_exists(tmp_path) -> None:
    _write_json(tmp_path / "configs" / "btc_paper_runtime.json", _runtime_config())

    report = _report(tmp_path)

    assert _check(report, "risk_runtime_config").status == "PASS"
    assert _check(report, "paper_monitoring").status == "WARNING"


def test_readiness_monitoring_passes_when_valid_config_exists(tmp_path) -> None:
    _write_json(tmp_path / "configs" / "btc_paper_runtime.json", _runtime_config())
    _write_json(tmp_path / "configs" / "btc_paper_monitoring.json", _monitoring_config())

    report = _report(tmp_path)

    assert _check(report, "paper_monitoring").status == "PASS"


def test_readiness_blocks_when_monitoring_config_is_dangerous(tmp_path) -> None:
    _write_json(tmp_path / "configs" / "btc_paper_runtime.json", _runtime_config())
    _write_json(tmp_path / "configs" / "btc_paper_monitoring.json", _monitoring_config(live_trading_expected=True))

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "paper_monitoring").status == "FAIL"


def test_readiness_remains_ready_with_valid_runner_config(tmp_path) -> None:
    _ready_files(tmp_path)

    report = _report(tmp_path)

    assert report.readiness_status == "READY"
    assert _check(report, "btc_paper_runner_dry_run_state_machine").status == "PASS"


def test_readiness_blocks_when_runner_config_is_dangerous(tmp_path) -> None:
    _write_json(tmp_path / "configs" / "btc_paper_runtime.json", _runtime_config())
    _write_json(tmp_path / "configs" / "btc_paper_monitoring.json", _monitoring_config())
    _write_json(tmp_path / "configs" / "btc_paper_runner.json", _runner_config(allow_order_submission=True))

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "btc_paper_runner_dry_run_state_machine").status == "FAIL"


def test_readiness_remains_ready_with_valid_signal_evaluation_config(tmp_path) -> None:
    _ready_files(tmp_path)

    report = _report(tmp_path)

    assert report.readiness_status == "READY"
    assert _check(report, "btc_paper_signal_evaluation_dry_run").status == "PASS"


def test_readiness_remains_ready_with_valid_trade_candidate_config(tmp_path) -> None:
    _ready_files(tmp_path)

    report = _report(tmp_path)

    assert report.readiness_status == "READY"
    assert _check(report, "btc_paper_trade_candidate_dry_run").status == "PASS"


def test_readiness_remains_ready_with_valid_candidate_journal_config(tmp_path) -> None:
    _ready_files(tmp_path)

    report = _report(tmp_path)

    assert report.readiness_status == "READY"
    assert _check(report, "btc_paper_candidate_journal_dry_run").status == "PASS"


def test_readiness_remains_ready_with_valid_forward_test_config(tmp_path) -> None:
    _ready_files(tmp_path)

    report = _report(tmp_path)

    assert report.readiness_status == "READY"
    assert _check(report, "btc_forward_test_loop_dry_run").status == "PASS"


def test_readiness_blocks_when_forward_test_config_is_dangerous(tmp_path) -> None:
    _write_json(tmp_path / "configs" / "btc_paper_runtime.json", _runtime_config())
    _write_json(tmp_path / "configs" / "btc_paper_monitoring.json", _monitoring_config())
    _write_json(tmp_path / "configs" / "btc_paper_runner.json", _runner_config())
    _write_json(tmp_path / "configs" / "btc_paper_signal_evaluation.json", _signal_evaluation_config())
    _write_json(tmp_path / "configs" / "btc_paper_trade_candidate.json", _trade_candidate_config())
    _write_json(tmp_path / "configs" / "btc_paper_candidate_journal.json", _candidate_journal_config())
    _write_json(tmp_path / "configs" / "btc_forward_test_loop.json", _forward_test_config(allow_order_submission=True))

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "btc_forward_test_loop_dry_run").status == "FAIL"


def test_readiness_blocks_when_candidate_journal_config_is_dangerous(tmp_path) -> None:
    _write_json(tmp_path / "configs" / "btc_paper_runtime.json", _runtime_config())
    _write_json(tmp_path / "configs" / "btc_paper_monitoring.json", _monitoring_config())
    _write_json(tmp_path / "configs" / "btc_paper_runner.json", _runner_config())
    _write_json(tmp_path / "configs" / "btc_paper_signal_evaluation.json", _signal_evaluation_config())
    _write_json(tmp_path / "configs" / "btc_paper_trade_candidate.json", _trade_candidate_config())
    _write_json(tmp_path / "configs" / "btc_paper_candidate_journal.json", _candidate_journal_config(allow_order_submission=True))

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "btc_paper_candidate_journal_dry_run").status == "FAIL"


def test_readiness_blocks_when_trade_candidate_config_is_dangerous(tmp_path) -> None:
    _write_json(tmp_path / "configs" / "btc_paper_runtime.json", _runtime_config())
    _write_json(tmp_path / "configs" / "btc_paper_monitoring.json", _monitoring_config())
    _write_json(tmp_path / "configs" / "btc_paper_runner.json", _runner_config())
    _write_json(tmp_path / "configs" / "btc_paper_signal_evaluation.json", _signal_evaluation_config())
    _write_json(tmp_path / "configs" / "btc_paper_trade_candidate.json", _trade_candidate_config(allow_order_submission=True))

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "btc_paper_trade_candidate_dry_run").status == "FAIL"


def test_readiness_blocks_when_signal_evaluation_config_is_dangerous(tmp_path) -> None:
    _write_json(tmp_path / "configs" / "btc_paper_runtime.json", _runtime_config())
    _write_json(tmp_path / "configs" / "btc_paper_monitoring.json", _monitoring_config())
    _write_json(tmp_path / "configs" / "btc_paper_runner.json", _runner_config())
    _write_json(tmp_path / "configs" / "btc_paper_signal_evaluation.json", _signal_evaluation_config(allow_order_submission=True))

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "btc_paper_signal_evaluation_dry_run").status == "FAIL"


def test_readiness_blocks_when_runtime_config_is_dangerous(tmp_path) -> None:
    _write_json(tmp_path / "configs" / "btc_paper_runtime.json", _runtime_config(live_trading_enabled=True))

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "risk_runtime_config").status == "FAIL"


def test_gate_pass_and_failure_are_reported(tmp_path) -> None:
    passing = _report(tmp_path / "pass", gate_runner=lambda **kwargs: 0, run_gate=True)
    failing = _report(tmp_path / "fail", gate_runner=lambda **kwargs: 1, run_gate=True)

    assert _check(passing, "official_validation_gate").status == "PASS"
    assert _check(failing, "official_validation_gate").status == "FAIL"
    assert failing.readiness_status == "BLOCKED"
