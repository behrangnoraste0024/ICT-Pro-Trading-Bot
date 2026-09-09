from __future__ import annotations

import re
from pathlib import Path

from engine.diagnostics.deployment_readiness_engine import DeploymentReadinessEngine


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = REPO_ROOT / "docs" / "deployment_operations_runbook.md"


def _text() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def _normalized() -> str:
    return _text().casefold()


def test_runbook_file_exists() -> None:
    assert RUNBOOK.exists()


def test_all_required_sections_exist() -> None:
    text = _text()
    required_headings = [
        "## Deployment Boundary",
        "## Environment Separation Policy",
        "## Secret Management Policy",
        "## Backup Procedure Policy",
        "## Restore Procedure Policy",
        "## Rollback Procedure Policy",
        "## Process Supervision Policy",
        "## Health / Status Surfaces",
        "## Monitoring and Alerting References",
        "## Versioned Configuration Expectations",
        "## Disaster Recovery Procedure Policy",
        "## Operator Access-Control Policy",
        "## Stop Conditions",
        "## Prohibited Actions",
    ]

    for heading in required_headings:
        assert heading in text


def test_runbook_declares_static_non_execution_boundary() -> None:
    text = _normalized()

    assert "static procedural documentation only" in text
    assert "does not authorize codex" in text
    assert "does not deploy anything" in text


def test_deployment_execution_and_service_mutation_remain_prohibited() -> None:
    text = _normalized()

    assert "deployment execution" in text
    assert "service start, stop, restart" in text
    assert "service mutation" in text
    assert "docker or cloud deployment mutation" in text
    assert "ssh or remote shell" in text


def test_migration_backup_restore_and_rollback_execution_remain_prohibited() -> None:
    text = _normalized()

    assert "migration execution" in text
    assert "backup execution" in text
    assert "restore execution" in text
    assert "rollback execution" in text
    assert "does not provide or authorize backup commands" in text
    assert "does not provide or authorize restore commands" in text
    assert "does not provide or authorize rollback commands" in text


def test_exchange_live_execution_and_orders_remain_prohibited() -> None:
    text = _normalized()

    assert "binance transport" in text
    assert "exchange transport" in text
    assert "exchange clients" in text
    assert "live execution" in text
    assert "live orders" in text
    assert "production trading remains disabled" in text
    assert "btcusdt" in text
    assert "testnet/demo" in text


def test_persistence_database_and_permit_mutation_remain_prohibited() -> None:
    text = _normalized()

    assert "database mutation" in text
    assert "persistence writes" in text
    assert "permit changes" in text
    assert "permit bypass" in text
    assert "must not refund or reuse consumed permits" in text


def test_secret_values_and_credential_material_are_not_embedded() -> None:
    text = _text()
    lowered = text.casefold()
    forbidden_patterns = [
        r"sk-[a-z0-9]",
        r"akia[0-9a-z]{16}",
        r"bearer\s+[0-9a-z._-]+",
        r"authorization:",
        r"signature=",
        r"://[^<\s]*:[^<\s]*@",
    ]

    for pattern in forbidden_patterns:
        assert re.search(pattern, text, flags=re.IGNORECASE) is None
    assert "usable credential examples" in lowered
    assert "must not contain real secret values" in lowered


def test_operator_access_control_policy_is_present() -> None:
    text = _normalized()

    assert "least privilege" in text
    assert "explicit authorization" in text
    assert "must not share credentials" in text
    assert "no automated elevation" in text
    assert "bypass safety gates" in text


def test_fail_closed_stop_condition_language_is_present() -> None:
    text = _normalized()

    assert "fail closed" in text
    assert "stop immediately" in text
    assert "stop - deployment operations blocked" in text
    assert "missing, malformed, ambiguous" in text


def test_phase_i_pass_1_readiness_recognizes_runbook_without_code_changes() -> None:
    report = DeploymentReadinessEngine(repo_root=REPO_ROOT).evaluate()
    checks = {check.check_id: check for check in report.checks}

    for check_id in (
        "backup_runbook",
        "deployment_runbook",
        "disaster_recovery_runbook",
        "operator_access_control",
        "process_supervision",
        "restore_runbook",
        "rollback_runbook",
    ):
        assert checks[check_id].status == "READY"
