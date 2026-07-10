from __future__ import annotations

from models.btc_paper_account import (
    BTCPaperAccountAction,
    BTCPaperAccountActionResult,
    BTCPaperAccountConfig,
    BTCPaperAccountDecision,
    BTCPaperAccountIssue,
    BTCPaperAccountLedgerEntry,
    BTCPaperAccountLedgerSummary,
    BTCPaperAccountState,
    BTCPaperAccountStatus,
    BTCPaperAccountValidationReport,
)
from reporting.btc_paper_account_report import (
    format_btc_paper_account_action_result,
    format_btc_paper_account_ledger_summary,
    format_btc_paper_account_validation_report,
)


def test_validation_report_displays_safety_flags() -> None:
    report = BTCPaperAccountValidationReport(
        config_path="configs/btc_paper_account.json",
        status=BTCPaperAccountStatus.PASS.value,
        config=BTCPaperAccountConfig(),
        diagnostics={"runtime_config_status": "PASS", "live_market_feed_config_status": "PASS"},
    )

    text = format_btc_paper_account_validation_report(report)

    assert "BTC LOCAL PAPER ACCOUNT CONFIG VALIDATION" in text
    assert "Simulation Only   : true" in text
    assert "Trading API       : false" in text
    assert "Real Orders       : false" in text
    assert "Runtime Config    : PASS" in text


def test_action_result_report_displays_account_and_safety_summary() -> None:
    result = BTCPaperAccountActionResult(
        action=BTCPaperAccountAction.SIMULATE_LIVE_OBSERVATION.value,
        status=BTCPaperAccountStatus.PASS.value,
        decision=BTCPaperAccountDecision.VIRTUAL_POSITION_OPENED.value,
        state_path="reports/paper_account/state.json",
        ledger_path="reports/paper_account/ledger.jsonl",
        state_exists=True,
        account_state=BTCPaperAccountState(cash_balance=9990.0, equity=10010.0, total_fees=4.0),
        virtual_order_created=True,
        virtual_position_created=True,
        safety_summary={
            "simulation_only": True,
            "dry_run_only": True,
            "private_api_used": False,
            "api_key_used": False,
            "trading_api_used": False,
            "account_data_used": False,
            "balance_fetch_used": False,
            "position_fetch_used": False,
            "real_order_submitted": False,
            "order_cancelled": False,
            "real_position_created": False,
            "exchange_connected_for_trading": False,
            "executable_trade_created": False,
            "runner_state_mutated": False,
            "execution_state_mutated": False,
        },
    )

    text = format_btc_paper_account_action_result(result)

    assert "BTC LOCAL PAPER ACCOUNT" in text
    assert "Virtual Order      : true" in text
    assert "Real Order Sent    : false" in text
    assert "Runner Mutated     : false" in text


def test_ledger_summary_report_displays_counts_and_entries() -> None:
    summary = BTCPaperAccountLedgerSummary(
        ledger_path="reports/paper_account/ledger.jsonl",
        status=BTCPaperAccountStatus.PASS.value,
        entries_read=1,
        virtual_orders=1,
        entries=[
            BTCPaperAccountLedgerEntry(
                entry_id="L1",
                created_at="2026-01-01T00:00:00+00:00",
                entry_type="VIRTUAL_ORDER",
                symbol="BTC/USDT",
                decision="VIRTUAL_ORDER_CREATED",
                balance_before=10000.0,
                balance_after=9995.0,
                equity_before=10000.0,
                equity_after=9995.0,
                realized_pnl_delta=0.0,
                unrealized_pnl_delta=0.0,
                virtual_order_id="O1",
                virtual_position_id="P1",
                reason="created",
            )
        ],
        issues=[BTCPaperAccountIssue(name="sample", severity="INFO", message="ok")],
    )

    text = format_btc_paper_account_ledger_summary(summary)

    assert "BTC LOCAL PAPER ACCOUNT LEDGER SUMMARY" in text
    assert "Virtual Orders     : 1" in text
    assert "VIRTUAL_ORDER_CREATED" in text
    assert "sample | INFO | ok" in text
