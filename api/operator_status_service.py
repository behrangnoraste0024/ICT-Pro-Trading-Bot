from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from infrastructure.observability.operational_metrics import OperationalCounterRegistry

from .kill_switch_control_service import KillSwitchControlService
from .live_control_plane_service import LiveControlPlaneService
from .persistence_read_model_service import PersistenceReadModelService

ENVIRONMENT = "BINANCE_FUTURES_TESTNET"
SYMBOL = "BTCUSDT"
SAFETY_DENIAL_COUNTER = "ict_tradingbot_safety_denials_total"
_KILL_SWITCH_STATES = {"ENGAGED", "RELEASED"}
_READINESS_STATES = {"BLOCKED", "READY", "WARNING"}
_VALIDATION_GATE_STATES = {"FAIL", "PASS", "WARNING"}

_WARNING_ORDER = {
    "OPERATOR_STATUS_UNAVAILABLE": 0,
    "KILL_SWITCH_UNAVAILABLE": 10,
    "KILL_SWITCH_NOT_RELEASED": 20,
    "RECOVERY_STATUS_UNAVAILABLE": 30,
    "RECOVERY_REQUIRED": 40,
    "PERSISTENCE_UNCONFIGURED": 50,
    "PERSISTENCE_UNAVAILABLE": 60,
    "PERSISTENCE_SCHEMA_NOT_READY": 70,
    "READINESS_NOT_READY": 80,
    "VALIDATION_GATE_NOT_PASS": 90,
    "ACTIVE_LOCK_PRESENT": 100,
    "ENVIRONMENT_NOT_TESTNET": 110,
    "SYMBOL_NOT_BTCUSDT": 120,
}

_WARNING_MESSAGES = {
    "OPERATOR_STATUS_UNAVAILABLE": "Operator status source is unavailable.",
    "KILL_SWITCH_UNAVAILABLE": "Kill switch status is unavailable.",
    "KILL_SWITCH_NOT_RELEASED": "Kill switch is not released.",
    "RECOVERY_STATUS_UNAVAILABLE": "Recovery status is unavailable.",
    "RECOVERY_REQUIRED": "Protective recovery is required.",
    "PERSISTENCE_UNCONFIGURED": "Persistence is not configured.",
    "PERSISTENCE_UNAVAILABLE": "Persistence is unavailable.",
    "PERSISTENCE_SCHEMA_NOT_READY": "Persistence schema is not ready.",
    "READINESS_NOT_READY": "BTC paper readiness is not ready.",
    "VALIDATION_GATE_NOT_PASS": "Validation gate has not passed.",
    "ACTIVE_LOCK_PRESENT": "A protective or recovery lock is active.",
    "ENVIRONMENT_NOT_TESTNET": "Operator status is restricted to Testnet.",
    "SYMBOL_NOT_BTCUSDT": "Operator status is restricted to BTCUSDT.",
}

_WARNING_SEVERITY = {
    "KILL_SWITCH_UNAVAILABLE": "UNAVAILABLE",
    "RECOVERY_STATUS_UNAVAILABLE": "UNAVAILABLE",
    "PERSISTENCE_UNAVAILABLE": "UNAVAILABLE",
    "OPERATOR_STATUS_UNAVAILABLE": "UNAVAILABLE",
}


