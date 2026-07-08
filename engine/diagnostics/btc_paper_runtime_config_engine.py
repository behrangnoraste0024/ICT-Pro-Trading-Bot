from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from models.btc_paper_runtime_config import (
    BTCPaperRuntimeConfig,
    BTCPaperRuntimeConfigIssue,
    BTCPaperRuntimeConfigValidationReport,
)


class BTCPaperRuntimeConfigEngine:
    def __init__(self, repo_root: str | Path | None = None) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)

    def validate(
        self,
        config_path: str = "configs/btc_paper_runtime.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCPaperRuntimeConfigValidationReport:
        path = self._resolve(config_path)
        issues: list[BTCPaperRuntimeConfigIssue] = []
        config: BTCPaperRuntimeConfig | None = None
        if not path.exists():
            issues.append(self._issue("config_missing", "FAIL", "BTC paper runtime config is missing.", {"config_path": str(path)}))
            return self._report(config_path, config, issues)
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("config JSON must be an object")
            config = BTCPaperRuntimeConfig(**{**BTCPaperRuntimeConfig().to_dict(), **loaded})
        except Exception as exc:
            issues.append(self._issue("config_invalid", "FAIL", f"BTC paper runtime config could not be loaded: {exc}", {"config_path": str(path)}))
            return self._report(config_path, config, issues)

        self._validate_values(config, expected_profile, issues)
        return self._report(config_path, config, issues)

    def _validate_values(
        self,
        config: BTCPaperRuntimeConfig,
        expected_profile: str,
        issues: list[BTCPaperRuntimeConfigIssue],
    ) -> None:
        self._expect(config.project_scope == "BTC_ONLY", issues, "project_scope", "project_scope must be BTC_ONLY.", {"project_scope": config.project_scope})
        self._expect(config.symbol == "BTC/USDT", issues, "symbol", "symbol must be BTC/USDT.", {"symbol": config.symbol})
        self._expect(config.strategy_profile == expected_profile, issues, "strategy_profile", f"strategy_profile must be {expected_profile}.", {"strategy_profile": config.strategy_profile, "expected_profile": expected_profile})
        self._expect(config.sample_scope in ("required_full", "btc_only"), issues, "sample_scope", "sample_scope must be required_full or btc_only.", {"sample_scope": config.sample_scope})
        self._expect(config.primary_timeframe == "15m", issues, "primary_timeframe", "primary_timeframe must be 15m.", {"primary_timeframe": config.primary_timeframe})
        self._expect(config.confirmation_timeframe == "1h", issues, "confirmation_timeframe", "confirmation_timeframe must be 1h.", {"confirmation_timeframe": config.confirmation_timeframe})
        self._expect(not config.live_trading_enabled, issues, "live_trading_enabled", "live_trading_enabled must remain false.")
        self._expect(not config.order_submission_enabled, issues, "order_submission_enabled", "order_submission_enabled must remain false.")
        self._expect(not config.paper_execution_enabled, issues, "paper_execution_enabled", "paper_execution_enabled must remain false for this pre-execution release.")
        self._expect(config.dry_run, issues, "dry_run", "dry_run must remain true.")
        self._expect(config.kill_switch_enabled, issues, "kill_switch_enabled", "kill_switch_enabled must be true.")
        self._expect(config.risk_per_trade_pct > 0, issues, "risk_per_trade_pct", "risk_per_trade_pct must be greater than 0.", {"risk_per_trade_pct": config.risk_per_trade_pct})
        self._expect(config.risk_per_trade_pct <= config.max_risk_per_trade_pct, issues, "risk_per_trade_pct_limit", "risk_per_trade_pct must be <= max_risk_per_trade_pct.", {"risk_per_trade_pct": config.risk_per_trade_pct, "max_risk_per_trade_pct": config.max_risk_per_trade_pct})
        self._expect(config.max_risk_per_trade_pct <= 0.01, issues, "max_risk_per_trade_pct", "max_risk_per_trade_pct must be <= 1%.", {"max_risk_per_trade_pct": config.max_risk_per_trade_pct})
        self._expect(config.max_daily_loss_pct <= 0.03, issues, "max_daily_loss_pct", "max_daily_loss_pct must be <= 3%.", {"max_daily_loss_pct": config.max_daily_loss_pct})
        self._expect(config.max_total_drawdown_pct <= 0.10, issues, "max_total_drawdown_pct", "max_total_drawdown_pct must be <= 10%.", {"max_total_drawdown_pct": config.max_total_drawdown_pct})
        self._expect(config.max_open_positions <= 1, issues, "max_open_positions", "max_open_positions must be <= 1 for BTC paper preparation.", {"max_open_positions": config.max_open_positions})
        self._expect(config.max_trades_per_day <= 5, issues, "max_trades_per_day", "max_trades_per_day must be <= 5.", {"max_trades_per_day": config.max_trades_per_day})
        self._expect(config.min_trade_interval_minutes >= 5, issues, "min_trade_interval_minutes", "min_trade_interval_minutes must be >= 5.", {"min_trade_interval_minutes": config.min_trade_interval_minutes})
        self._expect(config.max_position_notional_pct <= 0.30, issues, "max_position_notional_pct", "max_position_notional_pct must be <= 30%.", {"max_position_notional_pct": config.max_position_notional_pct})
        self._expect(config.min_risk_reward >= 1.5, issues, "min_risk_reward", "min_risk_reward must be >= 1.5.", {"min_risk_reward": config.min_risk_reward})
        self._expect(config.require_stop_loss, issues, "require_stop_loss", "require_stop_loss must be true.")
        self._expect(config.require_take_profit, issues, "require_take_profit", "require_take_profit must be true.")
        self._expect(config.allow_long or config.allow_short, issues, "direction_allowed", "At least one of allow_long or allow_short must be true.", {"allow_long": config.allow_long, "allow_short": config.allow_short})
        if config.enabled:
            issues.append(self._issue("enabled", "WARNING", "enabled is true, but execution flags remain disabled. Keep this false until a paper runner release.", {"enabled": config.enabled}))

    def _expect(
        self,
        condition: bool,
        issues: list[BTCPaperRuntimeConfigIssue],
        name: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message, details))

    def _report(
        self,
        config_path: str,
        config: BTCPaperRuntimeConfig | None,
        issues: list[BTCPaperRuntimeConfigIssue],
    ) -> BTCPaperRuntimeConfigValidationReport:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        status = "FAIL" if failures else "WARNING" if warnings else "PASS"
        return BTCPaperRuntimeConfigValidationReport(
            config_path=config_path,
            created_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
            status=status,
            issue_count=len(issues),
            warning_count=warnings,
            fail_count=failures,
            config=config,
            issues=issues,
        )

    def _resolve(self, config_path: str) -> Path:
        path = Path(config_path)
        if not path.is_absolute():
            path = self.repo_root / path
        return path

    def _issue(
        self,
        name: str,
        severity: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> BTCPaperRuntimeConfigIssue:
        return BTCPaperRuntimeConfigIssue(name=name, severity=severity, message=message, details=details or {})
