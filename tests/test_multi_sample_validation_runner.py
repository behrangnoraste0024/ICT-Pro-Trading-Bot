from __future__ import annotations

from models.multi_sample_validation import MultiSampleValidationResult, MultiSampleValidationRow
from scripts.run_multi_sample_validation import main


class _FakeMultiSampleValidationEngine:
    last_kwargs = None

    def validate(self, **kwargs) -> MultiSampleValidationResult:
        type(self).last_kwargs = kwargs
        progress = kwargs.get("progress_callback")
        if progress is not None:
            progress(
                {
                    "event": "start",
                    "samples": 1,
                    "strategy_set": "recommended_decision_profiles_with_costs",
                    "sort_by": "net_pnl_after_costs",
                }
            )
            progress({"event": "skip_missing", "sample": "mock_sample", "fixture": "mock.json"})
            progress(
                {
                    "event": "sample_finish",
                    "sample": "mock_sample",
                    "status": "SKIPPED_MISSING_FILE",
                    "elapsed_seconds": 0.0,
                    "trades": 0,
                    "net_pnl_after_costs": 0.0,
                }
            )
            progress({"event": "complete", "completed": 0, "skipped": 1, "errors": 0})
        return MultiSampleValidationResult(
            rows=[
                MultiSampleValidationRow(
                    sample_name="mock_sample",
                    fixture_path="mock.json",
                    symbol="BTC/USDT",
                    timeframe="15m",
                    status="SKIPPED_MISSING_FILE",
                )
            ],
            total_samples=1,
            skipped_samples=1,
            recommended_profile=kwargs["recommended_profile"],
        )


def test_script_default_command_works(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.run_multi_sample_validation.MultiSampleValidationEngine",
        _FakeMultiSampleValidationEngine,
    )

    return_code = main([])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[multi-sample] samples=1 strategy_set=recommended_decision_profiles_with_costs sort_by=net_pnl_after_costs" in captured.out
    assert "[multi-sample] skipping mock_sample missing file mock.json" in captured.out
    assert "[multi-sample] completed samples=0 skipped=1 errors=0" in captured.out
    assert "===== MULTI-SAMPLE VALIDATION =====" in captured.out
    assert "SKIPPED_MISSING_FILE" in captured.out


def test_script_show_details_works(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.run_multi_sample_validation.MultiSampleValidationEngine",
        _FakeMultiSampleValidationEngine,
    )

    return_code = main(["--show-details"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "Details:" in captured.out


def test_script_passes_cache_options_to_engine(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "scripts.run_multi_sample_validation.MultiSampleValidationEngine",
        _FakeMultiSampleValidationEngine,
    )
    cache_dir = tmp_path / "cache"

    return_code = main(["--use-cache", "--refresh-cache", "--cache-dir", str(cache_dir)])

    capsys.readouterr()
    assert return_code == 0
    assert _FakeMultiSampleValidationEngine.last_kwargs["use_cache"] is True
    assert _FakeMultiSampleValidationEngine.last_kwargs["refresh_cache"] is True
    assert _FakeMultiSampleValidationEngine.last_kwargs["cache_dir"] == str(cache_dir)


def test_script_rejects_invalid_max_windows(capsys) -> None:
    return_code = main(["--max-windows", "0"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "--max-windows must be greater than 0" in captured.out
