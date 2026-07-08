from __future__ import annotations

from models.multi_sample_validation import MultiSampleDefinition, MultiSampleValidationResult, MultiSampleValidationRow
from models.validation_sample_scope import ValidationSampleScopeResult
from scripts.run_multi_sample_validation import main


class _FakeScopeEngine:
    last_args = None

    def __init__(self, repo_root=None) -> None:
        self.repo_root = repo_root

    def select(self, registry_path: str, sample_scope: str, sample_names: list[str] | None = None) -> ValidationSampleScopeResult:
        type(self).last_args = (registry_path, sample_scope, sample_names)
        return ValidationSampleScopeResult(
            sample_scope="explicit" if sample_names else sample_scope,
            selected_samples=[MultiSampleDefinition("btc", "btc.json", "BTC/USDT", "15m")],
            excluded_samples=[MultiSampleDefinition("eth", "eth.json", "ETH/USDT", "15m")],
        )


class _FakeMultiSampleValidationEngine:
    last_kwargs = None

    def validate(self, **kwargs) -> MultiSampleValidationResult:
        type(self).last_kwargs = kwargs
        return MultiSampleValidationResult(
            rows=[
                MultiSampleValidationRow("btc", "btc.json", "BTC/USDT", "15m", "PASSED"),
                MultiSampleValidationRow("eth", "eth.json", "ETH/USDT", "15m", "SKIPPED_OUT_OF_SCOPE"),
            ],
            total_samples=2,
            selected_samples=1,
            excluded_samples=1,
            sample_scope=kwargs["sample_scope"],
            completed_samples=1,
            passed_samples=1,
            skipped_samples=1,
            recommended_profile=kwargs["recommended_profile"],
        )


def test_runner_passes_sample_scope_to_engine(capsys, monkeypatch) -> None:
    monkeypatch.setattr("scripts.run_multi_sample_validation.ValidationSampleScopeEngine", _FakeScopeEngine)
    monkeypatch.setattr("scripts.run_multi_sample_validation.MultiSampleValidationEngine", _FakeMultiSampleValidationEngine)

    return_code = main(["--sample-scope", "btc_only", "--show-details"])

    captured = capsys.readouterr()
    assert return_code == 0
    assert _FakeScopeEngine.last_args[1] == "btc_only"
    assert _FakeMultiSampleValidationEngine.last_kwargs["sample_scope"] == "btc_only"
    assert "Sample Scope        : btc_only" in captured.out
    assert "SKIPPED_OUT_OF_SCOPE" in captured.out


def test_runner_repeated_sample_uses_explicit_scope(capsys, monkeypatch) -> None:
    monkeypatch.setattr("scripts.run_multi_sample_validation.ValidationSampleScopeEngine", _FakeScopeEngine)
    monkeypatch.setattr("scripts.run_multi_sample_validation.MultiSampleValidationEngine", _FakeMultiSampleValidationEngine)

    return_code = main(["--sample", "btcusdt_15m_1000"])

    capsys.readouterr()
    assert return_code == 0
    assert _FakeScopeEngine.last_args[2] == ["btcusdt_15m_1000"]
    assert _FakeMultiSampleValidationEngine.last_kwargs["sample_scope"] == "explicit"
