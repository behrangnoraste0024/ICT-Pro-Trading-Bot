from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EngineConfig:
    dealing_range_mode: str = "current_external"
