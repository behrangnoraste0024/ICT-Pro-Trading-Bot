from __future__ import annotations

from models.rolling_backtest_result import RollingBacktestResult


def format_rolling_backtest_report(
    result: RollingBacktestResult,
    fixture_path: str,
    min_candles: int,
    max_windows: int | None = None,
    show_trades: bool = False,
) -> str:
    failed_windows = getattr(result, "failed_windows", 0)
    stateful_mode = getattr(result, "stateful_mode", False)
    opened_trades = getattr(result, "opened_trades", 0)
    closed_by_state = getattr(result, "closed_by_state", 0)
    duplicate_signals_skipped = getattr(result, "duplicate_signals_skipped", 0)
    strategy_profile = getattr(result, "strategy_profile", "default")
    dealing_range_mode = getattr(result, "dealing_range_mode", "current_external")
    range_mode_fallback_count = getattr(result, "range_mode_fallback_count", 0)
    exit_mode = getattr(result, "exit_mode", "original")
    exit_mode_fallback_counts = getattr(result, "exit_mode_fallback_counts", {})
    min_risk_reward = getattr(result, "min_risk_reward", 2.0)
    direction_mode = getattr(result, "direction_mode", "all")
    auto_trend_fallback = getattr(result, "auto_trend_fallback", "all")
    regime_mode = getattr(result, "regime_mode", "rolling_return")
    regime_lookback = getattr(result, "regime_lookback", 200)
    regime_threshold_pct = getattr(result, "regime_threshold_pct", 0.0)
    regime_fallback = getattr(result, "regime_fallback", "all")
    direction_quality_mode = getattr(result, "direction_quality_mode", "off")
    direction_mode_fallback_counts = getattr(result, "direction_mode_fallback_counts", {})
    cost_diagnostics = getattr(result, "cost_diagnostics", None)
    cost_model = "off" if cost_diagnostics is None else cost_diagnostics.cost_model
    commission_pct = 0.0 if cost_diagnostics is None else cost_diagnostics.commission_pct
    slippage_pct = 0.0 if cost_diagnostics is None else cost_diagnostics.slippage_pct
    spread_pct = 0.0 if cost_diagnostics is None else cost_diagnostics.spread_pct
    total_cost = 0.0 if cost_diagnostics is None else cost_diagnostics.total_cost
    net_pnl_after_costs = result.net_pnl if cost_diagnostics is None else cost_diagnostics.net_pnl_after_costs

    lines = [
        "===== ROLLING BACKTEST REPORT =====",
        f"Fixture           : {fixture_path}",
            f"Min Candles       : {min_candles}",
            f"Strategy Profile  : {strategy_profile}",
            f"Dealing Range Mode : {dealing_range_mode}",
            f"Range Mode Fallbacks: {range_mode_fallback_count}",
            f"Exit Mode         : {exit_mode}",
            f"Exit Mode Fallbacks: {_format_exit_mode_fallbacks(exit_mode_fallback_counts)}",
            f"Min Risk Reward   : {min_risk_reward}",
            f"Direction Mode    : {direction_mode}",
            f"Auto Trend Fallback: {auto_trend_fallback}",
            f"Regime Mode       : {regime_mode}",
            f"Regime Lookback   : {regime_lookback}",
            f"Regime Threshold  : {regime_threshold_pct}",
            f"Regime Fallback   : {regime_fallback}",
            f"Direction Quality Mode : {direction_quality_mode}",
            f"Strict Long Rules : require_regime_known={getattr(result, 'strict_long_require_regime_known', False)}, block_unknown_regime={getattr(result, 'strict_long_block_unknown_regime', False)}, require_regime_bullish={getattr(result, 'strict_long_require_regime_bullish', False)}, require_displacement={getattr(result, 'strict_long_require_displacement', False)}, min_setup_score={getattr(result, 'strict_long_min_setup_score', None)}",
            f"Strict Short Rules: require_regime_known={getattr(result, 'strict_short_require_regime_known', False)}, block_unknown_regime={getattr(result, 'strict_short_block_unknown_regime', False)}, require_regime_bearish={getattr(result, 'strict_short_require_regime_bearish', False)}, require_displacement={getattr(result, 'strict_short_require_displacement', False)}, min_setup_score={getattr(result, 'strict_short_min_setup_score', None)}",
            f"Direction Mode Fallbacks: {_format_exit_mode_fallbacks(direction_mode_fallback_counts)}",
    ]
    if max_windows is not None:
        lines.append(f"Max Windows       : {max_windows}")
    lines.extend(
        [
            f"Stateful Mode     : {stateful_mode}",
            f"Total Windows     : {result.total_windows}",
            f"Processed Windows : {result.processed_windows}",
            f"Skipped Windows   : {result.skipped_windows}",
            f"Failed Windows    : {failed_windows}",
            f"Opened Trades     : {opened_trades}",
            f"Closed By State   : {closed_by_state}",
            f"Duplicates Skipped: {duplicate_signals_skipped}",
            f"Total Trades      : {result.total_paper_trades}",
            f"Closed Trades     : {result.closed_trades}",
            f"Open Trades       : {result.open_trades}",
            f"Wins              : {result.wins}",
            f"Losses            : {result.losses}",
            f"Win Rate          : {result.win_rate}",
            f"Net PnL           : {result.net_pnl}",
            f"Gross Net PnL     : {result.net_pnl}",
            f"Cost Model        : {cost_model}",
            f"Commission Pct    : {commission_pct}",
            f"Slippage Pct      : {slippage_pct}",
            f"Spread Pct        : {spread_pct}",
            f"Total Cost        : {total_cost}",
            f"Net PnL After Costs: {net_pnl_after_costs}",
            f"Average PnL       : {result.average_pnl}",
            f"Max Drawdown      : {result.max_drawdown}",
        ]
    )
    if cost_diagnostics is not None:
        lines.extend(_format_cost_diagnostics(cost_diagnostics, show_trades=show_trades))
    trade_outcomes = getattr(result, "trade_outcome_diagnostics", None)
    if trade_outcomes is not None:
        lines.extend(_format_trade_outcome_diagnostics(trade_outcomes, show_trades=show_trades))
    execution_quality = _format_execution_quality_diagnostics(getattr(result, "trade_outcome_contexts", []), show_trades=show_trades)
    if execution_quality:
        lines.extend(execution_quality)
    decision_filter_simulation = getattr(result, "decision_filter_simulation", None)
    if decision_filter_simulation is not None:
        lines.extend(_format_decision_filter_simulation(decision_filter_simulation))
    regime_direction = getattr(result, "regime_direction_diagnostics", None)
    if regime_direction is not None:
        lines.extend(_format_regime_direction_diagnostics(regime_direction))
    sl_tp_outcomes = getattr(result, "sl_tp_outcome_diagnostics", None)
    if sl_tp_outcomes is not None:
        lines.extend(_format_sl_tp_outcome_diagnostics(sl_tp_outcomes, show_trades=show_trades))
    entry_followthrough = getattr(result, "entry_followthrough_diagnostics", None)
    if entry_followthrough is not None:
        lines.extend(_format_entry_followthrough_diagnostics(entry_followthrough, show_trades=show_trades))
    virtual_exit = getattr(result, "virtual_exit_diagnostics", None)
    if virtual_exit is not None:
        lines.extend(_format_virtual_exit_diagnostics(virtual_exit, show_trades=show_trades))
    diagnostics = getattr(result, "diagnostics", None)
    if diagnostics is not None:
        lines.extend(_format_diagnostics(diagnostics))
    return "\n".join(lines)


