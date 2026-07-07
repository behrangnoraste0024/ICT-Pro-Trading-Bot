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
            if kwargs.get("use_cache"):
                progress(
                    {
                        "event": "cache_hit",
                        "cache_path": str(kwargs.get("cache_dir")),
                        "cache_key_hash": "abc123",
                        "cache_age_seconds": 10.0,
                        "cache_read_elapsed_seconds": 0.03,
                        "original_elapsed_seconds": 12.0,
                        "estimated_saved_seconds": 11.97,
                    }
                )
            progress(
                {
                    "event": "sample_finish",
                    "sample": "mock_sample",
                    "status": "SKIPPED_MISSING_FILE",
                    "elapsed_seconds": 0.0,
                    "trades": 0,
                    "net_pnl_after_costs": 0.0,
                    "cache_status": "HIT" if kwargs.get("use_cache") else None,
                    "cache_read_elapsed_seconds": 0.03 if kwargs.get("use_cache") else None,
                    "original_elapsed_seconds": 12.0 if kwargs.get("use_cache") else None,
                    "estimated_saved_seconds": 11.97 if kwargs.get("use_cache") else None,
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

    captured = capsys.readouterr()
    assert return_code == 0
    assert _FakeMultiSampleValidationEngine.last_kwargs["use_cache"] is True
    assert _FakeMultiSampleValidationEngine.last_kwargs["refresh_cache"] is True
    assert _FakeMultiSampleValidationEngine.last_kwargs["cache_dir"] == str(cache_dir)
    assert "[cache] hit path=" in captured.out
    assert "original_elapsed=12.00s" in captured.out
    assert "cache_read_elapsed=0.03s" in captured.out
    assert "saved_estimate=11.97s" in captured.out


def test_script_rejects_invalid_max_windows(capsys) -> None:
    return_code = main(["--max-windows", "0"])

    captured = capsys.readouterr()
    assert return_code == 1
    assert "--max-windows must be greater than 0" in captured.out


def test_script_export_snapshot_json_writes_only_json(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "scripts.run_multi_sample_validation.MultiSampleValidationEngine",
        _FakeMultiSampleValidationEngine,
    )

    return_code = main(["--export-snapshot", "--snapshot-dir", str(tmp_path), "--snapshot-format", "json"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[snapshot] wrote" in captured.out
    assert list(tmp_path.glob("*.json"))
    assert not list(tmp_path.glob("*.md"))


def test_script_export_snapshot_md_writes_only_markdown(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "scripts.run_multi_sample_validation.MultiSampleValidationEngine",
        _FakeMultiSampleValidationEngine,
    )

    return_code = main(["--export-snapshot", "--snapshot-dir", str(tmp_path), "--snapshot-format", "md"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert "[snapshot] wrote" in captured.out
    assert list(tmp_path.glob("*.md"))
    assert not list(tmp_path.glob("*.json"))


def test_script_export_snapshot_both_writes_both_formats(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "scripts.run_multi_sample_validation.MultiSampleValidationEngine",
        _FakeMultiSampleValidationEngine,
    )

    return_code = main(["--export-snapshot", "--snapshot-dir", str(tmp_path), "--snapshot-format", "both"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert captured.out.count("[snapshot] wrote") == 2
    assert list(tmp_path.glob("*.json"))
    assert list(tmp_path.glob("*.md"))
