from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from engine.diagnostics.btc_live_market_feed_engine import BTCLiveMarketFeedEngine
from engine.diagnostics.btc_paper_account_engine import BTCPaperAccountEngine
from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine
from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from models.btc_futures_read_only_feed import (
    BTCFuturesFundingInfo,
    BTCFuturesMarkPrice,
    BTCFuturesReadOnlyCandle,
    BTCFuturesReadOnlyFeedConfig,
    BTCFuturesReadOnlyFeedResult,
    BTCFuturesReadOnlyFeedStatus,
    BTCFuturesReadOnlyIssue,
    BTCFuturesReadOnlyObservationDecision,
    BTCFuturesReadOnlyObservationResult,
    BTCFuturesReadOnlyValidationReport,
)


class BinancePublicFuturesReadOnlyAdapter:
    """Public Binance USD-M futures market-data adapter. No credentials are accepted."""

    BASE_URL = "https://fapi.binance.com"

    def fetch_ohlcv(self, exchange_symbol: str, timeframe: str, limit: int, timeout_seconds: int) -> list[BTCFuturesReadOnlyCandle]:
        query = urlencode({"symbol": exchange_symbol.upper(), "interval": timeframe, "limit": int(limit)})
        with urlopen(f"{self.BASE_URL}/fapi/v1/klines?{query}", timeout=timeout_seconds) as response:  # nosec B310 - public futures market-data endpoint only.
            payload = json.loads(response.read().decode("utf-8"))
        candles: list[BTCFuturesReadOnlyCandle] = []
        for row in payload:
            if not isinstance(row, list) or len(row) < 6:
                continue
            candles.append(
                BTCFuturesReadOnlyCandle(
                    timestamp=_ms_to_iso(row[0]),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            )
        return candles

    def fetch_mark_price(self, exchange_symbol: str, timeout_seconds: int) -> BTCFuturesMarkPrice:
        query = urlencode({"symbol": exchange_symbol.upper()})
        with urlopen(f"{self.BASE_URL}/fapi/v1/premiumIndex?{query}", timeout=timeout_seconds) as response:  # nosec B310 - public futures market-data endpoint only.
            payload = json.loads(response.read().decode("utf-8"))
        return BTCFuturesMarkPrice(
            symbol=str(payload.get("symbol", exchange_symbol.upper())),
            mark_price=float(payload["markPrice"]),
            index_price=_float_or_none(payload.get("indexPrice")),
            estimated_settle_price=_float_or_none(payload.get("estimatedSettlePrice")),
            funding_rate=_float_or_none(payload.get("lastFundingRate")),
            next_funding_time=_ms_to_iso(payload.get("nextFundingTime")),
            timestamp=_ms_to_iso(payload.get("time")),
            metadata=dict(payload),
        )

    def fetch_funding_info(self, exchange_symbol: str, timeout_seconds: int) -> BTCFuturesFundingInfo:
        query = urlencode({"symbol": exchange_symbol.upper(), "limit": 1})
        with urlopen(f"{self.BASE_URL}/fapi/v1/fundingRate?{query}", timeout=timeout_seconds) as response:  # nosec B310 - public futures market-data endpoint only.
            payload = json.loads(response.read().decode("utf-8"))
        latest = payload[-1] if isinstance(payload, list) and payload else {}
        return BTCFuturesFundingInfo(
            symbol=str(latest.get("symbol", exchange_symbol.upper())),
            funding_rate=_float_or_none(latest.get("fundingRate")),
            funding_time=_ms_to_iso(latest.get("fundingTime")),
            next_funding_time=None,
            metadata=dict(latest),
        )


class BTCFuturesReadOnlyFeedEngine:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        runtime_config_engine: BTCPaperRuntimeConfigEngine | None = None,
        monitoring_engine: BTCPaperMonitoringEngine | None = None,
        runner_engine: BTCPaperRunnerEngine | None = None,
        live_market_feed_engine: BTCLiveMarketFeedEngine | None = None,
        paper_account_engine: BTCPaperAccountEngine | None = None,
        market_data_adapter: Any | None = None,
        now_provider=None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.runtime_config_engine = runtime_config_engine or BTCPaperRuntimeConfigEngine(repo_root=self.repo_root)
        self.monitoring_engine = monitoring_engine or BTCPaperMonitoringEngine(repo_root=self.repo_root)
        self.runner_engine = runner_engine or BTCPaperRunnerEngine(repo_root=self.repo_root)
        self.live_market_feed_engine = live_market_feed_engine or BTCLiveMarketFeedEngine(repo_root=self.repo_root)
        self.paper_account_engine = paper_account_engine or BTCPaperAccountEngine(repo_root=self.repo_root)
        self.market_data_adapter = market_data_adapter or BinancePublicFuturesReadOnlyAdapter()
        self.now_provider = now_provider

    def validate(
        self,
        config_path: str = "configs/btc_futures_read_only_feed.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCFuturesReadOnlyValidationReport:
        issues: list[BTCFuturesReadOnlyIssue] = []
        diagnostics: dict[str, Any] = {
            "runtime_config_status": "UNKNOWN",
            "monitoring_config_status": "UNKNOWN",
            "runner_config_status": "UNKNOWN",
            "live_market_feed_config_status": "UNKNOWN",
            "paper_account_config_status": "UNKNOWN",
            "kill_switch_enabled": None,
        }
        config: BTCFuturesReadOnlyFeedConfig | None = None
        try:
            config = self.load_config(config_path)
        except Exception as exc:
            issues.append(self._issue("config_invalid", "FAIL", f"BTC futures read-only feed config could not be loaded: {exc}", {"config_path": config_path}))
            return self._report(config_path, config, issues, diagnostics)
        self._validate_config_values(config, expected_profile, issues, diagnostics)
        return self._report(config_path, config, issues, diagnostics)

    def fetch_once(
        self,
        config_path: str = "configs/btc_futures_read_only_feed.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCFuturesReadOnlyFeedResult:
        report = self.validate(config_path=config_path, expected_profile=expected_profile)
        config = report.config or BTCFuturesReadOnlyFeedConfig()
        issues = list(report.issues)
        primary: list[BTCFuturesReadOnlyCandle] = []
        confirmation: list[BTCFuturesReadOnlyCandle] = []
        mark_price: BTCFuturesMarkPrice | None = None
        funding_info: BTCFuturesFundingInfo | None = None
        if report.status != BTCFuturesReadOnlyFeedStatus.FAIL.value:
            primary, primary_issues = self._fetch_candles(config, config.primary_timeframe, config.primary_limit, config.min_primary_candles, "primary")
            confirmation, confirmation_issues = self._fetch_candles(config, config.confirmation_timeframe, config.confirmation_limit, config.min_confirmation_candles, "confirmation")
            mark_price, mark_issues = self._fetch_mark_price(config)
            funding_info, funding_issues = self._fetch_funding_info(config)
            issues.extend(primary_issues)
            issues.extend(confirmation_issues)
            issues.extend(mark_issues)
            issues.extend(funding_issues)
        return self._feed_result(config, primary, confirmation, mark_price, funding_info, issues)

    def observe_once(
        self,
        config_path: str = "configs/btc_futures_read_only_feed.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCFuturesReadOnlyObservationResult:
        feed = self.fetch_once(config_path=config_path, expected_profile=expected_profile)
        config = self.load_config(config_path) if self._resolve(config_path).exists() else BTCFuturesReadOnlyFeedConfig()
        if feed.status == BTCFuturesReadOnlyFeedStatus.FAIL.value:
            decision = BTCFuturesReadOnlyObservationDecision.FUTURES_FEED_FAILED.value
            reason = "Public futures read-only market data feed failed safely."
            status = "FAIL"
        elif feed.funding_info and feed.funding_info.funding_rate is not None:
            decision = BTCFuturesReadOnlyObservationDecision.FUTURES_FEED_OK_FUNDING_AVAILABLE.value
            reason = "Public futures candles, mark price, and funding metadata were fetched read-only."
            status = feed.status
        elif feed.mark_price is not None:
            decision = BTCFuturesReadOnlyObservationDecision.FUTURES_FEED_OK_MARK_PRICE_ONLY.value
            reason = "Public futures candles and mark price were fetched read-only; funding metadata unavailable."
            status = feed.status
        else:
            decision = BTCFuturesReadOnlyObservationDecision.FUTURES_FEED_WARNING.value
            reason = "Public futures read-only feed completed with missing optional diagnostics."
            status = feed.status
        return BTCFuturesReadOnlyObservationResult(
            created_at=self._now(),
            project_scope=config.project_scope,
            symbol=config.symbol,
            exchange_symbol=config.exchange_symbol,
            exchange=config.exchange,
            market_type=config.market_type,
            futures_contract_type=config.futures_contract_type,
            strategy_profile=config.strategy_profile,
            status=status,
            decision=decision,
            feed_status=feed.status,
            primary_candles=feed.primary_candles,
            confirmation_candles=feed.confirmation_candles,
            primary_latest_timestamp=feed.primary_latest_timestamp,
            confirmation_latest_timestamp=feed.confirmation_latest_timestamp,
            primary_latest_close=feed.primary_latest_close,
            confirmation_latest_close=feed.confirmation_latest_close,
            mark_price_value=None if feed.mark_price is None else feed.mark_price.mark_price,
            funding_rate=None if feed.funding_info is None else feed.funding_info.funding_rate,
            next_funding_time=(feed.mark_price.next_funding_time if feed.mark_price else None) or (feed.funding_info.next_funding_time if feed.funding_info else None),
            reason=reason,
            dry_run_only=True,
            public_futures_market_data_fetch_used=feed.public_futures_market_data_fetch_used,
            public_futures_mark_price_fetch_used=feed.public_futures_mark_price_fetch_used,
            public_futures_funding_fetch_used=feed.public_futures_funding_fetch_used,
            private_api_used=False,
            api_key_used=False,
            trading_api_used=False,
            account_data_used=False,
            balance_fetch_used=False,
            position_fetch_used=False,
            order_submitted=False,
            order_cancelled=False,
            real_position_created=False,
            paper_position_created=False,
            leverage_used=False,
            leverage_simulation_used=False,
            liquidation_modeling_used=False,
            executable_trade_created=False,
            exchange_connected_for_trading=False,
            runner_state_mutated=False,
            execution_state_mutated=False,
            safety_summary=self._safety_summary(feed),
            issues=list(feed.issues),
            metadata={
                "leverage_model_available": False,
                "liquidation_model_available": False,
                "paper_futures_position_created": False,
                "futures_trade_pipeline_invoked": False,
                "adapter": feed.metadata.get("adapter", "binance_public_futures_read_only"),
            },
        )

    def load_config(self, config_path: str = "configs/btc_futures_read_only_feed.json") -> BTCFuturesReadOnlyFeedConfig:
        path = self._resolve(config_path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("config JSON must be an object")
        return BTCFuturesReadOnlyFeedConfig(**{**BTCFuturesReadOnlyFeedConfig().to_dict(), **loaded})

    def _validate_config_values(self, config: BTCFuturesReadOnlyFeedConfig, expected_profile: str, issues: list[BTCFuturesReadOnlyIssue], diagnostics: dict[str, Any]) -> None:
        self._expect(config.project_scope == "BTC_ONLY", issues, "project_scope", "project_scope must be BTC_ONLY.", {"project_scope": config.project_scope})
        self._expect(config.symbol == "BTC/USDT", issues, "symbol", "symbol must be BTC/USDT.", {"symbol": config.symbol})
        self._expect(config.exchange_symbol == "BTCUSDT", issues, "exchange_symbol", "exchange_symbol must be BTCUSDT.", {"exchange_symbol": config.exchange_symbol})
        self._expect(config.exchange == "binance", issues, "exchange", "exchange must be binance.", {"exchange": config.exchange})
        self._expect(config.market_type == "futures", issues, "market_type", "market_type must be futures.", {"market_type": config.market_type})
        self._expect(config.futures_contract_type == "USDT_PERPETUAL", issues, "futures_contract_type", "futures_contract_type must be USDT_PERPETUAL.", {"futures_contract_type": config.futures_contract_type})
        self._expect(config.strategy_profile == expected_profile, issues, "strategy_profile", f"strategy_profile must be {expected_profile}.", {"strategy_profile": config.strategy_profile})
        self._expect(config.primary_timeframe == "15m", issues, "primary_timeframe", "primary_timeframe must be 15m.", {"primary_timeframe": config.primary_timeframe})
        self._expect(config.confirmation_timeframe == "1h", issues, "confirmation_timeframe", "confirmation_timeframe must be 1h.", {"confirmation_timeframe": config.confirmation_timeframe})
        self._expect(100 <= int(config.primary_limit) <= 1000, issues, "primary_limit", "primary_limit must be between 100 and 1000.", {"primary_limit": config.primary_limit})
        self._expect(100 <= int(config.confirmation_limit) <= 1000, issues, "confirmation_limit", "confirmation_limit must be between 100 and 1000.", {"confirmation_limit": config.confirmation_limit})
        self._expect(int(config.min_primary_candles) <= int(config.primary_limit), issues, "min_primary_candles", "min_primary_candles must be <= primary_limit.", {"min_primary_candles": config.min_primary_candles})
        self._expect(int(config.min_confirmation_candles) <= int(config.confirmation_limit), issues, "min_confirmation_candles", "min_confirmation_candles must be <= confirmation_limit.", {"min_confirmation_candles": config.min_confirmation_candles})
        self._expect(1 <= int(config.request_timeout_seconds) <= 30, issues, "request_timeout_seconds", "request_timeout_seconds must be between 1 and 30.", {"request_timeout_seconds": config.request_timeout_seconds})
        self._expect(0 <= int(config.max_fetch_retries) <= 3, issues, "max_fetch_retries", "max_fetch_retries must be between 0 and 3.", {"max_fetch_retries": config.max_fetch_retries})
        self._expect(config.observation_mode == "fetch_once", issues, "observation_mode", "observation_mode must be fetch_once.", {"observation_mode": config.observation_mode})
        self._expect(config.closed_candles_only in (True, False), issues, "closed_candles_only", "closed_candles_only must be boolean.")
        self._expect(config.feed_enabled in (True, False), issues, "feed_enabled", "feed_enabled must be boolean.")
        self._expect(config.dry_run_only, issues, "dry_run_only", "dry_run_only must be true.")
        self._expect(config.allow_public_futures_market_data_fetch, issues, "allow_public_futures_market_data_fetch", "public futures market data fetch must be explicitly allowed.")
        self._expect(config.allow_public_futures_mark_price_fetch, issues, "allow_public_futures_mark_price_fetch", "public futures mark price fetch must be explicitly allowed.")
        self._expect(config.allow_public_futures_funding_fetch, issues, "allow_public_futures_funding_fetch", "public futures funding fetch must be explicitly allowed.")
        for name in (
            "allow_private_api",
            "allow_api_key_usage",
            "allow_trading_api",
            "allow_account_data",
            "allow_balance_fetch",
            "allow_position_fetch",
            "allow_order_submission",
            "allow_order_cancellation",
            "allow_real_position_creation",
            "allow_paper_position_creation",
            "allow_leverage",
            "allow_leverage_simulation",
            "allow_liquidation_modeling",
            "allow_paper_trade_persistence",
            "allow_executable_trade_creation",
            "allow_runner_state_mutation",
            "allow_execution_state_mutation",
        ):
            self._expect(not bool(getattr(config, name)), issues, name, f"{name} must remain false.")
        self._validate_report_dir(config.status_export_dir, "status_export_dir", issues)
        self._validate_dependencies(config, expected_profile, issues, diagnostics)

    def _validate_dependencies(self, config: BTCFuturesReadOnlyFeedConfig, expected_profile: str, issues: list[BTCFuturesReadOnlyIssue], diagnostics: dict[str, Any]) -> None:
        runtime = self.runtime_config_engine.validate(config.runtime_config_path, expected_profile=expected_profile)
        diagnostics["runtime_config_status"] = runtime.status
        diagnostics["kill_switch_enabled"] = bool(getattr(runtime.config, "kill_switch_enabled", False))
        if config.require_runtime_config_pass and runtime.status != "PASS":
            issues.append(self._issue("runtime_config_validation", "FAIL", "Runtime config must validate PASS.", {"runtime_config_status": runtime.status}))
        if runtime.config is not None and config.require_kill_switch_enabled:
            self._expect(runtime.config.kill_switch_enabled, issues, "kill_switch_enabled", "kill_switch_enabled must remain true.")
        monitoring = self.monitoring_engine.validate(config.monitoring_config_path, expected_profile=expected_profile)
        diagnostics["monitoring_config_status"] = monitoring.status
        if config.require_monitoring_config_pass and monitoring.status != "PASS":
            issues.append(self._issue("monitoring_config_validation", "FAIL", "Monitoring config must validate PASS.", {"monitoring_config_status": monitoring.status}))
        _, runner_issues, _ = self.runner_engine.validate_config(config.runner_config_path, expected_profile=expected_profile)
        runner_fail_count = sum(1 for issue in runner_issues if issue.severity == "FAIL")
        diagnostics["runner_config_status"] = "FAIL" if runner_fail_count else "PASS"
        if config.require_runner_config_pass and runner_fail_count:
            issues.append(self._issue("runner_config_validation", "FAIL", "Runner config must validate PASS.", {"runner_fail_count": runner_fail_count}))
        live = self.live_market_feed_engine.validate(config.live_market_feed_config_path, expected_profile=expected_profile)
        diagnostics["live_market_feed_config_status"] = live.status
        if config.require_live_market_feed_config_pass and live.status != "PASS":
            issues.append(self._issue("live_market_feed_config_validation", "FAIL", "Live market feed config must validate PASS.", {"live_market_feed_config_status": live.status}))
        paper = self.paper_account_engine.validate(config.paper_account_config_path, expected_profile=expected_profile)
        diagnostics["paper_account_config_status"] = paper.status
        if config.require_paper_account_config_pass and paper.status != "PASS":
            issues.append(self._issue("paper_account_config_validation", "FAIL", "Paper account config must validate PASS.", {"paper_account_config_status": paper.status}))

    def _fetch_candles(self, config: BTCFuturesReadOnlyFeedConfig, timeframe: str, limit: int, min_candles: int, name: str) -> tuple[list[BTCFuturesReadOnlyCandle], list[BTCFuturesReadOnlyIssue]]:
        issues: list[BTCFuturesReadOnlyIssue] = []
        last_error: Exception | None = None
        candles: list[BTCFuturesReadOnlyCandle] = []
        for _ in range(int(config.max_fetch_retries) + 1):
            try:
                candles = self.market_data_adapter.fetch_ohlcv(config.exchange_symbol, timeframe, int(limit), int(config.request_timeout_seconds))
                break
            except Exception as exc:  # pragma: no cover - exact network errors are environment-specific.
                last_error = exc
        if last_error is not None and not candles:
            return [], [self._issue("public_futures_market_data_fetch_failed", "FAIL", f"Public futures {name} market data fetch failed: {last_error}", {"timeframe": timeframe})]
        candles = self._normalise_candles(candles)
        if config.closed_candles_only and candles:
            candles = candles[:-1]
        if len(candles) < int(min_candles):
            issues.append(self._issue(f"{name}_min_candles", "FAIL", f"{name} futures feed returned too few candles.", {"candle_count": len(candles), "min_candles": min_candles}))
        return candles, issues

    def _fetch_mark_price(self, config: BTCFuturesReadOnlyFeedConfig) -> tuple[BTCFuturesMarkPrice | None, list[BTCFuturesReadOnlyIssue]]:
        try:
            return self.market_data_adapter.fetch_mark_price(config.exchange_symbol, int(config.request_timeout_seconds)), []
        except Exception as exc:  # pragma: no cover - exact network errors are environment-specific.
            return None, [self._issue("public_futures_mark_price_fetch_failed", "WARNING", f"Public futures mark price fetch failed: {exc}")]

    def _fetch_funding_info(self, config: BTCFuturesReadOnlyFeedConfig) -> tuple[BTCFuturesFundingInfo | None, list[BTCFuturesReadOnlyIssue]]:
        try:
            return self.market_data_adapter.fetch_funding_info(config.exchange_symbol, int(config.request_timeout_seconds)), []
        except Exception as exc:  # pragma: no cover - exact network errors are environment-specific.
            return None, [self._issue("public_futures_funding_fetch_failed", "WARNING", f"Public futures funding fetch failed: {exc}")]

    def _feed_result(
        self,
        config: BTCFuturesReadOnlyFeedConfig,
        primary: list[BTCFuturesReadOnlyCandle],
        confirmation: list[BTCFuturesReadOnlyCandle],
        mark_price: BTCFuturesMarkPrice | None,
        funding_info: BTCFuturesFundingInfo | None,
        issues: list[BTCFuturesReadOnlyIssue],
    ) -> BTCFuturesReadOnlyFeedResult:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        status = "FAIL" if failures else "WARNING" if warnings else "PASS"
        market_fetch_attempted = bool(primary or confirmation or any(issue.name == "public_futures_market_data_fetch_failed" for issue in issues))
        mark_attempted = mark_price is not None or any(issue.name == "public_futures_mark_price_fetch_failed" for issue in issues)
        funding_attempted = funding_info is not None or any(issue.name == "public_futures_funding_fetch_failed" for issue in issues)
        return BTCFuturesReadOnlyFeedResult(
            created_at=self._now(),
            project_scope=config.project_scope,
            symbol=config.symbol,
            exchange_symbol=config.exchange_symbol,
            exchange=config.exchange,
            market_type=config.market_type,
            futures_contract_type=config.futures_contract_type,
            status=status,
            primary_timeframe=config.primary_timeframe,
            confirmation_timeframe=config.confirmation_timeframe,
            primary_candles=len(primary),
            confirmation_candles=len(confirmation),
            primary_latest_timestamp=None if not primary else primary[-1].timestamp,
            confirmation_latest_timestamp=None if not confirmation else confirmation[-1].timestamp,
            primary_latest_close=None if not primary else primary[-1].close,
            confirmation_latest_close=None if not confirmation else confirmation[-1].close,
            mark_price=mark_price,
            funding_info=funding_info,
            closed_candles_only=config.closed_candles_only,
            public_futures_market_data_fetch_used=market_fetch_attempted,
            public_futures_mark_price_fetch_used=mark_attempted,
            public_futures_funding_fetch_used=funding_attempted,
            private_api_used=False,
            api_key_used=False,
            trading_api_used=False,
            account_data_used=False,
            balance_fetch_used=False,
            position_fetch_used=False,
            order_submitted=False,
            order_cancelled=False,
            real_position_created=False,
            paper_position_created=False,
            leverage_used=False,
            leverage_simulation_used=False,
            liquidation_modeling_used=False,
            executable_trade_created=False,
            exchange_connected_for_trading=False,
            runner_state_mutated=False,
            execution_state_mutated=False,
            issues=issues,
            metadata={
                "adapter": "binance_public_futures_read_only",
                "leverage_model_available": False,
                "liquidation_model_available": False,
            },
        )

    def _safety_summary(self, feed: BTCFuturesReadOnlyFeedResult) -> dict[str, Any]:
        return {
            "dry_run_only": True,
            "public_futures_market_data_fetch_used": feed.public_futures_market_data_fetch_used,
            "public_futures_mark_price_fetch_used": feed.public_futures_mark_price_fetch_used,
            "public_futures_funding_fetch_used": feed.public_futures_funding_fetch_used,
            "private_api_used": False,
            "api_key_used": False,
            "trading_api_used": False,
            "account_data_used": False,
            "balance_fetch_used": False,
            "position_fetch_used": False,
            "order_submitted": False,
            "order_cancelled": False,
            "real_position_created": False,
            "paper_position_created": False,
            "leverage_used": False,
            "leverage_simulation_used": False,
            "liquidation_modeling_used": False,
            "executable_trade_created": False,
            "exchange_connected_for_trading": False,
            "runner_state_mutated": False,
            "execution_state_mutated": False,
        }

    def _normalise_candles(self, candles: list[Any]) -> list[BTCFuturesReadOnlyCandle]:
        normalised: list[BTCFuturesReadOnlyCandle] = []
        for item in candles:
            if isinstance(item, BTCFuturesReadOnlyCandle):
                normalised.append(item)
            elif isinstance(item, dict):
                normalised.append(
                    BTCFuturesReadOnlyCandle(
                        timestamp=str(item.get("timestamp")),
                        open=float(item.get("open")),
                        high=float(item.get("high")),
                        low=float(item.get("low")),
                        close=float(item.get("close")),
                        volume=float(item.get("volume", 0.0)),
                    )
                )
        return normalised

    def _validate_report_dir(self, value: str, name: str, issues: list[BTCFuturesReadOnlyIssue]) -> None:
        path = Path(value)
        if path.is_absolute():
            issues.append(self._issue(name, "FAIL", f"{name} must be a safe relative path under reports/futures_read_only_feed.", {name: value}))
            return
        parts = path.parts
        self._expect(len(parts) >= 2 and parts[0] == "reports" and parts[1] == "futures_read_only_feed" and ".." not in parts, issues, name, f"{name} must be under reports/futures_read_only_feed.", {name: value})

    def _report(self, config_path: str, config: BTCFuturesReadOnlyFeedConfig | None, issues: list[BTCFuturesReadOnlyIssue], diagnostics: dict[str, Any]) -> BTCFuturesReadOnlyValidationReport:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        status = "FAIL" if failures else "WARNING" if warnings else "PASS"
        return BTCFuturesReadOnlyValidationReport(
            config_path=config_path,
            created_at=self._now(),
            status=status,
            issue_count=len(issues),
            warning_count=warnings,
            fail_count=failures,
            config=config,
            issues=issues,
            diagnostics=diagnostics,
        )

    def _expect(self, condition: bool, issues: list[BTCFuturesReadOnlyIssue], name: str, message: str, details: dict[str, Any] | None = None) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message, details))

    def _issue(self, name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> BTCFuturesReadOnlyIssue:
        return BTCFuturesReadOnlyIssue(name=name, severity=severity, message=message, details=details or {})

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


def _ms_to_iso(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC).replace(microsecond=0).isoformat()
    except (TypeError, ValueError, OSError):
        return None
