from __future__ import annotations

import json
from pathlib import Path

from engine.diagnostics.btc_paper_readiness_engine import BTCPaperReadinessEngine


def test_readiness_engine_shares_one_operational_counter_registry_across_testnet_child_engines(tmp_path: Path) -> None:
    engine = BTCPaperReadinessEngine(repo_root=tmp_path, env={})
    registry = engine.operational_counter_registry

    assert engine.binance_futures_testnet_order_test_engine.authorization_policy.operational_counter_registry is registry
    assert engine.binance_futures_testnet_order_lifecycle_engine.authorization_policy.operational_counter_registry is registry
    assert engine.binance_futures_testnet_protective_orders_engine.authorization_policy.operational_counter_registry is registry


def _write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class _FakeLifecycleReport:
    def __init__(self, status: str = "PASS") -> None:
        self.status = status
        self.issue_count = 0 if status == "PASS" else 1
        self.warning_count = 0
        self.fail_count = 0 if status == "PASS" else 1
        self.issues = []
        self.diagnostics = {}


class _FakeOrderLifecycleEngine:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def validate(self, config_path: str, *args, **kwargs) -> _FakeLifecycleReport:
        payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
        return _FakeLifecycleReport("FAIL" if payload.get("allow_market_order") else "PASS")


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
    _write_json(root / "configs" / "btc_live_market_feed.json", _live_market_feed_config())
    _write_json(root / "configs" / "btc_paper_account.json", _paper_account_config())
    _write_json(root / "configs" / "btc_futures_read_only_feed.json", _futures_read_only_feed_config())
    _write_json(root / "configs" / "btc_futures_risk_model.json", _futures_risk_model_config())
    _write_json(root / "configs" / "btc_futures_paper_position.json", _futures_paper_position_config())
    _write_json(root / "configs" / "binance_futures_testnet_adapter.json", _binance_futures_testnet_adapter_config())
    _write_json(root / "configs" / "binance_futures_testnet_read_only.json", _binance_futures_testnet_read_only_config())
    _write_json(root / "configs" / "binance_futures_testnet_order_test.json", _binance_futures_testnet_order_test_config())
    _write_json(root / "configs" / "binance_futures_testnet_order_lifecycle.json", _binance_futures_testnet_order_lifecycle_config())
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


def _live_market_feed_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "exchange": "binance",
        "market_type": "spot",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "signal_evaluation_config_path": "configs/btc_paper_signal_evaluation.json",
        "trade_candidate_config_path": "configs/btc_paper_trade_candidate.json",
        "candidate_journal_config_path": "configs/btc_paper_candidate_journal.json",
        "forward_test_config_path": "configs/btc_forward_test_loop.json",
        "primary_timeframe": "15m",
        "confirmation_timeframe": "1h",
        "primary_limit": 100,
        "confirmation_limit": 100,
        "closed_candles_only": True,
        "dry_run_only": True,
        "feed_enabled": False,
        "allow_public_market_data_fetch": True,
        "allow_private_api": False,
        "allow_api_key_usage": False,
        "allow_trading_api": False,
        "allow_account_data": False,
        "allow_balance_fetch": False,
        "allow_position_fetch": False,
        "allow_order_submission": False,
        "allow_order_cancellation": False,
        "allow_position_creation": False,
        "allow_paper_trade_persistence": False,
        "allow_executable_trade_creation": False,
        "allow_state_mutation": False,
        "allow_journal_write": True,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_signal_config_pass": True,
        "require_trade_candidate_config_pass": True,
        "require_candidate_journal_config_pass": True,
        "require_kill_switch_enabled": True,
        "request_timeout_seconds": 10,
        "max_fetch_retries": 0,
        "min_primary_candles": 100,
        "min_confirmation_candles": 100,
        "observation_mode": "fetch_once",
        "status_export_dir": "reports/live_market_feed",
    }
    values.update(overrides)
    return values


def _paper_account_config(**overrides) -> dict:
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


