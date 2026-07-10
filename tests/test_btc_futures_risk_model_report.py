from __future__ import annotations

from models.btc_futures_risk_model import BTCFuturesRiskScenarioInput, BTCFuturesRiskValidationReport
from reporting.btc_futures_risk_model_report import format_btc_futures_leverage_comparison, format_btc_futures_risk_result, format_btc_futures_risk_validation_report
from tests.test_btc_futures_risk_model_engine import _engine, _scenario, _write_risk_configs


def test_validation_report_displays_approximate_model_and_safety(tmp_path) -> None:
    path = _write_risk_configs(tmp_path)
    report = _engine(tmp_path).validate(str(path))

    text = format_btc_futures_risk_validation_report(report)

    assert "BTC FUTURES RISK MODEL CONFIG VALIDATION" in text
    assert "Model Accuracy        : APPROXIMATE_CONSERVATIVE" in text
    assert "Exchange Exact        : false" in text
    assert "Paper Futures Position: false" in text


def test_risk_result_report_displays_calculation_and_assumptions(tmp_path) -> None:
    path = _write_risk_configs(tmp_path)
    result = _engine(tmp_path).analyze_scenario(_scenario(), str(path))

    text = format_btc_futures_risk_result(result)

    assert "BTC FUTURES LEVERAGE / LIQUIDATION RISK ANALYSIS" in text
    assert "Model Accuracy       : APPROXIMATE_CONSERVATIVE" in text
    assert "Estimated Liquidation:" in text
    assert "Exchange Leverage Set: false" in text
    assert "APPROXIMATE_CONSERVATIVE" in text


def test_leverage_comparison_report_displays_rows(tmp_path) -> None:
    path = _write_risk_configs(tmp_path)
    result = _engine(tmp_path).compare_leverage(_scenario(leverage=1), str(path))

    text = format_btc_futures_leverage_comparison(result)

    assert "BTC FUTURES LEVERAGE COMPARISON" in text
    assert "1x |" in text
    assert "5x |" in text
