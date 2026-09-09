from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from engine.diagnostics.binance_futures_testnet_protective_orders_engine import (
    BinanceFuturesTestnetProtectiveOrdersEngine,
    ProtectiveAbort,
)
from engine.diagnostics.binance_futures_testnet_read_only_engine import BinanceFuturesTestnetReadOnlyEngine
from engine.diagnostics.btc_paper_readiness_engine import BTCPaperReadinessEngine
from infrastructure.exchanges.binance_futures_testnet_read_only_client import BinanceFuturesTestnetReadOnlyClient
from infrastructure.observability.operational_metrics import OperationalCounterRegistry
from models.binance_futures_testnet_protective_orders import BinanceFuturesTestnetProtectiveOrdersConfig
from models.binance_futures_testnet_read_only import BinanceFuturesTestnetReadOnlyConfig


@dataclass
class LiveControlPlaneHTTPError(Exception):
    status_code: int
    code: str
    message: str


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _decimal_string(value: Any) -> str:
    try:
        return str(Decimal(str(value)))
    except Exception:
        return "0"


class LiveControlPlaneService:
    def __init__(
        self,
        repo_root: str | Path | None = None,
        env: dict[str, str] | None = None,
        read_only_engine: BinanceFuturesTestnetReadOnlyEngine | None = None,
        protective_engine: BinanceFuturesTestnetProtectiveOrdersEngine | None = None,
        readiness_engine: BTCPaperReadinessEngine | None = None,
        operational_counter_registry: OperationalCounterRegistry | None = None,
    ) -> None:
        self.repo_root = Path.cwd() if repo_root is None else Path(repo_root)
        self.env = os.environ if env is None else env
        self.operational_counter_registry = operational_counter_registry
        self.read_only_engine = read_only_engine or BinanceFuturesTestnetReadOnlyEngine(repo_root=self.repo_root, env=self.env)
        self.protective_engine = protective_engine or BinanceFuturesTestnetProtectiveOrdersEngine(repo_root=self.repo_root, env=self.env, operational_counter_registry=operational_counter_registry)
        self.readiness_engine = readiness_engine or BTCPaperReadinessEngine(repo_root=self.repo_root, env=self.env)

    def safety_status(self) -> dict[str, Any]:
        read_config = self._load_read_only_config()
        protective_config = self._load_protective_config()
        credentials = BinanceFuturesTestnetReadOnlyClient(read_config, env=self.env).inspect_credential_presence()
        journal_state = self._read_protective_journal_state(protective_config)
        return {
            "environment": "BINANCE_FUTURES_TESTNET",
            "live_trading_enabled": False,
            "automatic_execution_enabled": bool(getattr(protective_config, "automatic_execution_enabled", False)),
            "kill_switch_engaged": True,
            "credentials_configured": bool(credentials.credentials_complete),
            "active_lock": self._path_exists(protective_config.lock_path),
            "recovery_required": bool(journal_state.get("recovery_required", False)),
            "production_endpoint_allowed": bool(getattr(read_config, "allow_production_endpoint", False) or getattr(protective_config, "allow_production_endpoint", False)),
            "updated_at": _now(),
        }

    def readiness(self) -> dict[str, Any]:
        try:
            report = self.readiness_engine.build_report(strict=True, run_gate=True, use_cache=True)
        except Exception:
            raise LiveControlPlaneHTTPError(503, "READINESS_UNAVAILABLE", "Readiness dependency is unavailable.")
        checks = list(getattr(report, "checks", []))
        blocking = [self._safe_blocking_reason(check) for check in checks if check.status == "FAIL" or (check.status == "WARNING" and check.severity == "REQUIRED")]
        validation_gate = "UNKNOWN"
        for check in checks:
            if check.name == "official_validation_gate":
                validation_gate = check.status
                break
        return {
            "status": report.readiness_status,
            "symbol": "BTCUSDT",
            "checks_passed": int(report.passed_checks),
            "checks_warning": int(report.warning_checks),
            "checks_failed": int(report.failed_checks),
            "validation_gate": validation_gate,
            "blocking_reasons": blocking,
            "updated_at": report.created_at or _now(),
        }


    def _safe_blocking_reason(self, check: Any) -> str:
        name = getattr(check, "name", "")
        message = str(getattr(check, "message", ""))
        if name == "official_validation_gate" and "errored:" in message.lower():
            return "Official BTC validation gate failed or is unavailable."
        return message

    def position(self, symbol: str) -> dict[str, Any]:
        if symbol != "BTCUSDT":
            raise LiveControlPlaneHTTPError(400, "INVALID_SYMBOL", "Only BTCUSDT is supported.")
        config = self._load_read_only_config()
        host = urlparse(config.rest_base_url).hostname or ""
        if bool(getattr(config, "allow_production_endpoint", False)) or host != "demo-fapi.binance.com":
            raise LiveControlPlaneHTTPError(403, "PRODUCTION_ENDPOINT_FORBIDDEN", "Production or unsupported endpoint is forbidden.")
        credentials = BinanceFuturesTestnetReadOnlyClient(config, env=self.env).inspect_credential_presence()
        if not credentials.credentials_complete:
            raise LiveControlPlaneHTTPError(503, "CREDENTIALS_NOT_CONFIGURED", "Read-only testnet credentials are not configured.")
        result = self.read_only_engine.fetch_position_risk(symbol, confirmation=config.network_confirmation_phrase)
        if result.status != "PASS" or result.position_summary is None:
            raise LiveControlPlaneHTTPError(503, "POSITION_UNAVAILABLE", "Position read is unavailable.")
        position = result.position_summary
        qty = _decimal_string(position.position_amount)
        direction = None
        try:
            amount = Decimal(str(position.position_amount))
            if amount > 0:
                direction = "LONG"
            elif amount < 0:
                direction = "SHORT"
        except Exception:
            direction = None
        if not position.has_open_position:
            qty = "0"
            direction = None
        return {
            "symbol": position.symbol,
            "position_side": position.position_side,
            "direction": direction,
            "quantity": qty,
            "entry_price": _decimal_string(position.entry_price),
            "break_even_price": _decimal_string(position.break_even_price),
            "mark_price": _decimal_string(position.mark_price),
            "notional_usdt": _decimal_string(position.notional),
            "unrealized_pnl": _decimal_string(position.unrealized_profit),
            "liquidation_price": _decimal_string(position.liquidation_price),
            "has_open_position": bool(position.has_open_position),
            "source": "binance_futures_testnet_read_only",
            "updated_at": _now(),
        }

    def protective_orders_current(self) -> dict[str, Any]:
        config = self._load_protective_config()
        active_lock = self._path_exists(config.lock_path)
        state = self._read_protective_journal_state(config)
        if state["state"] == "NONE":
            return {"state": "NONE", "pair_id": None, "recovery_required": False, "blocking_reason": None, "active_lock": active_lock, "stop": None, "take_profit": None, "updated_at": _now()}
        if state["state"] in ("UNKNOWN", "RECOVERY_REQUIRED"):
            return {"state": state["state"], "pair_id": state.get("pair_id"), "recovery_required": True, "blocking_reason": state.get("reason"), "active_lock": active_lock, "stop": None, "take_profit": None, "updated_at": _now()}
        journal = state["journal"]
        return {
            "state": "ACTIVE" if journal.recovery_required else "COMPLETE" if journal.phase in ("COMPLETE", "RECOVERY_COMPLETE") else "ACTIVE",
            "pair_id": journal.pair_id,
            "recovery_required": bool(journal.recovery_required),
            "blocking_reason": None,
            "active_lock": active_lock,
            "stop": self._order_from_journal(journal, "STOP"),
            "take_profit": self._order_from_journal(journal, "TAKE_PROFIT"),
            "updated_at": _now(),
        }

    def recovery_status(self) -> dict[str, Any]:
        config = self._load_protective_config()
        state = self._read_protective_journal_state(config)
        required = state["state"] in ("UNKNOWN", "RECOVERY_REQUIRED") or bool(state.get("recovery_required", False))
        return {
            "required": bool(required),
            "reason": state.get("reason"),
            "pair_id": state.get("pair_id"),
            "phase": state.get("phase"),
            "active_lock": self._path_exists(config.lock_path),
            "updated_at": _now(),
        }

    def _load_read_only_config(self) -> BinanceFuturesTestnetReadOnlyConfig:
        return self.read_only_engine.load_config("configs/binance_futures_testnet_read_only.json")

    def _load_protective_config(self) -> BinanceFuturesTestnetProtectiveOrdersConfig:
        return self.protective_engine.load_config("configs/binance_futures_testnet_protective_orders.json")

    def _resolve(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else self.repo_root / path

    def _path_exists(self, value: str) -> bool:
        return self._resolve(value).exists()

    def _read_protective_journal_state(self, config: BinanceFuturesTestnetProtectiveOrdersConfig) -> dict[str, Any]:
        path = self._resolve(config.journal_path)
        if not path.exists():
            return {"state": "NONE", "recovery_required": False}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"state": "UNKNOWN", "recovery_required": True, "reason": "PROTECTIVE_JOURNAL_INVALID"}
            pair_id = payload.get("pair_id") if isinstance(payload.get("pair_id"), str) else ""
            stop_id = payload.get("stop_client_algo_id") if isinstance(payload.get("stop_client_algo_id"), str) else ""
            take_id = payload.get("take_profit_client_algo_id") if isinstance(payload.get("take_profit_client_algo_id"), str) else ""
            journal = self.protective_engine._load_existing_journal_strict(config, pair_id, stop_id, take_id)
            if journal is None:
                return {"state": "NONE", "recovery_required": False}
            unresolved = [intent for intent in journal.mutation_intents if not intent.resolved]
            if journal.recovery_required or unresolved:
                return {"state": "RECOVERY_REQUIRED", "journal": journal, "pair_id": journal.pair_id, "phase": journal.phase, "recovery_required": True, "reason": "PROTECTIVE_RECOVERY_REQUIRED"}
            return {"state": "OK", "journal": journal, "pair_id": journal.pair_id, "phase": journal.phase, "recovery_required": False}
        except (ProtectiveAbort, json.JSONDecodeError, OSError):
            return {"state": "UNKNOWN", "recovery_required": True, "reason": "PROTECTIVE_JOURNAL_UNTRUSTED"}
        except Exception:
            return {"state": "UNKNOWN", "recovery_required": True, "reason": "PROTECTIVE_STATE_UNAVAILABLE"}

    def _order_from_journal(self, journal, label: str) -> dict[str, Any] | None:
        client_id = journal.stop_client_algo_id if label == "STOP" else journal.take_profit_client_algo_id
        trigger = journal.stop_trigger if label == "STOP" else journal.take_profit_trigger
        if not client_id:
            return None
        return {
            "client_algo_id": client_id,
            "algo_id": None,
            "status": None,
            "trigger_price": None if trigger is None else str(trigger),
        }