def _futures_read_only_feed_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "exchange": "binance",
        "market_type": "futures",
        "futures_contract_type": "USDT_PERPETUAL",
        "exchange_symbol": "BTCUSDT",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "live_market_feed_config_path": "configs/btc_live_market_feed.json",
        "paper_account_config_path": "configs/btc_paper_account.json",
        "primary_timeframe": "15m",
        "confirmation_timeframe": "1h",
        "primary_limit": 500,
        "confirmation_limit": 500,
        "closed_candles_only": True,
        "dry_run_only": True,
        "feed_enabled": False,
        "allow_public_futures_market_data_fetch": True,
        "allow_public_futures_mark_price_fetch": True,
        "allow_public_futures_funding_fetch": True,
        "allow_private_api": False,
        "allow_api_key_usage": False,
        "allow_trading_api": False,
        "allow_account_data": False,
        "allow_balance_fetch": False,
        "allow_position_fetch": False,
        "allow_order_submission": False,
        "allow_order_cancellation": False,
        "allow_real_position_creation": False,
        "allow_paper_position_creation": False,
        "allow_leverage": False,
        "allow_leverage_simulation": False,
        "allow_liquidation_modeling": False,
        "allow_paper_trade_persistence": False,
        "allow_executable_trade_creation": False,
        "allow_runner_state_mutation": False,
        "allow_execution_state_mutation": False,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_live_market_feed_config_pass": True,
        "require_paper_account_config_pass": True,
        "require_kill_switch_enabled": True,
        "request_timeout_seconds": 10,
        "max_fetch_retries": 1,
        "min_primary_candles": 100,
        "min_confirmation_candles": 100,
        "observation_mode": "fetch_once",
        "status_export_dir": "reports/futures_read_only_feed",
    }
    values.update(overrides)
    return values


def _futures_risk_model_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "exchange_symbol": "BTCUSDT",
        "exchange": "binance",
        "market_type": "futures",
        "futures_contract_type": "USDT_PERPETUAL",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "futures_read_only_feed_config_path": "configs/btc_futures_read_only_feed.json",
        "paper_account_config_path": "configs/btc_paper_account.json",
        "risk_model_enabled": False,
        "simulation_only": True,
        "dry_run_only": True,
        "model_name": "simplified_isolated_linear_v1",
        "model_accuracy": "APPROXIMATE_CONSERVATIVE",
        "exchange_exact_liquidation": False,
        "margin_mode": "isolated",
        "position_mode": "one_way",
        "allowed_leverage": [1, 2, 3, 5],
        "default_leverage": 2,
        "max_leverage": 5,
        "default_scenario_side": "LONG",
        "default_notional": 1000.0,
        "default_stop_loss_distance_pct": 2.0,
        "default_take_profit_distance_pct": 3.0,
        "maintenance_margin_rate": 0.004,
        "liquidation_fee_reserve_rate": 0.002,
        "additional_safety_buffer_rate": 0.005,
        "min_liquidation_distance_pct": 5.0,
        "warning_liquidation_distance_pct": 10.0,
        "max_initial_margin_pct_of_account_equity": 20.0,
        "max_notional_pct_of_account_equity": 100.0,
        "allow_public_futures_market_data_fetch": True,
        "allow_public_mark_price_fetch": True,
        "allow_public_funding_fetch": True,
        "allow_leverage_simulation": True,
        "allow_liquidation_modeling": True,
        "allow_margin_calculation": True,
        "allow_funding_estimation": True,
        "allow_scenario_comparison": True,
        "allow_real_leverage_change": False,
        "allow_exchange_margin_mode_change": False,
        "allow_private_api": False,
        "allow_api_key_usage": False,
        "allow_trading_api": False,
        "allow_account_data": False,
        "allow_balance_fetch": False,
        "allow_position_fetch": False,
        "allow_order_submission": False,
        "allow_order_cancellation": False,
        "allow_real_position_creation": False,
        "allow_paper_futures_position_creation": False,
        "allow_paper_trade_persistence": False,
        "allow_executable_trade_creation": False,
        "allow_paper_account_state_mutation": False,
        "allow_runner_state_mutation": False,
        "allow_execution_state_mutation": False,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_futures_feed_config_pass": True,
        "require_paper_account_config_pass": True,
        "require_kill_switch_enabled": True,
        "funding_periods_to_estimate": 3,
        "report_export_dir": "reports/futures_risk_model",
    }
    values.update(overrides)
    return values


