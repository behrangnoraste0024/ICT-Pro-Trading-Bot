from __future__ import annotations

import json

import pytest

from engine.diagnostics.snapshot_comparison_engine import SnapshotComparisonEngine


def _row(**overrides):
    values = {
        "sample_name": "btcusdt_15m_1000",
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "status": "PASSED",
        "recommended_profile": "balanced_smc_decision_065",
        "total_trades": 5,
        "wins": 5,
        "losses": 0,
        "win_rate": 100.0,
        "net_pnl_after_costs": 1404.24,
        "max_drawdown": 0.0,
        "validation_status": "PASS",
        "profitable_segments": 4,
        "losing_segments": 0,
        "empty_segments": 0,
        "worst_segment_net_pnl_after_costs": 157.54,
    }
    values.update(overrides)
    return values


def _snapshot(rows=None, profile="balanced_smc_decision_065"):
    return {
        "metadata": {
            "snapshot_schema_version": "2.50.0",
            "created_at": "2026-07-07T12:00:00+00:00",
            "git_commit": "abc123",
            "git_branch": "v1-core",
            "recommended_profile": profile,
        },
        "multi_sample_result": {
            "rows": [_row()] if rows is None else rows,
            "total_samples": 1,
        },
    }


def _compare(baseline=None, candidate=None):
    return SnapshotComparisonEngine().compare_snapshots(
        _snapshot() if baseline is None else baseline,
        _snapshot() if candidate is None else candidate,
        "baseline.json",
        "candidate.json",
    )


def test_compares_matching_sample_rows_and_computes_deltas() -> None:
    result = _compare(candidate=_snapshot([_row(net_pnl_after_costs=1500.0, max_drawdown=10.0)]))

    row = result.sample_comparisons[0]
    assert row.sample_name == "btcusdt_15m_1000"
    assert row.net_after_costs_delta == pytest.approx(95.76)
    assert row.max_drawdown_delta == 10.0


def test_pass_when_candidate_equals_baseline() -> None:
    result = _compare()

    assert result.regression_status == "PASS"
    assert result.passed_samples == 1


def test_improvement_flags_when_candidate_net_after_costs_increases() -> None:
    result = _compare(candidate=_snapshot([_row(net_pnl_after_costs=1500.0)]))

    assert "btcusdt_15m_1000:NET_AFTER_COSTS_INCREASED" in result.improvement_flags


def test_warning_when_net_after_costs_decreases_slightly() -> None:
    result = _compare(candidate=_snapshot([_row(net_pnl_after_costs=1350.0)]))

    assert result.regression_status == "WARNING"
    assert "NET_AFTER_COSTS_DECREASED" in result.sample_comparisons[0].regression_flags


def test_fail_when_passed_sample_becomes_failed() -> None:
    result = _compare(candidate=_snapshot([_row(status="FAILED")]))

    assert result.regression_status == "FAIL"
    assert "STATUS_PASSED_TO_FAILED" in result.sample_comparisons[0].regression_flags


def test_fail_when_wf_status_pass_becomes_fail() -> None:
    result = _compare(candidate=_snapshot([_row(validation_status="FAIL")]))

    assert result.regression_status == "FAIL"
    assert "WF_PASS_TO_FAIL" in result.sample_comparisons[0].regression_flags


def test_fail_when_net_after_costs_drops_more_than_threshold() -> None:
    result = _compare(candidate=_snapshot([_row(net_pnl_after_costs=1000.0)]))

    assert result.regression_status == "FAIL"
    assert "NET_AFTER_COSTS_DROP_FAIL" in result.sample_comparisons[0].regression_flags


def test_warning_when_win_rate_decreases() -> None:
    result = _compare(candidate=_snapshot([_row(win_rate=80.0)]))

    assert result.regression_status == "WARNING"
    assert "WIN_RATE_DECREASED" in result.sample_comparisons[0].regression_flags


def test_warning_when_profitable_segments_decreases() -> None:
    result = _compare(candidate=_snapshot([_row(profitable_segments=3)]))

    assert result.regression_status == "WARNING"
    assert "PROFITABLE_SEGMENTS_DECREASED" in result.sample_comparisons[0].regression_flags


def test_detects_recommended_profile_change() -> None:
    result = _compare(candidate=_snapshot(profile="research_baseline"))

    assert result.recommended_profile_changed is True
    assert result.regression_status == "FAIL"
    assert "RECOMMENDED_PROFILE_CHANGED" in result.regression_flags


def test_handles_sample_missing_from_candidate() -> None:
    result = _compare(candidate=_snapshot([]))

    assert result.regression_status == "WARNING"
    assert "SAMPLE_MISSING_FROM_CANDIDATE" in result.sample_comparisons[0].regression_flags


def test_handles_new_candidate_only_sample() -> None:
    result = _compare(
        baseline=_snapshot([]),
        candidate=_snapshot([_row(sample_name="new_sample", status="WARNING")]),
    )

    assert result.regression_status == "WARNING"
    assert result.sample_comparisons[0].sample_name == "new_sample"
    assert "CANDIDATE_ONLY_NON_PASSED" in result.sample_comparisons[0].regression_flags


def test_skipped_out_of_scope_candidate_does_not_flag_regression() -> None:
    result = _compare(
        baseline=_snapshot([_row(sample_name="ethusdt_15m_1000", net_pnl_after_costs=100)]),
        candidate=_snapshot([_row(sample_name="ethusdt_15m_1000", status="SKIPPED_OUT_OF_SCOPE", net_pnl_after_costs=0)]),
    )

    comparison = result.sample_comparisons[0]
    assert comparison.severity == "PASS"
    assert comparison.regression_flags == []
    assert "SKIPPED_OUT_OF_SCOPE" in comparison.improvement_flags


def test_compare_files_loads_snapshot_json(tmp_path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(json.dumps(_snapshot()), encoding="utf-8")
    candidate.write_text(json.dumps(_snapshot([_row(net_pnl_after_costs=1500.0)])), encoding="utf-8")

    result = SnapshotComparisonEngine().compare_files(str(baseline), str(candidate))

    assert result.baseline_path == str(baseline)
    assert result.candidate_path == str(candidate)
    assert result.sample_comparisons[0].net_after_costs_delta == pytest.approx(95.76)