def _format_cost_diagnostics(diagnostics, show_trades: bool = False) -> list[str]:
    lines = [
        "",
        "===== COST DIAGNOSTICS =====",
        f"Cost Model                 : {diagnostics.cost_model}",
        f"Total Trades               : {diagnostics.total_trades}",
        f"Closed Trades              : {diagnostics.closed_trades}",
        f"Gross Net PnL              : {diagnostics.gross_net_pnl}",
        f"Total Commission Cost      : {diagnostics.total_commission_cost}",
        f"Total Slippage Cost        : {diagnostics.total_slippage_cost}",
        f"Total Spread Cost          : {diagnostics.total_spread_cost}",
        f"Total Cost                 : {diagnostics.total_cost}",
        f"Net PnL After Costs        : {diagnostics.net_pnl_after_costs}",
        f"Average Cost Per Trade     : {diagnostics.average_cost_per_trade}",
        f"Average Net PnL After Costs: {diagnostics.average_net_pnl_after_costs}",
        f"Cost/Gross Profit Ratio    : {_format_optional_float(diagnostics.cost_to_gross_profit_ratio)}",
        "",
        "Cost Trade Log:",
    ]
    if not diagnostics.trades:
        lines.append("No trades.")
    elif not show_trades:
        lines.append("Hidden. Use --show-trades to display cost trade log rows.")
    else:
        for trade in diagnostics.trades:
            lines.append(_format_cost_trade_row(trade))
    return lines


def _format_cost_trade_row(trade) -> str:
    return (
        f"#{trade.trade_index} | {trade.direction} | gross={trade.gross_pnl} | "
        f"commission={trade.commission_cost} | slippage={trade.slippage_cost} | "
        f"spread={trade.spread_cost} | total_cost={trade.total_cost} | "
        f"net_after_cost={trade.net_pnl_after_costs}"
    )


def _format_trade_outcome_diagnostics(diagnostics, show_trades: bool = False) -> list[str]:
    lines = [
        "",
        "===== TRADE OUTCOME DIAGNOSTICS =====",
        f"Total Trades        : {diagnostics.total_trades}",
        f"Closed Trades       : {diagnostics.closed_trades}",
        f"Open Trades         : {diagnostics.open_trades}",
        f"Wins                : {diagnostics.wins}",
        f"Losses              : {diagnostics.losses}",
        f"Win Rate            : {diagnostics.win_rate}",
        f"Net PnL             : {diagnostics.net_pnl}",
        f"Average PnL         : {diagnostics.average_pnl}",
        f"Average Win         : {_format_optional_float(diagnostics.average_win)}",
        f"Average Loss        : {_format_optional_float(diagnostics.average_loss)}",
        f"Largest Win         : {_format_optional_float(diagnostics.largest_win)}",
        f"Largest Loss        : {_format_optional_float(diagnostics.largest_loss)}",
        f"Average RR          : {_format_optional_float(diagnostics.average_rr)}",
        f"Average Setup Score : {_format_optional_float(diagnostics.average_setup_score)}",
        "",
        "Direction Summary:",
    ]
    direction_counts = diagnostics.trades_by_direction()
    direction_pnl = diagnostics.pnl_by_direction()
    if direction_counts:
        for direction in sorted(direction_counts):
            lines.append(f"{direction:<20}: count={direction_counts[direction]}, pnl={direction_pnl.get(direction, 0.0)}")
    else:
        lines.append("None")

    lines.extend(["", "Trade Log:"])
    if not diagnostics.trades:
        lines.append("No trades.")
    elif not show_trades:
        lines.append("Hidden. Use --show-trades to display trade log rows.")
    else:
        for trade in diagnostics.trades:
            lines.append(_format_trade_row(trade))
    return lines


