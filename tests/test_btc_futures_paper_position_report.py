from __future__ import annotations

from pathlib import Path

from engine.diagnostics.btc_futures_paper_position_engine import BTCFuturesPaperPositionEngine
from reporting.btc_futures_paper_position_report import (
    format_btc_futures_paper_action_result,
    format_btc_futures_paper_ledger_summary,
    format_btc_futures_paper_validation_report,
)
from tests.test_btc_futures_paper_position_engine import _engine, _write_configs


def test_validation_report_displays_safety_fields(tmp_path: Path) -> None:
    path = _write_configs(tmp_path)
    report = _engine(tmp_path).validate(str(path))

    text = format_btc_futures_paper_validation_report(report)

    assert "BTC FUTURES PAPER POSITION CONFIG VALIDATION" in text
    assert "Local Position Creation  : true" in text
    assert "Private API              : false" in text
    assert "Testnet Orders           : false" in text


def test_action_report_displays_account_position_and_safety(tmp_path: Path) -> None:
    path = _write_configs(tmp_path)
    engine = _engine(tmp_path)
    engine.initialize(str(path))
    result = engine.open_position("LONG", 64000, 64000, 62000, 67000, 1000, 3, "open", str(path))

    text = format_btc_futures_paper_action_result(result)

    assert "BTC FUTURES LOCAL PAPER POSITION" in text
    assert "Local Virtual Order     : true" in text
    assert "Local Futures Position  : true" in text
    assert "Real Order Submitted    : false" in text
    assert "Spot Account Mutated    : false" in text


def test_ledger_summary_report_displays_counts(tmp_path: Path) -> None:
    path = _write_configs(tmp_path)
    engine = BTCFuturesPaperPositionEngine(repo_root=tmp_path)
    engine.initialize(str(path))

    text = format_btc_futures_paper_ledger_summary(engine.ledger_summary(str(path)))

    assert "BTC FUTURES PAPER LEDGER SUMMARY" in text
    assert "Initialized Events     : 1" in text