@dataclass
class _Warning:
    code: str
    severity: str
    message: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "source": self.source,
        }


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _get(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _evaluate_operator_alerts(
    *,
    operational_metrics: dict[str, int],
    warnings: list[_Warning],
    recovery_required: bool,
    kill_switch_state: str | None,
) -> list[dict[str, str]]:
    warning_codes = {warning.code for warning in warnings}
    alerts: list[dict[str, str]] = []

    def add(alert_id: str, severity: str, safe_message: str, source_state: str) -> None:
        alerts.append(
            {
                "alert_id": alert_id,
                "severity": severity,
                "safe_message": safe_message,
                "source_state": source_state,
            }
        )

    if operational_metrics.get(SAFETY_DENIAL_COUNTER, 0) > 0:
        add("SAFETY_DENIAL_ACTIVE", "BLOCKING", "Safety denial counter is non-zero.", "NON_ZERO")
    if recovery_required is True:
        add("RECOVERY_REQUIRED", "BLOCKING", "Protective recovery is required.", "REQUIRED")
    if "PERSISTENCE_UNCONFIGURED" in warning_codes:
        add("PERSISTENCE_UNCONFIGURED", "BLOCKING", "Persistence is not configured.", "NOT_CONFIGURED")
    if "PERSISTENCE_UNAVAILABLE" in warning_codes:
        add("PERSISTENCE_UNAVAILABLE", "UNAVAILABLE", "Persistence is unavailable.", "UNAVAILABLE")
    if "PERSISTENCE_SCHEMA_NOT_READY" in warning_codes:
        add("PERSISTENCE_SCHEMA_NOT_READY", "BLOCKING", "Persistence schema is not ready.", "NOT_READY")
    if kill_switch_state == "ENGAGED" or "KILL_SWITCH_NOT_RELEASED" in warning_codes:
        add("KILL_SWITCH_ENGAGED", "BLOCKING", "Kill switch is not released.", "ENGAGED")
    if "KILL_SWITCH_UNAVAILABLE" in warning_codes:
        add("KILL_SWITCH_UNAVAILABLE", "UNAVAILABLE", "Kill switch status is unavailable.", "UNAVAILABLE")
    if "READINESS_NOT_READY" in warning_codes:
        add("READINESS_NOT_READY", "BLOCKING", "BTC paper readiness is not ready.", "NOT_READY")
    if "VALIDATION_GATE_NOT_PASS" in warning_codes:
        add("VALIDATION_GATE_NOT_PASS", "BLOCKING", "Validation gate has not passed.", "NOT_PASS")
    if "ACTIVE_LOCK_PRESENT" in warning_codes:
        add("ACTIVE_LOCK_PRESENT", "BLOCKING", "A protective or recovery lock is active.", "PRESENT")
    return alerts


class OperatorStatusService:
    """Read-only operator summary built from existing backend status providers."""

    def __init__(
        self,
        *,
        operational_counter_registry: OperationalCounterRegistry,
        live_service: LiveControlPlaneService | None = None,
        kill_switch_service: KillSwitchControlService | None = None,
        persistence_service: PersistenceReadModelService | None = None,
    ) -> None:
        self.operational_counter_registry = operational_counter_registry
        self.live_service = live_service or LiveControlPlaneService()
        self.kill_switch_service = kill_switch_service or KillSwitchControlService()
        self.persistence_service = persistence_service or PersistenceReadModelService()

    def status(self) -> dict[str, Any]:
        warnings: list[_Warning] = []
        environment = ENVIRONMENT
        symbol = SYMBOL
        kill_switch_state: str | None = None
        kill_switch_available = False
        recovery_required = True
        recovery_available = False
        persistence_configured = False
        persistence_reachable = False
        persistence_schema_ready = False
        readiness_status = "UNAVAILABLE"
        validation_gate = "UNKNOWN"
        active_lock = False

        safety = self._call_source(
            "safety",
            self.live_service.safety_status,
            warnings,
            "OPERATOR_STATUS_UNAVAILABLE",
            self._valid_safety_payload,
        )
        if safety is not None:
            environment = _get(safety, "environment")
            active_lock = _get(safety, "active_lock")
            if _get(safety, "production_endpoint_allowed"):
                self._add_warning(warnings, "ENVIRONMENT_NOT_TESTNET", "safety")
            if _get(safety, "automatic_execution_enabled"):
                self._add_warning(warnings, "OPERATOR_STATUS_UNAVAILABLE", "safety")

        kill_switch = self._call_source(
            "kill_switch",
            self.kill_switch_service.status,
            warnings,
            "KILL_SWITCH_UNAVAILABLE",
            self._valid_kill_switch_payload,
        )
        if kill_switch is not None:
            kill_switch_available = True
            kill_switch_state = _get(kill_switch, "state")
            environment = _get(kill_switch, "environment")
            symbol = _get(kill_switch, "symbol")
            if kill_switch_state != "RELEASED":
                self._add_warning(warnings, "KILL_SWITCH_NOT_RELEASED", "kill_switch")

        recovery = self._call_source(
            "recovery",
            self.live_service.recovery_status,
            warnings,
            "RECOVERY_STATUS_UNAVAILABLE",
            self._valid_recovery_payload,
        )
        if recovery is not None:
            recovery_available = True
            recovery_required = _get(recovery, "required")
            active_lock = active_lock or _get(recovery, "active_lock")
            if recovery_required:
                self._add_warning(warnings, "RECOVERY_REQUIRED", "recovery")

        persistence = self._call_source(
            "persistence",
            self.persistence_service.status,
            warnings,
            "PERSISTENCE_UNAVAILABLE",
            self._valid_persistence_payload,
        )
        if persistence is not None:
            persistence_configured = _get(persistence, "configured")
            persistence_reachable = _get(persistence, "reachable")
            persistence_schema_ready = _get(persistence, "schema_ready")
            if not persistence_configured:
                self._add_warning(warnings, "PERSISTENCE_UNCONFIGURED", "persistence")
            elif not persistence_reachable:
                self._add_warning(warnings, "PERSISTENCE_UNAVAILABLE", "persistence")
            elif not persistence_schema_ready:
                self._add_warning(warnings, "PERSISTENCE_SCHEMA_NOT_READY", "persistence")

        readiness = self._call_source(
            "readiness",
            self.live_service.readiness,
            warnings,
            "OPERATOR_STATUS_UNAVAILABLE",
            self._valid_readiness_payload,
        )
        if readiness is not None:
            readiness_status = _get(readiness, "status")
            symbol = _get(readiness, "symbol")
            validation_gate = _get(readiness, "validation_gate")
            if readiness_status != "READY":
                self._add_warning(warnings, "READINESS_NOT_READY", "readiness")
            if validation_gate != "PASS":
                self._add_warning(warnings, "VALIDATION_GATE_NOT_PASS", "readiness")

        if environment != ENVIRONMENT:
            self._add_warning(warnings, "ENVIRONMENT_NOT_TESTNET", "scope")
        if symbol != SYMBOL:
            self._add_warning(warnings, "SYMBOL_NOT_BTCUSDT", "scope")
        if active_lock:
            self._add_warning(warnings, "ACTIVE_LOCK_PRESENT", "lock")

        ordered_warnings = self._ordered_warnings(warnings)
        overall_status = self._overall_status(
            environment=environment,
            symbol=symbol,
            kill_switch_state=kill_switch_state,
            kill_switch_available=kill_switch_available,
            recovery_required=recovery_required,
            recovery_available=recovery_available,
            persistence_configured=persistence_configured,
            persistence_reachable=persistence_reachable,
            persistence_schema_ready=persistence_schema_ready,
            readiness_status=readiness_status,
            validation_gate=validation_gate,
            active_lock=active_lock,
            warnings=ordered_warnings,
        )
        metrics_snapshot = self.operational_counter_registry.snapshot()
        operational_metrics = {
            SAFETY_DENIAL_COUNTER: metrics_snapshot.get(SAFETY_DENIAL_COUNTER, 0),
        }
        alerts = _evaluate_operator_alerts(
            operational_metrics=operational_metrics,
            warnings=ordered_warnings,
            recovery_required=recovery_required,
            kill_switch_state=kill_switch_state,
        )
        return {
            "environment": environment,
            "symbol": symbol,
            "overall_status": overall_status,
            "kill_switch_state": kill_switch_state,
            "kill_switch_available": kill_switch_available,
            "recovery_required": recovery_required,
            "recovery_available": recovery_available,
            "persistence_configured": persistence_configured,
            "persistence_reachable": persistence_reachable,
            "persistence_schema_ready": persistence_schema_ready,
            "readiness_status": readiness_status,
            "validation_gate": validation_gate,
            "active_lock": active_lock,
            "warnings": [warning.to_dict() for warning in ordered_warnings],
            "operational_metrics": operational_metrics,
            "alerts": alerts,
            "updated_at": _now(),
        }

    def _call_source(self, source: str, callback, warnings: list[_Warning], warning_code: str, validator) -> Any:
        try:
            payload = callback()
        except Exception:
            self._add_warning(warnings, warning_code, source)
            return None
        if payload is None or not validator(payload):
            self._add_warning(warnings, warning_code, source)
            return None
        return payload

    def _add_warning(self, warnings: list[_Warning], code: str, source: str) -> None:
        if (code, source) in {(warning.code, warning.source) for warning in warnings}:
            return
        warnings.append(
            _Warning(
                code=code,
                severity=_WARNING_SEVERITY.get(code, "BLOCKING"),
                message=_WARNING_MESSAGES[code],
                source=source,
            )
        )

    def _ordered_warnings(self, warnings: list[_Warning]) -> list[_Warning]:
        return sorted(warnings, key=lambda item: (_WARNING_ORDER.get(item.code, 999), item.source))

    def _overall_status(self, **state: Any) -> str:
        unavailable_codes = {warning.code for warning in state["warnings"] if warning.severity == "UNAVAILABLE"}
        if unavailable_codes or not state["kill_switch_available"] or not state["recovery_available"]:
            return "UNAVAILABLE"
        ready = (
            state["environment"] == ENVIRONMENT
            and state["symbol"] == SYMBOL
            and state["kill_switch_state"] == "RELEASED"
            and state["recovery_required"] is False
            and state["persistence_configured"] is True
            and state["persistence_reachable"] is True
            and state["persistence_schema_ready"] is True
            and state["readiness_status"] == "READY"
            and state["validation_gate"] == "PASS"
            and state["active_lock"] is False
            and not state["warnings"]
        )
        return "READY" if ready else "BLOCKED"

    @staticmethod
    def _has_key(payload: Any, key: str) -> bool:
        return key in payload if isinstance(payload, dict) else hasattr(payload, key)

    @staticmethod
    def _real_bool(value: Any) -> bool:
        return type(value) is bool

    def _has_string(self, payload: Any, key: str, *, values: set[str] | None = None, exact: str | None = None) -> bool:
        if not self._has_key(payload, key):
            return False
        value = _get(payload, key)
        if not isinstance(value, str) or not value:
            return False
        if exact is not None:
            return value == exact
        if values is not None:
            return value in values
        return True

    def _has_bool(self, payload: Any, key: str) -> bool:
        return self._has_key(payload, key) and self._real_bool(_get(payload, key))

    def _valid_safety_payload(self, payload: Any) -> bool:
        return (
            self._has_string(payload, "environment", exact=ENVIRONMENT)
            and self._has_string(payload, "symbol", exact=SYMBOL)
            and self._has_bool(payload, "active_lock")
            and self._has_bool(payload, "production_endpoint_allowed")
            and self._has_bool(payload, "automatic_execution_enabled")
        )

    def _valid_kill_switch_payload(self, payload: Any) -> bool:
        return (
            self._has_string(payload, "environment", exact=ENVIRONMENT)
            and self._has_string(payload, "symbol", exact=SYMBOL)
            and self._has_string(payload, "state", values=_KILL_SWITCH_STATES)
        )

    def _valid_recovery_payload(self, payload: Any) -> bool:
        return self._has_bool(payload, "required") and self._has_bool(payload, "active_lock")

    def _valid_persistence_payload(self, payload: Any) -> bool:
        return (
            self._has_bool(payload, "configured")
            and self._has_bool(payload, "reachable")
            and self._has_bool(payload, "schema_ready")
        )

    def _valid_readiness_payload(self, payload: Any) -> bool:
        return (
            self._has_string(payload, "status", values=_READINESS_STATES)
            and self._has_string(payload, "symbol")
            and self._has_string(payload, "validation_gate", values=_VALIDATION_GATE_STATES)
        )