def _futures_paper_position_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "exchange_symbol": "BTCUSDT",
        "exchange": "binance",
        "market_type": "futures",
        "futures_contract_type": "USDT_PERPETUAL",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "futures_read_only_feed_config_path": "configs/btc_futures_read_only_feed.json",
        "futures_risk_model_config_path": "configs/btc_futures_risk_model.json",
        "spot_paper_account_config_path": "configs/btc_paper_account.json",
        "position_simulation_enabled": False,
        "simulation_only": True,
        "dry_run_only": True,
        "margin_mode": "isolated",
        "position_mode": "one_way",
        "max_open_positions": 1,
        "allowed_leverage": [1, 2, 3, 5],
        "default_leverage": 2,
        "max_leverage": 5,
        "initial_account_balance": 10000.0,
        "account_currency": "USDT",
        "default_notional": 1000.0,
        "min_notional": 10.0,
        "max_notional_pct_of_equity": 100.0,
        "max_initial_margin_pct_of_equity": 20.0,
        "minimum_risk_reward": 1.5,
        "max_daily_realized_loss_pct": 2.0,
        "max_account_drawdown_pct": 5.0,
        "max_trades_per_day": 3,
        "taker_fee_rate": 0.0004,
        "liquidation_fee_rate": 0.002,
        "default_funding_periods": 1,
        "require_risk_model_pass": True,
        "require_stop_before_liquidation": True,
        "require_stop_loss": True,
        "require_take_profit": True,
        "auto_close_on_stop_loss": True,
        "auto_close_on_take_profit": True,
        "auto_close_on_simulated_liquidation": True,
        "liquidation_trigger_precedence": True,
        "closed_position_retention_in_state": 0,
        "allow_public_mark_price_fetch": True,
        "allow_public_funding_fetch": True,
        "allow_local_futures_state_write": True,
        "allow_local_futures_ledger_write": True,
        "allow_local_virtual_order_creation": True,
        "allow_local_paper_futures_position_creation": True,
        "allow_local_mark_to_market": True,
        "allow_local_funding_application": True,
        "allow_local_position_close": True,
        "allow_local_simulated_liquidation": True,
        "allow_local_futures_state_reset": True,
        "allow_private_api": False,
        "allow_api_key_usage": False,
        "allow_trading_api": False,
        "allow_account_data": False,
        "allow_balance_fetch": False,
        "allow_position_fetch": False,
        "allow_real_order_submission": False,
        "allow_order_cancellation": False,
        "allow_real_position_creation": False,
        "allow_exchange_paper_position_creation": False,
        "allow_testnet_order_submission": False,
        "allow_exchange_leverage_change": False,
        "allow_exchange_margin_mode_change": False,
        "allow_spot_paper_account_state_mutation": False,
        "allow_runner_state_mutation": False,
        "allow_execution_state_mutation": False,
        "allow_exchange_state_mutation": False,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_futures_feed_config_pass": True,
        "require_futures_risk_model_config_pass": True,
        "require_spot_paper_account_config_pass": True,
        "require_kill_switch_enabled": True,
        "state_path": "reports/futures_paper_position/state.json",
        "ledger_path": "reports/futures_paper_position/ledger.jsonl",
        "report_export_dir": "reports/futures_paper_position",
        "lock_path": "reports/futures_paper_position/state.lock",
        "state_lock_timeout_seconds": 1,
    }
    values.update(overrides)
    return values


def _binance_futures_testnet_adapter_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "exchange_symbol": "BTCUSDT",
        "exchange": "binance",
        "market_type": "futures",
        "futures_contract_type": "USDT_PERPETUAL",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "futures_read_only_feed_config_path": "configs/btc_futures_read_only_feed.json",
        "futures_risk_model_config_path": "configs/btc_futures_risk_model.json",
        "futures_paper_position_config_path": "configs/btc_futures_paper_position.json",
        "adapter_enabled": False,
        "connection_mode": "disabled",
        "testnet_only": True,
        "dry_run_only": True,
        "rest_base_url": "https://demo-fapi.binance.com",
        "allowed_hosts": ["demo-fapi.binance.com"],
        "api_key_env_var": "BINANCE_FUTURES_TESTNET_API_KEY",
        "api_secret_env_var": "BINANCE_FUTURES_TESTNET_API_SECRET",
        "credential_source": "environment",
        "request_timeout_seconds": 10,
        "max_public_fetch_retries": 1,
        "recv_window_ms": 5000,
        "maximum_recv_window_ms": 10000,
        "maximum_clock_skew_ms": 5000,
        "allowed_public_paths": ["/fapi/v1/ping", "/fapi/v1/time", "/fapi/v1/exchangeInfo"],
        "allowed_signed_preview_paths": ["/fapi/v2/account", "/fapi/v2/balance", "/fapi/v2/positionRisk"],
        "allow_public_testnet_ping": True,
        "allow_public_testnet_time_fetch": True,
        "allow_public_testnet_exchange_info_fetch": True,
        "allow_environment_credential_presence_check": True,
        "allow_local_hmac_signing_preview": True,
        "allow_local_signed_request_preview": True,
        "allow_local_order_intent_build": True,
        "allow_authenticated_testnet_request": False,
        "allow_authenticated_account_read": False,
        "allow_authenticated_balance_read": False,
        "allow_authenticated_position_read": False,
        "allow_testnet_order_submission": False,
        "allow_testnet_order_cancellation": False,
        "allow_testnet_leverage_change": False,
        "allow_testnet_margin_mode_change": False,
        "allow_testnet_position_creation": False,
        "allow_user_data_stream": False,
        "allow_websocket_connection": False,
        "allow_production_endpoint": False,
        "allow_production_credentials": False,
        "allow_real_funds": False,
        "allow_futures_paper_state_mutation": False,
        "allow_spot_paper_account_state_mutation": False,
        "allow_runner_state_mutation": False,
        "allow_execution_state_mutation": False,
        "allow_exchange_state_mutation": False,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_futures_feed_config_pass": True,
        "require_futures_risk_model_config_pass": True,
        "require_futures_paper_position_config_pass": True,
        "require_kill_switch_enabled": True,
        "order_intent_allowed_sides": ["BUY", "SELL"],
        "order_intent_allowed_types": ["MARKET", "LIMIT", "STOP_MARKET", "TAKE_PROFIT_MARKET"],
        "order_intent_default_time_in_force": "GTC",
        "order_intent_max_quantity": 1.0,
        "order_intent_require_reduce_only_for_close": True,
        "report_export_dir": "reports/binance_futures_testnet_adapter",
    }
    values.update(overrides)
    return values


