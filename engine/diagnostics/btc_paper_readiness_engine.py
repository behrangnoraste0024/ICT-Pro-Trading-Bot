from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.diagnostics.historical_sample_registry_engine import HistoricalSampleRegistryEngine
from engine.diagnostics.validation_baseline_engine import ValidationBaselineEngine
from engine.diagnostics.binance_futures_testnet_adapter_engine import BinanceFuturesTestnetAdapterEngine
from engine.diagnostics.binance_futures_testnet_read_only_engine import BinanceFuturesTestnetReadOnlyEngine
from engine.diagnostics.binance_futures_testnet_order_test_engine import BinanceFuturesTestnetOrderTestEngine
from engine.diagnostics.binance_futures_testnet_order_lifecycle_engine import BinanceFuturesTestnetOrderLifecycleEngine
from engine.diagnostics.binance_futures_testnet_protective_orders_engine import BinanceFuturesTestnetProtectiveOrdersEngine
from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine
from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from engine.diagnostics.btc_paper_signal_evaluation_engine import BTCPaperSignalEvaluationEngine
from engine.diagnostics.btc_paper_candidate_journal_engine import BTCPaperCandidateJournalEngine
from engine.diagnostics.btc_paper_trade_candidate_engine import BTCPaperTradeCandidateEngine
from engine.diagnostics.btc_forward_test_loop_engine import BTCForwardTestLoopEngine
from engine.diagnostics.btc_futures_read_only_feed_engine import BTCFuturesReadOnlyFeedEngine
from engine.diagnostics.btc_futures_paper_position_engine import BTCFuturesPaperPositionEngine
from engine.diagnostics.btc_futures_risk_model_engine import BTCFuturesRiskModelEngine
from engine.diagnostics.btc_live_market_feed_engine import BTCLiveMarketFeedEngine
from engine.diagnostics.btc_paper_account_engine import BTCPaperAccountEngine
from infrastructure.observability.operational_metrics import OperationalCounterRegistry
from models.btc_paper_readiness import BTCPaperReadinessCheck, BTCPaperReadinessReport


class BTCPaperReadinessEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        registry_engine: HistoricalSampleRegistryEngine | None = None,
        baseline_engine: ValidationBaselineEngine | None = None,
        runtime_config_engine: BTCPaperRuntimeConfigEngine | None = None,
        monitoring_engine: BTCPaperMonitoringEngine | None = None,
        runner_engine: BTCPaperRunnerEngine | None = None,
        signal_evaluation_engine: BTCPaperSignalEvaluationEngine | None = None,
        trade_candidate_engine: BTCPaperTradeCandidateEngine | None = None,
        candidate_journal_engine: BTCPaperCandidateJournalEngine | None = None,
        forward_test_engine: BTCForwardTestLoopEngine | None = None,
        live_market_feed_engine: BTCLiveMarketFeedEngine | None = None,
        paper_account_engine: BTCPaperAccountEngine | None = None,
        futures_read_only_feed_engine: BTCFuturesReadOnlyFeedEngine | None = None,
        futures_risk_model_engine: BTCFuturesRiskModelEngine | None = None,
        futures_paper_position_engine: BTCFuturesPaperPositionEngine | None = None,
        binance_futures_testnet_adapter_engine: BinanceFuturesTestnetAdapterEngine | None = None,
        binance_futures_testnet_read_only_engine: BinanceFuturesTestnetReadOnlyEngine | None = None,
        binance_futures_testnet_order_test_engine: BinanceFuturesTestnetOrderTestEngine | None = None,
        binance_futures_testnet_order_lifecycle_engine: BinanceFuturesTestnetOrderLifecycleEngine | None = None,
        binance_futures_testnet_protective_orders_engine: BinanceFuturesTestnetProtectiveOrdersEngine | None = None,
        gate_runner: Callable[..., int] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.operational_counter_registry = OperationalCounterRegistry()
        self.registry_engine = registry_engine or HistoricalSampleRegistryEngine(repo_root=self.repo_root)
        self.baseline_engine = baseline_engine or ValidationBaselineEngine(repo_root=self.repo_root)
        self.runtime_config_engine = runtime_config_engine or BTCPaperRuntimeConfigEngine(repo_root=self.repo_root)
        self.monitoring_engine = monitoring_engine or BTCPaperMonitoringEngine(repo_root=self.repo_root)
        self.runner_engine = runner_engine or BTCPaperRunnerEngine(repo_root=self.repo_root)
        self.signal_evaluation_engine = signal_evaluation_engine or BTCPaperSignalEvaluationEngine(repo_root=self.repo_root)
        self.trade_candidate_engine = trade_candidate_engine or BTCPaperTradeCandidateEngine(repo_root=self.repo_root)
        self.candidate_journal_engine = candidate_journal_engine or BTCPaperCandidateJournalEngine(repo_root=self.repo_root)
        self.forward_test_engine = forward_test_engine or BTCForwardTestLoopEngine(repo_root=self.repo_root)
        self.live_market_feed_engine = live_market_feed_engine or BTCLiveMarketFeedEngine(repo_root=self.repo_root)
        self.paper_account_engine = paper_account_engine or BTCPaperAccountEngine(repo_root=self.repo_root)
        self.futures_read_only_feed_engine = futures_read_only_feed_engine or BTCFuturesReadOnlyFeedEngine(repo_root=self.repo_root)
        self.futures_risk_model_engine = futures_risk_model_engine or BTCFuturesRiskModelEngine(repo_root=self.repo_root)
        self.futures_paper_position_engine = futures_paper_position_engine or BTCFuturesPaperPositionEngine(repo_root=self.repo_root)
        self.binance_futures_testnet_adapter_engine = binance_futures_testnet_adapter_engine or BinanceFuturesTestnetAdapterEngine(repo_root=self.repo_root, env={})
        self.binance_futures_testnet_read_only_engine = binance_futures_testnet_read_only_engine or BinanceFuturesTestnetReadOnlyEngine(repo_root=self.repo_root, env={})
        self.binance_futures_testnet_order_test_engine = binance_futures_testnet_order_test_engine or BinanceFuturesTestnetOrderTestEngine(repo_root=self.repo_root, env={}, operational_counter_registry=self.operational_counter_registry)
        self.binance_futures_testnet_order_lifecycle_engine = binance_futures_testnet_order_lifecycle_engine or BinanceFuturesTestnetOrderLifecycleEngine(repo_root=self.repo_root, env={}, operational_counter_registry=self.operational_counter_registry)
        self.binance_futures_testnet_protective_orders_engine = binance_futures_testnet_protective_orders_engine or BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=self.repo_root, env={}, operational_counter_registry=self.operational_counter_registry)
        self.gate_runner = gate_runner
        self.env = os.environ if env is None else env

    def build_report(
        self,
        registry_path: str = "configs/historical_sample_registry.json",
        baseline_config: str = "configs/validation_baseline.json",
        expected_profile: str = "balanced_smc_decision_065",
        strict: bool = False,
        run_gate: bool = False,
        use_cache: bool = False,
        cache_dir: str = ".cache/backtests",
    ) -> BTCPaperReadinessReport:
        checks: list[BTCPaperReadinessCheck] = []
        registry_report = None
        baseline = None
        snapshot: dict[str, Any] | None = None

        try:
            registry_report = self.registry_engine.check(registry_path)
            checks.append(self._check("historical_sample_registry", "PASS", "REQUIRED", "Historical sample registry exists.", {"registry": registry_path}))
        except Exception as exc:
            checks.append(self._check("historical_sample_registry", "FAIL", "REQUIRED", f"Historical sample registry is unavailable: {exc}", {"registry": registry_path}))

        if registry_report is not None:
            checks.extend(self._btc_sample_checks(registry_report))
            checks.append(self._eth_optional_check_from_registry(registry_report))
        else:
            checks.append(self._check("required_btc_samples", "SKIPPED", "REQUIRED", "BTC sample availability skipped because registry is unavailable."))

        baseline_path = Path(baseline_config)
        if not baseline_path.is_absolute():
            baseline_path = self.repo_root / baseline_path
        if not baseline_path.exists():
            checks.append(self._check("validation_baseline_config", "FAIL", "REQUIRED", "Validation baseline config is missing.", {"baseline_config": baseline_config}))
        else:
            try:
                baseline = self.baseline_engine.load(str(baseline_path))
                checks.append(self._check("validation_baseline_config", "PASS", "REQUIRED", "Validation baseline config exists.", {"baseline_config": baseline_config}))
            except Exception as exc:
                checks.append(self._check("validation_baseline_config", "FAIL", "REQUIRED", f"Validation baseline config could not be loaded: {exc}", {"baseline_config": baseline_config}))

        if baseline is not None:
            checks.append(self._baseline_profile_check(baseline, expected_profile))
            snapshot_path = self.baseline_engine.resolve_baseline_path(baseline)
            if not snapshot_path:
                status = "FAIL" if strict else "WARNING"
                checks.append(self._check("baseline_snapshot", status, "REQUIRED", "Baseline snapshot path is not set.", {"strict": strict}))
            elif not Path(snapshot_path).exists():
                status = "FAIL" if strict else "WARNING"
                checks.append(self._check("baseline_snapshot", status, "REQUIRED", "Baseline snapshot is missing locally.", {"baseline_snapshot": snapshot_path, "strict": strict}))
            else:
                try:
                    snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
                    checks.append(self._check("baseline_snapshot", "PASS", "REQUIRED", "Baseline snapshot exists.", {"baseline_snapshot": snapshot_path}))
                except Exception as exc:
                    checks.append(self._check("baseline_snapshot", "FAIL", "REQUIRED", f"Baseline snapshot could not be read: {exc}", {"baseline_snapshot": snapshot_path}))
        else:
            checks.append(self._check("baseline_profile", "SKIPPED", "REQUIRED", "Baseline profile check skipped because baseline config is unavailable."))
            checks.append(self._check("baseline_snapshot", "SKIPPED", "REQUIRED", "Baseline snapshot check skipped because baseline config is unavailable."))

        checks.extend(self._snapshot_checks(snapshot))
        checks.append(self._paper_execution_disabled_check())
        checks.append(self._live_trading_disabled_check())
        checks.append(self._risk_readiness_check())
        checks.append(self._monitoring_readiness_check())
        checks.append(self._runner_readiness_check())
        checks.append(self._signal_evaluation_readiness_check())
        checks.append(self._trade_candidate_readiness_check())
        checks.append(self._candidate_journal_readiness_check())
        checks.append(self._forward_test_readiness_check())
        checks.append(self._live_market_feed_readiness_check())
        checks.append(self._paper_account_readiness_check())
        checks.append(self._futures_read_only_feed_readiness_check())
        checks.append(self._futures_risk_model_readiness_check())
        checks.append(self._futures_paper_position_readiness_check())
        checks.append(self._binance_futures_testnet_adapter_readiness_check())
        checks.append(self._binance_futures_testnet_read_only_readiness_check())
        checks.append(self._binance_futures_testnet_order_test_readiness_check())
        checks.append(self._binance_futures_testnet_order_lifecycle_readiness_check())
        checks.append(self._binance_futures_testnet_protective_orders_readiness_check())
        checks.append(self._cache_diagnostics_check(snapshot))
        if run_gate:
            checks.append(self._gate_check(use_cache=use_cache, cache_dir=cache_dir))

        return self._report(checks, expected_profile)

    def _btc_sample_checks(self, registry_report) -> list[BTCPaperReadinessCheck]:
        required = [
            row
            for row in registry_report.samples
            if row.symbol == "BTC/USDT" and row.required_for_full_gate
        ]
        checks: list[BTCPaperReadinessCheck] = []
        for expected in ("btcusdt_15m_1000", "btcusdt_1h_1000"):
            row = next((item for item in required if item.sample_name == expected), None)
            if row is None:
                checks.append(self._check(expected, "FAIL", "REQUIRED", f"Required BTC sample {expected} is missing from full-gate registry scope."))
            elif row.status == "AVAILABLE":
                checks.append(self._check(expected, "PASS", "REQUIRED", f"Required BTC sample {expected} is available.", row.to_dict()))
            else:
                checks.append(self._check(expected, "FAIL", "REQUIRED", f"Required BTC sample {expected} is not available: {row.status}.", row.to_dict()))
        return checks

    def _baseline_profile_check(self, baseline, expected_profile: str) -> BTCPaperReadinessCheck:
        actual = getattr(baseline, "recommended_profile", None)
        if actual == expected_profile:
            return self._check("baseline_profile", "PASS", "REQUIRED", f"Baseline profile matches {expected_profile}.", {"expected_profile": expected_profile, "actual_profile": actual})
        return self._check("baseline_profile", "FAIL", "REQUIRED", f"Baseline profile {actual} does not match expected {expected_profile}.", {"expected_profile": expected_profile, "actual_profile": actual})

    def _snapshot_checks(self, snapshot: dict[str, Any] | None) -> list[BTCPaperReadinessCheck]:
        if snapshot is None:
            return [
                self._check("snapshot_sample_scope", "SKIPPED", "REQUIRED", "Snapshot scope check skipped because baseline snapshot is unavailable."),
                self._check("btc_15m_validation", "SKIPPED", "REQUIRED", "BTC 15m validation check skipped because baseline snapshot is unavailable."),
                self._check("btc_1h_validation", "SKIPPED", "REQUIRED", "BTC 1h validation check skipped because baseline snapshot is unavailable."),
                self._check("eth_optional_scope", "SKIPPED", "INFO", "ETH optional scope check skipped because baseline snapshot is unavailable."),
            ]
        result = snapshot.get("multi_sample_result") or {}
        rows = result.get("rows") or []
        row_map = {row.get("sample_name"): row for row in rows if isinstance(row, dict)}
        checks = [
            self._snapshot_scope_check(result, row_map),
            self._snapshot_btc_row_check(row_map, "btcusdt_15m_1000", "btc_15m_validation"),
            self._snapshot_btc_row_check(row_map, "btcusdt_1h_1000", "btc_1h_validation"),
            self._eth_optional_check_from_snapshot(result, row_map),
        ]
        return checks

    def _snapshot_scope_check(self, result: dict[str, Any], row_map: dict[str, dict[str, Any]]) -> BTCPaperReadinessCheck:
        scope = result.get("sample_scope") or (result.get("diagnostics") or {}).get("sample_scope")
        btc_ok = all(name in row_map for name in ("btcusdt_15m_1000", "btcusdt_1h_1000"))
        eth_rows = [row for name, row in row_map.items() if str(name).startswith("eth")]
        eth_ok = all((row.get("status") in ("SKIPPED_OUT_OF_SCOPE", "SKIPPED_MISSING_FILE")) for row in eth_rows)
        if scope in ("required_full", "btc_only") and btc_ok:
            return self._check("snapshot_sample_scope", "PASS", "REQUIRED", "Baseline snapshot uses BTC official scope.", {"sample_scope": scope})
        if scope is None and btc_ok and eth_ok:
            return self._check("snapshot_sample_scope", "PASS", "REQUIRED", "Baseline snapshot appears BTC-scoped by sample rows.", {"sample_scope": None, "inferred": True})
        return self._check("snapshot_sample_scope", "FAIL", "REQUIRED", "Baseline snapshot does not appear to use official BTC scope.", {"sample_scope": scope, "btc_rows_present": btc_ok, "eth_rows": eth_rows})

    def _snapshot_btc_row_check(self, row_map: dict[str, dict[str, Any]], sample_name: str, check_name: str) -> BTCPaperReadinessCheck:
        row = row_map.get(sample_name)
        if row is None:
            return self._check(check_name, "FAIL", "REQUIRED", f"{sample_name} is missing from baseline snapshot.")
        passed = row.get("status") == "PASSED" and row.get("validation_status") in ("PASS", None)
        if passed:
            return self._check(check_name, "PASS", "REQUIRED", f"{sample_name} validation passed.", row)
        return self._check(check_name, "FAIL", "REQUIRED", f"{sample_name} validation did not pass.", row)

    def _eth_optional_check_from_registry(self, registry_report) -> BTCPaperReadinessCheck:
        eth_required = [
            row.sample_name
            for row in registry_report.samples
            if row.symbol == "ETH/USDT" and (row.required_for_full_gate or row.required_for_ci_gate)
        ]
        if eth_required:
            return self._check("eth_optional_registry", "WARNING", "INFO", "ETH samples are marked required; current BTC phase expects them optional.", {"eth_required": eth_required})
        return self._check("eth_optional_registry", "PASS", "INFO", "ETH samples are optional/stress-test only for BTC readiness.")

    def _eth_optional_check_from_snapshot(self, result: dict[str, Any], row_map: dict[str, dict[str, Any]]) -> BTCPaperReadinessCheck:
        eth_rows = [row for name, row in row_map.items() if str(name).startswith("eth")]
        if not eth_rows:
            return self._check("eth_optional_scope", "PASS", "INFO", "ETH samples are not present in the BTC readiness snapshot.")
        if all(row.get("status") == "SKIPPED_OUT_OF_SCOPE" for row in eth_rows):
            return self._check("eth_optional_scope", "PASS", "INFO", "ETH samples are skipped out-of-scope and do not block BTC readiness.")
        if any(row.get("status") in ("FAILED", "ERROR") for row in eth_rows):
            return self._check("eth_optional_scope", "WARNING", "INFO", "ETH rows failed in this snapshot; treat as multi-asset stress-test signal, not BTC blocker.", {"sample_scope": result.get("sample_scope"), "eth_rows": eth_rows})
        return self._check("eth_optional_scope", "PASS", "INFO", "ETH optional rows do not block BTC readiness.", {"eth_rows": eth_rows})

    def _paper_execution_disabled_check(self) -> BTCPaperReadinessCheck:
        enabled = self._flag_enabled("PAPER_TRADING_ENABLED") or self._flag_enabled("ENABLE_PAPER_EXECUTION")
        if enabled:
            return self._check("paper_execution_disabled", "FAIL", "REQUIRED", "Paper execution appears enabled; readiness diagnostics must not execute paper trades.")
        return self._check("paper_execution_disabled", "PASS", "REQUIRED", "Paper execution remains disabled/not started; this report is pre-paper readiness only.")

    def _live_trading_disabled_check(self) -> BTCPaperReadinessCheck:
        enabled = self._flag_enabled("LIVE_TRADING_ENABLED") or self._flag_enabled("ENABLE_LIVE_TRADING")
        if enabled:
            return self._check("live_trading_disabled", "FAIL", "REQUIRED", "Live trading activation detected.")
        return self._check("live_trading_disabled", "PASS", "REQUIRED", "No live trading activation detected.")

    def _risk_readiness_check(self) -> BTCPaperReadinessCheck:
        trade_plan_exists = (self.repo_root / "engine" / "trade_plan" / "trade_plan_engine.py").exists()
        runtime_config = self.repo_root / "configs" / "btc_paper_runtime.json"
        if not runtime_config.exists():
            return self._check(
                "risk_runtime_config",
                "WARNING",
                "RECOMMENDED",
                "Create BTC paper runtime config before executing paper trades.",
                {"trade_plan_engine_exists": trade_plan_exists, "runtime_config": str(runtime_config)},
            )
        report = self.runtime_config_engine.validate(str(runtime_config))
        details = {
            "trade_plan_engine_exists": trade_plan_exists,
            "runtime_config": str(runtime_config),
            "validation_status": report.status,
            "issue_count": report.issue_count,
            "warning_count": report.warning_count,
            "fail_count": report.fail_count,
            "issues": [issue.to_dict() for issue in report.issues],
        }
        if report.status == "PASS":
            return self._check(
                "risk_runtime_config",
                "PASS",
                "RECOMMENDED",
                "BTC paper runtime risk config is present and valid.",
                details,
            )
        if report.status == "WARNING":
            return self._check(
                "risk_runtime_config",
                "WARNING",
                "RECOMMENDED",
                "BTC paper runtime risk config has warnings.",
                details,
            )
        return self._check(
            "risk_runtime_config",
            "FAIL",
            "REQUIRED",
            "BTC paper runtime risk config failed safety validation.",
            details,
        )

    def _monitoring_readiness_check(self) -> BTCPaperReadinessCheck:
        config_path = self.repo_root / "configs" / "btc_paper_monitoring.json"
        if not config_path.exists():
            return self._check(
                "paper_monitoring",
                "WARNING",
                "RECOMMENDED",
                "Add BTC paper monitoring config before execution.",
                {"monitoring_config": str(config_path)},
            )
        report = self.monitoring_engine.validate(str(config_path))
        details = {
            "monitoring_config": str(config_path),
            "validation_status": report.status,
            "issue_count": report.issue_count,
            "warning_count": report.warning_count,
            "fail_count": report.fail_count,
            "issues": [issue.to_dict() for issue in report.issues],
            "diagnostics": dict(report.diagnostics),
        }
        if report.status == "PASS":
            return self._check(
                "paper_monitoring",
                "PASS",
                "RECOMMENDED",
                "BTC paper monitoring config and pre-runner telemetry readiness are present and safe.",
                details,
            )
        if report.status == "WARNING":
            return self._check(
                "paper_monitoring",
                "WARNING",
                "RECOMMENDED",
                "BTC paper monitoring config has warnings.",
                details,
            )
        return self._check(
            "paper_monitoring",
            "FAIL",
            "REQUIRED",
            "BTC paper monitoring config failed safety validation.",
            details,
        )

    def _runner_readiness_check(self) -> BTCPaperReadinessCheck:
        config_path = self.repo_root / "configs" / "btc_paper_runner.json"
        if not config_path.exists():
            return self._check(
                "btc_paper_runner_dry_run_state_machine",
                "SKIPPED",
                "INFO",
                "BTC paper runner dry-run state machine config is not present yet.",
                {"runner_config": str(config_path)},
            )
        _, issues, diagnostics = self.runner_engine.validate_config(str(config_path))
        details = {
            "runner_config": str(config_path),
            "issue_count": len(issues),
            "fail_count": sum(1 for issue in issues if issue.severity == "FAIL"),
            "issues": [issue.to_dict() for issue in issues],
            "diagnostics": diagnostics,
        }
        if not any(issue.severity == "FAIL" for issue in issues):
            return self._check(
                "btc_paper_runner_dry_run_state_machine",
                "PASS",
                "INFO",
                "BTC paper runner dry-run state machine config is present and safe.",
                details,
            )
        return self._check(
            "btc_paper_runner_dry_run_state_machine",
            "FAIL",
            "REQUIRED",
            "BTC paper runner dry-run state machine config failed safety validation.",
            details,
        )

    def _signal_evaluation_readiness_check(self) -> BTCPaperReadinessCheck:
        config_path = self.repo_root / "configs" / "btc_paper_signal_evaluation.json"
        if not config_path.exists():
            return self._check(
                "btc_paper_signal_evaluation_dry_run",
                "WARNING",
                "INFO",
                "BTC paper signal evaluation dry-run config is not present yet.",
                {"signal_evaluation_config": str(config_path)},
            )
        report = self.signal_evaluation_engine.validate(str(config_path))
        details = {
            "signal_evaluation_config": str(config_path),
            "validation_status": report.status,
            "issue_count": report.issue_count,
            "warning_count": report.warning_count,
            "fail_count": report.fail_count,
            "issues": [issue.to_dict() for issue in report.issues],
            "diagnostics": dict(report.diagnostics),
        }
        if report.status == "PASS":
            return self._check(
                "btc_paper_signal_evaluation_dry_run",
                "PASS",
                "INFO",
                "BTC paper signal evaluation dry-run config is present and safe.",
                details,
            )
        if report.status == "WARNING":
            return self._check(
                "btc_paper_signal_evaluation_dry_run",
                "WARNING",
                "INFO",
                "BTC paper signal evaluation dry-run config has warnings.",
                details,
            )
        return self._check(
            "btc_paper_signal_evaluation_dry_run",
            "FAIL",
            "REQUIRED",
            "BTC paper signal evaluation dry-run config failed safety validation.",
            details,
        )

    def _trade_candidate_readiness_check(self) -> BTCPaperReadinessCheck:
        config_path = self.repo_root / "configs" / "btc_paper_trade_candidate.json"
        if not config_path.exists():
            return self._check(
                "btc_paper_trade_candidate_dry_run",
                "WARNING",
                "INFO",
                "BTC paper trade candidate dry-run config is not present yet.",
                {"trade_candidate_config": str(config_path)},
            )
        report = self.trade_candidate_engine.validate(str(config_path))
        details = {
            "trade_candidate_config": str(config_path),
            "validation_status": report.status,
            "issue_count": report.issue_count,
            "warning_count": report.warning_count,
            "fail_count": report.fail_count,
            "issues": [issue.to_dict() for issue in report.issues],
            "diagnostics": dict(report.diagnostics),
        }
        if report.status == "PASS":
            return self._check(
                "btc_paper_trade_candidate_dry_run",
                "PASS",
                "INFO",
                "BTC paper trade candidate dry-run config is present and safe.",
                details,
            )
        if report.status == "WARNING":
            return self._check(
                "btc_paper_trade_candidate_dry_run",
                "WARNING",
                "INFO",
                "BTC paper trade candidate dry-run config has warnings.",
                details,
            )
        return self._check(
            "btc_paper_trade_candidate_dry_run",
            "FAIL",
            "REQUIRED",
            "BTC paper trade candidate dry-run config failed safety validation.",
            details,
        )

    def _candidate_journal_readiness_check(self) -> BTCPaperReadinessCheck:
        config_path = self.repo_root / "configs" / "btc_paper_candidate_journal.json"
        if not config_path.exists():
            return self._check(
                "btc_paper_candidate_journal_dry_run",
                "WARNING",
                "INFO",
                "BTC paper candidate journal dry-run config is not present yet.",
                {"candidate_journal_config": str(config_path)},
            )
        report = self.candidate_journal_engine.validate(str(config_path))
        details = {
            "candidate_journal_config": str(config_path),
            "validation_status": report.status,
            "issue_count": report.issue_count,
            "warning_count": report.warning_count,
            "fail_count": report.fail_count,
            "issues": [issue.to_dict() for issue in report.issues],
            "diagnostics": dict(report.diagnostics),
        }
        if report.status == "PASS":
            return self._check(
                "btc_paper_candidate_journal_dry_run",
                "PASS",
                "INFO",
                "BTC paper candidate journal dry-run config is present and safe.",
                details,
            )
        if report.status == "WARNING":
            return self._check(
                "btc_paper_candidate_journal_dry_run",
                "WARNING",
                "INFO",
                "BTC paper candidate journal dry-run config has warnings.",
                details,
            )
        return self._check(
            "btc_paper_candidate_journal_dry_run",
            "FAIL",
            "REQUIRED",
            "BTC paper candidate journal dry-run config failed safety validation.",
            details,
        )

    def _forward_test_readiness_check(self) -> BTCPaperReadinessCheck:
        config_path = self.repo_root / "configs" / "btc_forward_test_loop.json"
        if not config_path.exists():
            return self._check(
                "btc_forward_test_loop_dry_run",
                "WARNING",
                "INFO",
                "BTC forward test loop dry-run config is not present yet.",
                {"forward_test_config": str(config_path)},
            )
        report = self.forward_test_engine.validate(str(config_path))
        details = {
            "forward_test_config": str(config_path),
            "validation_status": report.status,
            "issue_count": report.issue_count,
            "warning_count": report.warning_count,
            "fail_count": report.fail_count,
            "issues": [issue.to_dict() for issue in report.issues],
            "diagnostics": dict(report.diagnostics),
        }
        if report.status == "PASS":
            return self._check(
                "btc_forward_test_loop_dry_run",
                "PASS",
                "INFO",
                "BTC forward test loop dry-run config is present and safe.",
                details,
            )
        if report.status == "WARNING":
            return self._check(
                "btc_forward_test_loop_dry_run",
                "WARNING",
                "INFO",
                "BTC forward test loop dry-run config has warnings.",
                details,
            )
        return self._check(
            "btc_forward_test_loop_dry_run",
            "FAIL",
            "REQUIRED",
            "BTC forward test loop dry-run config failed safety validation.",
            details,
        )

    def _live_market_feed_readiness_check(self) -> BTCPaperReadinessCheck:
        config_path = self.repo_root / "configs" / "btc_live_market_feed.json"
        if not config_path.exists():
            return self._check(
                "btc_live_market_read_only_feed_dry_run",
                "WARNING",
                "INFO",
                "BTC live market read-only feed dry-run config is not present yet.",
                {"live_market_feed_config": str(config_path)},
            )
        report = self.live_market_feed_engine.validate(str(config_path))
        details = {
            "live_market_feed_config": str(config_path),
            "validation_status": report.status,
            "issue_count": report.issue_count,
            "warning_count": report.warning_count,
            "fail_count": report.fail_count,
            "issues": [issue.to_dict() for issue in report.issues],
            "diagnostics": dict(report.diagnostics),
        }
        if report.status == "PASS":
            return self._check(
                "btc_live_market_read_only_feed_dry_run",
                "PASS",
                "INFO",
                "BTC live market read-only feed dry-run config is present and safe.",
                details,
            )
        if report.status == "WARNING":
            return self._check(
                "btc_live_market_read_only_feed_dry_run",
                "WARNING",
                "INFO",
                "BTC live market read-only feed dry-run config has warnings.",
                details,
            )
        return self._check(
            "btc_live_market_read_only_feed_dry_run",
            "FAIL",
            "REQUIRED",
            "BTC live market read-only feed dry-run config failed safety validation.",
            details,
        )

    def _paper_account_readiness_check(self) -> BTCPaperReadinessCheck:
        config_path = self.repo_root / "configs" / "btc_paper_account.json"
        if not config_path.exists():
            return self._check(
                "btc_local_paper_account_simulation",
                "WARNING",
                "INFO",
                "BTC local paper account simulation config is not present yet.",
                {"paper_account_config": str(config_path)},
            )
        report = self.paper_account_engine.validate(str(config_path))
        details = {
            "paper_account_config": str(config_path),
            "validation_status": report.status,
            "issue_count": report.issue_count,
            "warning_count": report.warning_count,
            "fail_count": report.fail_count,
            "issues": [issue.to_dict() for issue in report.issues],
            "diagnostics": dict(report.diagnostics),
        }
        if report.status == "PASS":
            return self._check(
                "btc_local_paper_account_simulation",
                "PASS",
                "INFO",
                "BTC local paper account simulation config is present and safe.",
                details,
            )
        if report.status == "WARNING":
            return self._check(
                "btc_local_paper_account_simulation",
                "WARNING",
                "INFO",
                "BTC local paper account simulation config has warnings.",
                details,
            )
        return self._check(
            "btc_local_paper_account_simulation",
            "FAIL",
            "REQUIRED",
            "BTC local paper account simulation config failed safety validation.",
            details,
        )

    def _futures_read_only_feed_readiness_check(self) -> BTCPaperReadinessCheck:
        config_path = self.repo_root / "configs" / "btc_futures_read_only_feed.json"
        if not config_path.exists():
            return self._check(
                "btc_futures_read_only_market_feed",
                "WARNING",
                "INFO",
                "BTC futures read-only market feed config is not present yet.",
                {"futures_read_only_feed_config": str(config_path)},
            )
        report = self.futures_read_only_feed_engine.validate(str(config_path))
        details = {
            "futures_read_only_feed_config": str(config_path),
            "validation_status": report.status,
            "issue_count": report.issue_count,
            "warning_count": report.warning_count,
            "fail_count": report.fail_count,
            "issues": [issue.to_dict() for issue in report.issues],
        }
        if report.status == "PASS":
            return self._check(
                "btc_futures_read_only_market_feed",
                "PASS",
                "INFO",
                "BTC futures read-only market feed config is present and safe.",
                details,
            )
        if report.status == "WARNING":
            return self._check(
                "btc_futures_read_only_market_feed",
                "WARNING",
                "INFO",
                "BTC futures read-only market feed config has warnings.",
                details,
            )
        return self._check(
            "btc_futures_read_only_market_feed",
            "FAIL",
            "REQUIRED",
            "BTC futures read-only market feed config failed safety validation.",
            details,
        )

    def _futures_risk_model_readiness_check(self) -> BTCPaperReadinessCheck:
        config_path = self.repo_root / "configs" / "btc_futures_risk_model.json"
        if not config_path.exists():
            return self._check(
                "btc_futures_leverage_liquidation_risk_model",
                "WARNING",
                "INFO",
                "BTC futures leverage/liquidation risk model config is not present yet.",
                {"futures_risk_model_config": str(config_path)},
            )
        report = self.futures_risk_model_engine.validate(str(config_path))
        details = {
            "futures_risk_model_config": str(config_path),
            "validation_status": report.status,
            "issue_count": report.issue_count,
            "warning_count": report.warning_count,
            "fail_count": report.fail_count,
            "issues": [issue.to_dict() for issue in report.issues],
        }
        if report.status == "PASS":
            return self._check(
                "btc_futures_leverage_liquidation_risk_model",
                "PASS",
                "INFO",
                "BTC futures leverage/liquidation risk model config is present and safe.",
                details,
            )
        if report.status == "WARNING":
            return self._check(
                "btc_futures_leverage_liquidation_risk_model",
                "WARNING",
                "INFO",
                "BTC futures leverage/liquidation risk model config has warnings.",
                details,
            )
        return self._check(
            "btc_futures_leverage_liquidation_risk_model",
            "FAIL",
            "REQUIRED",
            "BTC futures leverage/liquidation risk model config failed safety validation.",
            details,
        )

    def _futures_paper_position_readiness_check(self) -> BTCPaperReadinessCheck:
        config_path = self.repo_root / "configs" / "btc_futures_paper_position.json"
        if not config_path.exists():
            return self._check(
                "btc_futures_local_paper_position_simulation",
                "WARNING",
                "INFO",
                "BTC futures local paper position simulation config is not present yet.",
                {"futures_paper_position_config": str(config_path)},
            )
        report = self.futures_paper_position_engine.validate(str(config_path))
        details = {
            "futures_paper_position_config": str(config_path),
            "validation_status": report.status,
            "issue_count": report.issue_count,
            "warning_count": report.warning_count,
            "fail_count": report.fail_count,
            "issues": [issue.to_dict() for issue in report.issues],
        }
        if report.status == "PASS":
            return self._check(
                "btc_futures_local_paper_position_simulation",
                "PASS",
                "INFO",
                "BTC futures local paper position simulation config is present and safe.",
                details,
            )
        if report.status == "WARNING":
            return self._check(
                "btc_futures_local_paper_position_simulation",
                "WARNING",
                "INFO",
                "BTC futures local paper position simulation config has warnings.",
                details,
            )
        return self._check(
            "btc_futures_local_paper_position_simulation",
            "FAIL",
            "REQUIRED",
            "BTC futures local paper position simulation config failed safety validation.",
            details,
        )

    def _binance_futures_testnet_adapter_readiness_check(self) -> BTCPaperReadinessCheck:
        config_path = self.repo_root / "configs" / "binance_futures_testnet_adapter.json"
        if not config_path.exists():
            return self._check(
                "binance_futures_testnet_adapter_disabled",
                "WARNING",
                "INFO",
                "Binance futures testnet adapter config is not present yet.",
                {"binance_futures_testnet_adapter_config": str(config_path)},
            )
        report = self.binance_futures_testnet_adapter_engine.validate(str(config_path))
        details = {
            "binance_futures_testnet_adapter_config": str(config_path),
            "validation_status": report.status,
            "issue_count": report.issue_count,
            "warning_count": report.warning_count,
            "fail_count": report.fail_count,
            "issues": [issue.to_dict() for issue in report.issues],
        }
        if report.status == "PASS":
            return self._check(
                "binance_futures_testnet_adapter_disabled",
                "PASS",
                "INFO",
                "Binance futures testnet adapter config is present, disabled, and safe.",
                details,
            )
        if report.status == "WARNING":
            return self._check(
                "binance_futures_testnet_adapter_disabled",
                "WARNING",
                "INFO",
                "Binance futures testnet adapter config has warnings.",
                details,
            )
        return self._check(
            "binance_futures_testnet_adapter_disabled",
            "FAIL",
            "REQUIRED",
            "Binance futures testnet adapter config failed safety validation.",
            details,
        )

    def _binance_futures_testnet_read_only_readiness_check(self) -> BTCPaperReadinessCheck:
        config_path = self.repo_root / "configs" / "binance_futures_testnet_read_only.json"
        if not config_path.exists():
            return self._check(
                "binance_futures_testnet_authenticated_read_only",
                "WARNING",
                "INFO",
                "Binance futures testnet authenticated read-only config is not present yet.",
                {"binance_futures_testnet_read_only_config": str(config_path)},
            )
        report = self.binance_futures_testnet_read_only_engine.validate(str(config_path))
        details = {
            "binance_futures_testnet_read_only_config": str(config_path),
            "validation_status": report.status,
            "issue_count": report.issue_count,
            "warning_count": report.warning_count,
            "fail_count": report.fail_count,
            "issues": [issue.to_dict() for issue in report.issues],
        }
        if report.status == "PASS":
            return self._check(
                "binance_futures_testnet_authenticated_read_only",
                "PASS",
                "INFO",
                "Binance futures testnet authenticated read-only config is present, explicit-only, and safe.",
                details,
            )
        if report.status == "WARNING":
            return self._check(
                "binance_futures_testnet_authenticated_read_only",
                "WARNING",
                "INFO",
                "Binance futures testnet authenticated read-only config has warnings.",
                details,
            )
        return self._check(
            "binance_futures_testnet_authenticated_read_only",
            "FAIL",
            "REQUIRED",
            "Binance futures testnet authenticated read-only config failed safety validation.",
            details,
        )

    def _binance_futures_testnet_order_test_readiness_check(self) -> BTCPaperReadinessCheck:
        config_path = self.repo_root / "configs" / "binance_futures_testnet_order_test.json"
        if not config_path.exists():
            return self._check(
                "binance_futures_testnet_order_test_preflight",
                "WARNING",
                "INFO",
                "Binance futures testnet Test Order preflight config is not present yet.",
                {"binance_futures_testnet_order_test_config": str(config_path)},
            )
        report = self.binance_futures_testnet_order_test_engine.validate(str(config_path))
        details = {
            "binance_futures_testnet_order_test_config": str(config_path),
            "validation_status": report.status,
            "issue_count": report.issue_count,
            "warning_count": report.warning_count,
            "fail_count": report.fail_count,
            "issues": [issue.to_dict() for issue in report.issues],
            "diagnostics": dict(report.diagnostics),
        }
        if report.status == "PASS":
            return self._check(
                "binance_futures_testnet_order_test_preflight",
                "PASS",
                "INFO",
                "Binance futures testnet Test Order preflight config is present, explicit-only, and safe.",
                details,
            )
        if report.status == "WARNING":
            return self._check(
                "binance_futures_testnet_order_test_preflight",
                "WARNING",
                "INFO",
                "Binance futures testnet Test Order preflight config has warnings.",
                details,
            )
        return self._check(
            "binance_futures_testnet_order_test_preflight",
            "FAIL",
            "REQUIRED",
            "Binance futures testnet Test Order preflight config failed safety validation.",
            details,
        )

    def _binance_futures_testnet_order_lifecycle_readiness_check(self) -> BTCPaperReadinessCheck:
        config_path = self.repo_root / "configs" / "binance_futures_testnet_order_lifecycle.json"
        if not config_path.exists():
            return self._check(
                "binance_futures_testnet_manual_post_only_lifecycle",
                "WARNING",
                "INFO",
                "Binance futures testnet manual post-only lifecycle config is not present yet.",
                {"binance_futures_testnet_order_lifecycle_config": str(config_path)},
            )
        report = self.binance_futures_testnet_order_lifecycle_engine.validate(str(config_path))
        details = {
            "binance_futures_testnet_order_lifecycle_config": str(config_path),
            "validation_status": report.status,
            "issue_count": report.issue_count,
            "warning_count": report.warning_count,
            "fail_count": report.fail_count,
            "issues": [issue.to_dict() for issue in report.issues],
            "diagnostics": dict(report.diagnostics),
        }
        if report.status == "PASS":
            return self._check(
                "binance_futures_testnet_manual_post_only_lifecycle",
                "PASS",
                "INFO",
                "Binance futures testnet manual post-only lifecycle config is present, explicit-only, disabled by default, and safe.",
                details,
            )
        if report.status == "WARNING":
            return self._check(
                "binance_futures_testnet_manual_post_only_lifecycle",
                "WARNING",
                "INFO",
                "Binance futures testnet manual post-only lifecycle config has warnings.",
                details,
            )
        return self._check(
            "binance_futures_testnet_manual_post_only_lifecycle",
            "FAIL",
            "REQUIRED",
            "Binance futures testnet manual post-only lifecycle config failed safety validation.",
            details,
        )

    def _binance_futures_testnet_protective_orders_readiness_check(self) -> BTCPaperReadinessCheck:
        config_path = self.repo_root / "configs" / "binance_futures_testnet_protective_orders.json"
        if not config_path.exists():
            return self._check(
                "binance_futures_testnet_protective_sl_tp",
                "WARNING",
                "INFO",
                "Binance futures testnet protective SL/TP config is not present yet.",
                {"binance_futures_testnet_protective_orders_config": str(config_path)},
            )
        report = self.binance_futures_testnet_protective_orders_engine.validate(str(config_path))
        config = report.config
        safe_flags = bool(
            config
            and config.feature_enabled is False
            and config.explicit_cli_only
            and config.testnet_only
            and not config.allow_position_entry
            and not config.allow_position_close
            and not config.allow_production_endpoint
        )
        details = {
            "binance_futures_testnet_protective_orders_config": str(config_path),
            "validation_status": report.status,
            "issue_count": report.issue_count,
            "warning_count": report.warning_count,
            "fail_count": report.fail_count,
            "safe_flags": safe_flags,
            "issues": [issue.to_dict() for issue in report.issues],
            "diagnostics": dict(report.diagnostics),
        }
        if report.status == "PASS" and safe_flags:
            return self._check(
                "binance_futures_testnet_protective_sl_tp",
                "PASS",
                "INFO",
                "Binance futures testnet protective SL/TP config is present, disabled by default, explicit-only, testnet-only, and non-position-mutating.",
                details,
            )
        return self._check(
            "binance_futures_testnet_protective_sl_tp",
            "FAIL",
            "REQUIRED",
            "Binance futures testnet protective SL/TP config failed safety validation.",
            details,
        )

    def _cache_diagnostics_check(self, snapshot: dict[str, Any] | None) -> BTCPaperReadinessCheck:
        if snapshot is None:
            return self._check("cache_diagnostics", "SKIPPED", "INFO", "Cache diagnostics unavailable because baseline snapshot is unavailable.")
        rows = ((snapshot.get("multi_sample_result") or {}).get("rows") or [])
        cache_states = [row.get("cache_status") for row in rows if isinstance(row, dict) and row.get("cache_status")]
        return self._check("cache_diagnostics", "PASS" if cache_states else "SKIPPED", "INFO", "Cache diagnostics are informational only.", {"cache_statuses": cache_states})

    def _gate_check(self, use_cache: bool, cache_dir: str) -> BTCPaperReadinessCheck:
        try:
            code = self._run_gate(use_cache=use_cache, cache_dir=cache_dir)
        except Exception as exc:
            return self._check("official_validation_gate", "FAIL", "REQUIRED", f"Official BTC validation gate errored: {exc}")
        if code == 0:
            return self._check("official_validation_gate", "PASS", "REQUIRED", "Official BTC validation gate passed.", {"return_code": code})
        return self._check("official_validation_gate", "FAIL", "REQUIRED", "Official BTC validation gate failed.", {"return_code": code})

    def _run_gate(self, use_cache: bool, cache_dir: str) -> int:
        if self.gate_runner is not None:
            return int(self.gate_runner(use_cache=use_cache, cache_dir=cache_dir))
        from scripts.run_validation_gate import main as gate_main

        argv = ["--preset", "full", "--sample-scope", "required_full"]
        if use_cache:
            argv.extend(["--use-cache", "--cache-dir", cache_dir])
        return int(gate_main(argv))

    def _flag_enabled(self, name: str) -> bool:
        return str(self.env.get(name, "")).strip().lower() in ("1", "true", "yes", "on", "enabled")

    def _report(self, checks: list[BTCPaperReadinessCheck], expected_profile: str) -> BTCPaperReadinessReport:
        passed = sum(1 for check in checks if check.status == "PASS")
        warnings = sum(1 for check in checks if check.status == "WARNING")
        failed = sum(1 for check in checks if check.status == "FAIL")
        skipped = sum(1 for check in checks if check.status == "SKIPPED")
        readiness_status = self._readiness_status(checks)
        return BTCPaperReadinessReport(
            created_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
            project_scope="BTC_ONLY",
            recommended_profile=expected_profile,
            readiness_status=readiness_status,
            passed_checks=passed,
            warning_checks=warnings,
            failed_checks=failed,
            skipped_checks=skipped,
            checks=checks,
            next_actions=self._next_actions(checks, readiness_status),
        )

    def _readiness_status(self, checks: list[BTCPaperReadinessCheck]) -> str:
        if any(check.severity == "REQUIRED" and check.status == "FAIL" for check in checks):
            return "BLOCKED"
        if any(check.status == "WARNING" and check.severity in ("REQUIRED", "RECOMMENDED") for check in checks):
            return "WARNING"
        return "READY"

    def _next_actions(self, checks: list[BTCPaperReadinessCheck], readiness_status: str) -> list[str]:
        actions: list[str] = []
        for check in checks:
            if check.status in ("FAIL", "WARNING") and check.message not in actions:
                actions.append(check.message)
        if readiness_status != "READY":
            actions.append("Resolve blocking/warning readiness checks before starting BTC paper trading preparation.")
        else:
            actions.append("Proceed to BTC paper trading preparation with execution still disabled.")
        return actions

    def _check(
        self,
        name: str,
        status: str,
        severity: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> BTCPaperReadinessCheck:
        return BTCPaperReadinessCheck(
            name=name,
            status=status,
            severity=severity,
            message=message,
            details=details or {},
        )
