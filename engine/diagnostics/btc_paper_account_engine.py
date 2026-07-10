from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.diagnostics.btc_forward_test_loop_engine import BTCForwardTestLoopEngine
from engine.diagnostics.btc_live_market_feed_engine import BTCLiveMarketFeedEngine
from engine.diagnostics.btc_paper_candidate_journal_engine import BTCPaperCandidateJournalEngine
from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine
from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from engine.diagnostics.btc_paper_signal_evaluation_engine import BTCPaperSignalEvaluationEngine
from engine.diagnostics.btc_paper_trade_candidate_engine import BTCPaperTradeCandidateEngine
from models.btc_paper_account import (
    BTCPaperAccountAction,
    BTCPaperAccountActionResult,
    BTCPaperAccountConfig,
    BTCPaperAccountDecision,
    BTCPaperAccountIssue,
    BTCPaperAccountLedgerEntry,
    BTCPaperAccountLedgerSummary,
    BTCPaperAccountState,
    BTCPaperAccountStatus,
    BTCPaperAccountValidationReport,
    BTCPaperAccountVirtualOrder,
    BTCPaperAccountVirtualPosition,
)


class BTCPaperAccountEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        runtime_config_engine: BTCPaperRuntimeConfigEngine | None = None,
        monitoring_engine: BTCPaperMonitoringEngine | None = None,
        runner_engine: BTCPaperRunnerEngine | None = None,
        signal_engine: BTCPaperSignalEvaluationEngine | None = None,
        trade_candidate_engine: BTCPaperTradeCandidateEngine | None = None,
        candidate_journal_engine: BTCPaperCandidateJournalEngine | None = None,
        forward_test_engine: BTCForwardTestLoopEngine | None = None,
        live_market_feed_engine: BTCLiveMarketFeedEngine | None = None,
        now_provider=None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.runtime_config_engine = runtime_config_engine or BTCPaperRuntimeConfigEngine(repo_root=self.repo_root)
        self.monitoring_engine = monitoring_engine or BTCPaperMonitoringEngine(repo_root=self.repo_root)
        self.runner_engine = runner_engine or BTCPaperRunnerEngine(repo_root=self.repo_root)
        self.signal_engine = signal_engine or BTCPaperSignalEvaluationEngine(repo_root=self.repo_root)
        self.trade_candidate_engine = trade_candidate_engine or BTCPaperTradeCandidateEngine(repo_root=self.repo_root)
        self.candidate_journal_engine = candidate_journal_engine or BTCPaperCandidateJournalEngine(repo_root=self.repo_root)
        self.forward_test_engine = forward_test_engine or BTCForwardTestLoopEngine(repo_root=self.repo_root)
        self.live_market_feed_engine = live_market_feed_engine or BTCLiveMarketFeedEngine(repo_root=self.repo_root)
        self.now_provider = now_provider

    def validate(self, config_path: str = "configs/btc_paper_account.json", expected_profile: str = "balanced_smc_decision_065") -> BTCPaperAccountValidationReport:
        issues: list[BTCPaperAccountIssue] = []
        diagnostics: dict[str, Any] = {
            "runtime_config_status": "UNKNOWN",
            "monitoring_config_status": "UNKNOWN",
            "runner_config_status": "UNKNOWN",
            "signal_config_status": "UNKNOWN",
            "trade_candidate_config_status": "UNKNOWN",
            "candidate_journal_config_status": "UNKNOWN",
            "forward_test_config_status": "UNKNOWN",
            "live_market_feed_config_status": "UNKNOWN",
            "kill_switch_enabled": None,
        }
        config: BTCPaperAccountConfig | None = None
        try:
            config = self.load_config(config_path)
        except Exception as exc:
            issues.append(self._issue("config_invalid", "FAIL", f"BTC paper account config could not be loaded: {exc}", {"config_path": config_path}))
            return self._report(config_path, config, issues, diagnostics)
        self._validate_config_values(config, expected_profile, issues, diagnostics)
        return self._report(config_path, config, issues, diagnostics)

    def status(self, config_path: str = "configs/btc_paper_account.json", expected_profile: str = "balanced_smc_decision_065") -> BTCPaperAccountActionResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BTCPaperAccountConfig()
        issues = list(report.issues)
        state = self._load_state(config)
        if report.status == "FAIL":
            return self._result(config, "STATUS", "FAIL", BTCPaperAccountDecision.ACTION_FAILED.value, report.status, state, None, "Paper account config failed safety validation.", issues)
        if state is None:
            issues.append(self._issue("state_missing", "WARNING", "Paper account state file does not exist yet.", {"state_path": str(self._resolve(config.state_path))}))
            return self._result(config, "STATUS", "WARNING", BTCPaperAccountDecision.STATE_MISSING.value, report.status, None, None, "Paper account state is missing.", issues)
        return self._result(config, "STATUS", "PASS", BTCPaperAccountDecision.ACCOUNT_READY.value, report.status, state, None, "Paper account state loaded.", issues)

    def initialize(self, config_path: str = "configs/btc_paper_account.json", expected_profile: str = "balanced_smc_decision_065", force: bool = False) -> BTCPaperAccountActionResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BTCPaperAccountConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, "INITIALIZE", "FAIL", BTCPaperAccountDecision.ACTION_FAILED.value, report.status, None, None, "Paper account config failed safety validation.", issues)
        state_path = self._resolve(config.state_path)
        ledger_path = self._resolve(config.ledger_path)
        if state_path.exists() and not force:
            state = self._load_state(config)
            issues.append(self._issue("state_exists", "WARNING", "Paper account state already exists; use --force to reinitialize.", {"state_path": str(state_path)}))
            return self._result(config, "INITIALIZE", "WARNING", BTCPaperAccountDecision.ACCOUNT_READY.value, report.status, state, None, "Paper account state already exists.", issues)
        state = self._new_state(config)
        ledger = self._ledger_entry(config, "ACCOUNT_INITIALIZED", BTCPaperAccountDecision.ACCOUNT_INITIALIZED.value, state, state, "Local paper account initialized.")
        self._write_state(config, state)
        self._append_ledger(config, ledger, reset=force)
        return self._result(config, "INITIALIZE", "PASS", BTCPaperAccountDecision.ACCOUNT_INITIALIZED.value, report.status, state, ledger, "Local paper account initialized.", issues)

    def reset(self, config_path: str = "configs/btc_paper_account.json", expected_profile: str = "balanced_smc_decision_065", force: bool = False) -> BTCPaperAccountActionResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BTCPaperAccountConfig()
        issues = list(report.issues)
        if not force:
            issues.append(self._issue("force_required", "WARNING", "Reset requires --force; no files were changed."))
            return self._result(config, "RESET", "WARNING", BTCPaperAccountDecision.ACTION_FAILED.value, report.status, self._load_state(config), None, "Reset skipped because --force was not supplied.", issues)
        for path_text in (config.state_path, config.ledger_path):
            path = self._resolve(path_text)
            if self._safe_paper_account_path(path):
                path.unlink(missing_ok=True)
        state = self._new_state(config)
        ledger = self._ledger_entry(config, "ACCOUNT_INITIALIZED", BTCPaperAccountDecision.ACCOUNT_INITIALIZED.value, state, state, "Local paper account reset and initialized.")
        self._write_state(config, state)
        self._append_ledger(config, ledger, reset=True)
        return self._result(config, "RESET", "PASS", BTCPaperAccountDecision.ACCOUNT_INITIALIZED.value, report.status, state, ledger, "Local paper account reset.", issues)

    def simulate_live_observation(
        self,
        config_path: str = "configs/btc_paper_account.json",
        expected_profile: str = "balanced_smc_decision_065",
        initialize_if_missing: bool = False,
        no_ledger: bool = False,
    ) -> BTCPaperAccountActionResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BTCPaperAccountConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, "SIMULATE_LIVE_OBSERVATION", "FAIL", BTCPaperAccountDecision.ACTION_FAILED.value, report.status, None, None, "Paper account config failed safety validation.", issues)
        state = self._load_state(config)
        if state is None and initialize_if_missing:
            state = self._new_state(config)
            self._write_state(config, state)
            if not no_ledger:
                self._append_ledger(config, self._ledger_entry(config, "ACCOUNT_INITIALIZED", BTCPaperAccountDecision.ACCOUNT_INITIALIZED.value, state, state, "Local paper account initialized before simulation."))
        if state is None:
            issues.append(self._issue("state_missing", "WARNING", "Paper account state is missing; use --initialize-if-missing."))
            return self._result(config, "SIMULATE_LIVE_OBSERVATION", "WARNING", BTCPaperAccountDecision.STATE_MISSING.value, report.status, None, None, "Paper account state is missing.", issues)
        observation = self.live_market_feed_engine.observe_once(config.live_market_feed_config_path, expected_profile=expected_profile, journal=False)
        if observation.status == "FAIL":
            issues.extend(self._from_live_issues(getattr(observation, "issues", [])))
            return self._result(config, "SIMULATE_LIVE_OBSERVATION", "FAIL", BTCPaperAccountDecision.ACTION_FAILED.value, report.status, state, None, "Live market read-only observation failed safely.", issues, metadata={"observation": observation.to_dict()})
        before = self._copy_state(state)
        if not getattr(observation, "candidate_created", False):
            state.total_no_action_events += 1
            state.updated_at = self._now()
            ledger = self._ledger_entry(config, "NO_ACTION", BTCPaperAccountDecision.NO_ACTION_SIGNAL_NOT_APPROVED.value, before, state, observation.reason, metadata={"observation": observation.to_dict()})
            self._write_state(config, state)
            if not no_ledger:
                self._append_ledger(config, ledger)
            return self._result(config, "SIMULATE_LIVE_OBSERVATION", "WARNING", BTCPaperAccountDecision.NO_ACTION_SIGNAL_NOT_APPROVED.value, report.status, state, ledger, observation.reason, issues, no_action_recorded=True, metadata={"observation": observation.to_dict()})
        candidate = self._candidate_from_observation(observation)
        rejection = self._risk_rejection(config, state, candidate)
        if rejection:
            state.total_risk_rejections += 1
            state.updated_at = self._now()
            ledger = self._ledger_entry(config, "RISK_REJECTION", rejection[0], before, state, rejection[1], metadata={"observation": observation.to_dict(), "candidate": candidate})
            self._write_state(config, state)
            if not no_ledger:
                self._append_ledger(config, ledger)
            issues.append(self._issue("virtual_trade_rejected", "WARNING", rejection[1], {"decision": rejection[0]}))
            return self._result(config, "SIMULATE_LIVE_OBSERVATION", "WARNING", rejection[0], report.status, state, ledger, rejection[1], issues, metadata={"observation": observation.to_dict()})
        order, position = self._create_virtual_order_position(config, state, candidate)
        state.filled_orders.append(order)
        state.open_positions.append(position)
        state.total_virtual_orders += 1
        state.total_virtual_positions_opened += 1
        state.total_fees = self._round(state.total_fees + order.fee_estimate)
        state.total_slippage = self._round(state.total_slippage + order.slippage_estimate)
        state.cash_balance = self._round(state.cash_balance - order.fee_estimate - order.slippage_estimate)
        state.equity = self._round(state.cash_balance + state.unrealized_pnl)
        state.updated_at = self._now()
        ledger = self._ledger_entry(config, "VIRTUAL_POSITION_OPEN", BTCPaperAccountDecision.VIRTUAL_POSITION_OPENED.value, before, state, "Local virtual order and position opened.", order.order_id, position.position_id, {"observation": observation.to_dict(), "candidate": candidate})
        self._write_state(config, state)
        if not no_ledger:
            self._append_ledger(config, ledger)
        return self._result(config, "SIMULATE_LIVE_OBSERVATION", "PASS", BTCPaperAccountDecision.VIRTUAL_POSITION_OPENED.value, report.status, state, ledger, "Local virtual order and position opened.", issues, virtual_order_created=True, virtual_position_created=True, metadata={"observation": observation.to_dict()})

    def mark_to_market(self, config_path: str = "configs/btc_paper_account.json", expected_profile: str = "balanced_smc_decision_065", no_ledger: bool = False) -> BTCPaperAccountActionResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BTCPaperAccountConfig()
        issues = list(report.issues)
        state = self._load_state(config)
        if report.status == "FAIL":
            return self._result(config, "MARK_TO_MARKET", "FAIL", BTCPaperAccountDecision.ACTION_FAILED.value, report.status, state, None, "Paper account config failed safety validation.", issues)
        if state is None:
            issues.append(self._issue("state_missing", "WARNING", "Paper account state is missing."))
            return self._result(config, "MARK_TO_MARKET", "WARNING", BTCPaperAccountDecision.STATE_MISSING.value, report.status, None, None, "Paper account state is missing.", issues)
        if not state.open_positions:
            return self._result(config, "MARK_TO_MARKET", "WARNING", BTCPaperAccountDecision.ACCOUNT_READY.value, report.status, state, None, "No open virtual positions to mark.", issues)
        feed = self.live_market_feed_engine.fetch_once(config.live_market_feed_config_path, expected_profile=expected_profile)
        if feed.status == "FAIL" or feed.primary_latest_close is None:
            issues.extend(self._from_live_issues(getattr(feed, "issues", [])))
            return self._result(config, "MARK_TO_MARKET", "FAIL", BTCPaperAccountDecision.ACTION_FAILED.value, report.status, state, None, "Public mark price fetch failed safely.", issues)
        before = self._copy_state(state)
        mark = float(feed.primary_latest_close)
        total_unrealized = 0.0
        for position in state.open_positions:
            direction = 1 if position.side.upper() == "LONG" else -1
            position.mark_price = self._round(mark)
            position.unrealized_pnl = self._round((mark - position.entry_price) * position.quantity * direction)
            position.notional_value = self._round(mark * position.quantity)
            position.updated_at = self._now()
            total_unrealized += position.unrealized_pnl
        state.unrealized_pnl = self._round(total_unrealized)
        state.equity = self._round(state.cash_balance + state.unrealized_pnl)
        state.last_mark_price = self._round(mark)
        state.last_mark_at = self._now()
        state.updated_at = self._now()
        ledger = self._ledger_entry(config, "MARK_TO_MARKET", BTCPaperAccountDecision.MARK_TO_MARKET_UPDATED.value, before, state, "Virtual positions marked to public read-only latest close.", metadata={"feed": feed.to_dict()})
        self._write_state(config, state)
        if not no_ledger:
            self._append_ledger(config, ledger)
        return self._result(config, "MARK_TO_MARKET", "PASS", BTCPaperAccountDecision.MARK_TO_MARKET_UPDATED.value, report.status, state, ledger, "Virtual positions marked to market.", issues, mark_to_market_updated=True)

    def ledger_summary(self, config_path: str = "configs/btc_paper_account.json", expected_profile: str = "balanced_smc_decision_065", max_entries: int = 20) -> BTCPaperAccountLedgerSummary:
        report = self.validate(config_path, expected_profile)
        config = report.config or BTCPaperAccountConfig()
        issues = list(report.issues)
        path = self._resolve(config.ledger_path)
        if not path.exists():
            issues.append(self._issue("ledger_missing", "WARNING", "Paper account ledger does not exist yet.", {"ledger_path": str(path)}))
            return self._ledger_summary(path, [], issues)
        entries: list[BTCPaperAccountLedgerEntry] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                entries.append(BTCPaperAccountLedgerEntry(**{**json.loads(line)}))
            except Exception as exc:
                issues.append(self._issue("ledger_line_invalid", "WARNING", "Invalid ledger line skipped.", {"line_number": line_number, "error": str(exc)}))
        return self._ledger_summary(path, entries[-max_entries:], issues)

    def load_config(self, config_path: str = "configs/btc_paper_account.json") -> BTCPaperAccountConfig:
        path = self._resolve(config_path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("config JSON must be an object")
        return BTCPaperAccountConfig(**{**BTCPaperAccountConfig().to_dict(), **loaded})

    def _validate_config_values(self, config: BTCPaperAccountConfig, expected_profile: str, issues: list[BTCPaperAccountIssue], diagnostics: dict[str, Any]) -> None:
        self._expect(config.project_scope == "BTC_ONLY", issues, "project_scope", "project_scope must be BTC_ONLY.")
        self._expect(config.symbol == "BTC/USDT", issues, "symbol", "symbol must be BTC/USDT.", {"symbol": config.symbol})
        self._expect(config.quote_currency == "USDT", issues, "quote_currency", "quote_currency must be USDT.")
        self._expect(config.strategy_profile == expected_profile, issues, "strategy_profile", f"strategy_profile must be {expected_profile}.", {"strategy_profile": config.strategy_profile})
        self._expect(config.paper_account_enabled in (True, False), issues, "paper_account_enabled", "paper_account_enabled must be boolean.")
        self._expect(config.simulation_only, issues, "simulation_only", "simulation_only must be true.")
        self._expect(config.dry_run_only, issues, "dry_run_only", "dry_run_only must be true.")
        self._expect(float(config.initial_balance) > 0, issues, "initial_balance", "initial_balance must be positive.")
        self._expect(0 < float(config.risk_per_trade_pct) <= float(config.max_risk_per_trade_pct), issues, "risk_per_trade_pct", "risk_per_trade_pct must be > 0 and <= max_risk_per_trade_pct.")
        self._expect(config.require_stop_loss, issues, "require_stop_loss", "require_stop_loss must be true.")
        self._expect(config.require_take_profit, issues, "require_take_profit", "require_take_profit must be true.")
        self._expect(config.fill_model in ("virtual_next_close", "virtual_mark_price"), issues, "fill_model", "fill_model must be virtual_next_close or virtual_mark_price.")
        self._expect(0 <= float(config.slippage_rate) <= 0.01, issues, "slippage_rate", "slippage_rate must be between 0 and 0.01.")
        self._expect(0 <= float(config.fee_rate) <= 0.01, issues, "fee_rate", "fee_rate must be between 0 and 0.01.")
        for name in ("allow_local_paper_state_write", "allow_local_paper_ledger_write", "allow_virtual_order_creation", "allow_virtual_position_creation", "allow_virtual_pnl_calculation", "allow_public_market_data_fetch"):
            self._expect(bool(getattr(config, name)), issues, name, f"{name} must be true for local simulation.")
        for name in ("allow_private_api", "allow_api_key_usage", "allow_trading_api", "allow_account_data", "allow_balance_fetch", "allow_position_fetch", "allow_real_order_submission", "allow_order_cancellation", "allow_real_position_creation", "allow_exchange_connection_for_trading", "allow_executable_trade_creation", "allow_runner_state_mutation", "allow_execution_state_mutation"):
            self._expect(not bool(getattr(config, name)), issues, name, f"{name} must remain false.")
        self._validate_paper_account_path(config.state_path, "state_path", issues)
        self._validate_paper_account_path(config.ledger_path, "ledger_path", issues)
        self._validate_paper_account_path(config.report_export_dir, "report_export_dir", issues)
        self._validate_dependencies(config, expected_profile, issues, diagnostics)

    def _validate_dependencies(self, config: BTCPaperAccountConfig, expected_profile: str, issues: list[BTCPaperAccountIssue], diagnostics: dict[str, Any]) -> None:
        runtime = self.runtime_config_engine.validate(config.runtime_config_path, expected_profile=expected_profile)
        diagnostics["runtime_config_status"] = runtime.status
        runtime_config = runtime.config
        diagnostics["kill_switch_enabled"] = bool(getattr(runtime_config, "kill_switch_enabled", False))
        if config.require_runtime_config_pass and runtime.status != "PASS":
            issues.append(self._issue("runtime_config_validation", "FAIL", "Runtime config must validate PASS."))
        if runtime_config is not None:
            if config.require_kill_switch_enabled:
                self._expect(runtime_config.kill_switch_enabled, issues, "kill_switch_enabled", "kill_switch_enabled must remain true.")
            self._expect(float(config.max_risk_per_trade_pct) <= float(runtime_config.max_risk_per_trade_pct) * 100, issues, "max_risk_per_trade_pct_runtime", "max_risk_per_trade_pct must stay within runtime guardrail.")
            self._expect(float(config.max_daily_loss_pct) <= float(runtime_config.max_daily_loss_pct) * 100, issues, "max_daily_loss_pct_runtime", "max_daily_loss_pct must stay within runtime guardrail.")
            self._expect(float(config.max_drawdown_pct) <= float(runtime_config.max_total_drawdown_pct) * 100, issues, "max_drawdown_pct_runtime", "max_drawdown_pct must stay within runtime guardrail.")
            self._expect(int(config.max_open_virtual_positions) <= int(runtime_config.max_open_positions), issues, "max_open_virtual_positions_runtime", "max_open_virtual_positions must stay within runtime guardrail.")
            self._expect(int(config.max_virtual_trades_per_day) <= int(runtime_config.max_trades_per_day), issues, "max_virtual_trades_per_day_runtime", "max_virtual_trades_per_day must stay within runtime guardrail.")
            self._expect(float(config.min_risk_reward) >= max(float(runtime_config.min_risk_reward), 1.5), issues, "min_risk_reward_runtime", "min_risk_reward must be >= runtime min RR and 1.5.")
        monitoring = self.monitoring_engine.validate(config.monitoring_config_path, expected_profile=expected_profile)
        diagnostics["monitoring_config_status"] = monitoring.status
        if config.require_monitoring_config_pass and monitoring.status != "PASS":
            issues.append(self._issue("monitoring_config_validation", "FAIL", "Monitoring config must validate PASS."))
        _, runner_issues, _ = self.runner_engine.validate_config(config.runner_config_path, expected_profile=expected_profile)
        runner_fail_count = sum(1 for issue in runner_issues if issue.severity == "FAIL")
        diagnostics["runner_config_status"] = "FAIL" if runner_fail_count else "PASS"
        if config.require_runner_config_pass and runner_fail_count:
            issues.append(self._issue("runner_config_validation", "FAIL", "Runner config must validate PASS."))
        for name, engine, path, required in (
            ("signal_config_validation", self.signal_engine, config.signal_evaluation_config_path, config.require_signal_config_pass),
            ("trade_candidate_config_validation", self.trade_candidate_engine, config.trade_candidate_config_path, config.require_trade_candidate_config_pass),
            ("candidate_journal_config_validation", self.candidate_journal_engine, config.candidate_journal_config_path, config.require_candidate_journal_config_pass),
            ("forward_test_config_validation", self.forward_test_engine, config.forward_test_config_path, config.require_forward_test_config_pass),
            ("live_market_feed_config_validation", self.live_market_feed_engine, config.live_market_feed_config_path, config.require_live_market_feed_config_pass),
        ):
            report = engine.validate(path, expected_profile=expected_profile)
            diagnostics[name.replace("_validation", "_status")] = report.status
            if required and report.status != "PASS":
                issues.append(self._issue(name, "FAIL", f"{name} must validate PASS."))

    def _risk_rejection(self, config: BTCPaperAccountConfig, state: BTCPaperAccountState, candidate: dict[str, Any]) -> tuple[str, str] | None:
        if len(state.open_positions) >= int(config.max_open_virtual_positions):
            return BTCPaperAccountDecision.VIRTUAL_TRADE_REJECTED_LIMIT.value, "Maximum open virtual positions reached."
        if state.total_virtual_positions_opened >= int(config.max_virtual_trades_per_day):
            return BTCPaperAccountDecision.VIRTUAL_TRADE_REJECTED_LIMIT.value, "Maximum virtual trades per day reached."
        entry = self._float(candidate.get("entry_price"))
        stop = self._float(candidate.get("stop_loss"))
        take = self._float(candidate.get("take_profit"))
        side = str(candidate.get("direction") or candidate.get("side") or "").upper()
        if entry is None or entry <= 0 or stop is None or take is None or side not in ("LONG", "SHORT", "BULLISH", "BEARISH"):
            return BTCPaperAccountDecision.VIRTUAL_TRADE_REJECTED_RISK.value, "Candidate is missing valid entry, stop loss, take profit, or side."
        risk = abs(entry - stop)
        reward = abs(take - entry)
        if risk <= 0 or reward / risk < float(config.min_risk_reward):
            return BTCPaperAccountDecision.VIRTUAL_TRADE_REJECTED_RISK.value, "Candidate risk/reward is below local paper account minimum."
        return None

    def _create_virtual_order_position(self, config: BTCPaperAccountConfig, state: BTCPaperAccountState, candidate: dict[str, Any]) -> tuple[BTCPaperAccountVirtualOrder, BTCPaperAccountVirtualPosition]:
        entry = float(candidate["entry_price"])
        stop = float(candidate["stop_loss"])
        take = float(candidate["take_profit"])
        side = "LONG" if str(candidate.get("direction") or candidate.get("side")).upper() in ("LONG", "BULLISH", "BUY") else "SHORT"
        risk_amount = state.equity * (float(config.risk_per_trade_pct) / 100.0)
        quantity = risk_amount / abs(entry - stop)
        fee = quantity * entry * float(config.fee_rate)
        slippage = quantity * entry * float(config.slippage_rate)
        order_id = f"BTC-VORDER-{self._now()}"
        order = BTCPaperAccountVirtualOrder(order_id, self._now(), config.symbol, side, "MARKET", "FILLED", self._round(quantity), self._round(entry), self._round(stop), self._round(take), self._round(risk_amount), self._round(fee), self._round(slippage), "LOCAL_PAPER_ACCOUNT", str(candidate.get("candidate_id") or "live-observation"), dict(candidate))
        position = BTCPaperAccountVirtualPosition(f"BTC-VPOS-{self._now()}", self._now(), self._now(), config.symbol, side, "OPEN", self._round(quantity), self._round(entry), self._round(entry), self._round(stop), self._round(take), self._round(quantity * entry), self._round(risk_amount), 0.0, 0.0, self._round(fee), order_id, dict(candidate))
        return order, position

    def _candidate_from_observation(self, observation: Any) -> dict[str, Any]:
        metadata = getattr(observation, "metadata", {}) or {}
        candidate = metadata.get("candidate") or metadata.get("paper_candidate") or {}
        if candidate:
            return dict(candidate)
        latest_close = self._float(metadata.get("latest_close") or metadata.get("entry_price"))
        direction = metadata.get("direction_hint") or "BULLISH"
        if latest_close is None:
            return {}
        bullish = str(direction).upper() in ("BULLISH", "LONG", "BUY")
        stop = latest_close * (0.99 if bullish else 1.01)
        take = latest_close + abs(latest_close - stop) * 1.5 if bullish else latest_close - abs(latest_close - stop) * 1.5
        return {"candidate_id": "LIVE-OBSERVATION", "direction": "LONG" if bullish else "SHORT", "entry_price": latest_close, "stop_loss": stop, "take_profit": take}

    def _new_state(self, config: BTCPaperAccountConfig) -> BTCPaperAccountState:
        now = self._now()
        return BTCPaperAccountState(created_at=now, updated_at=now, project_scope=config.project_scope, symbol=config.symbol, quote_currency=config.quote_currency, strategy_profile=config.strategy_profile, initial_balance=self._round(config.initial_balance), cash_balance=self._round(config.initial_balance), equity=self._round(config.initial_balance))

    def _load_state(self, config: BTCPaperAccountConfig) -> BTCPaperAccountState | None:
        path = self._resolve(config.state_path)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["open_positions"] = [BTCPaperAccountVirtualPosition(**item) for item in payload.get("open_positions", [])]
        payload["closed_positions"] = [BTCPaperAccountVirtualPosition(**item) for item in payload.get("closed_positions", [])]
        payload["pending_orders"] = [BTCPaperAccountVirtualOrder(**item) for item in payload.get("pending_orders", [])]
        payload["filled_orders"] = [BTCPaperAccountVirtualOrder(**item) for item in payload.get("filled_orders", [])]
        return BTCPaperAccountState(**{**BTCPaperAccountState().to_dict(), **payload})

    def _write_state(self, config: BTCPaperAccountConfig, state: BTCPaperAccountState) -> None:
        path = self._resolve(config.state_path)
        if not self._safe_paper_account_path(path):
            raise ValueError("state_path must stay under reports/paper_account")
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
        temp_path.replace(path)

    def _append_ledger(self, config: BTCPaperAccountConfig, entry: BTCPaperAccountLedgerEntry, reset: bool = False) -> None:
        path = self._resolve(config.ledger_path)
        if not self._safe_paper_account_path(path):
            raise ValueError("ledger_path must stay under reports/paper_account")
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if reset else "a"
        with path.open(mode, encoding="utf-8") as handle:
            handle.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")

    def _ledger_entry(self, config: BTCPaperAccountConfig, entry_type: str, decision: str, before: BTCPaperAccountState, after: BTCPaperAccountState, reason: str, order_id: str | None = None, position_id: str | None = None, metadata: dict[str, Any] | None = None) -> BTCPaperAccountLedgerEntry:
        return BTCPaperAccountLedgerEntry(f"BTC-PAPER-LEDGER-{self._now()}", self._now(), entry_type, config.symbol, decision, before.cash_balance, after.cash_balance, before.equity, after.equity, self._round(after.realized_pnl - before.realized_pnl), self._round(after.unrealized_pnl - before.unrealized_pnl), order_id, position_id, reason, self._safety_summary(config), metadata or {})

    def _ledger_summary(self, path: Path, entries: list[BTCPaperAccountLedgerEntry], issues: list[BTCPaperAccountIssue]) -> BTCPaperAccountLedgerSummary:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        return BTCPaperAccountLedgerSummary(created_at=self._now(), ledger_path=str(path), status="FAIL" if failures else "WARNING" if warnings else "PASS", entries_read=len(entries), account_initialized=sum(1 for e in entries if e.entry_type == "ACCOUNT_INITIALIZED"), no_action=sum(1 for e in entries if e.entry_type == "NO_ACTION"), virtual_orders=sum(1 for e in entries if e.virtual_order_id), virtual_positions=sum(1 for e in entries if e.virtual_position_id), mark_to_market=sum(1 for e in entries if e.entry_type == "MARK_TO_MARKET"), risk_rejections=sum(1 for e in entries if e.entry_type == "RISK_REJECTION"), errors=sum(1 for e in entries if e.entry_type == "ERROR"), latest_entry_at=None if not entries else entries[-1].created_at, entries=entries, issues=issues)

    def _result(self, config: BTCPaperAccountConfig, action: str, status: str, decision: str, config_status: str, state: BTCPaperAccountState | None, ledger: BTCPaperAccountLedgerEntry | None, reason: str, issues: list[BTCPaperAccountIssue], virtual_order_created: bool = False, virtual_position_created: bool = False, no_action_recorded: bool = False, mark_to_market_updated: bool = False, metadata: dict[str, Any] | None = None) -> BTCPaperAccountActionResult:
        return BTCPaperAccountActionResult(created_at=self._now(), action=action, status=status, decision=decision, config_status=config_status, state_path=str(self._resolve(config.state_path)), ledger_path=str(self._resolve(config.ledger_path)), state_exists=self._resolve(config.state_path).exists(), account_state=state, ledger_entry=ledger, virtual_order_created=virtual_order_created, virtual_position_created=virtual_position_created, no_action_recorded=no_action_recorded, mark_to_market_updated=mark_to_market_updated, reason=reason, safety_summary=self._safety_summary(config), issues=issues, metadata=metadata or {})

    def _safety_summary(self, config: BTCPaperAccountConfig) -> dict[str, Any]:
        return {"simulation_only": True, "dry_run_only": True, "private_api_used": False, "api_key_used": False, "trading_api_used": False, "account_data_used": False, "balance_fetch_used": False, "position_fetch_used": False, "real_order_submitted": False, "order_cancelled": False, "real_position_created": False, "exchange_connected_for_trading": False, "executable_trade_created": False, "runner_state_mutated": False, "execution_state_mutated": False}

    def _report(self, config_path: str, config: BTCPaperAccountConfig | None, issues: list[BTCPaperAccountIssue], diagnostics: dict[str, Any]) -> BTCPaperAccountValidationReport:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        return BTCPaperAccountValidationReport(config_path=config_path, created_at=self._now(), status="FAIL" if failures else "WARNING" if warnings else "PASS", issue_count=len(issues), warning_count=warnings, fail_count=failures, config=config, issues=issues, diagnostics=diagnostics)

    def _validate_paper_account_path(self, value: str, name: str, issues: list[BTCPaperAccountIssue]) -> None:
        path = Path(value)
        if path.is_absolute():
            issues.append(self._issue(name, "FAIL", f"{name} must be a safe relative path under reports/paper_account.", {name: value}))
            return
        parts = path.parts
        self._expect(len(parts) >= 2 and parts[0] == "reports" and parts[1] == "paper_account" and ".." not in parts, issues, name, f"{name} must be under reports/paper_account.", {name: value})

    def _safe_paper_account_path(self, path: Path) -> bool:
        try:
            return path.resolve().is_relative_to((self.repo_root / "reports" / "paper_account").resolve())
        except AttributeError:
            return str(path.resolve()).startswith(str((self.repo_root / "reports" / "paper_account").resolve()))

    def _copy_state(self, state: BTCPaperAccountState) -> BTCPaperAccountState:
        payload = state.to_dict()
        payload["open_positions"] = [BTCPaperAccountVirtualPosition(**item) for item in payload.get("open_positions", [])]
        payload["closed_positions"] = [BTCPaperAccountVirtualPosition(**item) for item in payload.get("closed_positions", [])]
        payload["pending_orders"] = [BTCPaperAccountVirtualOrder(**item) for item in payload.get("pending_orders", [])]
        payload["filled_orders"] = [BTCPaperAccountVirtualOrder(**item) for item in payload.get("filled_orders", [])]
        return BTCPaperAccountState(**payload)

    def _from_live_issues(self, live_issues: list[Any]) -> list[BTCPaperAccountIssue]:
        return [self._issue(getattr(issue, "name", "live_issue"), getattr(issue, "severity", "WARNING"), getattr(issue, "message", ""), getattr(issue, "details", {})) for issue in live_issues]

    def _expect(self, condition: bool, issues: list[BTCPaperAccountIssue], name: str, message: str, details: dict[str, Any] | None = None) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message, details))

    def _issue(self, name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> BTCPaperAccountIssue:
        return BTCPaperAccountIssue(name=name, severity=severity, message=message, details=details or {})

    def _resolve(self, path_text: str) -> Path:
        path = Path(path_text)
        if not path.is_absolute():
            path = self.repo_root / path
        return path

    def _float(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _round(self, value: float) -> float:
        return round(float(value), 8)

    def _now(self) -> str:
        if self.now_provider is not None:
            return str(self.now_provider())
        return datetime.now(UTC).replace(microsecond=0).isoformat()
