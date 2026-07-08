from __future__ import annotations

import json

from models.btc_paper_monitoring import (
    BTCPaperMonitoringConfig,
    BTCPaperMonitoringIssue,
    BTCPaperMonitoringStatus,
    BTCPaperMonitoringValidationReport,
)
from scripts.validate_btc_paper_monitoring import main


class _FakeEngine:
    status = "PASS"
    last_kwargs = None

    def __init__(self, repo_root=None) -> None:
        self.repo_root = repo_root

    def validate(self, **kwargs) -> BTCPaperMonitoringValidationReport:
        type(self).last_kwargs = kwargs
        issues = []
        if self.status != "PASS":
            issues.append(BTCPaperMonitoringIssue("mock", self.status, "mock issue"))
        return BTCPaperMonitoringValidationReport(
            config_path=kwargs["config_path"],
            status=self.status,
            issue_count=len(issues),
            warning_count=1 if self.status == "WARNING" else 0,
            fail_count=1 if self.status == "FAIL" else 0,
            config=BTCPaperMonitoringConfig(),
            issues=issues,
            diagnostics={"runtime_config_status": "PASS"},
        )

    def build_status(self, **kwargs) -> BTCPaperMonitoringStatus:
        type(self).last_kwargs = kwargs
        return BTCPaperMonitoringStatus(
            monitoring_status="READY" if self.status == "PASS" else "BLOCKED",
            runtime_config_status="PASS",
            notes=["fake"],
        )


def test_default_runner_prints_report(capsys, monkeypatch) -> None:
    _FakeEngine.status = "PASS"
    monkeypatch.setattr("scripts.validate_btc_paper_monitoring.BTCPaperMonitoringEngine", _FakeEngine)

    code = main([])

    captured = capsys.readouterr()
    assert code == 0
    assert "BTC PAPER MONITORING CONFIG VALIDATION" in captured.out


def test_json_prints_serializable_validation_json(capsys, monkeypatch) -> None:
    _FakeEngine.status = "PASS"
    monkeypatch.setattr("scripts.validate_btc_paper_monitoring.BTCPaperMonitoringEngine", _FakeEngine)

    code = main(["--json"])

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["status"] == "PASS"


def test_status_json_prints_serializable_status_json(capsys, monkeypatch) -> None:
    _FakeEngine.status = "PASS"
    monkeypatch.setattr("scripts.validate_btc_paper_monitoring.BTCPaperMonitoringEngine", _FakeEngine)

    code = main(["--status", "--json"])

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["monitoring_status"] == "READY"


def test_strict_exits_zero_for_pass(capsys, monkeypatch) -> None:
    _FakeEngine.status = "PASS"
    monkeypatch.setattr("scripts.validate_btc_paper_monitoring.BTCPaperMonitoringEngine", _FakeEngine)

    code = main(["--strict"])

    capsys.readouterr()
    assert code == 0


def test_strict_exits_one_for_fail(capsys, monkeypatch) -> None:
    _FakeEngine.status = "FAIL"
    monkeypatch.setattr("scripts.validate_btc_paper_monitoring.BTCPaperMonitoringEngine", _FakeEngine)

    code = main(["--strict"])

    capsys.readouterr()
    assert code == 1


def test_export_json_and_md(tmp_path, capsys, monkeypatch) -> None:
    _FakeEngine.status = "PASS"
    monkeypatch.setattr("scripts.validate_btc_paper_monitoring.BTCPaperMonitoringEngine", _FakeEngine)
    json_path = tmp_path / "monitoring.json"
    md_path = tmp_path / "monitoring.md"

    code = main(["--export-json", str(json_path), "--export-md", str(md_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert json_path.exists()
    assert md_path.exists()
    assert "[btc-paper-monitoring] wrote" in captured.out
