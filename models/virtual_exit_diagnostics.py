from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VirtualExitPolicyResult:
    policy_name: str
    result: str = "UNKNOWN"
    virtual_pnl_r: float | None = None
    exit_price: float | None = None
    exit_index: int | None = None
    bars_to_exit: int | None = None
    target_r: float | None = None
    activated_be: bool = False
    bars_to_be_activation: int | None = None
    event_type: str = "VIRTUAL_EXIT_POLICY_RESULT"

    def __str__(self) -> str:
        return f"{self.policy_name} | {self.result} | pnl_r={self.virtual_pnl_r} | bars={self.bars_to_exit}"


@dataclass
class VirtualExitRecord:
    trade_number: int
    direction: str
    actual_result: str
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    risk: float | None = None
    original_rr: float | None = None
    actual_pnl: float | None = None
    actual_pnl_r: float | None = None
    bars_held: int | None = None
    setup_score: float | int | None = None
    entry_trigger_type: str | None = None
    current_price_zone: str | None = None
    in_ote_zone: bool | None = None
    matched_poi_count: int = 0
    matched_poi_types: list[str] = field(default_factory=list)
    policy_results: dict[str, VirtualExitPolicyResult] = field(default_factory=dict)
    best_policy_name: str | None = None
    best_policy_pnl_r: float | None = None
    would_tp_1r_win: bool = False
    would_tp_2r_win: bool = False
    would_be_0_5r_help: bool = False
    would_be_1r_help: bool = False
    event_type: str = "VIRTUAL_EXIT_RECORD"

    def __str__(self) -> str:
        best = f"{self.best_policy_name}:{self.best_policy_pnl_r}R" if self.best_policy_name else "None"
        return f"{self.event_type} #{self.trade_number} | {self.direction} | ACTUAL={self.actual_result} | BEST={best}"


@dataclass
class VirtualExitPolicySummary:
    policy_name: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakevens: int = 0
    opens: int = 0
    unknowns: int = 0
    win_rate: float | None = None
    average_pnl_r: float | None = None
    total_pnl_r: float = 0.0
    average_bars_to_exit: float | None = None
    event_type: str = "VIRTUAL_EXIT_POLICY_SUMMARY"

    def __str__(self) -> str:
        return f"{self.policy_name} | trades={self.total_trades} | win_rate={self.win_rate} | pnl_r={self.total_pnl_r}"


@dataclass
class VirtualExitDiagnostics:
    records: list[VirtualExitRecord] = field(default_factory=list)
    policy_summaries: dict[str, VirtualExitPolicySummary] = field(default_factory=dict)
    total_trades: int = 0
    actual_wins: int = 0
    actual_losses: int = 0
    actual_open_trades: int = 0
    actual_total_pnl_r: float | None = None
    best_policy_by_total_pnl_r: str | None = None
    best_policy_by_win_rate: str | None = None
    best_policy_by_average_pnl_r: str | None = None
    tp_1r_would_have_won_count: int = 0
    tp_1_5r_would_have_won_count: int = 0
    tp_2r_would_have_won_count: int = 0
    tp_3r_would_have_won_count: int = 0
    be_0_5r_would_help_count: int = 0
    be_1r_would_help_count: int = 0
    high_rr_loss_count: int = 0
    high_rr_loss_tp_1r_wins: int = 0
    high_rr_loss_tp_1_5r_wins: int = 0
    high_rr_loss_be_0_5r_saved: int = 0
    high_rr_loss_be_1r_saved: int = 0
    event_type: str = "VIRTUAL_EXIT_DIAGNOSTICS"

    def losing_records(self) -> list[VirtualExitRecord]:
        return [record for record in self.records if record.actual_result == "LOSS"]

    def records_where_policy_wins(self, policy_name: str) -> list[VirtualExitRecord]:
        return [record for record in self.records if record.policy_results.get(policy_name) and record.policy_results[policy_name].result == "WIN"]

    def records_where_be_helped(self, policy_name: str) -> list[VirtualExitRecord]:
        return [
            record
            for record in self.records
            if record.actual_result == "LOSS"
            and record.policy_results.get(policy_name)
            and record.policy_results[policy_name].result in ("BREAKEVEN", "WIN")
        ]

    def __str__(self) -> str:
        return f"{self.event_type} | TRADES={self.total_trades} | BEST={self.best_policy_by_total_pnl_r}"