def _format_trade_row(trade) -> str:
    poi_types = ",".join(trade.matched_poi_types) if trade.matched_poi_types else "None"
    return (
        f"#{trade.trade_number} | {trade.direction} | {trade.result} | "
        f"entry={trade.entry_price} | sl={trade.stop_loss} | tp={trade.take_profit} | "
        f"exit={trade.exit_price} | pnl={trade.pnl} | rr={trade.risk_reward} | "
        f"setup_score={trade.setup_score} | trigger={trade.entry_trigger_type} | "
        f"zone={trade.current_price_zone} | in_ote={trade.in_ote_zone} | poi={trade.matched_poi_count}:{poi_types} | "
        f"regime={trade.market_regime} | regime_ret={trade.market_regime_return_pct} | "
        f"regime_reason={trade.market_regime_reason} | dir_mode={trade.direction_mode_applied} | "
        f"resolved={trade.direction_mode_resolved_direction} | dir_reason={trade.direction_mode_fallback_reason} | "
        f"dir_quality={trade.direction_quality_applied} | dq_allowed={trade.direction_quality_allowed} | "
        f"dq_blocker={trade.direction_quality_blocker}"
    )


def _format_execution_quality_diagnostics(contexts, show_trades: bool = False) -> list[str]:
    trades = [context for context in contexts if getattr(context, "paper_trade_status", "NO_PAPER_TRADE") != "NO_PAPER_TRADE"]
    if not trades:
        return []

    scores = [
        float(score)
        for context in trades
        if (score := getattr(context, "execution_quality_score", None)) is not None
    ]
    decision_scores = [
        float(score)
        for context in trades
        if (score := getattr(context, "decision_score", None)) is not None
    ]
    decision_counts: dict[str, int] = {}
    for context in trades:
        decision = getattr(context, "decision_status", None)
        if decision is None:
            continue
        decision_counts[decision] = decision_counts.get(decision, 0) + 1

    lines = [
        "",
        "===== EXECUTION QUALITY / DECISION =====",
        f"Total Trades            : {len(trades)}",
        f"Average Execution Quality: {_format_optional_float(sum(scores) / len(scores) if scores else None)}",
        f"Average Decision Score  : {_format_optional_float(sum(decision_scores) / len(decision_scores) if decision_scores else None)}",
        "",
        "Decision Counts:",
    ]
    if decision_counts:
        for decision in sorted(decision_counts):
            lines.append(f"{decision:<20}: {decision_counts[decision]}")
    else:
        lines.append("None")

    lines.extend(["", "Execution Quality Trade Log:"])
    if not show_trades:
        lines.append("Hidden. Use --show-trades to display execution quality trade log rows.")
        return lines

    for index, context in enumerate(trades, start=1):
        lines.append(_format_execution_quality_trade_row(index, context))
    return lines


def _format_execution_quality_trade_row(trade_number: int, context) -> str:
    execution_quality = getattr(context, "execution_quality_result", None)
    adaptive_signal = getattr(context, "adaptive_signal", None)
    decision_result = getattr(context, "decision_result", None)
    execution_score = getattr(context, "execution_quality_score", None)
    decision_score = getattr(context, "decision_score", None)
    decision_status = getattr(context, "decision_status", None)
    return (
        f"#{trade_number} | {getattr(context, 'paper_trade_direction', 'NONE')} | "
        f"exec_q={_format_optional_float(execution_score)} | "
        f"decision={decision_status} | decision_score={_format_optional_float(decision_score)} | "
        f"adaptive={getattr(adaptive_signal, 'reason', None)} | "
        f"exec_reason={getattr(execution_quality, 'reasoning', None)} | "
        f"decision_breakdown={getattr(decision_result, 'breakdown', None)}"
    )


def _format_decision_filter_simulation(simulation) -> list[str]:
    lines = [
        "",
        "===== DECISION FILTER SIMULATION =====",
        f"Best By Net After Costs : {simulation.best_by_net_after_costs}",
        f"Best By Drawdown        : {simulation.best_by_drawdown}",
        "",
        "Bucket | Trades | W/L | Win% | GrossPnL | Cost | NetAfterCost | AvgDecision | AvgExecQ | MaxDD | PF",
    ]
    if not simulation.buckets:
        lines.append("None")
        return lines
    for bucket in simulation.buckets:
        lines.append(_format_decision_filter_bucket(bucket))
    return lines


def _format_decision_filter_bucket(bucket) -> str:
    return (
        f"{bucket.name} | {bucket.total_trades} | {bucket.wins}/{bucket.losses} | "
        f"{_format_optional_float(bucket.win_rate)} | {_format_optional_float(bucket.gross_net_pnl)} | "
        f"{_format_optional_float(bucket.total_cost)} | {_format_optional_float(bucket.net_pnl_after_costs)} | "
        f"{_format_optional_float(bucket.average_decision_score)} | "
        f"{_format_optional_float(bucket.average_execution_quality)} | "
        f"{_format_optional_float(bucket.max_drawdown)} | {_format_optional_float(bucket.profit_factor)}"
    )


