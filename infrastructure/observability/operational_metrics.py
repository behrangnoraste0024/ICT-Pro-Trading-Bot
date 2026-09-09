from __future__ import annotations

import re
from threading import Lock

METRIC_NAME_PATTERN = re.compile(r"^ict_tradingbot_[a-z][a-z0-9_]{0,95}_total$")

_FORBIDDEN_NORMALIZED_MARKERS = (
    "apikey",
    "apisecret",
    "xmbxapikey",
    "secret",
    "signature",
    "signedurl",
    "authenticatedurl",
    "authorization",
    "header",
    "databaseurl",
    "connectionstring",
    "postgresql",
    "mysql",
    "sqlite",
    "selectfrom",
    "sql",
    "traceback",
    "rawresponse",
    "rawexchangeresponse",
    "exchangeresponse",
    "credential",
    "requestfingerprint",
    "permitid",
    "orderid",
    "pairid",
    "clientorderid",
    "correlationid",
)


class OperationalCounterRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._lock = Lock()

    def register(self, name: str) -> None:
        validated = _validate_metric_name(name)
        with self._lock:
            self._counters.setdefault(validated, 0)

    def increment(self, name: str, amount: int = 1) -> int:
        validated = _validate_metric_name(name)
        _validate_increment(amount)
        with self._lock:
            if validated not in self._counters:
                raise KeyError("METRIC_UNKNOWN")
            self._counters[validated] += amount
            return self._counters[validated]

    def get(self, name: str) -> int:
        validated = _validate_metric_name(name)
        with self._lock:
            if validated not in self._counters:
                raise KeyError("METRIC_UNKNOWN")
            return self._counters[validated]

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(sorted(self._counters.items()))

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()


def _validate_metric_name(name: str) -> str:
    if not isinstance(name, str) or len(name) > 128 or METRIC_NAME_PATTERN.fullmatch(name) is None:
        raise ValueError("METRIC_NAME_INVALID")
    if _has_control_character(name) or _has_forbidden_marker(name):
        raise ValueError("METRIC_NAME_INVALID")
    return name


def _validate_increment(amount: int) -> None:
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ValueError("COUNTER_INCREMENT_INVALID")


def _has_control_character(value: str) -> bool:
    return any(character == "\n" or character == "\t" or ord(character) < 32 or ord(character) == 127 for character in value)


def _has_forbidden_marker(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "", value.casefold())
    return any(marker in normalized for marker in _FORBIDDEN_NORMALIZED_MARKERS)
