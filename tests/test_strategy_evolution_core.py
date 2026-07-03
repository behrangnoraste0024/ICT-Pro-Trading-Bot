from __future__ import annotations

from engine.evolution.strategy_evolution_core import StrategyEvolutionCore
from models.strategy_comparison import StrategyComparisonRow


def _row(**overrides) -> StrategyComparisonRow:
    values = {
        "strategy_name": "profile=balanced_smc",
        "dealing_range_mode": "recent_50",
        "exit_mode": "fixed_1_5r",
        "min_risk_reward": 1.5,
        "strategy_profile": "balanced_smc",
        "net_pnl": 100.0,
        "gross_net_pnl": 100.0,
        "net_pnl_after_costs": 90.0,
        "win_rate": 60.0,
        "profit_factor": 1.5,
        "max_drawdown": 10.0,
        "total_trades": 5,
    }
    values.update(overrides)
    return StrategyComparisonRow(**values)


def test_fitness_prefers_net_pnl_after_costs() -> None:
    core = StrategyEvolutionCore()

    high_gross = _row(strategy_name="gross", net_pnl=200, gross_net_pnl=200, net_pnl_after_costs=20)
    high_net = _row(strategy_name="net", net_pnl=100, gross_net_pnl=100, net_pnl_after_costs=90)

    assert core.fitness(high_net) > core.fitness(high_gross)


def test_fitness_falls_back_to_gross_pnl() -> None:
    core = StrategyEvolutionCore()
    row = _row(net_pnl=42, gross_net_pnl=0, net_pnl_after_costs=None)

    assert core.fitness(row) > 0


def test_rank_orders_by_fitness() -> None:
    ranked = StrategyEvolutionCore().rank([
        _row(strategy_name="weak", net_pnl_after_costs=10),
        _row(strategy_name="strong", net_pnl_after_costs=100),
    ])

    assert ranked[0].candidate.strategy_spec.name == "strong"


def test_low_win_rate_mutation_increases_risk_reward() -> None:
    evaluation = StrategyEvolutionCore().evaluate_row(_row(win_rate=20, total_trades=5), generation=0)

    candidate = StrategyEvolutionCore().mutate(evaluation, generation=1)

    assert candidate.mutation_reason == "LOW_WIN_RATE_RAISE_RR"
    assert candidate.strategy_spec.min_risk_reward == 2.0
    assert candidate.strategy_spec.exit_mode == "fixed_2r"


def test_high_drawdown_mutation_tightens_filters() -> None:
    evaluation = StrategyEvolutionCore().evaluate_row(_row(max_drawdown=200, net_pnl_after_costs=50), generation=0)

    candidate = StrategyEvolutionCore().mutate(evaluation, generation=1)

    assert candidate.mutation_reason == "HIGH_DRAWDOWN_TIGHTEN_FILTERS"
    assert candidate.strategy_spec.direction_quality_mode == "long_strict"


def test_low_cost_efficiency_mutation_lowers_slippage() -> None:
    evaluation = StrategyEvolutionCore().evaluate_row(
        _row(
            gross_net_pnl=100,
            net_pnl_after_costs=60,
            slippage_pct=0.0002,
        ),
        generation=0,
    )

    candidate = StrategyEvolutionCore().mutate(evaluation, generation=1)

    assert candidate.mutation_reason == "LOW_COST_EFFICIENCY_ADJUST_SLIPPAGE"
    assert candidate.strategy_spec.slippage_pct == 0.0001


def test_low_trades_mutation_relaxes_one_constraint() -> None:
    evaluation = StrategyEvolutionCore().evaluate_row(
        _row(total_trades=1, direction_quality_mode="long_strict", strict_long_preset="regime_known"),
        generation=0,
    )

    candidate = StrategyEvolutionCore().mutate(evaluation, generation=1)

    assert candidate.mutation_reason == "LOW_TRADES_RELAX_ONE_CONSTRAINT"
    assert candidate.strategy_spec.direction_quality_mode == "off"