def _format_exit_mode_fallbacks(fallback_counts: dict[str, int] | None) -> str:
    if not fallback_counts:
        return "None"
    return ", ".join(f"{reason}={count}" for reason, count in sorted(fallback_counts.items()))


def _format_regime_direction_diagnostics(diagnostics) -> list[str]:
    return [
        "",
        "===== REGIME DIRECTION DIAGNOSTICS =====",
        f"Total Trades              : {diagnostics.total_trades}",
        f"Trades With Regime        : {diagnostics.trades_with_regime}",
        f"Trades Missing Regime     : {diagnostics.trades_missing_regime}",
        f"Long In Bearish Count     : {diagnostics.long_in_bearish_count}",
        f"Long In Bearish PnL       : {diagnostics.long_in_bearish_pnl}",
        f"Short In Bullish Count    : {diagnostics.short_in_bullish_count}",
        f"Short In Bullish PnL      : {diagnostics.short_in_bullish_pnl}",
        f"Missing Metadata Count    : {diagnostics.missing_metadata_count}",
        "",
        "PnL by Direction / Regime:",
        *_format_regime_buckets(diagnostics.by_direction_regime),
        "",
        "PnL by Regime Reason:",
        *_format_regime_buckets(diagnostics.by_regime_reason),
        "",
        "PnL by Direction Mode Reason:",
        *_format_regime_buckets(diagnostics.by_direction_mode_reason),
        "",
        "PnL by Resolved Direction:",
        *_format_regime_buckets(diagnostics.by_resolved_direction),
        "",
        "PnL by Direction Quality Reason:",
        *_format_regime_buckets(getattr(diagnostics, "by_direction_quality_reason", {})),
    ]


def _format_regime_buckets(buckets) -> list[str]:
    if not buckets:
        return ["None"]
    lines = []
    for key in sorted(buckets):
        bucket = buckets[key]
        lines.append(
            f"{key:<35}: count={bucket.count}, wins={bucket.wins}, "
            f"losses={bucket.losses}, open={bucket.open_trades}, pnl={bucket.pnl}"
        )
    return lines


def _format_sl_tp_outcome_diagnostics(diagnostics, show_trades: bool = False) -> list[str]:
    lines = [
        "",
        "===== SL/TP OUTCOME DIAGNOSTICS =====",
        f"Total Trades             : {diagnostics.total_trades}",
        f"Closed Trades            : {diagnostics.closed_trades}",
        f"Open Trades              : {diagnostics.open_trades}",
        f"Wins                     : {diagnostics.wins}",
        f"Losses                   : {diagnostics.losses}",
        "",
        f"Average Bars Held        : {_format_optional_float(diagnostics.average_bars_held)}",
        f"Average MAE R            : {_format_optional_float(diagnostics.average_mae_r)}",
        f"Average MFE R            : {_format_optional_float(diagnostics.average_mfe_r)}",
        f"Average TP Progress      : {_format_optional_float(diagnostics.average_tp_progress)}",
        f"Average SL Progress      : {_format_optional_float(diagnostics.average_sl_progress)}",
        "",
        f"Fast Losses              : {diagnostics.fast_loss_count}",
        f"Almost TP Then Loss      : {diagnostics.almost_tp_then_loss_count}",
        f"No Follow-through Loss   : {diagnostics.no_follow_through_loss_count}",
        f"High RR Losses           : {diagnostics.high_rr_loss_count}",
        "",
        f"Reached 25% TP           : {diagnostics.reached_25_pct_tp_count}",
        f"Reached 50% TP           : {diagnostics.reached_50_pct_tp_count}",
        f"Reached 75% TP           : {diagnostics.reached_75_pct_tp_count}",
        f"Reached 25% SL           : {diagnostics.reached_25_pct_sl_count}",
        f"Reached 50% SL           : {diagnostics.reached_50_pct_sl_count}",
        f"Reached 75% SL           : {diagnostics.reached_75_pct_sl_count}",
        "",
        "Winners:",
        f"Average MFE R            : {_format_optional_float(diagnostics.average_mfe_r_winners)}",
        f"Average MAE R            : {_format_optional_float(diagnostics.average_mae_r_winners)}",
        "",
        "Losers:",
        f"Average MFE R            : {_format_optional_float(diagnostics.average_mfe_r_losers)}",
        f"Average MAE R            : {_format_optional_float(diagnostics.average_mae_r_losers)}",
        "",
        "Direction Outcomes:",
        f"LONG Wins                : {diagnostics.long_win_count}",
        f"LONG Losses              : {diagnostics.long_loss_count}",
        f"SHORT Wins               : {diagnostics.short_win_count}",
        f"SHORT Losses             : {diagnostics.short_loss_count}",
    ]

    lines.extend(["", "SL/TP Trade Log:"])
    if not diagnostics.records:
        lines.append("No trades.")
    elif not show_trades:
        lines.append("Hidden. Use --show-trades to display SL/TP trade log rows.")
    else:
        for record in diagnostics.records:
            lines.append(_format_sl_tp_trade_row(record))
    return lines


def _format_sl_tp_trade_row(record) -> str:
    return (
        f"#{record.trade_number} | {record.direction} | {record.result} | "
        f"bars={record.bars_held} | mae_r={record.mae_r} | mfe_r={record.mfe_r} | "
        f"tp_progress={record.tp_progress} | sl_progress={record.sl_progress} | "
        f"fast_loss={record.fast_loss} | high_rr_loss={record.high_rr_loss}"
    )


