from __future__ import annotations

import json

from models.btc_paper_readiness import BTCPaperReadinessCheck, BTCPaperReadinessReport
from scripts.run_btc_paper_readiness import main


class _FakeEngine:
    last_kwargs = None

    def __init__(self, repo_root=None) -> None:
        self.repo_root = repo_root

    def build_report(self, **kwargs) -> BTCPaperReadinessReport:
        type(self).last_kwargs = kwargs
        return BTCPaperReadinessReport(
            created_at="2026-07-08T00:00:00+00:00",
            readiness_status="WARNING",
            passed_checks=1,
            warning_checks=1,
            checks=[
                BTCPaperReadinessCheck("paper_execution_disabled", "PASS", "REQUIRED", "safe"),
                BTCPaperReadinessCheck("risk_runtime_config", "WARNING", "RECOMMENDED", "needs config"),
            ],
            next_actions=["next"],
        )


class _BlockedEngine(_FakeEngine):
    def build_report(self, **kwargs) -> BTCPaperReadinessReport:
        report = super().build_report(**kwargs)
        report.readiness_status = "BLOCKED"
        report.failed_checks = 1
        return report


def test_default_runner_prints_report(capsys, monkeypatch) -> None:
    monkeypatch.setattr("scripts.run_btc_paper_readiness.BTCPaperReadinessEngine", _FakeEngine)

    code = main([])

    captured = capsys.readouterr()
    assert code == 0
    assert "===== BTC PAPER TRADING READINESS =====" in captured.out
    assert _FakeEngine.last_kwargs["strict"] is False


def test_json_prints_serializable_json(capsys, monkeypatch) -> None:
    monkeypatch.setattr("scripts.run_btc_paper_readiness.BTCPaperReadinessEngine", _FakeEngine)

    code = main(["--json"])

    captured = capsys.readouterr()
    assert code == 0
    data = json.loads(captured.out)
    assert data["project_scope"] == "BTC_ONLY"
    assert data["checks"][0]["name"] == "paper_execution_disabled"


def test_exports_json_and_markdown(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setattr("scripts.run_btc_paper_readiness.BTCPaperReadinessEngine", _FakeEngine)
    json_path = tmp_path / "readiness.json"
    md_path = tmp_path / "readiness.md"

    code = main(["--export-json", str(json_path), "--export-md", str(md_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert json_path.exists()
    assert md_path.exists()
    assert "[btc-readiness] wrote" in captured.out
    assert json.loads(json_path.read_text(encoding="utf-8"))["readiness_status"] == "WARNING"
    assert "BTC PAPER TRADING READINESS" in md_path.read_text(encoding="utf-8")


def test_run_gate_options_are_passed_to_engine(capsys, monkeypatch) -> None:
    monkeypatch.setattr("scripts.run_btc_paper_readiness.BTCPaperReadinessEngine", _FakeEngine)

    code = main(["--run-gate", "--use-cache", "--cache-dir", ".cache/test"])

    capsys.readouterr()
    assert code == 0
    assert _FakeEngine.last_kwargs["run_gate"] is True
    assert _FakeEngine.last_kwargs["use_cache"] is True
    assert _FakeEngine.last_kwargs["cache_dir"] == ".cache/test"


def test_strict_blocked_exits_one(capsys, monkeypatch) -> None:
    monkeypatch.setattr("scripts.run_btc_paper_readiness.BTCPaperReadinessEngine", _BlockedEngine)

    code = main(["--strict"])

    capsys.readouterr()
    assert code == 1
