from __future__ import annotations

import os
import socket

from engine.diagnostics.deployment_readiness_engine import DeploymentReadinessEngine
from models.deployment_readiness import NOT_READY, READY, DeploymentReadinessCriterion


def _criterion(
    check_id: str,
    evidence_type: str,
    *,
    path: str | None = None,
    key_path: tuple[str, ...] = (),
    expected_terms: tuple[str, ...] = (),
    expected_env_names: tuple[str, ...] = (),
) -> DeploymentReadinessCriterion:
    return DeploymentReadinessCriterion(
        check_id=check_id,
        description=f"{check_id} description",
        evidence_type=evidence_type,
        path=path,
        key_path=key_path,
        expected_terms=expected_terms,
        expected_env_names=expected_env_names,
    )


def test_all_required_evidence_present_is_ready(tmp_path) -> None:
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "app.json").write_text('{"schema_version": "1.0"}', encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ops.md").write_text("deployment rollback backup restore", encoding="utf-8")

    report = DeploymentReadinessEngine(
        repo_root=tmp_path,
        criteria=(
            _criterion("config_schema", "json_key", path="configs/app.json", key_path=("schema_version",)),
            _criterion("deployment_doc", "text_contains_any", path="docs/ops.md", expected_terms=("deployment",)),
            _criterion("env_names", "env_name_expectation", expected_env_names=("ICT_DATABASE_URL", "ICT_RUNTIME_ENV")),
        ),
    ).evaluate()

    assert report.readiness_status == READY
    assert report.passed_checks == 3
    assert report.failed_checks == 0


def test_missing_required_evidence_is_not_ready(tmp_path) -> None:
    report = DeploymentReadinessEngine(
        repo_root=tmp_path,
        criteria=(_criterion("missing_doc", "path_exists", path="docs/deployment_operations_runbook.md"),),
    ).evaluate()

    assert report.readiness_status == NOT_READY
    assert report.failed_checks == 1
    assert report.checks[0].reason_code == "EVIDENCE_MISSING"


def test_malformed_required_evidence_is_not_ready(tmp_path) -> None:
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "app.json").write_text("{malformed", encoding="utf-8")

    report = DeploymentReadinessEngine(
        repo_root=tmp_path,
        criteria=(_criterion("config_schema", "json_key", path="configs/app.json", key_path=("schema_version",)),),
    ).evaluate()

    assert report.readiness_status == NOT_READY
    assert report.checks[0].reason_code == "EVIDENCE_UNREADABLE"


def test_no_optimistic_fallback_for_empty_or_unknown_criteria(tmp_path) -> None:
    empty = DeploymentReadinessEngine(repo_root=tmp_path, criteria=()).evaluate()
    unknown = DeploymentReadinessEngine(
        repo_root=tmp_path,
        criteria=(_criterion("unknown", "unsupported"),),
    ).evaluate()

    assert empty.readiness_status == NOT_READY
    assert unknown.readiness_status == NOT_READY
    assert unknown.checks[0].reason_code == "UNSUPPORTED_EVIDENCE_TYPE"


def test_stable_check_ordering_and_identical_inputs(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("ready", encoding="utf-8")
    criteria = (
        _criterion("z_check", "path_exists", path="a.txt"),
        _criterion("a_check", "path_exists", path="a.txt"),
    )

    first = DeploymentReadinessEngine(repo_root=tmp_path, criteria=criteria).evaluate()
    second = DeploymentReadinessEngine(repo_root=tmp_path, criteria=criteria).evaluate()

    assert [check.check_id for check in first.checks] == ["a_check", "z_check"]
    assert first.to_dict() == second.to_dict()


def test_environment_is_not_mutated_or_value_inspected(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ICT_DATABASE_URL", "postgresql://user:secret@example/db")
    before = dict(os.environ)

    report = DeploymentReadinessEngine(
        repo_root=tmp_path,
        criteria=(_criterion("env_names", "env_name_expectation", expected_env_names=("ICT_DATABASE_URL", "ICT_RUNTIME_ENV")),),
    ).evaluate()

    assert report.readiness_status == READY
    assert dict(os.environ) == before
    assert "secret" not in str(report.to_dict())
    assert "postgresql://" not in str(report.to_dict())


def test_inspected_files_are_not_mutated(tmp_path) -> None:
    path = tmp_path / "ops.md"
    path.write_text("deployment", encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    DeploymentReadinessEngine(
        repo_root=tmp_path,
        criteria=(_criterion("deployment_doc", "text_contains_any", path="ops.md", expected_terms=("deployment",)),),
    ).evaluate()

    assert path.read_text(encoding="utf-8") == before


def test_no_network_exchange_or_persistence_transport(tmp_path, monkeypatch) -> None:
    def fail_socket(*args, **kwargs):
        raise AssertionError("network transport must not be used")

    monkeypatch.setattr(socket, "create_connection", fail_socket)
    (tmp_path / "ready.txt").write_text("ready", encoding="utf-8")

    report = DeploymentReadinessEngine(
        repo_root=tmp_path,
        criteria=(_criterion("local_file", "path_exists", path="ready.txt"),),
    ).evaluate()

    assert report.readiness_status == READY


def test_sanitized_reasons_do_not_expose_secret_material(tmp_path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ops.md").write_text(
        "token=SECRET signature=abc Authorization: Bearer value",
        encoding="utf-8",
    )

    report = DeploymentReadinessEngine(
        repo_root=tmp_path,
        criteria=(_criterion("deployment_doc", "text_contains_any", path="docs/ops.md", expected_terms=("deployment",)),),
    ).evaluate()

    rendered = str(report.to_dict())
    assert report.readiness_status == NOT_READY
    assert "SECRET" not in rendered
    assert "Bearer" not in rendered
    assert "signature=abc" not in rendered