def _format_entry_followthrough_diagnostics(diagnostics, show_trades: bool = False) -> list[str]:
    lines = [
        "",
        "===== ENTRY FOLLOW-THROUGH DIAGNOSTICS =====",
        f"Total Trades                  : {diagnostics.total_trades}",
        f"Closed Trades                 : {diagnostics.closed_trades}",
        f"Open Trades                   : {diagnostics.open_trades}",
        f"Wins                          : {diagnostics.wins}",
        f"Losses                        : {diagnostics.losses}",
        "",
        "Next Candle:",
        f"Available                     : {diagnostics.next_candle_available_count}",
        f"Continuation                  : {diagnostics.next_candle_continuation_count}",
        f"Rejection                     : {diagnostics.next_candle_rejection_count}",
        "",
        "Early Movement:",
        f"Immediate Favorable           : {diagnostics.immediate_favorable_count}",
        f"Immediate Adverse             : {diagnostics.immediate_adverse_count}",
        f"No Follow-through H3          : {diagnostics.no_followthrough_3_count}",
        f"Strong Follow-through H3      : {diagnostics.strong_followthrough_3_count}",
        f"Early Reversal H3             : {diagnostics.early_reversal_3_count}",
        "",
        "Averages:",
        f"Avg H1 Favorable R            : {_format_optional_float(diagnostics.average_h1_favorable_r)}",
        f"Avg H1 Adverse R              : {_format_optional_float(diagnostics.average_h1_adverse_r)}",
        f"Avg H3 Favorable R            : {_format_optional_float(diagnostics.average_h3_favorable_r)}",
        f"Avg H3 Adverse R              : {_format_optional_float(diagnostics.average_h3_adverse_r)}",
        f"Avg H5 Favorable R            : {_format_optional_float(diagnostics.average_h5_favorable_r)}",
        f"Avg H5 Adverse R              : {_format_optional_float(diagnostics.average_h5_adverse_r)}",
        "",
        "By Result:",
        f"Winners Avg H3 Favorable R    : {_format_optional_float(diagnostics.winners_average_h3_favorable_r)}",
        f"Losers Avg H3 Favorable R     : {_format_optional_float(diagnostics.losers_average_h3_favorable_r)}",
        f"Winners Next Continuation     : {diagnostics.winners_next_candle_continuation_count}",
        f"Losers Next Continuation      : {diagnostics.losers_next_candle_continuation_count}",
        "",
        "By Trigger:",
    ]
    if diagnostics.trigger_counts:
        for trigger in sorted(diagnostics.trigger_counts):
            lines.append(
                f"{trigger:<30}: count={diagnostics.trigger_counts.get(trigger, 0)}, "
                f"wins={diagnostics.trigger_win_counts.get(trigger, 0)}, "
                f"losses={diagnostics.trigger_loss_counts.get(trigger, 0)}, "
                f"avg_h3_fav_r={_format_optional_float(diagnostics.trigger_average_h3_favorable_r.get(trigger))}, "
                f"avg_h3_adv_r={_format_optional_float(diagnostics.trigger_average_h3_adverse_r.get(trigger))}"
            )
    else:
        lines.append("None")

    lines.extend(
        [
            "",
            "By Direction:",
            f"LONG No Follow-through H3     : {diagnostics.long_no_followthrough_3_count}",
            f"SHORT No Follow-through H3    : {diagnostics.short_no_followthrough_3_count}",
            f"LONG Early Reversal H3        : {diagnostics.long_early_reversal_3_count}",
            f"SHORT Early Reversal H3       : {diagnostics.short_early_reversal_3_count}",
            "",
            "Entry Follow-through Trade Log:",
        ]
    )
    if not diagnostics.records:
        lines.append("No trades.")
    elif not show_trades:
        lines.append("Hidden. Use --show-trades to display entry follow-through trade log rows.")
    else:
        for record in diagnostics.records:
            lines.append(_format_entry_followthrough_trade_row(record))
    return lines


def _format_entry_followthrough_trade_row(record) -> str:
    h1 = record.horizons.get(1)
    h3 = record.horizons.get(3)
    return (
        f"#{record.trade_number} | {record.direction} | {record.result} | "
        f"trigger={record.entry_trigger_type} | next_cont={record.next_candle_continuation} | "
        f"h1_fav_r={getattr(h1, 'favorable_r', None)} | h1_adv_r={getattr(h1, 'adverse_r', None)} | "
        f"h3_fav_r={getattr(h3, 'favorable_r', None)} | h3_adv_r={getattr(h3, 'adverse_r', None)} | "
        f"no_ft3={record.no_followthrough_3} | early_rev3={record.early_reversal_3}"
    )


