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
