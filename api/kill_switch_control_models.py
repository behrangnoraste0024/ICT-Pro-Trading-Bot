from __future__ import annotations

from pydantic import BaseModel, ConfigDict, StrictBool, field_validator


ENVIRONMENT = "BINANCE_FUTURES_TESTNET"
SYMBOL = "BTCUSDT"
ENGAGE_CONFIRMATION = "ENGAGE BTCUSDT TESTNET KILL SWITCH"
RELEASE_CONFIRMATION = "RELEASE BTCUSDT TESTNET KILL SWITCH"


class _KillSwitchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: str
    symbol: str
    acknowledged: StrictBool

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

    @field_validator("acknowledged")
    def acknowledgement_required(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("acknowledgement is required")
        return value


class KillSwitchEngageRequest(_KillSwitchRequest):
    confirmation: str

    @field_validator("confirmation")
    def exact_confirmation(cls, value: str) -> str:
        if value != ENGAGE_CONFIRMATION:
            raise ValueError("invalid confirmation")
        return value


class KillSwitchReleaseRequest(_KillSwitchRequest):
    confirmation: str

    @field_validator("confirmation")
    def exact_confirmation(cls, value: str) -> str:
        if value != RELEASE_CONFIRMATION:
            raise ValueError("invalid confirmation")
        return value


class KillSwitchControlResponse(BaseModel):
    accepted: bool
    environment: str
    symbol: str
    state: str | None = None
    changed: bool = False
    version: int | None = None
    updated_at: str | None = None
    blocking_code: str | None = None