def _format_virtual_exit_diagnostics(diagnostics, show_trades: bool = False) -> list[str]:
    lines = [
        "",
        "===== VIRTUAL EXIT DIAGNOSTICS =====",
        f"Total Trades                 : {diagnostics.total_trades}",
        f"Actual Wins                  : {diagnostics.actual_wins}",
        f"Actual Losses                : {diagnostics.actual_losses}",
        f"Actual Open Trades           : {diagnostics.actual_open_trades}",
        f"Actual Total PnL R           : {_format_optional_float(diagnostics.actual_total_pnl_r)}",
        "",
        f"Best Policy by Total PnL R   : {_format_optional_float(diagnostics.best_policy_by_total_pnl_r)}",
        f"Best Policy by Win Rate      : {_format_optional_float(diagnostics.best_policy_by_win_rate)}",
        f"Best Policy by Avg PnL R     : {_format_optional_float(diagnostics.best_policy_by_average_pnl_r)}",
        "",
        "Improvement Counts:",
        f"TP 1R Would Win              : {diagnostics.tp_1r_would_have_won_count}",
        f"TP 1.5R Would Win            : {diagnostics.tp_1_5r_would_have_won_count}",
        f"TP 2R Would Win              : {diagnostics.tp_2r_would_have_won_count}",
        f"TP 3R Would Win              : {diagnostics.tp_3r_would_have_won_count}",
        f"BE 0.5R Would Help           : {diagnostics.be_0_5r_would_help_count}",
        f"BE 1R Would Help             : {diagnostics.be_1r_would_help_count}",
        "",
        "High RR Loss Analysis:",
        f"High RR Losses               : {diagnostics.high_rr_loss_count}",
        f"High RR Loss TP 1R Wins      : {diagnostics.high_rr_loss_tp_1r_wins}",
        f"High RR Loss TP 1.5R Wins    : {diagnostics.high_rr_loss_tp_1_5r_wins}",
        f"High RR Loss BE 0.5R Saved   : {diagnostics.high_rr_loss_be_0_5r_saved}",
        f"High RR Loss BE 1R Saved     : {diagnostics.high_rr_loss_be_1r_saved}",
        "",
        "Policy Summary:",
    ]
    if diagnostics.policy_summaries:
        for policy_name in [
            "TP_1R",
            "TP_1_5R",
            "TP_2R",
            "TP_3R",
            "BE_AFTER_0_5R",
            "BE_AFTER_1R",
            "TP_1R_STOP",
            "TP_1_5R_STOP",
        ]:
            summary = diagnostics.policy_summaries.get(policy_name)
            if summary is None:
                continue
            lines.append(
                f"{policy_name:<30}: trades={summary.total_trades}, wins={summary.wins}, "
                f"losses={summary.losses}, be={summary.breakevens}, open={summary.opens}, "
                f"win_rate={_format_optional_float(summary.win_rate)}, "
                f"total_pnl_r={summary.total_pnl_r}, avg_pnl_r={_format_optional_float(summary.average_pnl_r)}"
            )
    else:
        lines.append("None")

    lines.extend(["", "Virtual Exit Trade Log:"])
    if not diagnostics.records:
        lines.append("No trades.")
    elif not show_trades:
        lines.append("Hidden. Use --show-trades to display virtual exit trade log rows.")
    else:
        for record in diagnostics.records:
            lines.append(_format_virtual_exit_trade_row(record))
    return lines


def _format_virtual_exit_trade_row(record) -> str:
    tp_1r = record.policy_results.get("TP_1R")
    tp_2r = record.policy_results.get("TP_2R")
    be = record.policy_results.get("BE_AFTER_0_5R")
    best = f"{record.best_policy_name}:{record.best_policy_pnl_r}R" if record.best_policy_name else "None"
    return (
        f"#{record.trade_number} | {record.direction} | ACTUAL={record.actual_result} | "
        f"actual_r={record.actual_pnl_r} | best={best} | "
        f"TP_1R={_policy_result_text(tp_1r)} | TP_2R={_policy_result_text(tp_2r)} | "
        f"BE_0_5R={_policy_result_text(be)}"
    )


def _policy_result_text(result) -> str:
    if result is None:
        return "None"
    return f"{result.result}:{result.virtual_pnl_r}R"


def _format_diagnostics(diagnostics) -> list[str]:
    lines = [
        "",
        "===== BACKTEST DIAGNOSTICS =====",
        f"Windows Analyzed : {diagnostics.windows_analyzed}",
        "",
        "Setup Status Counts:",
        *_format_counts(diagnostics.setup_status_counts),
        "",
        "Setup Blockers:",
        *_format_counts(diagnostics.setup_blockers, sort_by_count=True),
        "",
        "Entry Status Counts:",
        *_format_counts(diagnostics.entry_status_counts),
        "",
        "Entry Blockers:",
        *_format_counts(diagnostics.entry_blockers, sort_by_count=True),
        "",
        "Trade Plan Status Counts:",
        *_format_counts(diagnostics.trade_plan_status_counts),
        "",
        "Trade Plan Blockers:",
        *_format_counts(diagnostics.trade_plan_blockers, sort_by_count=True),
        "",
        "Trade Quality Status Counts:",
        *_format_counts(diagnostics.trade_quality_status_counts),
        "",
        "Trade Quality Blockers:",
        *_format_counts(diagnostics.trade_quality_blockers, sort_by_count=True),
        "",
        "Paper Trade Status Counts:",
        *_format_counts(diagnostics.paper_trade_status_counts),
        "",
        "Paper Trade Blockers:",
        *_format_counts(diagnostics.paper_trade_blockers, sort_by_count=True),
    ]
    ote_diagnostics = getattr(diagnostics, "ote_diagnostics", None)
    if ote_diagnostics is not None:
        lines.extend(_format_ote_diagnostics(ote_diagnostics))
    dealing_range_diagnostics = getattr(diagnostics, "dealing_range_diagnostics", None)
    if dealing_range_diagnostics is not None:
        lines.extend(_format_dealing_range_diagnostics(dealing_range_diagnostics))
    range_candidate_diagnostics = getattr(diagnostics, "range_candidate_diagnostics", None)
    if range_candidate_diagnostics is not None:
        lines.extend(_format_range_candidate_diagnostics(range_candidate_diagnostics))
    return lines