def _binance_futures_testnet_read_only_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "exchange_symbol": "BTCUSDT",
        "exchange": "binance",
        "market_type": "futures",
        "futures_contract_type": "USDT_PERPETUAL",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "testnet_adapter_config_path": "configs/binance_futures_testnet_adapter.json",
        "futures_read_only_feed_config_path": "configs/btc_futures_read_only_feed.json",
        "futures_risk_model_config_path": "configs/btc_futures_risk_model.json",
        "futures_paper_position_config_path": "configs/btc_futures_paper_position.json",
        "feature_enabled": False,
        "automatic_execution_enabled": False,
        "explicit_cli_only": True,
        "authenticated_read_only_available": True,
        "dry_run_trading_only": True,
        "testnet_only": True,
        "rest_base_url": "https://demo-fapi.binance.com",
        "allowed_hosts": ["demo-fapi.binance.com"],
        "api_key_env_var": "BINANCE_FUTURES_TESTNET_API_KEY",
        "api_secret_env_var": "BINANCE_FUTURES_TESTNET_API_SECRET",
        "credential_source": "environment",
        "allowed_http_methods": ["GET"],
        "allowed_authenticated_paths": ["/fapi/v3/account", "/fapi/v3/balance", "/fapi/v3/positionRisk"],
        "account_path": "/fapi/v3/account",
        "balance_path": "/fapi/v3/balance",
        "position_risk_path": "/fapi/v3/positionRisk",
        "server_time_path": "/fapi/v1/time",
        "require_explicit_network_confirmation": True,
        "network_confirmation_phrase": "CONFIRM_TESTNET_READ_ONLY",
        "request_timeout_seconds": 10,
        "max_authenticated_fetch_retries": 0,
        "recv_window_ms": 5000,
        "maximum_recv_window_ms": 10000,
        "maximum_clock_skew_ms": 5000,
        "allow_public_server_time_fetch": True,
        "allow_explicit_authenticated_account_read": True,
        "allow_explicit_authenticated_balance_read": True,
        "allow_explicit_authenticated_position_read": True,
        "allow_explicit_combined_account_snapshot": True,
        "allow_automatic_authenticated_requests": False,
        "allow_background_authenticated_polling": False,
        "allow_runner_authenticated_requests": False,
        "allow_monitoring_authenticated_requests": False,
        "allow_order_query": False,
        "allow_trade_query": False,
        "allow_income_query": False,
        "allow_open_order_query": False,
        "allow_testnet_order_submission": False,
        "allow_testnet_order_test_submission": False,
        "allow_testnet_order_cancellation": False,
        "allow_testnet_order_modification": False,
        "allow_testnet_position_creation": False,
        "allow_testnet_position_close": False,
        "allow_testnet_leverage_change": False,
        "allow_testnet_margin_mode_change": False,
        "allow_testnet_position_mode_change": False,
        "allow_testnet_multi_assets_mode_change": False,
        "allow_testnet_position_margin_change": False,
        "allow_user_data_stream": False,
        "allow_listen_key": False,
        "allow_websocket_connection": False,
        "allow_production_endpoint": False,
        "allow_production_credentials": False,
        "allow_real_funds": False,
        "allow_raw_authenticated_response_print": False,
        "allow_raw_authenticated_response_persistence": False,
        "allow_authenticated_header_logging": False,
        "allow_signature_logging": False,
        "allow_signed_url_logging": False,
        "allow_futures_paper_state_mutation": False,
        "allow_spot_paper_account_state_mutation": False,
        "allow_runner_state_mutation": False,
        "allow_execution_state_mutation": False,
        "allow_exchange_state_mutation": False,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_testnet_adapter_config_pass": True,
        "require_futures_feed_config_pass": True,
        "require_futures_risk_model_config_pass": True,
        "require_futures_paper_position_config_pass": True,
        "require_kill_switch_enabled": True,
        "balance_asset_filter": "USDT",
        "position_symbol_filter": "BTCUSDT",
        "include_zero_balance_asset": True,
        "include_zero_position": True,
        "report_export_dir": "reports/binance_futures_testnet_read_only",
    }
    values.update(overrides)
    return values


