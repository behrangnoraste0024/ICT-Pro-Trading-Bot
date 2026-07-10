from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from engine.diagnostics.btc_forward_test_loop_engine import BTCForwardTestLoopEngine
from engine.diagnostics.btc_paper_candidate_journal_engine import BTCPaperCandidateJournalEngine
from engine.diagnostics.btc_paper_monitoring_engine import BTCPaperMonitoringEngine
from engine.diagnostics.btc_paper_runner_engine import BTCPaperRunnerEngine
from engine.diagnostics.btc_paper_runtime_config_engine import BTCPaperRuntimeConfigEngine
from engine.diagnostics.btc_paper_signal_evaluation_engine import BTCPaperSignalEvaluationEngine
from engine.diagnostics.btc_paper_trade_candidate_engine import BTCPaperTradeCandidateEngine
from models.btc_live_market_feed import (
    BTCLiveMarketCandle,
    BTCLiveMarketFeedConfig,
    BTCLiveMarketFeedIssue,
    BTCLiveMarketFeedResult,
    BTCLiveMarketFeedStatus,
    BTCLiveMarketFeedValidationReport,
    BTCLiveMarketObservationDecision,
    BTCLiveMarketObservationResult,
)


class BinancePublicOHLCVAdapter:
    """Public Binance klines adapter. It never accepts credentials or private endpoints."""

    BASE_URL = "https://api.binance.com/api/v3/klines"

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int, timeout_seconds: int) -> list[BTCLiveMarketCandle]:
        market = symbol.replace("/", "").upper()
        query = urlencode({"symbol": market, "interval": timeframe, "limit": int(limit)})
        with urlopen(f"{self.BASE_URL}?{query}", timeout=timeout_seconds) as response:  # nosec B310 - public market-data endpoint only.
            payload = json.loads(response.read().decode("utf-8"))
        candles: list[BTCLiveMarketCandle] = []
        for row in payload:
            if not isinstance(row, list) or len(row) < 6:
                continue
            candles.append(
                BTCLiveMarketCandle(
                    timestamp=datetime.fromtimestamp(int(row[0]) / 1000, tz=UTC).replace(microsecond=0).isoformat(),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            )
        return candles


class BTCLiveMarketFeedEngine:
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
        market_data_adapter: Any | None = None,
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
        self.market_data_adapter = market_data_adapter or BinancePublicOHLCVAdapter()
        self.now_provider = now_provider

    def validate(
        self,
        config_path: str = "configs/btc_live_market_feed.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCLiveMarketFeedValidationReport:
        issues: list[BTCLiveMarketFeedIssue] = []
        diagnostics: dict[str, Any] = {
            "runtime_config_status": "UNKNOWN",
            "monitoring_config_status": "UNKNOWN",
            "runner_config_status": "UNKNOWN",
            "signal_config_status": "UNKNOWN",
            "trade_candidate_config_status": "UNKNOWN",
            "candidate_journal_config_status": "UNKNOWN",
            "forward_test_config_status": "UNKNOWN",
            "kill_switch_enabled": None,
        }
        config: BTCLiveMarketFeedConfig | None = None
        try:
            config = self.load_config(config_path)
        except Exception as exc:
            issues.append(self._issue("config_invalid", "FAIL", f"BTC live market feed config could not be loaded: {exc}", {"config_path": config_path}))
            return self._report(config_path, config, issues, diagnostics)
        self._validate_config_values(config, expected_profile, issues, diagnostics)
        return self._report(config_path, config, issues, diagnostics)

    def fetch_once(
        self,
        config_path: str = "configs/btc_live_market_feed.json",
        expected_profile: str = "balanced_smc_decision_065",
    ) -> BTCLiveMarketFeedResult:
        report = self.validate(config_path=config_path, expected_profile=expected_profile)
        config = report.config or BTCLiveMarketFeedConfig()
        issues = list(report.issues)
        primary: list[BTCLiveMarketCandle] = []
        confirmation: list[BTCLiveMarketCandle] = []
        if report.status != BTCLiveMarketFeedStatus.FAIL.value:
            primary, primary_issues = self._fetch_candles(config, config.primary_timeframe, config.primary_limit, config.min_primary_candles, "primary")
            confirmation, confirmation_issues = self._fetch_candles(config, config.confirmation_timeframe, config.confirmation_limit, config.min_confirmation_candles, "confirmation")
            issues.extend(primary_issues)
            issues.extend(confirmation_issues)
        return self._feed_result(config, primary, confirmation, issues)

    def observe_once(
        self,
        config_path: str = "configs/btc_live_market_feed.json",
        expected_profile: str = "balanced_smc_decision_065",
        journal: bool | None = None,
    ) -> BTCLiveMarketObservationResult:
        report = self.validate(config_path=config_path, expected_profile=expected_profile)
        config = report.config or BTCLiveMarketFeedConfig()
        if report.status != "FAIL":
            issues = list(report.issues)
            primary, primary_issues = self._fetch_candles(config, config.primary_timeframe, config.primary_limit, config.min_primary_candles, "primary")
            confirmation, confirmation_issues = self._fetch_candles(config, config.confirmation_timeframe, config.confirmation_limit, config.min_confirmation_candles, "confirmation")
            issues.extend(primary_issues)
            issues.extend(confirmation_issues)
            feed = self._feed_result(config, primary, confirmation, issues, include_raw=True)
        else:
            feed = self._feed_result(config, [], [], list(report.issues))
        issues = list(feed.issues)
        if feed.status == "FAIL":
            return self._observation_result(
                config=config,
                feed=feed,
                status="FAIL",
                decision=BTCLiveMarketObservationDecision.FEED_FAILED.value,
                reason="Public market data feed failed safely.",
                issues=issues,
            )
        score = self._score_candles(feed.metadata.get("primary_candles_raw", []))
        threshold = self._signal_threshold(config)
        direction = self._infer_direction(feed.metadata.get("primary_candles_raw", []))
        signal_decision = "APPROVED_DRY_RUN" if score is not None and score >= threshold else "WARNING_DRY_RUN" if score and score > 0 else "NONE"
        candidate_created = bool(signal_decision == "APPROVED_DRY_RUN" and score is not None and score >= self._candidate_threshold(config) and direction in ("BULLISH", "BEARISH"))
        if candidate_created:
            status = "PASS"
            decision = BTCLiveMarketObservationDecision.FEED_OK_CANDIDATE_CREATED_DRY_RUN.value
            candidate_decision = "CANDIDATE_CREATED_DRY_RUN"
            reason = "Public market data observation produced a non-executable dry-run candidate."
        elif signal_decision == "APPROVED_DRY_RUN":
            status = "WARNING"
            decision = BTCLiveMarketObservationDecision.FEED_OK_CANDIDATE_REJECTED.value
            candidate_decision = "NO_CANDIDATE_SCORE_TOO_LOW"
            reason = "Signal was approved but candidate threshold was not met; no executable action was taken."
        elif signal_decision == "WARNING_DRY_RUN":
            status = "WARNING"
            decision = BTCLiveMarketObservationDecision.FEED_OK_SIGNAL_WARNING.value
            candidate_decision = "NO_CANDIDATE_SIGNAL_NOT_APPROVED"
            reason = "Public market data signal score is below threshold; no executable action was taken."
        else:
            status = "WARNING"
            decision = BTCLiveMarketObservationDecision.FEED_OK.value
            candidate_decision = "NO_CANDIDATE_SIGNAL_NOT_APPROVED"
            reason = "Public market data fetched, but no actionable dry-run signal context was found."
        result = self._observation_result(
            config=config,
            feed=feed,
            status=status,
            decision=decision,
            reason=reason,
            issues=issues,
            signal_status=status,
            signal_decision=signal_decision,
            signal_score=score,
            signal_threshold=threshold,
            candidate_status=status,
            candidate_decision=candidate_decision,
            candidate_created=candidate_created,
            metadata={"direction_hint": direction, "adapter": "live_market_read_only_dry_run", "trade_pipeline_invoked": False},
        )
        write_journal = config.allow_journal_write if journal is None else bool(journal)
        if write_journal and result.status in ("PASS", "WARNING"):
            entry_id = self._write_observation_journal(config, result)
            result.journal_entry_written = True
            result.journal_entry_id = entry_id
        return result

    def load_config(self, config_path: str = "configs/btc_live_market_feed.json") -> BTCLiveMarketFeedConfig:
        path = self._resolve(config_path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("config JSON must be an object")
        return BTCLiveMarketFeedConfig(**{**BTCLiveMarketFeedConfig().to_dict(), **loaded})

    def _validate_config_values(self, config: BTCLiveMarketFeedConfig, expected_profile: str, issues: list[BTCLiveMarketFeedIssue], diagnostics: dict[str, Any]) -> None:
        self._expect(config.project_scope == "BTC_ONLY", issues, "project_scope", "project_scope must be BTC_ONLY.", {"project_scope": config.project_scope})
        self._expect(config.symbol == "BTC/USDT", issues, "symbol", "symbol must be BTC/USDT.", {"symbol": config.symbol})
        self._expect(config.exchange == "binance", issues, "exchange", "exchange must be binance.", {"exchange": config.exchange})
        self._expect(config.market_type in ("spot", "future"), issues, "market_type", "market_type must be spot or future.", {"market_type": config.market_type})
        self._expect(config.strategy_profile == expected_profile, issues, "strategy_profile", f"strategy_profile must be {expected_profile}.", {"strategy_profile": config.strategy_profile})
        self._expect(config.primary_timeframe == "15m", issues, "primary_timeframe", "primary_timeframe must be 15m.", {"primary_timeframe": config.primary_timeframe})
        self._expect(config.confirmation_timeframe == "1h", issues, "confirmation_timeframe", "confirmation_timeframe must be 1h.", {"confirmation_timeframe": config.confirmation_timeframe})
        self._expect(100 <= int(config.primary_limit) <= 1000, issues, "primary_limit", "primary_limit must be between 100 and 1000.", {"primary_limit": config.primary_limit})
        self._expect(100 <= int(config.confirmation_limit) <= 1000, issues, "confirmation_limit", "confirmation_limit must be between 100 and 1000.", {"confirmation_limit": config.confirmation_limit})
        self._expect(int(config.min_primary_candles) <= int(config.primary_limit), issues, "min_primary_candles", "min_primary_candles must be <= primary_limit.", {"min_primary_candles": config.min_primary_candles, "primary_limit": config.primary_limit})
        self._expect(int(config.min_confirmation_candles) <= int(config.confirmation_limit), issues, "min_confirmation_candles", "min_confirmation_candles must be <= confirmation_limit.", {"min_confirmation_candles": config.min_confirmation_candles, "confirmation_limit": config.confirmation_limit})
        self._expect(1 <= int(config.request_timeout_seconds) <= 30, issues, "request_timeout_seconds", "request_timeout_seconds must be between 1 and 30.", {"request_timeout_seconds": config.request_timeout_seconds})
        self._expect(0 <= int(config.max_fetch_retries) <= 3, issues, "max_fetch_retries", "max_fetch_retries must be between 0 and 3.", {"max_fetch_retries": config.max_fetch_retries})
        self._expect(config.observation_mode == "fetch_once", issues, "observation_mode", "observation_mode must be fetch_once.", {"observation_mode": config.observation_mode})
        self._expect(config.closed_candles_only in (True, False), issues, "closed_candles_only", "closed_candles_only must be boolean.")
        self._expect(config.feed_enabled in (True, False), issues, "feed_enabled", "feed_enabled must be boolean.")
        self._expect(config.dry_run_only, issues, "dry_run_only", "dry_run_only must be true.")
        self._expect(config.allow_public_market_data_fetch, issues, "allow_public_market_data_fetch", "public market data fetch must be explicitly allowed.")
        for name in (
            "allow_private_api",
            "allow_api_key_usage",
            "allow_trading_api",
            "allow_account_data",
            "allow_balance_fetch",
            "allow_position_fetch",
            "allow_order_submission",
            "allow_order_cancellation",
            "allow_position_creation",
            "allow_paper_trade_persistence",
            "allow_executable_trade_creation",
            "allow_state_mutation",
        ):
            self._expect(not bool(getattr(config, name)), issues, name, f"{name} must remain false.")
        self._validate_live_feed_dir(config.status_export_dir, "status_export_dir", issues)
        self._validate_dependencies(config, expected_profile, issues, diagnostics)

    def _validate_dependencies(self, config: BTCLiveMarketFeedConfig, expected_profile: str, issues: list[BTCLiveMarketFeedIssue], diagnostics: dict[str, Any]) -> None:
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
        signal = self.signal_engine.validate(config.signal_evaluation_config_path, expected_profile=expected_profile)
        diagnostics["signal_config_status"] = signal.status
        if config.require_signal_config_pass and signal.status != "PASS":
            issues.append(self._issue("signal_config_validation", "FAIL", "Signal evaluation config must validate PASS.", {"signal_config_status": signal.status}))
        candidate = self.trade_candidate_engine.validate(config.trade_candidate_config_path, expected_profile=expected_profile)
        diagnostics["trade_candidate_config_status"] = candidate.status
        if config.require_trade_candidate_config_pass and candidate.status != "PASS":
            issues.append(self._issue("trade_candidate_config_validation", "FAIL", "Trade candidate config must validate PASS.", {"trade_candidate_config_status": candidate.status}))
        journal = self.candidate_journal_engine.validate(config.candidate_journal_config_path, expected_profile=expected_profile)
        diagnostics["candidate_journal_config_status"] = journal.status
        if config.require_candidate_journal_config_pass and journal.status != "PASS":
            issues.append(self._issue("candidate_journal_config_validation", "FAIL", "Candidate journal config must validate PASS.", {"candidate_journal_config_status": journal.status}))
        forward_path = self._resolve(config.forward_test_config_path)
        if forward_path.exists():
            forward = self.forward_test_engine.validate(config.forward_test_config_path, expected_profile=expected_profile)
            diagnostics["forward_test_config_status"] = forward.status

    def _fetch_candles(self, config: BTCLiveMarketFeedConfig, timeframe: str, limit: int, min_candles: int, name: str) -> tuple[list[BTCLiveMarketCandle], list[BTCLiveMarketFeedIssue]]:
        issues: list[BTCLiveMarketFeedIssue] = []
        last_error: Exception | None = None
        candles: list[BTCLiveMarketCandle] = []
        for _ in range(int(config.max_fetch_retries) + 1):
            try:
                candles = self.market_data_adapter.fetch_ohlcv(config.symbol, timeframe, int(limit), int(config.request_timeout_seconds))
                break
            except Exception as exc:  # pragma: no cover - exact network errors are environment-specific.
                last_error = exc
        if last_error is not None and not candles:
            return [], [self._issue("public_market_data_fetch_failed", "FAIL", f"Public {name} market data fetch failed: {last_error}", {"timeframe": timeframe})]
        candles = self._normalise_candles(candles)
        if config.closed_candles_only and candles:
            candles = candles[:-1]
        if len(candles) < int(min_candles):
            issues.append(self._issue(f"{name}_min_candles", "FAIL", f"{name} feed returned too few candles.", {"candle_count": len(candles), "min_candles": min_candles}))
        return candles, issues

    def _feed_result(
        self,
        config: BTCLiveMarketFeedConfig,
        primary: list[BTCLiveMarketCandle],
        confirmation: list[BTCLiveMarketCandle],
        issues: list[BTCLiveMarketFeedIssue],
        include_raw: bool = False,
    ) -> BTCLiveMarketFeedResult:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        status = "FAIL" if failures else "WARNING" if warnings else "PASS"
        return BTCLiveMarketFeedResult(
            created_at=self._now(),
            project_scope=config.project_scope,
            symbol=config.symbol,
            exchange=config.exchange,
            market_type=config.market_type,
            status=status,
            primary_timeframe=config.primary_timeframe,
            confirmation_timeframe=config.confirmation_timeframe,
            primary_candles=len(primary),
            confirmation_candles=len(confirmation),
            primary_latest_timestamp=None if not primary else primary[-1].timestamp,
            confirmation_latest_timestamp=None if not confirmation else confirmation[-1].timestamp,
            primary_latest_close=None if not primary else primary[-1].close,
            confirmation_latest_close=None if not confirmation else confirmation[-1].close,
            closed_candles_only=config.closed_candles_only,
            public_market_data_fetch_used=bool(primary or confirmation or any(issue.name == "public_market_data_fetch_failed" for issue in issues)),
            private_api_used=False,
            api_key_used=False,
            trading_api_used=False,
            account_data_used=False,
            balance_fetch_used=False,
            position_fetch_used=False,
            order_submitted=False,
            order_cancelled=False,
            exchange_connected_for_trading=False,
            issues=issues,
            metadata={
                "primary_candles_raw": [candle.to_dict() for candle in primary] if include_raw else [],
                "confirmation_candles_raw": [candle.to_dict() for candle in confirmation] if include_raw else [],
                "adapter": "binance_public_ohlcv",
            },
        )

    def _observation_result(self, config: BTCLiveMarketFeedConfig, feed: BTCLiveMarketFeedResult, status: str, decision: str, reason: str, issues: list[BTCLiveMarketFeedIssue], **kwargs: Any) -> BTCLiveMarketObservationResult:
        return BTCLiveMarketObservationResult(
            created_at=self._now(),
            project_scope=config.project_scope,
            symbol=config.symbol,
            exchange=config.exchange,
            market_type=config.market_type,
            strategy_profile=config.strategy_profile,
            status=status,
            decision=decision,
            feed_status=feed.status,
            reason=reason,
            primary_candles=feed.primary_candles,
            confirmation_candles=feed.confirmation_candles,
            primary_latest_timestamp=feed.primary_latest_timestamp,
            confirmation_latest_timestamp=feed.confirmation_latest_timestamp,
            dry_run_only=True,
            public_market_data_fetch_used=feed.public_market_data_fetch_used,
            private_api_used=False,
            api_key_used=False,
            trading_api_used=False,
            account_data_used=False,
            balance_fetch_used=False,
            position_fetch_used=False,
            executable_trade_created=False,
            paper_trade_persisted=False,
            position_created=False,
            order_submitted=False,
            order_cancelled=False,
            exchange_connected_for_trading=False,
            state_mutated=False,
            safety_summary={
                "dry_run_only": True,
                "public_market_data_fetch_used": feed.public_market_data_fetch_used,
                "private_api_used": False,
                "api_key_used": False,
                "trading_api_used": False,
                "order_submitted": False,
                "state_mutated": False,
            },
            issues=issues,
            **kwargs,
        )

    def _write_observation_journal(self, config: BTCLiveMarketFeedConfig, result: BTCLiveMarketObservationResult) -> str:
        path = self._resolve(str(Path(config.status_export_dir) / "btc_live_market_observations.jsonl"))
        if not self._safe_live_feed_path(path):
            raise ValueError("live market feed journal must stay under reports/live_market_feed")
        path.parent.mkdir(parents=True, exist_ok=True)
        entry_id = f"BTC-LIVE-FEED-{self._now()}"
        payload = {**result.to_dict(), "journal_entry_id": entry_id}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return entry_id

    def _signal_threshold(self, config: BTCLiveMarketFeedConfig) -> float:
        try:
            return float(self.signal_engine.load_config(config.signal_evaluation_config_path).decision_threshold)
        except Exception:
            return 0.65

    def _candidate_threshold(self, config: BTCLiveMarketFeedConfig) -> float:
        try:
            return float(self.trade_candidate_engine.load_config(config.trade_candidate_config_path).min_signal_score)
        except Exception:
            return 0.65

    def _score_candles(self, raw_candles: list[dict[str, Any]]) -> float | None:
        if len(raw_candles) < 2:
            return None
        first = self._float_value(raw_candles[0].get("close"))
        last = self._float_value(raw_candles[-1].get("close"))
        if first is None or last is None or first == 0:
            return None
        return round(min(abs(last - first) / abs(first), 1.0), 4)

    def _infer_direction(self, raw_candles: list[dict[str, Any]]) -> str:
        if len(raw_candles) < 2:
            return "NONE"
        first = self._float_value(raw_candles[0].get("close"))
        last = self._float_value(raw_candles[-1].get("close"))
        if first is None or last is None:
            return "NONE"
        if last > first:
            return "BULLISH"
        if last < first:
            return "BEARISH"
        return "RANGE"

    def _normalise_candles(self, candles: list[Any]) -> list[BTCLiveMarketCandle]:
        normalised: list[BTCLiveMarketCandle] = []
        for item in candles:
            if isinstance(item, BTCLiveMarketCandle):
                normalised.append(item)
            elif isinstance(item, dict):
                normalised.append(
                    BTCLiveMarketCandle(
                        timestamp=str(item.get("timestamp")),
                        open=float(item.get("open")),
                        high=float(item.get("high")),
                        low=float(item.get("low")),
                        close=float(item.get("close")),
                        volume=float(item.get("volume", 0.0)),
                    )
                )
        return normalised

    def _validate_live_feed_dir(self, value: str, name: str, issues: list[BTCLiveMarketFeedIssue]) -> None:
        path = Path(value)
        if path.is_absolute():
            issues.append(self._issue(name, "FAIL", f"{name} must be a safe relative path under reports/live_market_feed.", {name: value}))
            return
        parts = path.parts
        self._expect(len(parts) >= 2 and parts[0] == "reports" and parts[1] == "live_market_feed" and ".." not in parts, issues, name, f"{name} must be under reports/live_market_feed.", {name: value})

    def _safe_live_feed_path(self, path: Path) -> bool:
        try:
            return path.resolve().is_relative_to((self.repo_root / "reports" / "live_market_feed").resolve())
        except AttributeError:
            return str(path.resolve()).startswith(str((self.repo_root / "reports" / "live_market_feed").resolve()))

    def _report(self, config_path: str, config: BTCLiveMarketFeedConfig | None, issues: list[BTCLiveMarketFeedIssue], diagnostics: dict[str, Any]) -> BTCLiveMarketFeedValidationReport:
        failures = sum(1 for issue in issues if issue.severity == "FAIL")
        warnings = sum(1 for issue in issues if issue.severity == "WARNING")
        status = "FAIL" if failures else "WARNING" if warnings else "PASS"
        return BTCLiveMarketFeedValidationReport(
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

    def _expect(self, condition: bool, issues: list[BTCLiveMarketFeedIssue], name: str, message: str, details: dict[str, Any] | None = None) -> None:
        if not condition:
            issues.append(self._issue(name, "FAIL", message, details))

    def _issue(self, name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> BTCLiveMarketFeedIssue:
        return BTCLiveMarketFeedIssue(name=name, severity=severity, message=message, details=details or {})

    def _resolve(self, path_text: str) -> Path:
        path = Path(path_text)
        if not path.is_absolute():
            path = self.repo_root / path
        return path

    def _float_value(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _now(self) -> str:
        if self.now_provider is not None:
            return str(self.now_provider())
        return datetime.now(UTC).replace(microsecond=0).isoformat()

    def stale_after(self) -> str:
        return (datetime.now(UTC) + timedelta(minutes=15)).replace(microsecond=0).isoformat()
