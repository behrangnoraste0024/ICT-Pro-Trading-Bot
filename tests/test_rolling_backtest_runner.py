from __future__ import annotations

import importlib
from pathlib import Path

from models.rolling_backtest_result import RollingBacktestResult
from reporting.rolling_backtest_report import format_rolling_backtest_report
from scripts.run_rolling_backtest import main


FIXTURE_PATH = "tests/fixtures/btcusdt_100_candles.json"


def _result() -> RollingBacktestResult:
    return RollingBacktestResult(
        total_windows=100,
        processed_windows=51,
        skipped_windows=49,
        failed_windows=0,
        min_candles=50,
        total_paper_trades=5,
        closed_trades=4,
        open_trades=1,
        wins=3,
        losses=1,
        win_rate=75.0,
        net_pnl=25.0,
        average_pnl=6.25,
        max_drawdown=5.0,
        ignored_contexts=46,
    )


def test_formatter_includes_key_metrics() -> None:
    report = format_rolling_backtest_report(_result(), FIXTURE_PATH, 50)

    assert "ROLLING BACKTEST REPORT" in report
    assert "Total Windows" in report
    assert "Processed Windows" in report
    assert "Win Rate" in report
    assert "Net PnL" in report
    assert "Max Drawdown" in report


def test_formatter_includes_fixture_path_and_min_candles() -> None:
    report = format_rolling_backtest_report(_result(), FIXTURE_PATH, 50)

    assert FIXTURE_PATH in report
    assert "Min Candles       : 50" in report


def test_runner_loads_fixture_and_returns_success(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "ROLLING BACKTEST REPORT" in captured.out


def test_missing_fixture_returns_failure(capsys) -> None:
    return_code = main(["--fixture", "missing_file.json"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "fixture not found" in captured.out


def test_invalid_min_candles_returns_failure(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "0"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "--min-candles must be greater than 0" in captured.out


def test_no_live_network_uses_fixture_only() -> None:
    assert Path(FIXTURE_PATH).exists()
    assert main(["--fixture", FIXTURE_PATH, "--min-candles", "100"]) == 0


def test_script_import_is_safe() -> None:
    module = importlib.import_module("scripts.run_rolling_backtest")

    assert hasattr(module, "main")


def test_main_success_stdout_contains_report_header(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "100"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "===== ROLLING BACKTEST REPORT =====" in captured.out