def _format_counts(counts: dict[str, int], sort_by_count: bool = False) -> list[str]:
    if not counts:
        return ["None"]

    if sort_by_count:
        items = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    else:
        items = sorted(counts.items())
    return [f"{name:<30}: {count}" for name, count in items]


def _format_ote_diagnostics(diagnostics) -> list[str]:
    return [
        "",
        "===== OTE DISTANCE DIAGNOSTICS =====",
        f"Windows Analyzed           : {diagnostics.windows_analyzed}",
        f"OTE Available              : {diagnostics.ote_available_count}",
        f"OTE Missing                : {diagnostics.ote_missing_count}",
        f"In OTE                     : {diagnostics.in_ote_count}",
        f"Not In OTE                 : {diagnostics.not_in_ote_count}",
        f"Near OTE <= 0.1%           : {diagnostics.near_ote_0_1_pct_count}",
        f"Near OTE <= 0.25%          : {diagnostics.near_ote_0_25_pct_count}",
        f"Near OTE <= 0.5%           : {diagnostics.near_ote_0_5_pct_count}",
        f"Near OTE <= 1.0%           : {diagnostics.near_ote_1_0_pct_count}",
        f"Average Distance To OTE    : {_format_optional_float(diagnostics.average_distance_to_ote)}",
        f"Median Distance To OTE     : {_format_optional_float(diagnostics.median_distance_to_ote)}",
        f"Max Distance To OTE        : {_format_optional_float(diagnostics.max_distance_to_ote)}",
        "",
        "Price Zone Counts:",
        f"PREMIUM                    : {diagnostics.premium_count}",
        f"DISCOUNT                   : {diagnostics.discount_count}",
        f"EQUILIBRIUM                : {diagnostics.equilibrium_count}",
        f"UNKNOWN                    : {diagnostics.unknown_zone_count}",
        "",
        "OTE Direction Counts:",
        f"BULLISH                    : {diagnostics.bullish_ote_count}",
        f"BEARISH                    : {diagnostics.bearish_ote_count}",
        f"NONE                       : {diagnostics.none_ote_count}",
        "",
        "Equilibrium Distance:",
        f"Near EQ <= 0.1%            : {diagnostics.near_equilibrium_0_1_pct_count}",
        f"Near EQ <= 0.25%           : {diagnostics.near_equilibrium_0_25_pct_count}",
        f"Near EQ <= 0.5%            : {diagnostics.near_equilibrium_0_5_pct_count}",
        f"Average Distance To EQ     : {_format_optional_float(diagnostics.average_distance_to_equilibrium)}",
        f"Median Distance To EQ      : {_format_optional_float(diagnostics.median_distance_to_equilibrium)}",
        f"Max Distance To EQ         : {_format_optional_float(diagnostics.max_distance_to_equilibrium)}",
    ]


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return "None"
    return str(value)


def _format_dealing_range_diagnostics(diagnostics) -> list[str]:
    return [
        "",
        "===== DEALING RANGE DIAGNOSTICS =====",
        f"Windows Analyzed              : {diagnostics.windows_analyzed}",
        f"Range Available               : {diagnostics.range_available_count}",
        f"Range Missing                 : {diagnostics.range_missing_count}",
        f"Invalid Range                 : {diagnostics.invalid_range_count}",
        "",
        "Range Size:",
        f"Average Range Size            : {_format_optional_float(diagnostics.average_range_size)}",
        f"Median Range Size             : {_format_optional_float(diagnostics.median_range_size)}",
        f"Min Range Size                : {_format_optional_float(diagnostics.min_range_size)}",
        f"Max Range Size                : {_format_optional_float(diagnostics.max_range_size)}",
        f"Average Range Size %          : {_format_optional_float(diagnostics.average_range_size_percent)}",
        f"Median Range Size %           : {_format_optional_float(diagnostics.median_range_size_percent)}",
        f"Min Range Size %              : {_format_optional_float(diagnostics.min_range_size_percent)}",
        f"Max Range Size %              : {_format_optional_float(diagnostics.max_range_size_percent)}",
        "",
        "Equilibrium Distance:",
        f"Average Distance To EQ        : {_format_optional_float(diagnostics.average_distance_to_equilibrium)}",
        f"Median Distance To EQ         : {_format_optional_float(diagnostics.median_distance_to_equilibrium)}",
        f"Max Distance To EQ            : {_format_optional_float(diagnostics.max_distance_to_equilibrium)}",
        f"Average Distance To EQ %      : {_format_optional_float(diagnostics.average_distance_to_equilibrium_percent)}",
        f"Median Distance To EQ %       : {_format_optional_float(diagnostics.median_distance_to_equilibrium_percent)}",
        f"Max Distance To EQ %          : {_format_optional_float(diagnostics.max_distance_to_equilibrium_percent)}",
        "",
        "Zone Counts:",
        f"PREMIUM                       : {diagnostics.premium_count}",
        f"DISCOUNT                      : {diagnostics.discount_count}",
        f"EQUILIBRIUM                   : {diagnostics.equilibrium_count}",
        f"UNKNOWN                       : {diagnostics.unknown_zone_count}",
        "",
        "Trend Counts:",
        f"UPTREND                       : {diagnostics.uptrend_count}",
        f"DOWNTREND                     : {diagnostics.downtrend_count}",
        f"RANGE                         : {diagnostics.range_trend_count}",
        f"UNKNOWN                       : {diagnostics.unknown_trend_count}",
        "",
        "Trend / Zone Matrix:",
        *_format_matrix(diagnostics.trend_zone_counts),
        "",
        "OTE Direction / Zone Matrix:",
        *_format_matrix(diagnostics.ote_direction_zone_counts),
        "",
        "Mismatch Counts:",
        f"BEARISH_OTE_IN_DISCOUNT       : {diagnostics.bearish_ote_discount_count}",
        f"BULLISH_OTE_IN_PREMIUM        : {diagnostics.bullish_ote_premium_count}",
        f"DOWNTREND_IN_DISCOUNT         : {diagnostics.downtrend_discount_count}",
        f"UPTREND_IN_PREMIUM            : {diagnostics.uptrend_premium_count}",
        "",
        "Range Age:",
        f"Average External High Age     : {_format_optional_float(diagnostics.average_external_high_age)}",
        f"Average External Low Age      : {_format_optional_float(diagnostics.average_external_low_age)}",
        f"Max External High Age         : {_format_optional_float(diagnostics.max_external_high_age)}",
        f"Max External Low Age          : {_format_optional_float(diagnostics.max_external_low_age)}",
    ]


