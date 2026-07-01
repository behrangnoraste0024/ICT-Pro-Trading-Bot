from __future__ import annotations

import json

import pytest

from scripts.run_strategy_comparison import main


FIXTURE_PATH = "tests/fixtures/btcusdt_100_candles.json"


def test_help_works(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])

    captured = capsys.readouterr()
    assert exc.value.code == 0
    assert "Compare rolling backtest strategy configurations" in captured.out


def test_default_run_on_fixture_exits_successfully(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--strategy-set", "default"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[strategy-comparison] starting" in captured.out
    assert "[strategy-comparison] finished" in captured.out
    assert "===== STRATEGY COMPARISON REPORT =====" in captured.out
    assert "Strategies   : 7" in captured.out


def test_exit_modes_recent_50_strategy_set_works(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--strategy-set", "exit_modes_recent_50"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "recent_50|fixed_1r|min_rr=1.0" in captured.out
    assert "recent_50|fixed_3r|min_rr=3.0" in captured.out


def test_current_external_only_strategy_set_works(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--strategy-set", "current_external_only"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 4" in captured.out
    assert "current_external|fixed_1_5r|min_rr=1.5" in captured.out


def test_custom_strategy_set_works(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "custom",
            "--dealing-range-modes",
            "recent_50",
            "--exit-modes",
            "fixed_1r,fixed_1_5r",
            "--min-risk-rewards",
            "1.0,1.5",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Strategies   : 4" in captured.out
    assert "recent_50|fixed_1_5r|min_rr=1.5" in captured.out


def test_fast_mode_exits_successfully(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "current_external_only",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "===== STRATEGY COMPARISON REPORT =====" in captured.out


def test_progress_every_prints_rolling_progress(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "exit_modes_recent_50",
            "--progress-every",
            "25",
            "--fast",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 0
    assert "processed=" in captured.out
    assert "duplicates=" in captured.out


def test_output_json_writes_valid_json(tmp_path) -> None:
    output_path = tmp_path / "comparison.json"

    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "current_external_only",
            "--output-json",
            str(output_path),
        ]
    )

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert return_code == 0
    assert data["event_type"] == "STRATEGY_COMPARISON_REPORT"
    assert data["strategies"]
    assert "elapsed_seconds" in data["strategies"][0]


def test_output_csv_writes_headers(tmp_path) -> None:
    output_path = tmp_path / "comparison.csv"

    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--min-candles",
            "50",
            "--strategy-set",
            "current_external_only",
            "--output-csv",
            str(output_path),
        ]
    )

    text = output_path.read_text(encoding="utf-8")
    assert return_code == 0
    assert "strategy_name" in text.splitlines()[0]
    assert "net_pnl" in text.splitlines()[0]
    assert "elapsed_seconds" in text.splitlines()[0]


def test_invalid_strategy_set_rejected_by_argparse() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--fixture", FIXTURE_PATH, "--strategy-set", "bad"])

    assert exc.value.code == 2


def test_invalid_exit_mode_in_custom_returns_error(capsys) -> None:
    return_code = main(
        [
            "--fixture",
            FIXTURE_PATH,
            "--strategy-set",
            "custom",
            "--dealing-range-modes",
            "recent_50",
            "--exit-modes",
            "fixed_4r",
            "--min-risk-rewards",
            "1.0",
        ]
    )

    captured = capsys.readouterr()
    assert return_code == 1
    assert "Unsupported exit mode" in captured.out


def test_script_does_not_require_historical_file(capsys) -> None:
    return_code = main(["--fixture", FIXTURE_PATH, "--min-candles", "50", "--strategy-set", "current_external_only"])

    assert return_code == 0