def _binance_futures_testnet_order_test_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "exchange_symbol": "BTCUSDT",
        "exchange": "binance",
        "market_type": "futures",
        "futures_contract_type": "USDT_PERPETUAL",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "testnet_adapter_config_path": "configs/binance_futures_testnet_adapter.json",
        "testnet_read_only_config_path": "configs/binance_futures_testnet_read_only.json",
        "futures_feed_config_path": "configs/btc_futures_read_only_feed.json",
        "futures_risk_model_config_path": "configs/btc_futures_risk_model.json",
        "futures_paper_position_config_path": "configs/btc_futures_paper_position.json",
        "feature_enabled": False,
        "automatic_execution_enabled": False,
        "explicit_cli_only": True,
        "testnet_only": True,
        "test_order_only": True,
        "rest_base_url": "https://demo-fapi.binance.com",
        "allowed_hosts": ["demo-fapi.binance.com"],
        "api_key_env_var": "BINANCE_FUTURES_TESTNET_API_KEY",
        "api_secret_env_var": "BINANCE_FUTURES_TESTNET_API_SECRET",
        "allowed_http_methods": ["POST"],
        "test_order_path": "/fapi/v1/order/test",
        "mark_price_path": "/fapi/v1/premiumIndex",
        "market_reference_price_source": "MARK_PRICE",
        "allowed_authenticated_paths": ["/fapi/v1/order/test"],
        "require_explicit_network_confirmation": True,
        "network_confirmation_phrase": "CONFIRM_TESTNET_ORDER_TEST",
        "request_timeout_seconds": 10,
        "max_authenticated_retries": 0,
        "recv_window_ms": 5000,
        "maximum_recv_window_ms": 10000,
        "maximum_clock_skew_ms": 5000,
        "allow_public_server_time_fetch": True,
        "allow_public_exchange_info_fetch": True,
        "allow_local_order_test_preview": True,
        "allow_explicit_test_order_request": True,
        "require_market_reference_price": True,
        "allow_zero_market_reference_price": False,
        "allow_unknown_market_notional": False,
        "allow_unvalidated_exchange_filters_for_transmission": False,
        "require_exchange_filters_before_transmission": True,
        "allowed_order_types": ["MARKET", "LIMIT"],
        "allowed_sides": ["BUY", "SELL"],
        "default_time_in_force": "GTC",
        "allowed_time_in_force": ["GTC", "IOC", "FOK"],
        "maximum_quantity": 0.01,
        "maximum_test_notional_usdt": 100.0,
        "require_exchange_filter_validation": True,
        "require_unique_client_order_id": True,
        "client_order_id_prefix": "smcbot-test-",
        "maximum_client_order_id_length": 36,
        "allow_reduce_only": True,
        "allow_close_position": False,
        "allow_position_side": False,
        "allow_actual_order_submission": False,
        "allow_order_cancellation": False,
        "allow_order_modification": False,
        "allow_order_query": False,
        "allow_open_order_query": False,
        "allow_trade_query": False,
        "allow_income_query": False,
        "allow_conditional_order": False,
        "allow_algo_order": False,
        "allow_position_creation": False,
        "allow_position_close": False,
        "allow_leverage_change": False,
        "allow_margin_mode_change": False,
        "allow_position_mode_change": False,
        "allow_multi_assets_mode_change": False,
        "allow_position_margin_change": False,
        "allow_user_data_stream": False,
        "allow_listen_key": False,
        "allow_websocket_connection": False,
        "allow_production_endpoint": False,
        "allow_production_credentials": False,
        "allow_real_funds": False,
        "allow_raw_request_print": False,
        "allow_raw_response_print": False,
        "allow_raw_request_persistence": False,
        "allow_raw_response_persistence": False,
        "allow_authenticated_header_logging": False,
        "allow_signature_logging": False,
        "allow_signed_url_logging": False,
        "allow_futures_paper_state_mutation": False,
        "allow_spot_paper_account_state_mutation": False,
        "allow_runner_state_mutation": False,
        "allow_execution_state_mutation": False,
        "allow_exchange_state_mutation": False,
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_testnet_adapter_config_pass": True,
        "require_testnet_read_only_config_pass": True,
        "require_futures_feed_config_pass": True,
        "require_futures_risk_model_config_pass": True,
        "require_futures_paper_position_config_pass": True,
        "require_kill_switch_enabled": True,
        "report_export_dir": "reports/binance_futures_testnet_order_test",
    }
    values.update(overrides)
    return values


