from __future__ import annotations

import importlib
from pathlib import Path

from models.backtest_diagnostics import BacktestDiagnostics
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


def _result_with_diagnostics() -> RollingBacktestResult:
    result = _result()
    result.diagnostics = BacktestDiagnostics(
        setup_blockers={"A": 1, "B": 3},
        entry_blockers={},
        trade_plan_blockers={},
        trade_quality_blockers={},
        paper_trade_blockers={},
        setup_status_counts={"INVALID": 2},
        entry_status_counts={"NOT_CONFIRMED": 2},
        trade_plan_status_counts={"NO_TRADE": 2},
        trade_quality_status_counts={"REJECTED": 2},
        paper_trade_status_counts={"NO_PAPER_TRADE": 2},
        windows_analyzed=2,
    )
    return result


def test_formatter_includes_key_metrics() -> None:
    report = format_rolling_backtest_report(_result(), FIXTURE_PATH, 50)

    assert "ROLLING BACKTEST REPORT" in report
    assert "Total Windows" in report
    assert "Processed Windows" in report
    assert "Win Rate" in report
    assert "Net PnL" in report
    assert "Max Drawdown" in report
    assert "Stateful Mode" in report
    assert "Opened Trades" in report
    assert "Closed By State" in report
    assert "Duplicates Skipped" in report


def test_formatter_includes_fixture_path_and_min_candles() -> None:
    report = format_rolling_backtest_report(_result(), FIXTURE_PATH, 50)

    assert FIXTURE_PATH in report
    assert "Min Candles       : 50" in report


def test_formatter_includes_max_windows_when_provided() -> None:
    report = format_rolling_backtest_report(_result(), FIXTURE_PATH, 50, 5)

    assert "Max Windows       : 5" in report


def test_report_includes_backtest_diagnostics_section() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "===== BACKTEST DIAGNOSTICS =====" in report
    assert "Windows Analyzed : 2" in report


def test_report_includes_setup_blockers() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "Setup Blockers:" in report
    assert "B                             : 3" in report


def test_report_prints_none_for_empty_blocker_sections() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert "Entry Blockers:\nNone" in report


def test_report_sorts_blockers_by_count_descending() -> None:
    report = format_rolling_backtest_report(_result_with_diagnostics(), FIXTURE_PATH, 50)

    assert report.index("B                             : 3") < report.index("A                             : 1")


def test_runner_loads_fixture_and_returns_success(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "ROLLING BACKTEST REPORT" in captured.out


def test_runner_output_includes_diagnostics_when_using_fixture(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--progress-every", "0"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "===== BACKTEST DIAGNOSTICS =====" in captured.out


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


def test_runner_accepts_max_windows(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--max-windows", "5"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Max Windows       : 5" in captured.out


def test_runner_accepts_progress_every_zero(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--progress-every", "0"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[rolling]" not in captured.out


def test_invalid_progress_every_returns_failure(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--progress-every", "-1"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "--progress-every must be greater than or equal to 0" in captured.out


def test_invalid_max_windows_returns_failure(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--max-windows", "0"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "--max-windows must be greater than 0" in captured.out


def test_stdout_contains_progress_when_progress_every_is_small(capsys) -> None:
    return_code = main(
        ["--fixture", FIXTURE_PATH, "--min-candles", "50", "--max-windows", "5", "--progress-every", "2"]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[rolling]" in captured.out


def test_stdout_does_not_contain_progress_when_progress_every_zero(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--progress-every", "0"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[rolling]" not in captured.out


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
