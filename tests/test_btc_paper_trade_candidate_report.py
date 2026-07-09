from __future__ import annotations

from models.btc_paper_trade_candidate import (
    BTCPaperTradeCandidate,
    BTCPaperTradeCandidateResult,
    BTCPaperTradeCandidateValidationReport,
)
from reporting.btc_paper_trade_candidate_report import (
    format_btc_paper_trade_candidate_result,
    format_btc_paper_trade_candidate_validation_report,
)


def test_validation_report_displays_safety_fields() -> None:
    report = BTCPaperTradeCandidateValidationReport(
        config_path="configs/btc_paper_trade_candidate.json",
        status="PASS",
        diagnostics={
            "runtime_config_status": "PASS",
            "monitoring_config_status": "PASS",
            "runner_config_status": "PASS",
            "signal_config_status": "PASS",
        },
    )

    rendered = format_btc_paper_trade_candidate_validation_report(report)

    assert "BTC PAPER TRADE CANDIDATE CONFIG VALIDATION" in rendered
    assert "Runtime Config    : PASS" in rendered
    assert "Signal Config     : PASS" in rendered


def test_result_report_displays_candidate_and_non_execution_safety() -> None:
    candidate = BTCPaperTradeCandidate(
        candidate_id="BTC-DRYRUN-1",
        created_at="2026-01-01T00:00:00+00:00",
        symbol="BTC/USDT",
        strategy_profile="balanced_smc_decision_065",
        direction="LONG",
        entry_price=100.0,
        stop_loss=99.0,
        take_profit=101.5,
        risk_reward=1.5,
        signal_score=0.8,
        signal_threshold=0.65,
        account_currency="USDT",
        starting_equity=10000.0,
        risk_per_trade_pct=0.005,
        estimated_risk_amount=50.0,
        estimated_position_size=50.0,
        estimated_notional=5000.0,
        max_candidate_notional=2500.0,
    )
    result = BTCPaperTradeCandidateResult(
        status="PASS",
        decision="CANDIDATE_CREATED_DRY_RUN",
        candidate_created=True,
        candidate=candidate,
        signal_decision="APPROVED_DRY_RUN",
        signal_score=0.8,
        safety_summary={"kill_switch_enabled": True},
    )

    rendered = format_btc_paper_trade_candidate_result(result)

    assert "BTC PAPER TRADE CANDIDATE DRY-RUN" in rendered
    assert "Candidate Created   : true" in rendered
    assert "Direction           : LONG" in rendered
    assert "Executable          : false" in rendered
    assert "Paper Persisted     : false" in rendered
    assert "Order Submitted     : false" in rendered
