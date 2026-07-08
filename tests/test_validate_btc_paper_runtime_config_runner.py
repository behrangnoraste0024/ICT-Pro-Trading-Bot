from __future__ import annotations

import json

from models.btc_paper_runtime_config import (
    BTCPaperRuntimeConfig,
    BTCPaperRuntimeConfigIssue,
    BTCPaperRuntimeConfigValidationReport,
)
from scripts.validate_btc_paper_runtime_config import main


class _FakeEngine:
    status = "PASS"
    last_kwargs = None

    def __init__(self, repo_root=None) -> None:
        self.repo_root = repo_root

    def validate(self, **kwargs) -> BTCPaperRuntimeConfigValidationReport:
        type(self).last_kwargs = kwargs
        issues = []
        if self.status != "PASS":
            issues.append(BTCPaperRuntimeConfigIssue("mock", self.status, "mock issue"))
        return BTCPaperRuntimeConfigValidationReport(
            config_path=kwargs["config_path"],
            status=self.status,
            issue_count=len(issues),
            warning_count=1 if self.status == "WARNING" else 0,
            fail_count=1 if self.status == "FAIL" else 0,
            config=BTCPaperRuntimeConfig(),
            issues=issues,
        )


def test_default_runner_prints_report(capsys, monkeypatch) -> None:
    _FakeEngine.status = "PASS"
    monkeypatch.setattr("scripts.validate_btc_paper_runtime_config.BTCPaperRuntimeConfigEngine", _FakeEngine)

    code = main([])

    captured = capsys.readouterr()
    assert code == 0
    assert "BTC PAPER RUNTIME CONFIG VALIDATION" in captured.out


def test_json_prints_serializable_json(capsys, monkeypatch) -> None:
    _FakeEngine.status = "PASS"
    monkeypatch.setattr("scripts.validate_btc_paper_runtime_config.BTCPaperRuntimeConfigEngine", _FakeEngine)

    code = main(["--json"])

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["status"] == "PASS"


def test_strict_exits_zero_for_pass(capsys, monkeypatch) -> None:
    _FakeEngine.status = "PASS"
    monkeypatch.setattr("scripts.validate_btc_paper_runtime_config.BTCPaperRuntimeConfigEngine", _FakeEngine)

    code = main(["--strict"])

    capsys.readouterr()
    assert code == 0


def test_strict_exits_one_for_warning(capsys, monkeypatch) -> None:
    _FakeEngine.status = "WARNING"
    monkeypatch.setattr("scripts.validate_btc_paper_runtime_config.BTCPaperRuntimeConfigEngine", _FakeEngine)

    code = main(["--strict"])

    capsys.readouterr()
    assert code == 1


def test_fail_exits_one(capsys, monkeypatch) -> None:
    _FakeEngine.status = "FAIL"
    monkeypatch.setattr("scripts.validate_btc_paper_runtime_config.BTCPaperRuntimeConfigEngine", _FakeEngine)

    code = main([])

    capsys.readouterr()
    assert code == 1


def test_export_json_and_md(tmp_path, capsys, monkeypatch) -> None:
    _FakeEngine.status = "PASS"
    monkeypatch.setattr("scripts.validate_btc_paper_runtime_config.BTCPaperRuntimeConfigEngine", _FakeEngine)
    json_path = tmp_path / "runtime.json"
    md_path = tmp_path / "runtime.md"

    code = main(["--export-json", str(json_path), "--export-md", str(md_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert json_path.exists()
    assert md_path.exists()
    assert "[btc-runtime-config] wrote" in captured.out
