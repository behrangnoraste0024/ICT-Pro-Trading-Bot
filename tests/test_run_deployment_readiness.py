from __future__ import annotations

import json

from scripts.run_deployment_readiness import main


def _ready_repo(root) -> None:
    (root / "alembic" / "versions").mkdir(parents=True)
    (root / "api").mkdir()
    (root / "api" / "live_control_plane_routes.py").write_text(
        "operator/status kill-switch/status recovery/status",
        encoding="utf-8",
    )
    (root / "configs").mkdir()
    (root / "configs" / "validation_baseline.json").write_text(
        json.dumps({"schema_version": "1.0"}),
        encoding="utf-8",
    )
    (root / "docs").mkdir()
    (root / "docs" / "deployment_operations_runbook.md").write_text(
        "\n".join(
            [
                "deployment",
                "backup",
                "restore",
                "rollback",
                "process supervision",
                "operator access control",
                "disaster recovery",
            ]
        ),
        encoding="utf-8",
    )
    (root / "infrastructure" / "observability").mkdir(parents=True)
    (root / "infrastructure" / "observability" / "operational_metrics.py").write_text(
        "class OperationalCounterRegistry: pass",
        encoding="utf-8",
    )


def test_cli_exit_code_zero_only_for_ready(tmp_path, capsys) -> None:
    _ready_repo(tmp_path)

    code = main(["--repo-root", str(tmp_path)])
    output = capsys.readouterr().out

    assert code == 0
    assert "Readiness Status : READY" in output


def test_cli_nonzero_exit_code_for_not_ready(tmp_path, capsys) -> None:
    code = main(["--repo-root", str(tmp_path)])
    output = capsys.readouterr().out

    assert code == 1
    assert "Readiness Status : NOT_READY" in output


def test_cli_json_output_is_sanitized_and_deterministic(tmp_path, capsys) -> None:
    _ready_repo(tmp_path)

    first_code = main(["--repo-root", str(tmp_path), "--json"])
    first = capsys.readouterr().out
    second_code = main(["--repo-root", str(tmp_path), "--json"])
    second = capsys.readouterr().out

    assert first_code == 0
    assert second_code == 0
    assert first == second
    assert "READY" in first
    assert "secret" not in first.casefold()
    assert "traceback" not in first.casefold()
