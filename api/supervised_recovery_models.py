from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

ENVIRONMENT = "BINANCE_FUTURES_TESTNET"
SYMBOL = "BTCUSDT"
CONFIRMATION = "RUN BTCUSDT TESTNET RECOVERY"
UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


class SupervisedRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: str
    symbol: str
    pair_id: str
    correlation_id: str
    confirmation: str
    dry_run: StrictBool

    @field_validator("environment")
    def exact_environment(cls, value: str) -> str:
        if value != ENVIRONMENT:
            raise ValueError("unsupported environment")
        return value

    @field_validator("symbol")
    def exact_symbol(cls, value: str) -> str:
        if value != SYMBOL:
            raise ValueError("unsupported symbol")
        return value

    @field_validator("pair_id", "correlation_id")
    def canonical_uuid(cls, value: str) -> str:
        if not isinstance(value, str) or UUID_PATTERN.fullmatch(value) is None:
            raise ValueError("identifier must be a canonical UUID")
        return value

    @field_validator("confirmation")
    def exact_confirmation(cls, value: str) -> str:
        if value != CONFIRMATION:
            raise ValueError("invalid confirmation")
        return value


class SupervisedRecoveryResponse(BaseModel):
    accepted: bool
    dry_run: bool
    recovery_ready: bool = False
    recovery_executed: bool = False
    environment: str
    symbol: str
    pair_id: str
    correlation_id: str
    current_phase: str | None = None
    final_phase: str | None = None
    pair_state: str | None = None
    final_pair_state: str | None = None
    recovery_required: bool
    planned_actions: list[str] = Field(default_factory=list)
    stop_result: str | None = None
    take_profit_result: str | None = None
    blocking_code: str | None = None
