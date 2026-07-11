from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.diagnostics.btc_futures_read_only_feed_engine import BTCFuturesReadOnlyFeedEngine
from engine.diagnostics.btc_paper_account_engine import BTCPaperAccountEngine
from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine
from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from models.btc_futures_risk_model import (
    BTCFuturesLeverageComparisonResult,
    BTCFuturesLeverageComparisonRow,
    BTCFuturesPositionSide,
    BTCFuturesRiskCalculation,
    BTCFuturesRiskConfig,
    BTCFuturesRiskDecision,
    BTCFuturesRiskIssue,
    BTCFuturesRiskResult,
    BTCFuturesRiskScenarioInput,
    BTCFuturesRiskStatus,
    BTCFuturesRiskValidationReport,
)


class BTCFuturesRiskModelEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        runtime_config_engine: BTCPaperRuntimeConfigEngine | None = None,
        monitoring_engine: BTCPaperMonitoringEngine | None = None,
        runner_engine: BTCPaperRunnerEngine | None = None,
        futures_feed_engine: BTCFuturesReadOnlyFeedEngine | None = None,
        paper_account_engine: BTCPaperAccountEngine | None = None,
        now_provider=None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.runtime_config_engine = runtime_config_engine or BTCPaperRuntimeConfigEngine(repo_root=self.repo_root)
        self.monitoring_engine = monitoring_engine or BTCPaperMonitoringEngine(repo_root=self.repo_root)
        self.runner_engine = runner_engine or BTCPaperRunnerEngine(repo_root=self.repo_root)
        self.futures_feed_engine = futures_feed_engine or BTCFuturesReadOnlyFeedEngine(repo_root=self.repo_root)
        self.paper_account_engine = paper_account_engine or BTCPaperAccountEngine(repo_root=self.repo_root)
        self.now_provider = now_provider

    def validate(
        self,
        config_path: str = "configs/btc_futures_risk_model.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCFuturesRiskValidationReport:
        issues: list[BTCFuturesRiskIssue] = []
        diagnostics: dict[str, Any] = {
            "runtime_config_status": "UNKNOWN",
            "monitoring_config_status": "UNKNOWN",
            "runner_config_status": "UNKNOWN",
            "futures_feed_config_status": "UNKNOWN",
            "paper_account_config_status": "UNKNOWN",
            "kill_switch_enabled": None,
        }
        config: BTCFuturesRiskConfig | None = None
        try:
            config = self.load_config(config_path)
        except Exception as exc:
            issues.append(self._issue("config_invalid", "FAIL", f"BTC futures risk model config could not be loaded: {exc}", {"config_path": config_path}))
            return self._report(config_path, config, issues, diagnostics)
        self._validate_config_values(config, expected_profile, issues, diagnostics)
        return self._report(config_path, config, issues, diagnostics)

    def analyze_scenario(
        self,
        scenario: BTCFuturesRiskScenarioInput,
        config_path: str = "configs/btc_futures_risk_model.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCFuturesRiskResult:
        report = self.validate(config_path=config_path, expected_profile=expected_profile)
        config = report.config or BTCFuturesRiskConfig()
        issues = list(report.issues)
        if report.status == BTCFuturesRiskStatus.FAIL.value:
            return self._result(config, scenario, None, "FAIL", BTCFuturesRiskDecision.MODEL_FAILED.value, "Risk model config failed validation.", issues)
        scenario_issues, decision = self._validate_scenario(config, scenario)
        issues.extend(scenario_issues)
        if scenario_issues:
            return self._result(config, scenario, None, "FAIL", decision, "Scenario failed risk-model validation.", issues)
        try:
            calculation = self._calculate(config, scenario)
        except Exception as exc:
            issues.append(self._issue("model_calculation_failed", "FAIL", f"Risk model calculation failed: {exc}"))
            return self._result(config, scenario, None, "FAIL", BTCFuturesRiskDecision.MODEL_FAILED.value, "Risk model calculation failed.", issues)
        status, final_decision, reason, decision_issues = self._decision(config, scenario, calculation)
        issues.extend(decision_issues)
        return self._result(config, scenario, calculation, status, final_decision, reason, issues)

    def analyze_live(
        self,
        side: str | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        notional: float | None = None,
        account_equity: float = 10000.0,
        leverage: int | None = None,
        config_path: str = "configs/btc_futures_risk_model.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCFuturesRiskResult:
        report = self.validate(config_path=config_path, expected_profile=expected_profile)
        config = report.config or BTCFuturesRiskConfig()
        if report.status == "FAIL":
            scenario = BTCFuturesRiskScenarioInput(side=side or config.default_scenario_side, entry_price=0, mark_price=0, stop_loss=0, take_profit=0, notional_value=notional or config.default_notional, leverage=leverage or config.default_leverage, account_equity=account_equity, source="live_read_only")
            return self._result(config, scenario, None, "FAIL", BTCFuturesRiskDecision.MODEL_FAILED.value, "Risk model config failed validation.", list(report.issues), public_market_data_used=False)
        feed = self.futures_feed_engine.fetch_once(config.futures_read_only_feed_config_path, expected_profile=expected_profile)
        if feed.status == "FAIL" or feed.primary_latest_close is None:
            scenario = BTCFuturesRiskScenarioInput(side=side or config.default_scenario_side, entry_price=0, mark_price=0, stop_loss=0, take_profit=0, notional_value=notional or config.default_notional, leverage=leverage or config.default_leverage, account_equity=account_equity, source="live_read_only")
            issues = list(report.issues)
            issues.extend(self._issue(issue.name, issue.severity, issue.message, issue.details) for issue in feed.issues)
            return self._result(config, scenario, None, "FAIL", BTCFuturesRiskDecision.DATA_FETCH_FAILED.value, "Public futures data fetch failed safely.", issues, public_market_data_used=feed.public_futures_market_data_fetch_used)
        entry = float(feed.primary_latest_close)
        mark = float(feed.mark_price.mark_price if feed.mark_price else feed.primary_latest_close)
        scenario_side = (side or config.default_scenario_side).upper()
        defaulted = []
        if stop_loss is None:
            stop_loss = entry * (1 - config.default_stop_loss_distance_pct / 100) if scenario_side == "LONG" else entry * (1 + config.default_stop_loss_distance_pct / 100)
            defaulted.append("stop_loss")
        if take_profit is None:
            take_profit = entry * (1 + config.default_take_profit_distance_pct / 100) if scenario_side == "LONG" else entry * (1 - config.default_take_profit_distance_pct / 100)
            defaulted.append("take_profit")
        scenario = BTCFuturesRiskScenarioInput(
            side=scenario_side,
            entry_price=entry,
            mark_price=mark,
            stop_loss=float(stop_loss),
            take_profit=float(take_profit),
            notional_value=float(notional or config.default_notional),
            leverage=int(leverage or config.default_leverage),
            account_equity=float(account_equity),
            funding_rate=(feed.funding_info.funding_rate if feed.funding_info else None) or (feed.mark_price.funding_rate if feed.mark_price else None),
            funding_periods=int(config.funding_periods_to_estimate),
            source="live_read_only",
            metadata={"futures_feed_invoked": True, "futures_trade_pipeline_invoked": False, "paper_account_invoked": False, "hypothetical_scenario_only": True, "diagnostic_defaults_used": defaulted},
        )
        result = self.analyze_scenario(scenario, config_path=config_path, expected_profile=expected_profile)
        result.public_market_data_used = feed.public_futures_market_data_fetch_used
        result.metadata.update(scenario.metadata)
        return result

    def compare_leverage(
        self,
        base_scenario: BTCFuturesRiskScenarioInput,
        config_path: str = "configs/btc_futures_risk_model.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCFuturesLeverageComparisonResult:
        config = self.load_config(config_path)
        rows: list[BTCFuturesLeverageComparisonRow] = []
        for leverage in config.allowed_leverage:
            scenario = BTCFuturesRiskScenarioInput(**{**base_scenario.to_dict(), "leverage": int(leverage), "source": base_scenario.source or "comparison"})
            result = self.analyze_scenario(scenario, config_path=config_path, expected_profile=expected_profile)
            calc = result.calculation
            rows.append(
                BTCFuturesLeverageComparisonRow(
                    leverage=int(leverage),
                    status=result.status,
                    decision=result.decision,
                    initial_margin=None if calc is None else calc.initial_margin,
                    estimated_liquidation_price=None if calc is None else calc.estimated_liquidation_price,
                    liquidation_distance_pct=None if calc is None else calc.liquidation_distance_pct,
                    margin_ratio=None if calc is None else calc.margin_ratio,
                    stop_before_liquidation=None if calc is None else calc.stop_before_liquidation,
                    total_funding_estimate=None if calc is None else calc.total_funding_estimate,
                    reason=result.reason,
                )
            )
        accepted = [row for row in rows if row.status in ("PASS", "WARNING")]
        safest = sorted(accepted, key=lambda row: (0 if row.status == "PASS" else 1, -(row.liquidation_distance_pct or 0), -(row.margin_ratio or 0), row.leverage))
        status = "PASS" if any(row.status == "PASS" for row in rows) else "WARNING" if accepted else "FAIL"
        return BTCFuturesLeverageComparisonResult(
            created_at=self._now(),
            symbol=config.symbol,
            side=base_scenario.side,
            entry_price=base_scenario.entry_price,
            mark_price=base_scenario.mark_price,
            stop_loss=base_scenario.stop_loss,
            take_profit=base_scenario.take_profit,
            notional_value=base_scenario.notional_value,
            account_equity=base_scenario.account_equity,
            status=status,
            safest_leverage=None if not safest else safest[0].leverage,
            highest_accepted_leverage=None if not accepted else max(row.leverage for row in accepted),
            rows=rows,
            safety_summary=self._safety_summary(),
        )

    def load_config(self, config_path: str = "configs/btc_futures_risk_model.json") -> BTCFuturesRiskConfig:
        path = self._resolve(config_path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("config JSON must be an object")
        return BTCFuturesRiskConfig(**{**BTCFuturesRiskConfig().to_dict(), **loaded})

    def _validate_config_values(self, config: BTCFuturesRiskConfig, expected_profile: str, issues: list[BTCFuturesRiskIssue], diagnostics: dict[str, Any]) -> None:
        self._expect(config.project_scope == "BTC_ONLY", issues, "project_scope", "project_scope must be BTC_ONLY.")
        self._expect(config.symbol == "BTC/USDT", issues, "symbol", "symbol must be BTC/USDT.")
        self._expect(config.exchange_symbol == "BTCUSDT", issues, "exchange_symbol", "exchange_symbol must be BTCUSDT.")
        self._expect(config.exchange == "binance", issues, "exchange", "exchange must be binance.")
        self._expect(config.market_type == "futures", issues, "market_type", "market_type must be futures.")
        self._expect(config.futures_contract_type == "USDT_PERPETUAL", issues, "futures_contract_type", "futures_contract_type must be USDT_PERPETUAL.")
        self._expect(config.strategy_profile == expected_profile, issues, "strategy_profile", f"strategy_profile must be {expected_profile}.")
        self._expect(config.simulation_only, issues, "simulation_only", "simulation_only must be true.")
        self._expect(config.dry_run_only, issues, "dry_run_only", "dry_run_only must be true.")
        self._expect(config.model_accuracy == "APPROXIMATE_CONSERVATIVE", issues, "model_accuracy", "model_accuracy must be APPROXIMATE_CONSERVATIVE.")
        self._expect(not config.exchange_exact_liquidation, issues, "exchange_exact_liquidation", "exchange_exact_liquidation must remain false.")
        self._expect(config.margin_mode == "isolated", issues, "margin_mode", "margin_mode must be isolated.")
        self._expect(config.position_mode == "one_way", issues, "position_mode", "position_mode must be one_way.")
        self._expect(bool(config.allowed_leverage) and all(isinstance(item, int) and item > 0 for item in config.allowed_leverage), issues, "allowed_leverage", "allowed_leverage must contain positive integers.")
        self._expect(max(config.allowed_leverage or [0]) <= 5 and int(config.max_leverage) <= 5, issues, "max_leverage", "maximum leverage must be <= 5.")
        self._expect(int(config.default_leverage) in config.allowed_leverage, issues, "default_leverage", "default_leverage must be allowed.")
        self._expect(0 < float(config.maintenance_margin_rate) <= 0.02, issues, "maintenance_margin_rate", "maintenance_margin_rate must be > 0 and <= 0.02.")
        self._expect(0 <= float(config.liquidation_fee_reserve_rate) <= 0.02, issues, "liquidation_fee_reserve_rate", "liquidation_fee_reserve_rate must be between 0 and 0.02.")
        self._expect(0 <= float(config.additional_safety_buffer_rate) <= 0.05, issues, "additional_safety_buffer_rate", "additional_safety_buffer_rate must be between 0 and 0.05.")
        self._expect(float(config.min_liquidation_distance_pct) > 0, issues, "min_liquidation_distance_pct", "min liquidation distance must be > 0.")
        self._expect(float(config.warning_liquidation_distance_pct) >= float(config.min_liquidation_distance_pct), issues, "warning_liquidation_distance_pct", "warning distance must be >= minimum distance.")
        self._expect(float(config.max_initial_margin_pct_of_account_equity) > 0, issues, "max_initial_margin_pct_of_account_equity", "max margin percentage must be positive.")
        self._expect(float(config.max_notional_pct_of_account_equity) > 0, issues, "max_notional_pct_of_account_equity", "max notional percentage must be positive.")
        for name in ("allow_leverage_simulation", "allow_liquidation_modeling", "allow_margin_calculation", "allow_funding_estimation", "allow_scenario_comparison", "allow_public_futures_market_data_fetch", "allow_public_mark_price_fetch", "allow_public_funding_fetch"):
            self._expect(bool(getattr(config, name)), issues, name, f"{name} must be true for local diagnostics.")
        for name in (
            "allow_real_leverage_change", "allow_exchange_margin_mode_change", "allow_private_api", "allow_api_key_usage", "allow_trading_api",
            "allow_account_data", "allow_balance_fetch", "allow_position_fetch", "allow_order_submission", "allow_order_cancellation",
            "allow_real_position_creation", "allow_paper_futures_position_creation", "allow_paper_trade_persistence", "allow_executable_trade_creation",
            "allow_paper_account_state_mutation", "allow_runner_state_mutation", "allow_execution_state_mutation",
        ):
            self._expect(not bool(getattr(config, name)), issues, name, f"{name} must remain false.")
        self._validate_report_dir(config.report_export_dir, "report_export_dir", issues)
        self._validate_dependencies(config, expected_profile, issues, diagnostics)

    def _validate_dependencies(self, config: BTCFuturesRiskConfig, expected_profile: str, issues: list[BTCFuturesRiskIssue], diagnostics: dict[str, Any]) -> None:
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
        runner_fail_count = sum(1 for issue in runner_issues if issue.severity == "FAIL")
        diagnostics["runner_config_status"] = "FAIL" if runner_fail_count else "PASS"
        if config.require_runner_config_pass and runner_fail_count:
            issues.append(self._issue("runner_config_validation", "FAIL", "Runner config must validate PASS."))
        feed = self.futures_feed_engine.validate(config.futures_read_only_feed_config_path, expected_profile=expected_profile)
        diagnostics["futures_feed_config_status"] = feed.status
        if config.require_futures_feed_config_pass and feed.status != "PASS":
            issues.append(self._issue("futures_feed_config_validation", "FAIL", "Futures read-only feed config must validate PASS."))
        paper = self.paper_account_engine.validate(config.paper_account_config_path, expected_profile=expected_profile)
        diagnostics["paper_account_config_status"] = paper.status
        if config.require_paper_account_config_pass and paper.status != "PASS":
            issues.append(self._issue("paper_account_config_validation", "FAIL", "Paper account config must validate PASS."))

    def _validate_scenario(self, config: BTCFuturesRiskConfig, scenario: BTCFuturesRiskScenarioInput) -> tuple[list[BTCFuturesRiskIssue], str]:
        issues: list[BTCFuturesRiskIssue] = []
        side = str(scenario.side).upper()
        if side not in ("LONG", "SHORT"):
            issues.append(self._issue("side", "FAIL", "side must be LONG or SHORT."))
            return issues, BTCFuturesRiskDecision.INVALID_SCENARIO.value
        if int(scenario.leverage) not in config.allowed_leverage or int(scenario.leverage) > int(config.max_leverage):
            issues.append(self._issue("leverage", "FAIL", "leverage is not allowed."))
            return issues, BTCFuturesRiskDecision.REJECT_LEVERAGE_NOT_ALLOWED.value
        for name in ("entry_price", "mark_price", "stop_loss", "take_profit", "notional_value", "account_equity"):
            if _float_or_none(getattr(scenario, name)) is None or float(getattr(scenario, name)) <= 0:
                issues.append(self._issue(name, "FAIL", f"{name} must be positive."))
                return issues, BTCFuturesRiskDecision.INVALID_SCENARIO.value
        if side == "LONG" and scenario.stop_loss >= scenario.entry_price:
            issues.append(self._issue("long_stop_loss", "FAIL", "LONG stop_loss must be below entry_price."))
        if side == "LONG" and scenario.take_profit <= scenario.entry_price:
            issues.append(self._issue("long_take_profit", "FAIL", "LONG take_profit must be above entry_price."))
        if side == "SHORT" and scenario.stop_loss <= scenario.entry_price:
            issues.append(self._issue("short_stop_loss", "FAIL", "SHORT stop_loss must be above entry_price."))
        if side == "SHORT" and scenario.take_profit >= scenario.entry_price:
            issues.append(self._issue("short_take_profit", "FAIL", "SHORT take_profit must be below entry_price."))
        return issues, BTCFuturesRiskDecision.INVALID_SCENARIO.value if issues else BTCFuturesRiskDecision.SAFE_SIMULATION.value

    def _calculate(self, config: BTCFuturesRiskConfig, scenario: BTCFuturesRiskScenarioInput) -> BTCFuturesRiskCalculation:
        side = scenario.side.upper()
        entry = float(scenario.entry_price)
        mark = float(scenario.mark_price)
        notional = float(scenario.notional_value)
        leverage = int(scenario.leverage)
        quantity = notional / entry
        initial_margin = notional / leverage
        initial_margin_pct = (initial_margin / float(scenario.account_equity)) * 100
        effective_rate = float(config.maintenance_margin_rate) + float(config.liquidation_fee_reserve_rate) + float(config.additional_safety_buffer_rate)
        if side == "LONG":
            unrealized = quantity * (mark - entry)
            denominator = 1 - effective_rate
            liq = entry * (1 - 1 / leverage) / denominator
            bankruptcy = entry * (1 - 1 / leverage)
            liquidation_distance_value = mark - liq
            stop_before_liq = scenario.stop_loss > liq
            liquidation_buffer_after_stop_pct = ((scenario.stop_loss - liq) / mark) * 100
            risk = quantity * (entry - scenario.stop_loss)
            reward = quantity * (scenario.take_profit - entry)
        else:
            unrealized = quantity * (entry - mark)
            denominator = 1 + effective_rate
            liq = entry * (1 + 1 / leverage) / denominator
            bankruptcy = entry * (1 + 1 / leverage)
            liquidation_distance_value = liq - mark
            stop_before_liq = scenario.stop_loss < liq
            liquidation_buffer_after_stop_pct = ((liq - scenario.stop_loss) / mark) * 100
            risk = quantity * (scenario.stop_loss - entry)
            reward = quantity * (entry - scenario.take_profit)
        maintenance = quantity * mark * float(config.maintenance_margin_rate)
        reserve = quantity * mark * float(config.liquidation_fee_reserve_rate)
        equity_at_mark = initial_margin + unrealized
        required_margin = maintenance + reserve
        margin_ratio = None if required_margin <= 0 else equity_at_mark / required_margin
        liquidation_distance_pct = (liquidation_distance_value / mark) * 100
        stop_distance = abs(entry - scenario.stop_loss)
        take_profit_distance = abs(scenario.take_profit - entry)
        funding_per_period = self._funding_payment(scenario)
        total_funding = None if funding_per_period is None else funding_per_period * int(scenario.funding_periods)
        return BTCFuturesRiskCalculation(
            quantity=quantity,
            notional_value=notional,
            leverage=leverage,
            initial_margin=initial_margin,
            initial_margin_pct_of_equity=initial_margin_pct,
            maintenance_margin_at_mark=maintenance,
            liquidation_fee_reserve_at_mark=reserve,
            effective_maintenance_rate=effective_rate,
            estimated_liquidation_price=liq,
            bankruptcy_price_estimate=bankruptcy,
            liquidation_distance_value=liquidation_distance_value,
            liquidation_distance_pct=liquidation_distance_pct,
            stop_distance_value=stop_distance,
            stop_distance_pct=(stop_distance / entry) * 100,
            take_profit_distance_value=take_profit_distance,
            take_profit_distance_pct=(take_profit_distance / entry) * 100,
            risk_amount_to_stop=risk,
            reward_amount_to_take_profit=reward,
            risk_reward_ratio=0.0 if risk <= 0 else reward / risk,
            unrealized_pnl_at_mark=unrealized,
            equity_at_mark=equity_at_mark,
            margin_ratio=margin_ratio,
            funding_payment_per_period=funding_per_period,
            total_funding_estimate=total_funding,
            stop_before_liquidation=stop_before_liq,
            liquidation_buffer_after_stop_pct=liquidation_buffer_after_stop_pct,
            model_accuracy=config.model_accuracy,
            assumptions=[
                "APPROXIMATE_CONSERVATIVE simplified isolated linear model.",
                "Exchange-specific maintenance margin tiers are not modeled.",
                "Cross-margin wallet effects and private leverage brackets are not modeled.",
                "No order, position, leverage, margin mode, or account state is mutated.",
            ],
            metadata={"margin_mode": config.margin_mode, "position_mode": config.position_mode},
        )

    def _decision(self, config: BTCFuturesRiskConfig, scenario: BTCFuturesRiskScenarioInput, calc: BTCFuturesRiskCalculation) -> tuple[str, str, str, list[BTCFuturesRiskIssue]]:
        issues: list[BTCFuturesRiskIssue] = []
        if not calc.stop_before_liquidation:
            issues.append(self._issue("stop_beyond_liquidation", "FAIL", "Stop loss is beyond or equal to estimated liquidation price."))
            return "FAIL", BTCFuturesRiskDecision.REJECT_STOP_BEYOND_LIQUIDATION.value, "Stop loss is not safely before estimated liquidation.", issues
        if calc.liquidation_distance_pct <= float(config.min_liquidation_distance_pct):
            issues.append(self._issue("liquidation_distance", "FAIL", "Liquidation distance is below minimum threshold."))
            return "FAIL", BTCFuturesRiskDecision.REJECT_LIQUIDATION_TOO_CLOSE.value, "Estimated liquidation is too close.", issues
        if calc.initial_margin_pct_of_equity > float(config.max_initial_margin_pct_of_account_equity):
            issues.append(self._issue("initial_margin_limit", "FAIL", "Initial margin exceeds configured account-equity percentage."))
            return "FAIL", BTCFuturesRiskDecision.REJECT_MARGIN_LIMIT.value, "Initial margin exceeds risk limit.", issues
        if (calc.notional_value / scenario.account_equity) * 100 > float(config.max_notional_pct_of_account_equity):
            issues.append(self._issue("notional_limit", "FAIL", "Notional exceeds configured account-equity percentage."))
            return "FAIL", BTCFuturesRiskDecision.REJECT_NOTIONAL_LIMIT.value, "Notional exceeds risk limit.", issues
        min_rr = self._min_risk_reward(config)
        if calc.risk_reward_ratio < min_rr:
            issues.append(self._issue("risk_reward", "FAIL", "Risk/reward is below configured minimum.", {"risk_reward_ratio": calc.risk_reward_ratio, "minimum": min_rr}))
            return "FAIL", BTCFuturesRiskDecision.REJECT_INVALID_RISK_REWARD.value, "Risk/reward is below configured minimum.", issues
        if calc.liquidation_distance_pct < float(config.warning_liquidation_distance_pct):
            issues.append(self._issue("liquidation_distance_warning", "WARNING", "Liquidation distance is in the warning band."))
            return "WARNING", BTCFuturesRiskDecision.WARNING_LIQUIDATION_DISTANCE.value, "Estimated liquidation distance is above minimum but below warning threshold.", issues
        if calc.total_funding_estimate is not None and calc.total_funding_estimate < -(calc.notional_value * 0.001):
            issues.append(self._issue("funding_cost_warning", "WARNING", "Estimated funding cost is material."))
            return "WARNING", BTCFuturesRiskDecision.WARNING_FUNDING_COST.value, "Estimated funding cost is material.", issues
        return "PASS", BTCFuturesRiskDecision.SAFE_SIMULATION.value, "Hypothetical futures risk scenario passed conservative diagnostics.", issues

    def _funding_payment(self, scenario: BTCFuturesRiskScenarioInput) -> float | None:
        if scenario.funding_rate is None:
            return None
        absolute = float(scenario.notional_value) * abs(float(scenario.funding_rate))
        positive_rate = float(scenario.funding_rate) > 0
        if scenario.side.upper() == "LONG":
            return -absolute if positive_rate else absolute
        return absolute if positive_rate else -absolute

    def _min_risk_reward(self, config: BTCFuturesRiskConfig) -> float:
        try:
            return float(self.runtime_config_engine.load_config(config.runtime_config_path).min_risk_reward)
        except Exception:
            return 1.5

    def _result(self, config: BTCFuturesRiskConfig, scenario: BTCFuturesRiskScenarioInput, calculation: BTCFuturesRiskCalculation | None, status: str, decision: str, reason: str, issues: list[BTCFuturesRiskIssue], public_market_data_used: bool = False) -> BTCFuturesRiskResult:
        return BTCFuturesRiskResult(
            created_at=self._now(),
            project_scope=config.project_scope,
            symbol=config.symbol,
            exchange_symbol=config.exchange_symbol,
            market_type=config.market_type,
            futures_contract_type=config.futures_contract_type,
            strategy_profile=config.strategy_profile,
            status=status,
            decision=decision,
            reason=reason,
            scenario=scenario,
            calculation=calculation,
            dry_run_only=True,
            simulation_only=True,
            model_name=config.model_name,
            model_accuracy=config.model_accuracy,
            exchange_exact_liquidation=False,
            public_market_data_used=public_market_data_used,
            issues=issues,
            safety_summary=self._safety_summary(),
            metadata={"hypothetical_scenario_only": True, **dict(scenario.metadata)},
        )

    def _safety_summary(self) -> dict[str, Any]:
        return {
            "private_api_used": False,
            "api_key_used": False,
            "trading_api_used": False,
            "account_data_used": False,
            "balance_fetch_used": False,
            "position_fetch_used": False,
            "exchange_leverage_changed": False,
            "exchange_margin_mode_changed": False,
            "order_submitted": False,
            "order_cancelled": False,
            "real_position_created": False,
            "paper_futures_position_created": False,
            "paper_trade_persisted": False,
            "executable_trade_created": False,
            "paper_account_state_mutated": False,
            "runner_state_mutated": False,
            "execution_state_mutated": False,
        }

    def _validate_report_dir(self, value: str, name: str, issues: list[BTCFuturesRiskIssue]) -> None:
        path = Path(value)
        if path.is_absolute():
            issues.append(self._issue(name, "FAIL", f"{name} must be a safe relative path under reports/futures_risk_model."))
            return
        parts = path.parts
        self._expect(len(parts) >= 2 and parts[0] == "reports" and parts[1] == "futures_risk_model" and ".." not in parts, issues, name, f"{name} must be under reports/futures_risk_model.")

    def _report(self, config_path: str, config: BTCFuturesRiskConfig | None, issues: list[BTCFuturesRiskIssue], diagnostics: dict[str, Any]) -> BTCFuturesRiskValidationReport:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        return BTCFuturesRiskValidationReport(
            config_path=config_path,
            created_at=self._now(),
            status="FAIL" if failures else "WARNING" if warnings else "PASS",
            issue_count=len(issues),
            warning_count=warnings,
            fail_count=failures,
            config=config,
            issues=issues,
            diagnostics=diagnostics,
        )

    def _expect(self, condition: bool, issues: list[BTCFuturesRiskIssue], name: str, message: str) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message))

    def _issue(self, name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> BTCFuturesRiskIssue:
        return BTCFuturesRiskIssue(name=name, severity=severity, message=message, details=details or {})

    def _resolve(self, path_text: str) -> Path:
        path = Path(path_text)
        if not path.is_absolute():
            path = self.repo_root / path
        return path

    def _now(self) -> str:
        if self.now_provider is not None:
            return str(self.now_provider())
        return datetime.now(UTC).replace(microsecond=0).isoformat()


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
