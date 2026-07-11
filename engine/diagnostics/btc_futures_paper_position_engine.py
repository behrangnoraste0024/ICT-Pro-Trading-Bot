from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from engine.diagnostics.btc_futures_read_only_feed_engine import BTCFuturesReadOnlyFeedEngine
from engine.diagnostics.btc_futures_risk_model_engine import BTCFuturesRiskModelEngine
from engine.diagnostics.btc_paper_account_engine import BTCPaperAccountEngine
from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine
from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from models.btc_futures_paper_position import (
    BTCFuturesPaperAccountState,
    BTCFuturesPaperAccountStatus,
    BTCFuturesPaperAction,
    BTCFuturesPaperActionResult,
    BTCFuturesPaperConfig,
    BTCFuturesPaperDecision,
    BTCFuturesPaperIssue,
    BTCFuturesPaperLedgerEntry,
    BTCFuturesPaperLedgerSummary,
    BTCFuturesPaperPosition,
    BTCFuturesPaperPositionStatus,
    BTCFuturesPaperStatus,
    BTCFuturesPaperValidationReport,
    dataclass_from_dict,
)
from models.btc_futures_risk_model import BTCFuturesRiskScenarioInput


class BTCFuturesPaperPositionEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        runtime_config_engine: BTCPaperRuntimeConfigEngine | None = None,
        monitoring_engine: BTCPaperMonitoringEngine | None = None,
        runner_engine: BTCPaperRunnerEngine | None = None,
        futures_feed_engine: BTCFuturesReadOnlyFeedEngine | None = None,
        futures_risk_model_engine: BTCFuturesRiskModelEngine | None = None,
        spot_paper_account_engine: BTCPaperAccountEngine | None = None,
        now_provider=None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.runtime_config_engine = runtime_config_engine or BTCPaperRuntimeConfigEngine(repo_root=self.repo_root)
        self.monitoring_engine = monitoring_engine or BTCPaperMonitoringEngine(repo_root=self.repo_root)
        self.runner_engine = runner_engine or BTCPaperRunnerEngine(repo_root=self.repo_root)
        self.futures_feed_engine = futures_feed_engine or BTCFuturesReadOnlyFeedEngine(repo_root=self.repo_root)
        self.futures_risk_model_engine = futures_risk_model_engine or BTCFuturesRiskModelEngine(repo_root=self.repo_root)
        self.spot_paper_account_engine = spot_paper_account_engine or BTCPaperAccountEngine(repo_root=self.repo_root)
        self.now_provider = now_provider

    def validate(
        self,
        config_path: str = "configs/btc_futures_paper_position.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCFuturesPaperValidationReport:
        issues: list[BTCFuturesPaperIssue] = []
        diagnostics: dict[str, Any] = {
            "runtime_config_status": "UNKNOWN",
            "monitoring_config_status": "UNKNOWN",
            "runner_config_status": "UNKNOWN",
            "futures_feed_config_status": "UNKNOWN",
            "futures_risk_model_config_status": "UNKNOWN",
            "spot_paper_account_config_status": "UNKNOWN",
            "kill_switch_enabled": None,
        }
        config: BTCFuturesPaperConfig | None = None
        try:
            config = self.load_config(config_path)
        except Exception as exc:
            issues.append(self._issue("config_invalid", "FAIL", f"BTC futures paper position config could not be loaded: {exc}", {"config_path": config_path}))
            return self._validation_report(config_path, config, issues, diagnostics)
        self._validate_config_values(config, expected_profile, issues, diagnostics)
        return self._validation_report(config_path, config, issues, diagnostics)

    def status(self, config_path: str = "configs/btc_futures_paper_position.json", expected_profile: str = "balanced_smc_decision_065") -> BTCFuturesPaperActionResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BTCFuturesPaperConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, BTCFuturesPaperAction.STATUS.value, "FAIL", BTCFuturesPaperDecision.OPERATION_FAILED.value, None, None, "Futures paper position config failed validation.", issues)
        state, state_issues = self._load_state_with_issues(config)
        issues.extend(state_issues)
        if state is None:
            status = "FAIL" if any(issue.name == "state_corrupt" for issue in state_issues) else "WARNING"
            decision = BTCFuturesPaperDecision.STATE_CORRUPT.value if status == "FAIL" else BTCFuturesPaperDecision.STATE_MISSING.value
            return self._result(config, BTCFuturesPaperAction.STATUS.value, status, decision, None, None, "Local futures paper state is not ready.", issues)
        return self._result(config, BTCFuturesPaperAction.STATUS.value, "PASS", BTCFuturesPaperDecision.ACCOUNT_READY.value, state, None, "Local futures paper account state loaded.", issues)

    def initialize(self, config_path: str = "configs/btc_futures_paper_position.json", expected_profile: str = "balanced_smc_decision_065", force: bool = False) -> BTCFuturesPaperActionResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BTCFuturesPaperConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, BTCFuturesPaperAction.INITIALIZE.value, "FAIL", BTCFuturesPaperDecision.OPERATION_FAILED.value, None, None, "Futures paper position config failed validation.", issues)
        state_path = self._resolve(config.state_path)
        with self._state_lock(config, issues) as locked:
            if not locked:
                return self._result(config, BTCFuturesPaperAction.INITIALIZE.value, "FAIL", BTCFuturesPaperDecision.OPERATION_FAILED.value, None, None, "State lock could not be acquired.", issues)
            if state_path.exists() and not force:
                state, state_issues = self._load_state_with_issues(config)
                issues.extend(state_issues)
                issues.append(self._issue("state_exists", "WARNING", "Futures paper state already exists; initialization did not overwrite it."))
                return self._result(config, BTCFuturesPaperAction.INITIALIZE.value, "WARNING", BTCFuturesPaperDecision.STATE_ALREADY_INITIALIZED.value, state, None, "Futures paper account already initialized.", issues)
            state = self._new_state(config)
            ledger = self._ledger_entry(config, "ACCOUNT_INITIALIZED", None, state, state, "Local BTC futures paper account initialized.")
            self._write_state(config, state)
            self._append_ledger(config, ledger, reset=force)
            return self._result(config, BTCFuturesPaperAction.INITIALIZE.value, "PASS", BTCFuturesPaperDecision.STATE_INITIALIZED.value, state, ledger, "Local BTC futures paper account initialized.", issues, state_written=True, ledger_written=True)

    def reset(self, config_path: str = "configs/btc_futures_paper_position.json", expected_profile: str = "balanced_smc_decision_065", force: bool = False) -> BTCFuturesPaperActionResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BTCFuturesPaperConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, BTCFuturesPaperAction.RESET.value, "FAIL", BTCFuturesPaperDecision.OPERATION_FAILED.value, self._load_state(config), None, "Futures paper position config failed validation.", issues)
        if not force:
            issues.append(self._issue("force_required", "WARNING", "Reset requires --force; no local futures state was changed."))
            return self._result(config, BTCFuturesPaperAction.RESET.value, "WARNING", BTCFuturesPaperDecision.OPERATION_FAILED.value, self._load_state(config), None, "Reset skipped because --force was not supplied.", issues)
        with self._state_lock(config, issues) as locked:
            if not locked:
                return self._result(config, BTCFuturesPaperAction.RESET.value, "FAIL", BTCFuturesPaperDecision.OPERATION_FAILED.value, self._load_state(config), None, "State lock could not be acquired.", issues)
            for path_text in (config.state_path, config.ledger_path):
                path = self._resolve(path_text)
                if self._safe_local_path(path):
                    path.unlink(missing_ok=True)
            state = self._new_state(config)
            ledger = self._ledger_entry(config, "ACCOUNT_RESET", None, state, state, "Local BTC futures paper account reset.")
            self._write_state(config, state)
            self._append_ledger(config, ledger, reset=True)
            return self._result(config, BTCFuturesPaperAction.RESET.value, "PASS", BTCFuturesPaperDecision.RESET_COMPLETED.value, state, ledger, "Local BTC futures paper account reset.", issues, state_written=True, ledger_written=True)

    def open_position(
        self,
        side: str,
        entry_price: float,
        mark_price: float,
        stop_loss: float,
        take_profit: float,
        notional: float,
        leverage: int,
        action_id: str | None = None,
        config_path: str = "configs/btc_futures_paper_position.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCFuturesPaperActionResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BTCFuturesPaperConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, BTCFuturesPaperAction.OPEN_POSITION.value, "FAIL", BTCFuturesPaperDecision.OPERATION_FAILED.value, self._load_state(config), None, "Futures paper position config failed validation.", issues)
        with self._state_lock(config, issues) as locked:
            if not locked:
                return self._result(config, BTCFuturesPaperAction.OPEN_POSITION.value, "FAIL", BTCFuturesPaperDecision.OPERATION_FAILED.value, self._load_state(config), None, "State lock could not be acquired.", issues)
            state = self._load_state(config)
            if state is None:
                issues.append(self._issue("state_missing", "WARNING", "Initialize local futures paper state before opening a position."))
                return self._result(config, BTCFuturesPaperAction.OPEN_POSITION.value, "WARNING", BTCFuturesPaperDecision.STATE_MISSING.value, None, None, "Futures paper state is missing.", issues)
            duplicate = self._duplicate_result(config, state, BTCFuturesPaperAction.OPEN_POSITION.value, action_id, issues)
            if duplicate:
                return duplicate
            rejection = self._open_guard(config, state, side, entry_price, stop_loss, take_profit, notional, leverage)
            if rejection:
                decision, message = rejection
                self._record_action(state, action_id)
                return self._rejected_result(config, state, BTCFuturesPaperAction.OPEN_POSITION.value, decision, message, issues)
            scenario = BTCFuturesRiskScenarioInput(side=side.upper(), entry_price=float(entry_price), mark_price=float(mark_price), stop_loss=float(stop_loss), take_profit=float(take_profit), notional_value=float(notional), leverage=int(leverage), account_equity=float(state.equity), source="local_futures_paper_open")
            risk = self.futures_risk_model_engine.analyze_scenario(scenario, config.futures_risk_model_config_path, expected_profile=expected_profile)
            if config.require_risk_model_pass and risk.status != "PASS":
                issues.extend(self._risk_issues(risk))
                self._record_action(state, action_id)
                return self._rejected_result(config, state, BTCFuturesPaperAction.OPEN_POSITION.value, BTCFuturesPaperDecision.RISK_MODEL_REJECTED.value, "Release 2.75 risk model did not PASS.", issues)
            if risk.decision != "SAFE_SIMULATION":
                issues.extend(self._risk_issues(risk))
                self._record_action(state, action_id)
                return self._rejected_result(config, state, BTCFuturesPaperAction.OPEN_POSITION.value, BTCFuturesPaperDecision.RISK_MODEL_REJECTED.value, "Release 2.75 risk decision was not SAFE_SIMULATION.", issues)
            calc = risk.calculation
            if calc is None or (config.require_stop_before_liquidation and not calc.stop_before_liquidation):
                self._record_action(state, action_id)
                return self._rejected_result(config, state, BTCFuturesPaperAction.OPEN_POSITION.value, BTCFuturesPaperDecision.RISK_MODEL_REJECTED.value, "Risk calculation did not confirm stop before liquidation.", issues)
            before = self._copy_state(state)
            now = self._now()
            entry_fee = self._round(float(notional) * float(config.taker_fee_rate))
            position = BTCFuturesPaperPosition(
                position_id=self._id("fut-pos"),
                virtual_order_id=self._id("fut-order"),
                symbol=config.symbol,
                side=side.upper(),
                status=BTCFuturesPaperPositionStatus.OPEN.value,
                leverage=int(leverage),
                quantity=self._round(calc.quantity),
                entry_price=float(entry_price),
                mark_price=float(mark_price),
                stop_loss=float(stop_loss),
                take_profit=float(take_profit),
                notional_at_entry=float(notional),
                current_notional=self._round(calc.quantity * float(mark_price)),
                initial_margin=self._round(calc.initial_margin),
                maintenance_margin=self._round(calc.maintenance_margin_at_mark),
                liquidation_fee_reserve=self._round(calc.liquidation_fee_reserve_at_mark),
                estimated_liquidation_price=self._round(calc.estimated_liquidation_price),
                liquidation_distance_pct=self._round(calc.liquidation_distance_pct),
                unrealized_pnl=self._round(calc.unrealized_pnl_at_mark),
                realized_pnl=0.0,
                funding_pnl=0.0,
                entry_fee=entry_fee,
                exit_fee=0.0,
                total_fees=entry_fee,
                risk_reward_ratio=self._round(calc.risk_reward_ratio),
                opened_at=now,
                updated_at=now,
                model_accuracy=calc.model_accuracy,
                exchange_exact_liquidation=False,
                metadata={"risk_model": risk.to_dict(), "action_id": action_id},
            )
            state.open_position = position
            state.opened_positions_count += 1
            state.trades_today += 1
            state.wallet_balance = self._round(state.wallet_balance - entry_fee)
            state.margin_used = position.initial_margin
            state.total_fees_paid = self._round(state.total_fees_paid + entry_fee)
            self._recalculate_account(state)
            self._record_action(state, action_id)
            ledger = self._ledger_entry(config, "POSITION_OPENED", action_id, before, state, "Local virtual BTC futures position opened.", position, fee_delta=entry_fee)
            self._write_state(config, state)
            self._append_ledger(config, ledger)
            return self._result(config, BTCFuturesPaperAction.OPEN_POSITION.value, "PASS", BTCFuturesPaperDecision.POSITION_OPENED.value, state, ledger, "Local virtual BTC futures position opened.", issues, position=position, state_written=True, ledger_written=True, local_virtual_order_created=True, local_paper_futures_position_created=True)

    def mark_to_market(self, mark_price: float, action_id: str | None = None, config_path: str = "configs/btc_futures_paper_position.json", expected_profile: str = "balanced_smc_decision_065") -> BTCFuturesPaperActionResult:
        return self._mark_to_market(mark_price, action_id, config_path, expected_profile, public_mark=False)

    def mark_to_market_live(self, action_id: str | None = None, config_path: str = "configs/btc_futures_paper_position.json", expected_profile: str = "balanced_smc_decision_065") -> BTCFuturesPaperActionResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BTCFuturesPaperConfig()
        state_before = self._load_state(config)
        feed = self.futures_feed_engine.fetch_once(config.futures_read_only_feed_config_path, expected_profile=expected_profile)
        if feed.status == "FAIL" or feed.mark_price is None:
            issues = list(report.issues)
            issues.extend(self._issue(issue.name, issue.severity, issue.message, issue.details) for issue in getattr(feed, "issues", []))
            return self._result(config, BTCFuturesPaperAction.MARK_TO_MARKET_LIVE.value, "FAIL", BTCFuturesPaperDecision.LIVE_MARK_FETCH_FAILED.value, state_before, None, "Public futures mark price fetch failed safely; state was not mutated.", issues, public_mark_price_used=feed.public_futures_mark_price_fetch_used)
        return self._mark_to_market(float(feed.mark_price.mark_price), action_id, config_path, expected_profile, public_mark=True)

    def _mark_to_market(self, mark_price: float, action_id: str | None, config_path: str, expected_profile: str, public_mark: bool = False) -> BTCFuturesPaperActionResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BTCFuturesPaperConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, BTCFuturesPaperAction.MARK_TO_MARKET.value, "FAIL", BTCFuturesPaperDecision.OPERATION_FAILED.value, self._load_state(config), None, "Futures paper position config failed validation.", issues)
        if float(mark_price) <= 0:
            issues.append(self._issue("invalid_mark_price", "FAIL", "mark_price must be positive."))
            return self._result(config, BTCFuturesPaperAction.MARK_TO_MARKET.value, "FAIL", BTCFuturesPaperDecision.OPERATION_FAILED.value, self._load_state(config), None, "Invalid mark price.", issues)
        with self._state_lock(config, issues) as locked:
            if not locked:
                return self._result(config, BTCFuturesPaperAction.MARK_TO_MARKET.value, "FAIL", BTCFuturesPaperDecision.OPERATION_FAILED.value, self._load_state(config), None, "State lock could not be acquired.", issues)
            state = self._load_state(config)
            if state is None or state.open_position is None:
                return self._result(config, BTCFuturesPaperAction.MARK_TO_MARKET.value, "WARNING", BTCFuturesPaperDecision.NO_OPEN_POSITION.value, state, None, "No open futures position to mark.", issues)
            duplicate = self._duplicate_result(config, state, BTCFuturesPaperAction.MARK_TO_MARKET.value, action_id, issues)
            if duplicate:
                return duplicate
            before = self._copy_state(state)
            self._update_position_mark(config, state.open_position, float(mark_price))
            trigger = self._trigger_decision(config, state.open_position, float(mark_price))
            if trigger is not None:
                decision, status, reason = trigger
                return self._close_open_position(config, state, before, float(mark_price), reason, decision, action_id, issues, event_type=status, public_mark=public_mark)
            self._recalculate_account(state)
            self._record_action(state, action_id)
            ledger = self._ledger_entry(config, "MARK_TO_MARKET", action_id, before, state, "Local futures position marked to market.", state.open_position)
            self._write_state(config, state)
            self._append_ledger(config, ledger)
            return self._result(config, BTCFuturesPaperAction.MARK_TO_MARKET.value, "PASS", BTCFuturesPaperDecision.MARK_UPDATED.value, state, ledger, "Local futures position marked to market.", issues, position=state.open_position, state_written=True, ledger_written=True, public_mark_price_used=public_mark)

    def apply_funding(self, funding_rate: float, funding_periods: int | None = None, action_id: str | None = None, config_path: str = "configs/btc_futures_paper_position.json", expected_profile: str = "balanced_smc_decision_065", public_funding: bool = False) -> BTCFuturesPaperActionResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BTCFuturesPaperConfig()
        issues = list(report.issues)
        periods = int(funding_periods or config.default_funding_periods)
        if report.status == "FAIL":
            return self._result(config, BTCFuturesPaperAction.APPLY_FUNDING.value, "FAIL", BTCFuturesPaperDecision.OPERATION_FAILED.value, self._load_state(config), None, "Futures paper position config failed validation.", issues)
        with self._state_lock(config, issues) as locked:
            if not locked:
                return self._result(config, BTCFuturesPaperAction.APPLY_FUNDING.value, "FAIL", BTCFuturesPaperDecision.OPERATION_FAILED.value, self._load_state(config), None, "State lock could not be acquired.", issues)
            state = self._load_state(config)
            if state is None or state.open_position is None:
                return self._result(config, BTCFuturesPaperAction.APPLY_FUNDING.value, "WARNING", BTCFuturesPaperDecision.NO_OPEN_POSITION.value, state, None, "No open futures position for funding.", issues)
            duplicate = self._duplicate_result(config, state, BTCFuturesPaperAction.APPLY_FUNDING.value, action_id, issues)
            if duplicate:
                return duplicate
            before = self._copy_state(state)
            delta = self._funding_payment(state.open_position, float(funding_rate), periods)
            state.wallet_balance = self._round(state.wallet_balance + delta)
            state.funding_pnl = self._round(state.funding_pnl + delta)
            state.open_position.funding_pnl = self._round(state.open_position.funding_pnl + delta)
            state.open_position.updated_at = self._now()
            self._recalculate_account(state)
            self._record_action(state, action_id)
            ledger = self._ledger_entry(config, "FUNDING_APPLIED", action_id, before, state, "Local simulated funding applied.", state.open_position, funding_pnl_delta=delta)
            self._write_state(config, state)
            self._append_ledger(config, ledger)
            return self._result(config, BTCFuturesPaperAction.APPLY_FUNDING.value, "PASS", BTCFuturesPaperDecision.FUNDING_APPLIED.value, state, ledger, "Local simulated funding applied.", issues, position=state.open_position, state_written=True, ledger_written=True, local_funding_applied=True, public_funding_used=public_funding)

    def apply_funding_live(self, action_id: str | None = None, config_path: str = "configs/btc_futures_paper_position.json", expected_profile: str = "balanced_smc_decision_065") -> BTCFuturesPaperActionResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BTCFuturesPaperConfig()
        state_before = self._load_state(config)
        feed = self.futures_feed_engine.fetch_once(config.futures_read_only_feed_config_path, expected_profile=expected_profile)
        rate = None if feed.funding_info is None else feed.funding_info.funding_rate
        if feed.status == "FAIL" or rate is None:
            issues = list(report.issues)
            issues.extend(self._issue(issue.name, issue.severity, issue.message, issue.details) for issue in getattr(feed, "issues", []))
            return self._result(config, BTCFuturesPaperAction.APPLY_FUNDING.value, "FAIL", BTCFuturesPaperDecision.OPERATION_FAILED.value, state_before, None, "Public futures funding fetch failed safely; state was not mutated.", issues, public_funding_used=feed.public_futures_funding_fetch_used)
        return self.apply_funding(float(rate), config.default_funding_periods, action_id, config_path, expected_profile, public_funding=True)

    def close_position(self, close_price: float, close_reason: str = "MANUAL", action_id: str | None = None, config_path: str = "configs/btc_futures_paper_position.json", expected_profile: str = "balanced_smc_decision_065") -> BTCFuturesPaperActionResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BTCFuturesPaperConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, BTCFuturesPaperAction.CLOSE_POSITION.value, "FAIL", BTCFuturesPaperDecision.OPERATION_FAILED.value, self._load_state(config), None, "Futures paper position config failed validation.", issues)
        with self._state_lock(config, issues) as locked:
            if not locked:
                return self._result(config, BTCFuturesPaperAction.CLOSE_POSITION.value, "FAIL", BTCFuturesPaperDecision.OPERATION_FAILED.value, self._load_state(config), None, "State lock could not be acquired.", issues)
            state = self._load_state(config)
            if state is None or state.open_position is None:
                return self._result(config, BTCFuturesPaperAction.CLOSE_POSITION.value, "WARNING", BTCFuturesPaperDecision.NO_OPEN_POSITION.value, state, None, "No open futures position to close.", issues)
            duplicate = self._duplicate_result(config, state, BTCFuturesPaperAction.CLOSE_POSITION.value, action_id, issues)
            if duplicate:
                return duplicate
            before = self._copy_state(state)
            return self._close_open_position(config, state, before, float(close_price), close_reason, BTCFuturesPaperDecision.POSITION_CLOSED_MANUAL.value, action_id, issues, event_type="MANUAL_CLOSE")

    def ledger_summary(self, config_path: str = "configs/btc_futures_paper_position.json") -> BTCFuturesPaperLedgerSummary:
        config = self.load_config(config_path)
        path = self._resolve(config.ledger_path)
        summary = BTCFuturesPaperLedgerSummary()
        if not path.exists():
            return summary
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            event_type = str(row.get("event_type"))
            summary.total_entries += 1
            summary.initialized_events += int(event_type in ("ACCOUNT_INITIALIZED", "ACCOUNT_RESET"))
            summary.position_opened_events += int(event_type == "POSITION_OPENED")
            summary.mark_events += int(event_type == "MARK_TO_MARKET")
            summary.funding_events += int(event_type == "FUNDING_APPLIED")
            summary.manual_close_events += int(event_type == "MANUAL_CLOSE")
            summary.stop_loss_events += int(event_type == "STOP_LOSS")
            summary.take_profit_events += int(event_type == "TAKE_PROFIT")
            summary.liquidation_events += int(event_type == "LIQUIDATED_SIMULATED")
            summary.rejected_events += int(event_type == "REJECTED")
            summary.realized_pnl_total = self._round(summary.realized_pnl_total + float(row.get("realized_pnl_delta") or 0.0))
            summary.funding_pnl_total = self._round(summary.funding_pnl_total + float(row.get("funding_pnl_delta") or 0.0))
            summary.fee_total = self._round(summary.fee_total + float(row.get("fee_delta") or 0.0))
            summary.latest_event_at = row.get("created_at")
            summary.latest_event_id = row.get("event_id")
        return summary

    def simulate_lifecycle(self, config_path: str = "configs/btc_futures_paper_position.json", expected_profile: str = "balanced_smc_decision_065") -> BTCFuturesPaperActionResult:
        report = self.validate(config_path, expected_profile)
        config = report.config or BTCFuturesPaperConfig()
        issues = list(report.issues)
        if report.status == "FAIL":
            return self._result(config, BTCFuturesPaperAction.SIMULATE_LIFECYCLE.value, "FAIL", BTCFuturesPaperDecision.OPERATION_FAILED.value, None, None, "Futures paper position config failed validation.", issues, metadata={"lifecycle_simulation": True, "persistent_state_used": False})
        state = self._new_state(config)
        before = self._copy_state(state)
        risk = self.futures_risk_model_engine.analyze_scenario(
            BTCFuturesRiskScenarioInput(side="LONG", entry_price=64000.0, mark_price=64000.0, stop_loss=62000.0, take_profit=67000.0, notional_value=1000.0, leverage=2, account_equity=state.equity, source="in_memory_lifecycle"),
            config.futures_risk_model_config_path,
            expected_profile=expected_profile,
        )
        if risk.status == "FAIL" or risk.calculation is None:
            issues.extend(self._risk_issues(risk))
            return self._result(config, BTCFuturesPaperAction.SIMULATE_LIFECYCLE.value, "FAIL", BTCFuturesPaperDecision.RISK_MODEL_REJECTED.value, state, None, "In-memory lifecycle risk model rejected scenario.", issues, metadata={"lifecycle_simulation": True, "persistent_state_used": False})
        calc = risk.calculation
        now = self._now()
        entry_fee = self._round(1000.0 * config.taker_fee_rate)
        position = BTCFuturesPaperPosition(self._id("lifecycle-pos"), self._id("lifecycle-order"), config.symbol, "LONG", "OPEN", 2, self._round(calc.quantity), 64000.0, 64000.0, 62000.0, 67000.0, 1000.0, 1000.0, self._round(calc.initial_margin), self._round(calc.maintenance_margin_at_mark), self._round(calc.liquidation_fee_reserve_at_mark), self._round(calc.estimated_liquidation_price), self._round(calc.liquidation_distance_pct), 0.0, 0.0, 0.0, entry_fee, 0.0, entry_fee, self._round(calc.risk_reward_ratio), now, now)
        state.open_position = position
        state.opened_positions_count = 1
        state.trades_today = 1
        state.wallet_balance = self._round(state.wallet_balance - entry_fee)
        state.margin_used = position.initial_margin
        state.total_fees_paid = entry_fee
        self._update_position_mark(config, position, 65000.0)
        funding_delta = self._funding_payment(position, 0.0001, 1)
        state.wallet_balance = self._round(state.wallet_balance + funding_delta)
        state.funding_pnl = funding_delta
        position.funding_pnl = funding_delta
        self._recalculate_account(state)
        result = self._close_open_position(config, state, before, 66000.0, "MANUAL", BTCFuturesPaperDecision.POSITION_CLOSED_MANUAL.value, "lifecycle-close", issues, event_type="MANUAL_CLOSE", persistent=False)
        result.action = BTCFuturesPaperAction.SIMULATE_LIFECYCLE.value
        result.metadata.update({"lifecycle_simulation": True, "persistent_state_used": False, "futures_trade_pipeline_invoked": False, "local_example_only": True})
        result.state_written = False
        result.ledger_written = False
        return result

    def load_config(self, config_path: str = "configs/btc_futures_paper_position.json") -> BTCFuturesPaperConfig:
        path = self._resolve(config_path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("config JSON must be an object")
        return BTCFuturesPaperConfig(**{**BTCFuturesPaperConfig().to_dict(), **loaded})

    def _validate_config_values(self, config: BTCFuturesPaperConfig, expected_profile: str, issues: list[BTCFuturesPaperIssue], diagnostics: dict[str, Any]) -> None:
        expected = {
            "project_scope": "BTC_ONLY",
            "symbol": "BTC/USDT",
            "exchange_symbol": "BTCUSDT",
            "exchange": "binance",
            "market_type": "futures",
            "futures_contract_type": "USDT_PERPETUAL",
            "strategy_profile": expected_profile,
            "margin_mode": "isolated",
            "position_mode": "one_way",
        }
        for name, value in expected.items():
            self._expect(getattr(config, name) == value, issues, name, f"{name} must be {value}.")
        self._expect(config.simulation_only, issues, "simulation_only", "simulation_only must be true.")
        self._expect(config.dry_run_only, issues, "dry_run_only", "dry_run_only must be true.")
        self._expect(int(config.max_open_positions) == 1, issues, "max_open_positions", "max_open_positions must be 1.")
        self._expect(bool(config.allowed_leverage) and all(isinstance(item, int) and item in (1, 2, 3, 5) for item in config.allowed_leverage), issues, "allowed_leverage", "allowed_leverage may only contain 1, 2, 3, 5.")
        self._expect(int(config.max_leverage) <= 5, issues, "max_leverage", "max_leverage must be <= 5.")
        self._expect(int(config.default_leverage) in config.allowed_leverage, issues, "default_leverage", "default_leverage must be allowed.")
        for name in ("initial_account_balance", "default_notional", "min_notional", "max_notional_pct_of_equity", "max_initial_margin_pct_of_equity", "minimum_risk_reward", "max_daily_realized_loss_pct", "max_account_drawdown_pct"):
            self._expect(float(getattr(config, name)) > 0, issues, name, f"{name} must be positive.")
        self._expect(int(config.max_trades_per_day) > 0, issues, "max_trades_per_day", "max_trades_per_day must be positive.")
        self._expect(0 <= float(config.taker_fee_rate) <= 0.01, issues, "taker_fee_rate", "taker_fee_rate must be between 0 and 0.01.")
        self._expect(0 <= float(config.liquidation_fee_rate) <= 0.02, issues, "liquidation_fee_rate", "liquidation_fee_rate must be between 0 and 0.02.")
        self._expect(config.require_risk_model_pass, issues, "require_risk_model_pass", "require_risk_model_pass must be true.")
        self._expect(config.require_stop_before_liquidation, issues, "require_stop_before_liquidation", "require_stop_before_liquidation must be true.")
        self._expect(config.require_stop_loss, issues, "require_stop_loss", "require_stop_loss must be true.")
        self._expect(config.require_take_profit, issues, "require_take_profit", "require_take_profit must be true.")
        for name in ("allow_local_futures_state_write", "allow_local_futures_ledger_write", "allow_local_virtual_order_creation", "allow_local_paper_futures_position_creation", "allow_local_mark_to_market", "allow_local_funding_application", "allow_local_position_close", "allow_local_simulated_liquidation", "allow_local_futures_state_reset", "allow_public_mark_price_fetch", "allow_public_funding_fetch"):
            self._expect(bool(getattr(config, name)), issues, name, f"{name} must be true for explicit local simulation actions.")
        for name in (
            "allow_private_api", "allow_api_key_usage", "allow_trading_api", "allow_account_data", "allow_balance_fetch", "allow_position_fetch",
            "allow_real_order_submission", "allow_order_cancellation", "allow_real_position_creation", "allow_exchange_paper_position_creation",
            "allow_testnet_order_submission", "allow_exchange_leverage_change", "allow_exchange_margin_mode_change", "allow_spot_paper_account_state_mutation",
            "allow_runner_state_mutation", "allow_execution_state_mutation", "allow_exchange_state_mutation",
        ):
            self._expect(not bool(getattr(config, name)), issues, name, f"{name} must remain false.")
        self._validate_local_path(config.state_path, "state_path", "reports/futures_paper_position", issues)
        self._validate_local_path(config.ledger_path, "ledger_path", "reports/futures_paper_position", issues)
        self._validate_local_path(config.lock_path, "lock_path", "reports/futures_paper_position", issues)
        self._validate_local_path(config.report_export_dir, "report_export_dir", "reports/futures_paper_position", issues)
        self._validate_dependencies(config, expected_profile, issues, diagnostics)

    def _validate_dependencies(self, config: BTCFuturesPaperConfig, expected_profile: str, issues: list[BTCFuturesPaperIssue], diagnostics: dict[str, Any]) -> None:
        runtime = self.runtime_config_engine.validate(config.runtime_config_path, expected_profile=expected_profile)
        diagnostics["runtime_config_status"] = runtime.status
        diagnostics["kill_switch_enabled"] = bool(getattr(runtime.config, "kill_switch_enabled", False))
        if config.require_runtime_config_pass and runtime.status != "PASS":
            issues.append(self._issue("runtime_config_validation", "FAIL", "Runtime config must validate PASS."))
        if runtime.config is not None and config.require_kill_switch_enabled:
            self._expect(runtime.config.kill_switch_enabled, issues, "kill_switch_enabled", "kill_switch_enabled must remain true.")
        monitoring = self.monitoring_engine.validate(config.monitoring_config_path, expected_profile=expected_profile)
        diagnostics["monitoring_config_status"] = monitoring.status
        if config.require_monitoring_config_pass and monitoring.status != "PASS":
            issues.append(self._issue("monitoring_config_validation", "FAIL", "Monitoring config must validate PASS."))
        _, runner_issues, _ = self.runner_engine.validate_config(config.runner_config_path, expected_profile=expected_profile)
        diagnostics["runner_config_status"] = "FAIL" if any(issue.severity == "FAIL" for issue in runner_issues) else "PASS"
        if config.require_runner_config_pass and diagnostics["runner_config_status"] != "PASS":
            issues.append(self._issue("runner_config_validation", "FAIL", "Runner config must validate PASS."))
        feed = self.futures_feed_engine.validate(config.futures_read_only_feed_config_path, expected_profile=expected_profile)
        diagnostics["futures_feed_config_status"] = feed.status
        if config.require_futures_feed_config_pass and feed.status != "PASS":
            issues.append(self._issue("futures_feed_config_validation", "FAIL", "Futures read-only feed config must validate PASS."))
        risk = self.futures_risk_model_engine.validate(config.futures_risk_model_config_path, expected_profile=expected_profile)
        diagnostics["futures_risk_model_config_status"] = risk.status
        if config.require_futures_risk_model_config_pass and risk.status != "PASS":
            issues.append(self._issue("futures_risk_model_config_validation", "FAIL", "Futures risk model config must validate PASS."))
        spot = self.spot_paper_account_engine.validate(config.spot_paper_account_config_path, expected_profile=expected_profile)
        diagnostics["spot_paper_account_config_status"] = spot.status
        if config.require_spot_paper_account_config_pass and spot.status != "PASS":
            issues.append(self._issue("spot_paper_account_config_validation", "FAIL", "Spot paper account config must validate PASS."))

    def _open_guard(self, config: BTCFuturesPaperConfig, state: BTCFuturesPaperAccountState, side: str, entry: float, stop: float, tp: float, notional: float, leverage: int) -> tuple[str, str] | None:
        if state.open_position is not None:
            return BTCFuturesPaperDecision.POSITION_ALREADY_OPEN.value, "Only one local BTC futures paper position may be open."
        if int(leverage) not in config.allowed_leverage:
            return BTCFuturesPaperDecision.LEVERAGE_NOT_ALLOWED.value, "Leverage is not allowed."
        if float(notional) < float(config.min_notional):
            return BTCFuturesPaperDecision.POSITION_OPEN_REJECTED.value, "Notional is below minimum."
        if (float(notional) / state.equity) * 100 > float(config.max_notional_pct_of_equity):
            return BTCFuturesPaperDecision.INSUFFICIENT_MARGIN.value, "Notional exceeds configured equity percentage."
        initial_margin = float(notional) / int(leverage)
        if (initial_margin / state.equity) * 100 > float(config.max_initial_margin_pct_of_equity):
            return BTCFuturesPaperDecision.INSUFFICIENT_MARGIN.value, "Initial margin exceeds configured equity percentage."
        if state.available_balance < initial_margin + float(notional) * float(config.taker_fee_rate):
            return BTCFuturesPaperDecision.INSUFFICIENT_MARGIN.value, "Available balance is insufficient."
        if state.daily_realized_pnl <= -(state.starting_balance * float(config.max_daily_realized_loss_pct) / 100):
            return BTCFuturesPaperDecision.DAILY_LOSS_LIMIT_REACHED.value, "Daily realized loss limit reached."
        if state.current_drawdown_pct >= float(config.max_account_drawdown_pct):
            return BTCFuturesPaperDecision.DRAWDOWN_LIMIT_REACHED.value, "Account drawdown limit reached."
        if state.trades_today >= int(config.max_trades_per_day):
            return BTCFuturesPaperDecision.MAX_TRADES_REACHED.value, "Max trades per day reached."
        if side.upper() == "LONG" and stop >= entry:
            return BTCFuturesPaperDecision.POSITION_OPEN_REJECTED.value, "LONG stop loss must be below entry."
        if side.upper() == "LONG" and tp <= entry:
            return BTCFuturesPaperDecision.POSITION_OPEN_REJECTED.value, "LONG take profit must be above entry."
        if side.upper() == "SHORT" and stop <= entry:
            return BTCFuturesPaperDecision.POSITION_OPEN_REJECTED.value, "SHORT stop loss must be above entry."
        if side.upper() == "SHORT" and tp >= entry:
            return BTCFuturesPaperDecision.POSITION_OPEN_REJECTED.value, "SHORT take profit must be below entry."
        risk = abs(float(entry) - float(stop))
        reward = abs(float(tp) - float(entry))
        if risk <= 0 or reward / risk < float(config.minimum_risk_reward):
            return BTCFuturesPaperDecision.POSITION_OPEN_REJECTED.value, "Risk/reward is below configured minimum."
        return None

    def _close_open_position(self, config: BTCFuturesPaperConfig, state: BTCFuturesPaperAccountState, before: BTCFuturesPaperAccountState, close_price: float, reason: str, decision: str, action_id: str | None, issues: list[BTCFuturesPaperIssue], event_type: str, public_mark: bool = False, persistent: bool = True) -> BTCFuturesPaperActionResult:
        position = state.open_position
        if position is None:
            return self._result(config, BTCFuturesPaperAction.CLOSE_POSITION.value, "WARNING", BTCFuturesPaperDecision.NO_OPEN_POSITION.value, state, None, "No open futures position to close.", issues)
        self._update_position_mark(config, position, close_price)
        price_pnl = position.unrealized_pnl
        exit_fee = self._round(close_price * position.quantity * float(config.taker_fee_rate))
        if decision == BTCFuturesPaperDecision.POSITION_LIQUIDATED_SIMULATED.value:
            exit_fee = self._round(exit_fee + close_price * position.quantity * float(config.liquidation_fee_rate))
        position.realized_pnl = self._round(price_pnl)
        position.exit_fee = exit_fee
        position.total_fees = self._round(position.entry_fee + exit_fee)
        position.close_price = close_price
        position.close_reason = reason
        position.closed_at = self._now()
        position.updated_at = position.closed_at
        position.unrealized_pnl = 0.0
        position.status = self._position_status_from_decision(decision)
        state.wallet_balance = self._round(state.wallet_balance + price_pnl - exit_fee)
        state.realized_pnl = self._round(state.realized_pnl + price_pnl)
        state.daily_realized_pnl = self._round(state.daily_realized_pnl + price_pnl)
        state.total_fees_paid = self._round(state.total_fees_paid + exit_fee)
        state.closed_positions_count += 1
        if decision == BTCFuturesPaperDecision.POSITION_LIQUIDATED_SIMULATED.value:
            state.liquidated_positions_count += 1
        state.open_position = None
        state.margin_used = 0.0
        state.unrealized_pnl = 0.0
        self._recalculate_account(state)
        self._record_action(state, action_id)
        ledger = self._ledger_entry(config, event_type, action_id, before, state, f"Local futures position closed: {reason}.", position, realized_pnl_delta=price_pnl, fee_delta=exit_fee)
        if persistent:
            self._write_state(config, state)
            self._append_ledger(config, ledger)
        return self._result(config, BTCFuturesPaperAction.CLOSE_POSITION.value, "PASS", decision, state, ledger, f"Local futures position closed: {reason}.", issues, position=position, state_written=persistent, ledger_written=persistent, local_position_closed=True, local_simulated_liquidation_applied=decision == BTCFuturesPaperDecision.POSITION_LIQUIDATED_SIMULATED.value, public_mark_price_used=public_mark)

    def _trigger_decision(self, config: BTCFuturesPaperConfig, position: BTCFuturesPaperPosition, mark: float) -> tuple[str, str, str] | None:
        side = position.side.upper()
        if config.liquidation_trigger_precedence and config.auto_close_on_simulated_liquidation:
            if side == "LONG" and mark <= position.estimated_liquidation_price:
                return BTCFuturesPaperDecision.POSITION_LIQUIDATED_SIMULATED.value, "LIQUIDATED_SIMULATED", "SIMULATED_LIQUIDATION"
            if side == "SHORT" and mark >= position.estimated_liquidation_price:
                return BTCFuturesPaperDecision.POSITION_LIQUIDATED_SIMULATED.value, "LIQUIDATED_SIMULATED", "SIMULATED_LIQUIDATION"
        if config.auto_close_on_stop_loss:
            if side == "LONG" and mark <= position.stop_loss:
                return BTCFuturesPaperDecision.POSITION_CLOSED_STOP_LOSS.value, "STOP_LOSS", "STOP_LOSS"
            if side == "SHORT" and mark >= position.stop_loss:
                return BTCFuturesPaperDecision.POSITION_CLOSED_STOP_LOSS.value, "STOP_LOSS", "STOP_LOSS"
        if config.auto_close_on_take_profit:
            if side == "LONG" and mark >= position.take_profit:
                return BTCFuturesPaperDecision.POSITION_CLOSED_TAKE_PROFIT.value, "TAKE_PROFIT", "TAKE_PROFIT"
            if side == "SHORT" and mark <= position.take_profit:
                return BTCFuturesPaperDecision.POSITION_CLOSED_TAKE_PROFIT.value, "TAKE_PROFIT", "TAKE_PROFIT"
        return None

    def _update_position_mark(self, config: BTCFuturesPaperConfig, position: BTCFuturesPaperPosition, mark: float) -> None:
        direction = 1 if position.side.upper() == "LONG" else -1
        position.mark_price = self._round(mark)
        position.current_notional = self._round(mark * position.quantity)
        position.unrealized_pnl = self._round((mark - position.entry_price) * position.quantity * direction)
        position.maintenance_margin = self._round(position.current_notional * 0.004)
        position.liquidation_fee_reserve = self._round(position.current_notional * float(config.liquidation_fee_rate))
        distance = (mark - position.estimated_liquidation_price) if position.side.upper() == "LONG" else (position.estimated_liquidation_price - mark)
        position.liquidation_distance_pct = self._round((distance / mark) * 100)
        position.updated_at = self._now()

    def _recalculate_account(self, state: BTCFuturesPaperAccountState) -> None:
        state.unrealized_pnl = 0.0 if state.open_position is None else self._round(state.open_position.unrealized_pnl)
        state.equity = self._round(state.wallet_balance + state.unrealized_pnl)
        state.available_balance = self._round(state.wallet_balance + state.unrealized_pnl - state.margin_used)
        state.peak_equity = max(state.peak_equity, state.equity)
        state.current_drawdown_pct = 0.0 if state.peak_equity <= 0 else self._round(((state.peak_equity - state.equity) / state.peak_equity) * 100)
        state.updated_at = self._now()
        state.state_version += 1

    def _new_state(self, config: BTCFuturesPaperConfig) -> BTCFuturesPaperAccountState:
        now = self._now()
        balance = self._round(config.initial_account_balance)
        return BTCFuturesPaperAccountState(
            schema_version=config.schema_version,
            state_version=1,
            account_id="btc-futures-paper-local",
            created_at=now,
            updated_at=now,
            project_scope=config.project_scope,
            symbol=config.symbol,
            account_currency=config.account_currency,
            account_status=BTCFuturesPaperAccountStatus.READY.value,
            starting_balance=balance,
            wallet_balance=balance,
            available_balance=balance,
            equity=balance,
            peak_equity=balance,
            current_drawdown_pct=0.0,
            margin_used=0.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            daily_realized_pnl=0.0,
            funding_pnl=0.0,
            total_fees_paid=0.0,
            open_position=None,
            opened_positions_count=0,
            closed_positions_count=0,
            liquidated_positions_count=0,
            trades_today=0,
            trading_day=now[:10],
            last_event_id=None,
            processed_action_ids=[],
            metadata={"simulation_only": True, "dry_run_only": True},
        )

    def _load_state(self, config: BTCFuturesPaperConfig) -> BTCFuturesPaperAccountState | None:
        state, _ = self._load_state_with_issues(config)
        return state

    def _load_state_with_issues(self, config: BTCFuturesPaperConfig) -> tuple[BTCFuturesPaperAccountState | None, list[BTCFuturesPaperIssue]]:
        path = self._resolve(config.state_path)
        if not path.exists():
            return None, [self._issue("state_missing", "WARNING", "Futures paper state file does not exist yet.", {"state_path": str(path)})]
        try:
            return dataclass_from_dict(BTCFuturesPaperAccountState, json.loads(path.read_text(encoding="utf-8"))), []
        except Exception as exc:
            return None, [self._issue("state_corrupt", "FAIL", f"Futures paper state file is corrupt: {exc}", {"state_path": str(path)})]

    def _write_state(self, config: BTCFuturesPaperConfig, state: BTCFuturesPaperAccountState) -> None:
        path = self._resolve(config.state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
        temp.replace(path)

    def _append_ledger(self, config: BTCFuturesPaperConfig, entry: BTCFuturesPaperLedgerEntry, reset: bool = False) -> None:
        path = self._resolve(config.ledger_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if reset else "a"
        with path.open(mode, encoding="utf-8") as handle:
            handle.write(json.dumps(entry.to_dict()) + "\n")

    @contextmanager
    def _state_lock(self, config: BTCFuturesPaperConfig, issues: list[BTCFuturesPaperIssue]) -> Iterator[bool]:
        path = self._resolve(config.lock_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + float(config.state_lock_timeout_seconds)
        acquired = False
        while time.time() <= deadline:
            try:
                handle = path.open("x", encoding="utf-8")
                handle.write(self._now())
                handle.close()
                acquired = True
                break
            except FileExistsError:
                time.sleep(0.05)
        if not acquired:
            issues.append(self._issue("state_lock_timeout", "FAIL", "Could not acquire local futures paper state lock."))
            yield False
            return
        try:
            yield True
        finally:
            path.unlink(missing_ok=True)

    def _ledger_entry(self, config: BTCFuturesPaperConfig, event_type: str, action_id: str | None, before: BTCFuturesPaperAccountState, after: BTCFuturesPaperAccountState, reason: str, position: BTCFuturesPaperPosition | None = None, realized_pnl_delta: float = 0.0, funding_pnl_delta: float = 0.0, fee_delta: float = 0.0) -> BTCFuturesPaperLedgerEntry:
        entry = BTCFuturesPaperLedgerEntry(
            schema_version=config.schema_version,
            event_id=self._id("fut-ledger"),
            action_id=action_id,
            created_at=self._now(),
            event_type=event_type,
            account_id=after.account_id,
            position_id=None if position is None else position.position_id,
            virtual_order_id=None if position is None else position.virtual_order_id,
            side=None if position is None else position.side,
            price=None if position is None else position.mark_price,
            quantity=None if position is None else position.quantity,
            notional=None if position is None else position.current_notional,
            leverage=None if position is None else position.leverage,
            wallet_balance_before=before.wallet_balance,
            wallet_balance_after=after.wallet_balance,
            equity_before=before.equity,
            equity_after=after.equity,
            realized_pnl_delta=self._round(realized_pnl_delta),
            unrealized_pnl_after=after.unrealized_pnl,
            funding_pnl_delta=self._round(funding_pnl_delta),
            fee_delta=self._round(fee_delta),
            reason=reason,
            metadata={"local_only": True, "exchange_state_mutated": False},
        )
        after.last_event_id = entry.event_id
        return entry

    def _result(self, config: BTCFuturesPaperConfig, action: str, status: str, decision: str, state: BTCFuturesPaperAccountState | None, ledger: BTCFuturesPaperLedgerEntry | None, reason: str, issues: list[BTCFuturesPaperIssue], position: BTCFuturesPaperPosition | None = None, **flags) -> BTCFuturesPaperActionResult:
        safety = self._safety_summary(flags)
        return BTCFuturesPaperActionResult(
            created_at=self._now(),
            action=action,
            status=status,
            decision=decision,
            reason=reason,
            state_path=config.state_path,
            ledger_path=config.ledger_path,
            account_state=state,
            position=position if position is not None else (None if state is None else state.open_position),
            ledger_entry=ledger,
            issues=issues,
            safety_summary=safety,
            metadata={"local_futures_paper_position_simulation": True, "spot_paper_account_mutated": False, **dict(flags.pop("metadata", {}) or {})},
            **flags,
        )

    def _rejected_result(self, config: BTCFuturesPaperConfig, state: BTCFuturesPaperAccountState, action: str, decision: str, message: str, issues: list[BTCFuturesPaperIssue]) -> BTCFuturesPaperActionResult:
        issues.append(self._issue("action_rejected", "WARNING", message, {"decision": decision}))
        return self._result(config, action, "WARNING", decision, state, None, message, issues)

    def _duplicate_result(self, config: BTCFuturesPaperConfig, state: BTCFuturesPaperAccountState, action: str, action_id: str | None, issues: list[BTCFuturesPaperIssue]) -> BTCFuturesPaperActionResult | None:
        if action_id and action_id in state.processed_action_ids:
            issues.append(self._issue("duplicate_action_id", "WARNING", "Action ID was already processed; no mutation was applied.", {"action_id": action_id}))
            return self._result(config, action, "WARNING", BTCFuturesPaperDecision.DUPLICATE_ACTION.value, state, None, "Duplicate action ID ignored.", issues)
        return None

    def _record_action(self, state: BTCFuturesPaperAccountState, action_id: str | None) -> None:
        if action_id:
            state.processed_action_ids.append(action_id)
            state.processed_action_ids = state.processed_action_ids[-200:]

    def _funding_payment(self, position: BTCFuturesPaperPosition, funding_rate: float, periods: int) -> float:
        absolute = position.current_notional * abs(funding_rate) * int(periods)
        positive = funding_rate > 0
        if position.side.upper() == "LONG":
            return self._round(-absolute if positive else absolute)
        return self._round(absolute if positive else -absolute)

    def _risk_issues(self, risk) -> list[BTCFuturesPaperIssue]:
        return [self._issue(f"risk_model_{issue.name}", issue.severity, issue.message, issue.details) for issue in getattr(risk, "issues", [])]

    def _position_status_from_decision(self, decision: str) -> str:
        mapping = {
            BTCFuturesPaperDecision.POSITION_CLOSED_STOP_LOSS.value: BTCFuturesPaperPositionStatus.STOPPED_OUT.value,
            BTCFuturesPaperDecision.POSITION_CLOSED_TAKE_PROFIT.value: BTCFuturesPaperPositionStatus.TAKE_PROFIT.value,
            BTCFuturesPaperDecision.POSITION_LIQUIDATED_SIMULATED.value: BTCFuturesPaperPositionStatus.LIQUIDATED_SIMULATED.value,
        }
        return mapping.get(decision, BTCFuturesPaperPositionStatus.CLOSED.value)

    def _validation_report(self, config_path: str, config: BTCFuturesPaperConfig | None, issues: list[BTCFuturesPaperIssue], diagnostics: dict[str, Any]) -> BTCFuturesPaperValidationReport:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        return BTCFuturesPaperValidationReport(config_path=config_path, created_at=self._now(), status="FAIL" if failures else "WARNING" if warnings else "PASS", issue_count=len(issues), warning_count=warnings, fail_count=failures, config=config, issues=issues, diagnostics=diagnostics)

    def _validate_local_path(self, value: str, name: str, root: str, issues: list[BTCFuturesPaperIssue]) -> None:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            issues.append(self._issue(name, "FAIL", f"{name} must be a safe relative path under {root}."))
            return
        expected = Path(root)
        self._expect(len(path.parts) >= len(expected.parts) and path.parts[: len(expected.parts)] == expected.parts, issues, name, f"{name} must be under {root}.")

    def _safe_local_path(self, path: Path) -> bool:
        try:
            path.resolve().relative_to((self.repo_root / "reports" / "futures_paper_position").resolve())
            return True
        except ValueError:
            return False

    def _copy_state(self, state: BTCFuturesPaperAccountState) -> BTCFuturesPaperAccountState:
        return dataclass_from_dict(BTCFuturesPaperAccountState, state.to_dict())

    def _safety_summary(self, flags: dict[str, Any] | None = None) -> dict[str, Any]:
        flags = flags or {}
        return {
            "private_api_used": False,
            "api_key_used": False,
            "trading_api_used": False,
            "account_data_used": False,
            "balance_fetch_used": False,
            "position_fetch_used": False,
            "real_order_submitted": False,
            "order_cancelled": False,
            "real_position_created": False,
            "exchange_paper_position_created": False,
            "testnet_order_submitted": False,
            "exchange_leverage_changed": False,
            "exchange_margin_mode_changed": False,
            "spot_paper_account_state_mutated": False,
            "runner_state_mutated": False,
            "execution_state_mutated": False,
            "exchange_state_mutated": False,
            "state_written": bool(flags.get("state_written", False)),
            "ledger_written": bool(flags.get("ledger_written", False)),
        }

    def _expect(self, condition: bool, issues: list[BTCFuturesPaperIssue], name: str, message: str) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message))

    def _issue(self, name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> BTCFuturesPaperIssue:
        return BTCFuturesPaperIssue(name=name, severity=severity, message=message, details=details or {})

    def _resolve(self, path_text: str) -> Path:
        path = Path(path_text)
        return path if path.is_absolute() else self.repo_root / path

    def _id(self, prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:12]}"

    def _now(self) -> str:
        if self.now_provider is not None:
            return str(self.now_provider())
        return datetime.now(UTC).replace(microsecond=0).isoformat()

    def _round(self, value: float) -> float:
        return round(float(value), 6)