def _binance_futures_testnet_order_lifecycle_config(**overrides) -> dict:
    values = {
        "schema_version": "1.0",
        "project_scope": "BTC_ONLY",
        "symbol": "BTC/USDT",
        "exchange_symbol": "BTCUSDT",
        "exchange": "binance",
        "market_type": "futures",
        "futures_contract_type": "USDT_PERPETUAL",
        "strategy_profile": "balanced_smc_decision_065",
        "runtime_config_path": "configs/btc_paper_runtime.json",
        "monitoring_config_path": "configs/btc_paper_monitoring.json",
        "runner_config_path": "configs/btc_paper_runner.json",
        "testnet_adapter_config_path": "configs/binance_futures_testnet_adapter.json",
        "testnet_read_only_config_path": "configs/binance_futures_testnet_read_only.json",
        "testnet_order_test_config_path": "configs/binance_futures_testnet_order_test.json",
        "futures_feed_config_path": "configs/btc_futures_read_only_feed.json",
        "futures_risk_model_config_path": "configs/btc_futures_risk_model.json",
        "futures_paper_position_config_path": "configs/btc_futures_paper_position.json",
        "feature_enabled": False,
        "automatic_execution_enabled": False,
        "explicit_cli_only": True,
        "manual_lifecycle_only": True,
        "testnet_only": True,
        "single_order_only": True,
        "rest_base_url": "https://demo-fapi.binance.com",
        "allowed_hosts": ["demo-fapi.binance.com"],
        "api_key_env_var": "BINANCE_FUTURES_TESTNET_API_KEY",
        "api_secret_env_var": "BINANCE_FUTURES_TESTNET_API_SECRET",
        "server_time_path": "/fapi/v1/time",
        "exchange_info_path": "/fapi/v1/exchangeInfo",
        "book_ticker_path": "/fapi/v1/ticker/bookTicker",
        "position_mode_path": "/fapi/v1/positionSide/dual",
        "position_risk_path": "/fapi/v3/positionRisk",
        "order_path": "/fapi/v1/order",
        "allowed_order_methods": ["POST", "GET", "DELETE"],
        "allowed_order_types": ["LIMIT"],
        "allowed_time_in_force": ["GTX"],
        "allowed_sides": ["BUY", "SELL"],
        "required_position_mode": "ONE_WAY",
        "required_position_side": "BOTH",
        "require_zero_position_before_create": True,
        "require_zero_position_after_cancel": True,
        "require_explicit_lifecycle_confirmation": True,
        "lifecycle_confirmation_phrase": "CONFIRM_TESTNET_POST_ONLY_LIFECYCLE",
        "require_explicit_cancel_confirmation": True,
        "cancel_confirmation_phrase": "CONFIRM_TESTNET_CANCEL_ORDER",
        "require_explicit_query_confirmation": True,
        "query_confirmation_phrase": "CONFIRM_TESTNET_READ_ONLY",
        "request_timeout_seconds": 10,
        "max_create_retries": 0,
        "max_cancel_retries": 0,
        "max_query_retries": 1,
        "recv_window_ms": 5000,
        "maximum_recv_window_ms": 10000,
        "maximum_clock_skew_ms": 5000,
        "minimum_price_offset_bps": 50,
        "default_price_offset_bps": 100,
        "maximum_price_offset_bps": 5000,
        "maximum_quantity": 0.01,
        "maximum_lifecycle_notional_usdt": 100.0,
        "new_order_response_type": "ACK",
        "client_order_id_prefix": "smcbot-lifecycle-",
        "maximum_client_order_id_length": 36,
        "require_exchange_filter_validation": True,
        "require_book_ticker_validation": True,
        "require_non_marketable_price": True,
        "require_gtx_post_only": True,
        "allow_standalone_create": False,
        "allow_lifecycle_create_query_cancel": True,
        "allow_exact_order_query": True,
        "allow_exact_order_recovery_cancel": True,
        "allow_market_order": False,
        "allow_conditional_order": False,
        "allow_algo_order": False,
        "allow_batch_order": False,
        "allow_order_modification": False,
        "allow_cancel_all": False,
        "allow_open_order_list_query": False,
        "allow_all_order_history_query": False,
        "allow_trade_history_query": False,
        "allow_position_creation": False,
        "allow_position_close": False,
        "allow_leverage_change": False,
        "allow_margin_mode_change": False,
        "allow_position_mode_change": False,
        "allow_multi_assets_mode_change": False,
        "allow_position_margin_change": False,
        "allow_user_data_stream": False,
        "allow_listen_key": False,
        "allow_websocket_connection": False,
        "allow_production_endpoint": False,
        "allow_production_credentials": False,
        "allow_real_funds": False,
        "allow_runner_order_creation": False,
        "allow_monitoring_order_creation": False,
        "allow_strategy_order_creation": False,
        "allow_background_order_creation": False,
        "allow_futures_paper_state_mutation": False,
        "allow_spot_paper_account_state_mutation": False,
        "allow_runner_state_mutation": False,
        "allow_execution_state_mutation": False,
        "allow_raw_request_print": False,
        "allow_raw_response_print": False,
        "allow_raw_request_persistence": False,
        "allow_raw_response_persistence": False,
        "allow_authenticated_header_logging": False,
        "allow_signature_logging": False,
        "allow_signed_url_logging": False,
        "allow_sanitized_local_lifecycle_journal": True,
        "lifecycle_journal_path": "data/runtime/binance_futures_testnet_order_lifecycle/lifecycle.json",
        "lifecycle_lock_path": "data/runtime/binance_futures_testnet_order_lifecycle/lifecycle.lock",
        "require_runtime_config_pass": True,
        "require_monitoring_config_pass": True,
        "require_runner_config_pass": True,
        "require_testnet_adapter_config_pass": True,
        "require_testnet_read_only_config_pass": True,
        "require_testnet_order_test_config_pass": True,
        "require_futures_feed_config_pass": True,
        "require_futures_risk_model_config_pass": True,
        "require_futures_paper_position_config_pass": True,
        "require_kill_switch_enabled": True,
        "report_export_dir": "reports/binance_futures_testnet_order_lifecycle",
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
    return BTCPaperReadinessEngine(
        repo_root=root,
        env=kwargs.pop("env", {}),
        gate_runner=kwargs.pop("gate_runner", None),
        binance_futures_testnet_order_lifecycle_engine=kwargs.pop("binance_futures_testnet_order_lifecycle_engine", _FakeOrderLifecycleEngine(root)),
    ).build_report(
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
    assert _check(report, "btc_live_market_read_only_feed_dry_run").status == "PASS"
    assert _check(report, "btc_local_paper_account_simulation").status == "PASS"
    assert _check(report, "btc_futures_read_only_market_feed").status == "PASS"
    assert _check(report, "btc_futures_leverage_liquidation_risk_model").status == "PASS"
    assert _check(report, "binance_futures_testnet_authenticated_read_only").status == "PASS"
    assert _check(report, "binance_futures_testnet_order_test_preflight").status == "PASS"
    assert _check(report, "binance_futures_testnet_manual_post_only_lifecycle").status == "PASS"


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


def test_readiness_remains_ready_with_valid_live_market_feed_config(tmp_path) -> None:
    _ready_files(tmp_path)

    report = _report(tmp_path)

    assert report.readiness_status == "READY"
    assert _check(report, "btc_live_market_read_only_feed_dry_run").status == "PASS"


def test_readiness_blocks_when_live_market_feed_config_is_dangerous(tmp_path) -> None:
    _write_json(tmp_path / "configs" / "btc_paper_runtime.json", _runtime_config())
    _write_json(tmp_path / "configs" / "btc_paper_monitoring.json", _monitoring_config())
    _write_json(tmp_path / "configs" / "btc_paper_runner.json", _runner_config())
    _write_json(tmp_path / "configs" / "btc_paper_signal_evaluation.json", _signal_evaluation_config())
    _write_json(tmp_path / "configs" / "btc_paper_trade_candidate.json", _trade_candidate_config())
    _write_json(tmp_path / "configs" / "btc_paper_candidate_journal.json", _candidate_journal_config())
    _write_json(tmp_path / "configs" / "btc_forward_test_loop.json", _forward_test_config())
    _write_json(tmp_path / "configs" / "btc_live_market_feed.json", _live_market_feed_config(allow_order_submission=True))

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "btc_live_market_read_only_feed_dry_run").status == "FAIL"


def test_readiness_blocks_when_paper_account_config_is_dangerous(tmp_path) -> None:
    _ready_files(tmp_path)
    _write_json(tmp_path / "configs" / "btc_paper_account.json", _paper_account_config(allow_real_order_submission=True))

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "btc_local_paper_account_simulation").status == "FAIL"


