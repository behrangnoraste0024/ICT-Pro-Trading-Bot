from __future__ import annotations

from dataclasses import dataclass, field

from models.ote_diagnostics import OTEDiagnostics


@dataclass
class BacktestDiagnostics:
    setup_blockers: dict[str, int] = field(default_factory=dict)
    entry_blockers: dict[str, int] = field(default_factory=dict)
    trade_plan_blockers: dict[str, int] = field(default_factory=dict)
    trade_quality_blockers: dict[str, int] = field(default_factory=dict)
    paper_trade_blockers: dict[str, int] = field(default_factory=dict)
    setup_status_counts: dict[str, int] = field(default_factory=dict)
    entry_status_counts: dict[str, int] = field(default_factory=dict)
    trade_plan_status_counts: dict[str, int] = field(default_factory=dict)
    trade_quality_status_counts: dict[str, int] = field(default_factory=dict)
    paper_trade_status_counts: dict[str, int] = field(default_factory=dict)
    ote_diagnostics: OTEDiagnostics | None = None
    windows_analyzed: int = 0
    event_type: str = "BACKTEST_DIAGNOSTICS"

    def most_common_setup_blockers(self, limit: int = 10) -> list[tuple[str, int]]:
        return self._most_common(self.setup_blockers, limit)

    def most_common_entry_blockers(self, limit: int = 10) -> list[tuple[str, int]]:
        return self._most_common(self.entry_blockers, limit)

    def most_common_trade_plan_blockers(self, limit: int = 10) -> list[tuple[str, int]]:
        return self._most_common(self.trade_plan_blockers, limit)

    def most_common_trade_quality_blockers(self, limit: int = 10) -> list[tuple[str, int]]:
        return self._most_common(self.trade_quality_blockers, limit)

    def most_common_paper_trade_blockers(self, limit: int = 10) -> list[tuple[str, int]]:
        return self._most_common(self.paper_trade_blockers, limit)

    def _most_common(self, values: dict[str, int], limit: int) -> list[tuple[str, int]]:
        return sorted(values.items(), key=lambda item: (-item[1], item[0]))[:limit]

    def __str__(self) -> str:
        return (
            f"{self.event_type} | WINDOWS={self.windows_analyzed} | "
            f"SETUP_BLOCKERS={len(self.setup_blockers)} | "
            f"ENTRY_BLOCKERS={len(self.entry_blockers)}"
        )
