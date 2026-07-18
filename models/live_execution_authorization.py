from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


LIVE_EXECUTION_POLICY_VERSION = "1.0"


class LiveExecutionOperation(StrEnum):
    PROTECTIVE_CREATE = "PROTECTIVE_CREATE"
    PROTECTIVE_CANCEL = "PROTECTIVE_CANCEL"
    ORDER_LIFECYCLE_CREATE = "ORDER_LIFECYCLE_CREATE"
    ORDER_LIFECYCLE_CANCEL = "ORDER_LIFECYCLE_CANCEL"
    SIGNED_ORDER_TEST_CREATE = "SIGNED_ORDER_TEST_CREATE"


@dataclass(frozen=True)
class LiveExecutionAuthorizationContext:
    operation: LiveExecutionOperation
    environment: str
    symbol: str
    live_trading_enabled: bool
    dry_run: bool
    confirmation_verified: bool
    credentials_configured: bool
    current_pair_id: str | None = None


@dataclass(frozen=True)
class LiveExecutionAuthorizationDecision:
    allowed: bool
    code: str
    operation: str | None
    policy_version: str = LIVE_EXECUTION_POLICY_VERSION
    message: str = "Exchange mutation is not authorized."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
