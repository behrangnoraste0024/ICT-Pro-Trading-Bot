from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LiveSafetyStatusResponse(BaseModel):
    environment: str
    live_trading_enabled: bool
    automatic_execution_enabled: bool
    kill_switch_engaged: bool
    credentials_configured: bool
    active_lock: bool
    recovery_required: bool
    production_endpoint_allowed: bool
    updated_at: str


class LiveReadinessResponse(BaseModel):
    status: str
    symbol: str
    checks_passed: int
    checks_warning: int
    checks_failed: int
    validation_gate: str
    blocking_reasons: list[str] = Field(default_factory=list)
    updated_at: str


class LivePositionResponse(BaseModel):
    symbol: str
    position_side: str | None = None
    direction: str | None = None
    quantity: str
    entry_price: str
    break_even_price: str
    mark_price: str
    notional_usdt: str
    unrealized_pnl: str
    liquidation_price: str
    has_open_position: bool
    source: str
    updated_at: str


class ProtectiveOrderSummaryResponse(BaseModel):
    client_algo_id: str | None = None
    algo_id: str | None = None
    status: str | None = None
    trigger_price: str | None = None


class LiveProtectiveOrdersCurrentResponse(BaseModel):
    state: str
    pair_id: str | None = None
    recovery_required: bool
    blocking_reason: str | None = None
    active_lock: bool
    stop: ProtectiveOrderSummaryResponse | None = None
    take_profit: ProtectiveOrderSummaryResponse | None = None
    updated_at: str


class LiveRecoveryStatusResponse(BaseModel):
    required: bool
    reason: str | None = None
    pair_id: str | None = None
    phase: str | None = None
    active_lock: bool
    updated_at: str


class LiveControlPlaneError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class OperatorWarningResponse(BaseModel):
    code: str
    severity: str
    message: str
    source: str


class OperatorStatusResponse(BaseModel):
    environment: str
    symbol: str
    overall_status: str
    kill_switch_state: str | None = None
    kill_switch_available: bool
    recovery_required: bool
    recovery_available: bool
    persistence_configured: bool
    persistence_reachable: bool
    persistence_schema_ready: bool
    readiness_status: str
    validation_gate: str
    active_lock: bool
    warnings: list[OperatorWarningResponse] = Field(default_factory=list)
    updated_at: str


class PersistenceStatusResponse(BaseModel):
    configured: bool
    reachable: bool
    schema_ready: bool
    migration_revision: str | None = None
    read_only: bool = True
    source_of_truth: bool = False
    updated_at: str


class ExecutionIntentReadResponse(BaseModel):
    correlation_id: str
    environment: str
    symbol: str
    intent_type: str
    state: str
    requested_quantity: str | None = None
    requested_price: str | None = None
    failure_code: str | None = None
    version: int
    created_at: str
    updated_at: str


class ProtectivePairReadResponse(BaseModel):
    pair_id: str
    correlation_id: str
    environment: str
    symbol: str
    position_side: str
    direction: str
    quantity: str
    state: str
    recovery_required: bool
    blocking_reason: str | None = None
    version: int
    created_at: str
    updated_at: str


class ExchangeOrderReadResponse(BaseModel):
    leg_type: str
    client_algo_id: str
    exchange_algo_id: str | None = None
    exchange_order_id: str | None = None
    status: str
    trigger_price: str | None = None
    version: int
    created_at: str
    updated_at: str


class ProtectivePairOrdersResponse(BaseModel):
    pair_id: str
    orders: list[ExchangeOrderReadResponse] = Field(default_factory=list)


class PersistenceEventReadResponse(BaseModel):
    event_kind: str
    correlation_id: str | None = None
    event_type: str | None = None
    action: str | None = None
    from_state: str | None = None
    to_state: str | None = None
    reason_code: str | None = None
    result: str
    error_code: str | None = None
    created_at: str


class ProtectivePairEventsResponse(BaseModel):
    pair_id: str
    events: list[PersistenceEventReadResponse] = Field(default_factory=list)
    limit: int
    offset: int


class LiveExecutionPermitStatusResponse(BaseModel):
    permit_id: str
    operation: str
    environment: str
    symbol: str
    state: str
    effective_expired: bool
    expires_at: str
    issued_at: str
    consumed_at: str | None = None
    revoked_at: str | None = None
    revocation_reason: str | None = None
    version: int
    updated_at: str
