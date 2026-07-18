from __future__ import annotations

from typing import Callable

from infrastructure.persistence.kill_switch_persistence import (
    KillSwitchPersistence,
    KillSwitchPersistenceError,
)


class KillSwitchGateError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DurableKillSwitchGate:
    """Short-lived, fail-closed guard for every exchange mutation boundary."""

    def __init__(
        self,
        env: dict[str, str] | None = None,
        persistence_factory: Callable[..., KillSwitchPersistence] = KillSwitchPersistence,
    ) -> None:
        self.env = env
        self.persistence_factory = persistence_factory

    def require_released(self) -> None:
        self._require("RELEASED", "KILL_SWITCH_ENGAGED")

    def require_engaged(self) -> None:
        self._require("ENGAGED", "KILL_SWITCH_NOT_ENGAGED")

    def _require(self, expected: str, blocked_code: str) -> None:
        persistence = self.persistence_factory(env=self.env)
        try:
            persistence.ensure_available()
            state = persistence.current()
            if state is None or state.state != expected:
                raise KillSwitchGateError(blocked_code)
        except KillSwitchGateError:
            raise
        except (KillSwitchPersistenceError, ValueError) as exc:
            raise KillSwitchGateError("KILL_SWITCH_STATE_UNAVAILABLE") from exc
        except Exception as exc:
            raise KillSwitchGateError("KILL_SWITCH_STATE_UNAVAILABLE") from exc
        finally:
            persistence.close()