def test_readiness_blocks_when_futures_read_only_feed_config_is_dangerous(tmp_path) -> None:
    _ready_files(tmp_path)
    _write_json(tmp_path / "configs" / "btc_futures_read_only_feed.json", _futures_read_only_feed_config(allow_leverage=True))

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "btc_futures_read_only_market_feed").status == "FAIL"


def test_readiness_blocks_when_futures_risk_model_config_is_dangerous(tmp_path) -> None:
    _ready_files(tmp_path)
    _write_json(tmp_path / "configs" / "btc_futures_risk_model.json", _futures_risk_model_config(allow_private_api=True))

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "btc_futures_leverage_liquidation_risk_model").status == "FAIL"


def test_readiness_reports_futures_paper_position_config_pass(tmp_path) -> None:
    _ready_files(tmp_path)

    report = _report(tmp_path)

    assert report.readiness_status == "READY"
    assert _check(report, "btc_futures_local_paper_position_simulation").status == "PASS"


def test_readiness_reports_binance_futures_testnet_adapter_config_pass(tmp_path) -> None:
    _ready_files(tmp_path)

    report = _report(tmp_path)

    assert report.readiness_status == "READY"
    assert _check(report, "binance_futures_testnet_adapter_disabled").status == "PASS"


def test_readiness_blocks_when_binance_futures_testnet_adapter_config_is_dangerous(tmp_path) -> None:
    _ready_files(tmp_path)
    _write_json(
        tmp_path / "configs" / "binance_futures_testnet_adapter.json",
        _binance_futures_testnet_adapter_config(allow_testnet_order_submission=True),
    )

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "binance_futures_testnet_adapter_disabled").status == "FAIL"