def _format_matrix(counts: dict[str, int]) -> list[str]:
    if not counts:
        return ["None"]
    items = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [f"{key:<30}: {count}" for key, count in items]


def _format_range_candidate_diagnostics(diagnostics) -> list[str]:
    best_aligned = diagnostics.best_candidate_by_aligned_zone()
    best_in_ote = diagnostics.best_candidate_by_in_ote()
    best_wrong_zone_fix = diagnostics.best_candidate_by_wrong_zone_fix()
    lines = [
        "",
        "===== RANGE CANDIDATE DIAGNOSTICS =====",
        f"Windows Analyzed              : {diagnostics.windows_analyzed}",
        "",
        f"Best By Aligned Zone          : {_candidate_name_or_none(best_aligned)}",
        f"Best By In OTE                : {_candidate_name_or_none(best_in_ote)}",
        f"Best By Wrong Zone Fix        : {_candidate_name_or_none(best_wrong_zone_fix)}",
    ]
    for candidate_name in [
        "CURRENT_EXTERNAL_RANGE",
        "RECENT_50_CANDLE_RANGE",
        "RECENT_100_CANDLE_RANGE",
        "RECENT_200_CANDLE_RANGE",
        "RECENT_SWING_RANGE",
    ]:
        stats = diagnostics.candidates.get(candidate_name)
        if stats is None:
            continue
        lines.extend(_format_range_candidate_stats(stats))
    return lines


def _candidate_name_or_none(stats) -> str:
    if stats is None:
        return "None"
    return stats.candidate_name


def _format_range_candidate_stats(stats) -> list[str]:
    return [
        "",
        f"--- {stats.candidate_name} ---",
        f"Available                     : {stats.available_count}",
        f"Missing                       : {stats.missing_count}",
        f"Invalid                       : {stats.invalid_count}",
        f"Premium                       : {stats.premium_count}",
        f"Discount                      : {stats.discount_count}",
        f"Equilibrium                   : {stats.equilibrium_count}",
        f"Unknown Zone                  : {stats.unknown_zone_count}",
        f"In OTE                        : {stats.in_ote_count}",
        f"Not In OTE                    : {stats.not_in_ote_count}",
        f"OTE Unavailable               : {stats.ote_unavailable_count}",
        f"Near OTE <= 0.1%              : {stats.near_ote_0_1_pct_count}",
        f"Near OTE <= 0.25%             : {stats.near_ote_0_25_pct_count}",
        f"Near OTE <= 0.5%              : {stats.near_ote_0_5_pct_count}",
        f"Near OTE <= 1.0%              : {stats.near_ote_1_0_pct_count}",
        f"Average Distance To OTE       : {_format_optional_float(stats.average_distance_to_ote)}",
        f"Median Distance To OTE        : {_format_optional_float(stats.median_distance_to_ote)}",
        f"Max Distance To OTE           : {_format_optional_float(stats.max_distance_to_ote)}",
        f"Average Range Size            : {_format_optional_float(stats.average_range_size)}",
        f"Median Range Size             : {_format_optional_float(stats.median_range_size)}",
        f"Average Range Size %          : {_format_optional_float(stats.average_range_size_percent)}",
        f"Median Range Size %           : {_format_optional_float(stats.median_range_size_percent)}",
        f"Bearish OTE + Premium         : {stats.bearish_ote_premium_count}",
        f"Bearish OTE + Discount        : {stats.bearish_ote_discount_count}",
        f"Bullish OTE + Discount        : {stats.bullish_ote_discount_count}",
        f"Bullish OTE + Premium         : {stats.bullish_ote_premium_count}",
        f"Aligned Zone Count            : {stats.candidate_aligned_zone_count}",
        f"Wrong Zone Count              : {stats.candidate_wrong_zone_count}",
        f"Fix Wrong Zone Count          : {stats.candidate_fix_wrong_zone_count}",
        f"Fix Not In OTE Count          : {stats.candidate_fix_not_in_ote_count}",
        f"Fix Near OTE <= 0.5% Count    : {stats.candidate_fix_near_ote_0_5_count}",
    ]