def test_readiness_reports_binance_futures_testnet_read_only_config_pass(tmp_path) -> None:
    _ready_files(tmp_path)

    report = _report(tmp_path)

    assert report.readiness_status == "READY"
    assert _check(report, "binance_futures_testnet_authenticated_read_only").status == "PASS"


def test_readiness_blocks_when_binance_futures_testnet_read_only_config_is_dangerous(tmp_path) -> None:
    _ready_files(tmp_path)
    _write_json(
        tmp_path / "configs" / "binance_futures_testnet_read_only.json",
        _binance_futures_testnet_read_only_config(allow_testnet_order_submission=True),
    )

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "binance_futures_testnet_authenticated_read_only").status == "FAIL"


def test_missing_credentials_do_not_block_readiness(tmp_path) -> None:
    _ready_files(tmp_path)

    report = _report(tmp_path, env={})

    assert report.readiness_status == "READY"
    assert _check(report, "binance_futures_testnet_authenticated_read_only").status == "PASS"
    assert _check(report, "binance_futures_testnet_order_test_preflight").status == "PASS"


def test_readiness_reports_binance_futures_testnet_order_test_config_pass(tmp_path) -> None:
    _ready_files(tmp_path)

    report = _report(tmp_path)

    assert report.readiness_status == "READY"
    assert _check(report, "binance_futures_testnet_order_test_preflight").status == "PASS"


def test_readiness_blocks_when_binance_futures_testnet_order_test_config_is_dangerous(tmp_path) -> None:
    _ready_files(tmp_path)
    _write_json(
        tmp_path / "configs" / "binance_futures_testnet_order_test.json",
        _binance_futures_testnet_order_test_config(allow_actual_order_submission=True),
    )

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "binance_futures_testnet_order_test_preflight").status == "FAIL"


def test_readiness_blocks_when_order_test_market_public_validation_is_unsafe(tmp_path) -> None:
    _ready_files(tmp_path)
    _write_json(
        tmp_path / "configs" / "binance_futures_testnet_order_test.json",
        _binance_futures_testnet_order_test_config(allow_unknown_market_notional=True),
    )

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "binance_futures_testnet_order_test_preflight").status == "FAIL"


def test_readiness_blocks_when_order_lifecycle_config_is_dangerous(tmp_path) -> None:
    _ready_files(tmp_path)
    _write_json(
        tmp_path / "configs" / "binance_futures_testnet_order_lifecycle.json",
        _binance_futures_testnet_order_lifecycle_config(allow_market_order=True),
    )

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "binance_futures_testnet_manual_post_only_lifecycle").status == "FAIL"


def test_readiness_blocks_when_futures_paper_position_config_is_dangerous(tmp_path) -> None:
    _ready_files(tmp_path)
    _write_json(tmp_path / "configs" / "btc_futures_paper_position.json", _futures_paper_position_config(allow_private_api=True))

    report = _report(tmp_path)

    assert report.readiness_status == "BLOCKED"
    assert _check(report, "btc_futures_local_paper_position_simulation").status == "FAIL"


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
