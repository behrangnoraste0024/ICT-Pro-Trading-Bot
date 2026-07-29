from __future__ import annotations

import contextlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from infrastructure.persistence.execution_orm import AuditEventORM, LiveExecutionPermitORM
from infrastructure.persistence.live_execution_permit_persistence import (
    ISSUE_CONFIRMATION,
    REVOKE_CONFIRMATION,
    LiveExecutionPermitPersistence as RealLiveExecutionPermitPersistence,
)
from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit import LiveExecutionPermitState
from tests.kill_switch_test_support import durable_state_env

import scripts.issue_live_execution_permit as issue_cli
import scripts.revoke_live_execution_permit as revoke_cli
import scripts.run_binance_futures_testnet_order_lifecycle as lifecycle_cli
import scripts.run_binance_futures_testnet_order_test as order_test_cli
import scripts.run_binance_futures_testnet_protective_orders as protective_cli
import scripts.show_live_execution_permit as show_cli


STOP_CREATE_PERMIT_ID = "permit-0123456789abcdef0123456789abcdef"
TAKE_PROFIT_CREATE_PERMIT_ID = "permit-11111111111111111111111111111111"
TAKE_PROFIT_CANCEL_PERMIT_ID = "permit-22222222222222222222222222222222"
STOP_CANCEL_PERMIT_ID = "permit-33333333333333333333333333333333"
LIFECYCLE_CREATE_PERMIT_ID = "permit-44444444444444444444444444444444"
LIFECYCLE_CANCEL_PERMIT_ID = "permit-55555555555555555555555555555555"
ORDER_TEST_PERMIT_ID = "permit-66666666666666666666666666666666"
SENSITIVE_MARKERS = (
    "unit-test-api-secret",
    "unit-test-full-api-key",
    "signature=",
    "signed_query",
    "https://authenticated.example.test",
    "x-mbx-apikey",
    "raw credential",
    "database-password",
    "select * from",
    "traceback",
    "raw exception chain",
)


@dataclass
class CliResult:
    code: int
    stdout: str
    stderr: str


class _CountingPermitPersistence:
    issue_attempt = 0
    issue_success = 0
    show_attempt = 0
    show_success = 0
    revoke_attempt = 0
    revoke_success = 0
    consume_attempt = 0
    consume_success = 0
    ensure_count = 0
    close_count = 0

    def __init__(self, *args, **kwargs) -> None:
        self._real = RealLiveExecutionPermitPersistence(*args, **kwargs)

    @classmethod
    def reset(cls) -> None:
        cls.issue_attempt = 0
        cls.issue_success = 0
        cls.show_attempt = 0
        cls.show_success = 0
        cls.revoke_attempt = 0
        cls.revoke_success = 0
        cls.consume_attempt = 0
        cls.consume_success = 0
        cls.ensure_count = 0
        cls.close_count = 0

    @classmethod
    def snapshot(cls) -> dict[str, int]:
        return {
            "issue_attempt": cls.issue_attempt,
            "issue_success": cls.issue_success,
            "show_attempt": cls.show_attempt,
            "show_success": cls.show_success,
            "revoke_attempt": cls.revoke_attempt,
            "revoke_success": cls.revoke_success,
            "consume_attempt": cls.consume_attempt,
            "consume_success": cls.consume_success,
            "ensure_count": cls.ensure_count,
            "close_count": cls.close_count,
        }

    def ensure_available(self, *args, **kwargs):
        type(self).ensure_count += 1
        return self._real.ensure_available(*args, **kwargs)

    def issue(self, *args, **kwargs):
        type(self).issue_attempt += 1
        result = self._real.issue(*args, **kwargs)
        type(self).issue_success += 1
        return result

    def show(self, *args, **kwargs):
        type(self).show_attempt += 1
        result = self._real.show(*args, **kwargs)
        type(self).show_success += 1
        return result

    def revoke(self, *args, **kwargs):
        type(self).revoke_attempt += 1
        result = self._real.revoke(*args, **kwargs)
        type(self).revoke_success += 1
        return result

    def consume(self, *args, **kwargs):
        type(self).consume_attempt += 1
        result = self._real.consume(*args, **kwargs)
        type(self).consume_success += 1
        return result

    def close(self) -> None:
        type(self).close_count += 1
        return self._real.close()


class _RecordingExecutionEngine:
    instances: list["_RecordingExecutionEngine"] = []
    constructor_count = 0
    signing_count = 0
    post_count = 0
    delete_count = 0
    post_retry_count = 0
    delete_retry_count = 0

    def __init__(self, *args, **kwargs) -> None:
        _RecordingExecutionEngine.constructor_count += 1
        self.calls: list[tuple[str, dict[str, Any]]] = []
        type(self).instances.append(self)

    @classmethod
    def reset(cls) -> None:
        cls.instances = []
        cls.constructor_count = 0
        cls.signing_count = 0
        cls.post_count = 0
        cls.delete_count = 0
        cls.post_retry_count = 0
        cls.delete_retry_count = 0

    def validate(self, *args, **kwargs):
        self.calls.append(("validate", kwargs))
        return _Result("VALIDATE", status="PASS")

    def run_protective_lifecycle(self, *args, **kwargs):
        self.calls.append(("run_protective_lifecycle", kwargs))
        return _Result("PROTECTIVE_RECORDED")

    def run_lifecycle(self, *args, **kwargs):
        self.calls.append(("run_lifecycle", kwargs))
        return _Result("LIFECYCLE_RECORDED")

    def submit_test_order(self, *args, **kwargs):
        self.calls.append(("submit_test_order", kwargs))
        return _Result("ORDER_TEST_RECORDED")


class _RejectingExecutionEngine(_RecordingExecutionEngine):
    def run_protective_lifecycle(self, *args, **kwargs):
        self.calls.append(("run_protective_lifecycle", kwargs))
        raise AssertionError("execution engine must not be invoked")

    def run_lifecycle(self, *args, **kwargs):
        self.calls.append(("run_lifecycle", kwargs))
        raise AssertionError("execution engine must not be invoked")

    def submit_test_order(self, *args, **kwargs):
        self.calls.append(("submit_test_order", kwargs))
        raise AssertionError("execution engine must not be invoked")


class _Result:
    def __init__(self, decision: str, status: str = "FAIL") -> None:
        self.decision = decision
        self.status = status

    def to_dict(self) -> dict[str, str]:
        return {"status": self.status, "decision": self.decision}


@pytest.fixture(autouse=True)
def _clean_recorders(monkeypatch):
    _RecordingExecutionEngine.reset()
    _CountingPermitPersistence.reset()
    yield
    _RecordingExecutionEngine.reset()
    _CountingPermitPersistence.reset()


@pytest.fixture
def permit_env(monkeypatch):
    env = durable_state_env("RELEASED")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(issue_cli, "LiveExecutionPermitPersistence", _CountingPermitPersistence)
    monkeypatch.setattr(show_cli, "LiveExecutionPermitPersistence", _CountingPermitPersistence)
    monkeypatch.setattr(revoke_cli, "LiveExecutionPermitPersistence", _CountingPermitPersistence)
    return env


def _run_cli(func, argv: list[str]) -> CliResult:
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = func(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return CliResult(code, out.getvalue(), err.getvalue())


def _assert_sanitized(*values) -> None:
    text = json.dumps(values, default=str, sort_keys=True).lower()
    for marker in SENSITIVE_MARKERS:
        assert marker not in text


def _assert_no_execution_transport() -> None:
    assert _RecordingExecutionEngine.signing_count == 0
    assert _RecordingExecutionEngine.post_count == 0
    assert _RecordingExecutionEngine.delete_count == 0
    assert _RecordingExecutionEngine.post_retry_count == 0
    assert _RecordingExecutionEngine.delete_retry_count == 0


def _engine_method_call_count() -> int:
    return sum(len(instance.calls) for instance in _RecordingExecutionEngine.instances)


def _assert_no_engine_method_calls() -> None:
    assert _engine_method_call_count() == 0


def _assert_no_permit_persistence_activity() -> None:
    assert _CountingPermitPersistence.issue_attempt == 0
    assert _CountingPermitPersistence.issue_success == 0
    assert _CountingPermitPersistence.show_attempt == 0
    assert _CountingPermitPersistence.show_success == 0
    assert _CountingPermitPersistence.revoke_attempt == 0
    assert _CountingPermitPersistence.revoke_success == 0
    assert _CountingPermitPersistence.consume_attempt == 0
    assert _CountingPermitPersistence.consume_success == 0


def _permit_rows(env: dict[str, str]) -> list[tuple[str, str, int]]:
    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine) as session:
            return [
                (row.permit_id, row.state, row.version)
                for row in session.scalars(select(LiveExecutionPermitORM).order_by(LiveExecutionPermitORM.permit_id)).all()
            ]
    finally:
        engine.dispose()


def _permit_ids(env: dict[str, str]) -> list[str]:
    return [row[0] for row in _permit_rows(env)]


def _audit_actions(env: dict[str, str]) -> list[str]:
    engine = create_engine(env["ICT_DATABASE_URL"], future=True)
    try:
        with Session(engine) as session:
            return list(session.scalars(select(AuditEventORM.action).order_by(AuditEventORM.id)).all())
    finally:
        engine.dispose()


def _assert_db_and_audit_unchanged(env: dict[str, str], rows: list[tuple[str, str, int]], actions: list[str]) -> None:
    assert _permit_rows(env) == rows
    assert _audit_actions(env) == actions


def _assert_no_permit_mutation_audits(env: dict[str, str]) -> None:
    actions = _audit_actions(env)
    assert "PERMIT_ISSUED" not in actions
    assert "PERMIT_REVOKED" not in actions
    assert "PERMIT_CONSUMED" not in actions


def _valid_request_payload(operation: LiveExecutionOperation = LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE) -> dict:
    return {
        "schema_version": "1.0",
        "operation": operation.value,
        "environment": "TESTNET",
        "symbol": "BTCUSDT",
        "client_order_id": "smcbot-cli-contract-001",
        "side": "BUY",
        "position_side": "BOTH",
        "order_type": "LIMIT",
        "quantity": "0.001",
        "price": "49500",
        "time_in_force": "GTC",
        "reduce_only": False,
    }


def _write_request(tmp_path: Path, payload: dict | str) -> Path:
    path = tmp_path / f"permit-request-{len(list(tmp_path.glob('permit-request-*')))}.json"
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _issue_permit(tmp_path: Path, env: dict[str, str]) -> dict:
    path = _write_request(tmp_path, _valid_request_payload())
    result = _run_cli(
        issue_cli.main,
        ["--operation", LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value, "--request-file", str(path), "--issued-by", "cli-test", "--confirmation", ISSUE_CONFIRMATION],
    )
    assert result.code == 0
    return json.loads(result.stdout)


def _patch_protective(monkeypatch, engine_cls):
    monkeypatch.setattr(protective_cli, "BinanceFuturesTestnetProtectiveOrdersEngine", engine_cls)
    monkeypatch.setattr(protective_cli, "format_binance_futures_testnet_protective_orders_result", lambda result: json.dumps(result.to_dict()))


def _patch_lifecycle(monkeypatch, engine_cls):
    monkeypatch.setattr(lifecycle_cli, "BinanceFuturesTestnetOrderLifecycleEngine", engine_cls)
    monkeypatch.setattr(lifecycle_cli, "format_binance_futures_testnet_order_lifecycle_result", lambda result: json.dumps(result.to_dict()))


def _patch_order_test(monkeypatch, engine_cls):
    monkeypatch.setattr(order_test_cli, "BinanceFuturesTestnetOrderTestEngine", engine_cls)
    monkeypatch.setattr(order_test_cli, "format_binance_futures_testnet_order_test_result", lambda result: json.dumps(result.to_dict()))


def _execution_before(env: dict[str, str]) -> tuple[list[tuple[str, str, int]], list[str]]:
    _RecordingExecutionEngine.reset()
    return _permit_rows(env), _audit_actions(env)


def _assert_execution_rejected(env: dict[str, str], before_rows: list[tuple[str, str, int]], before_actions: list[str], result: CliResult, *, expected_engine_methods: int = 0, expected_constructors: int = 0) -> None:
    assert result.code != 0
    assert _RecordingExecutionEngine.constructor_count == expected_constructors
    assert len(_RecordingExecutionEngine.instances) == expected_constructors
    assert _engine_method_call_count() == expected_engine_methods
    _assert_no_permit_persistence_activity()
    _assert_db_and_audit_unchanged(env, before_rows, before_actions)
    _assert_no_permit_mutation_audits(env)
    _assert_no_execution_transport()
    _assert_sanitized(result.stdout, result.stderr)


def test_protective_cli_requires_all_exact_permit_references(monkeypatch, permit_env):
    _patch_protective(monkeypatch, _RejectingExecutionEngine)
    before_rows, before_actions = _execution_before(permit_env)
    result = _run_cli(protective_cli.main, ["--run-protective-lifecycle", "--confirm-testnet-protective-pair", "CONFIRM_BINANCE_FUTURES_TESTNET_PROTECTIVE_ORDERS"])
    _assert_execution_rejected(permit_env, before_rows, before_actions, result)


def test_protective_cli_rejects_missing_permit_version_before_engine(monkeypatch, permit_env):
    _patch_protective(monkeypatch, _RejectingExecutionEngine)
    before_rows, before_actions = _execution_before(permit_env)
    result = _run_cli(protective_cli.main, ["--run-protective-lifecycle", "--stop-create-permit-id", STOP_CREATE_PERMIT_ID])
    _assert_execution_rejected(permit_env, before_rows, before_actions, result)


def test_protective_cli_rejects_malformed_permit_reference_without_auto_issue(monkeypatch, permit_env):
    _patch_protective(monkeypatch, _RejectingExecutionEngine)
    cases = [
        ["--stop-create-permit-id", "not-a-permit", "--stop-create-permit-version", "1"],
        ["--stop-create-permit-id", STOP_CREATE_PERMIT_ID, "--stop-create-permit-version", "0"],
        ["--stop-create-permit-id", STOP_CREATE_PERMIT_ID, "--stop-create-permit-version", "-1"],
        ["--stop-create-permit-id", STOP_CREATE_PERMIT_ID, "--stop-create-permit-version", "not-an-int"],
    ]
    for extra in cases:
        before_rows, before_actions = _execution_before(permit_env)
        result = _run_cli(protective_cli.main, ["--run-protective-lifecycle", *extra])
        _assert_execution_rejected(permit_env, before_rows, before_actions, result)


def test_protective_cli_forwards_exact_permits_once_without_bypass_or_transport(monkeypatch, permit_env):
    _patch_protective(monkeypatch, _RecordingExecutionEngine)
    before_rows, before_actions = _execution_before(permit_env)
    argv = [
        "--run-protective-lifecycle", "--confirm-testnet-protective-pair", "CONFIRM_BINANCE_FUTURES_TESTNET_PROTECTIVE_ORDERS",
        "--stop-create-permit-id", STOP_CREATE_PERMIT_ID, "--stop-create-permit-version", "1",
        "--take-profit-create-permit-id", TAKE_PROFIT_CREATE_PERMIT_ID, "--take-profit-create-permit-version", "2",
        "--take-profit-cancel-permit-id", TAKE_PROFIT_CANCEL_PERMIT_ID, "--take-profit-cancel-permit-version", "3",
        "--stop-cancel-permit-id", STOP_CANCEL_PERMIT_ID, "--stop-cancel-permit-version", "4",
    ]
    result = _run_cli(protective_cli.main, argv)
    assert result.code == 1
    assert _RecordingExecutionEngine.constructor_count == 1
    assert len(_RecordingExecutionEngine.instances) == 1
    assert _engine_method_call_count() == 1
    call, kwargs = _RecordingExecutionEngine.instances[0].calls[0]
    assert call == "run_protective_lifecycle"
    assert kwargs["stop_create_permit"].permit_id == STOP_CREATE_PERMIT_ID
    assert kwargs["stop_create_permit"].expected_version == 1
    assert kwargs["take_profit_create_permit"].permit_id == TAKE_PROFIT_CREATE_PERMIT_ID
    assert kwargs["take_profit_create_permit"].expected_version == 2
    assert kwargs["take_profit_cancel_permit"].permit_id == TAKE_PROFIT_CANCEL_PERMIT_ID
    assert kwargs["take_profit_cancel_permit"].expected_version == 3
    assert kwargs["stop_cancel_permit"].permit_id == STOP_CANCEL_PERMIT_ID
    assert kwargs["stop_cancel_permit"].expected_version == 4
    _assert_no_permit_persistence_activity()
    _assert_db_and_audit_unchanged(permit_env, before_rows, before_actions)
    _assert_no_permit_mutation_audits(permit_env)
    _assert_no_execution_transport()
    _assert_sanitized(result.stdout, result.stderr)


def test_lifecycle_cli_requires_exact_create_and_cancel_permit_references(monkeypatch, permit_env):
    _patch_lifecycle(monkeypatch, _RejectingExecutionEngine)
    before_rows, before_actions = _execution_before(permit_env)
    result = _run_cli(lifecycle_cli.main, ["--run-lifecycle", "--confirm-testnet-lifecycle", "CONFIRM_BINANCE_FUTURES_TESTNET_ORDER_LIFECYCLE"])
    _assert_execution_rejected(permit_env, before_rows, before_actions, result)


def test_lifecycle_cli_rejects_missing_permit_version_before_engine(monkeypatch, permit_env):
    _patch_lifecycle(monkeypatch, _RejectingExecutionEngine)
    before_rows, before_actions = _execution_before(permit_env)
    result = _run_cli(lifecycle_cli.main, ["--run-lifecycle", "--create-permit-id", LIFECYCLE_CREATE_PERMIT_ID])
    _assert_execution_rejected(permit_env, before_rows, before_actions, result)


def test_lifecycle_cli_rejects_malformed_permit_reference_without_auto_issue(monkeypatch, permit_env):
    _patch_lifecycle(monkeypatch, _RejectingExecutionEngine)
    cases = [
        ["--create-permit-id", "bad", "--create-permit-version", "1"],
        ["--create-permit-id", LIFECYCLE_CREATE_PERMIT_ID, "--create-permit-version", "0"],
        ["--create-permit-id", LIFECYCLE_CREATE_PERMIT_ID, "--create-permit-version", "-1"],
        ["--create-permit-id", LIFECYCLE_CREATE_PERMIT_ID, "--create-permit-version", "not-an-int"],
    ]
    for extra in cases:
        before_rows, before_actions = _execution_before(permit_env)
        result = _run_cli(lifecycle_cli.main, ["--run-lifecycle", *extra])
        _assert_execution_rejected(permit_env, before_rows, before_actions, result)


def test_lifecycle_cli_forwards_exact_permits_once_without_bypass_or_transport(monkeypatch, permit_env):
    _patch_lifecycle(monkeypatch, _RecordingExecutionEngine)
    before_rows, before_actions = _execution_before(permit_env)
    result = _run_cli(lifecycle_cli.main, ["--run-lifecycle", "--confirm-testnet-lifecycle", "CONFIRM_BINANCE_FUTURES_TESTNET_ORDER_LIFECYCLE", "--create-permit-id", LIFECYCLE_CREATE_PERMIT_ID, "--create-permit-version", "5", "--cancel-permit-id", LIFECYCLE_CANCEL_PERMIT_ID, "--cancel-permit-version", "6"])
    assert result.code == 1
    assert _RecordingExecutionEngine.constructor_count == 1
    assert len(_RecordingExecutionEngine.instances) == 1
    assert _engine_method_call_count() == 1
    call, kwargs = _RecordingExecutionEngine.instances[0].calls[0]
    assert call == "run_lifecycle"
    assert kwargs["create_permit"].permit_id == LIFECYCLE_CREATE_PERMIT_ID
    assert kwargs["create_permit"].expected_version == 5
    assert kwargs["cancel_permit"].permit_id == LIFECYCLE_CANCEL_PERMIT_ID
    assert kwargs["cancel_permit"].expected_version == 6
    _assert_no_permit_persistence_activity()
    _assert_db_and_audit_unchanged(permit_env, before_rows, before_actions)
    _assert_no_permit_mutation_audits(permit_env)
    _assert_no_execution_transport()
    _assert_sanitized(result.stdout, result.stderr)


def test_order_test_cli_requires_exact_permit_reference(monkeypatch, permit_env):
    _patch_order_test(monkeypatch, _RejectingExecutionEngine)
    before_rows, before_actions = _execution_before(permit_env)
    result = _run_cli(order_test_cli.main, ["--submit-test-order", "--confirm-testnet-order-test", "CONFIRM_BINANCE_FUTURES_TESTNET_ORDER_TEST"])
    _assert_execution_rejected(permit_env, before_rows, before_actions, result)


def test_order_test_cli_rejects_missing_permit_version_before_engine(monkeypatch, permit_env):
    _patch_order_test(monkeypatch, _RejectingExecutionEngine)
    before_rows, before_actions = _execution_before(permit_env)
    result = _run_cli(order_test_cli.main, ["--submit-test-order", "--permit-id", ORDER_TEST_PERMIT_ID])
    _assert_execution_rejected(permit_env, before_rows, before_actions, result)


def test_order_test_cli_rejects_malformed_permit_reference_without_auto_issue(monkeypatch, permit_env):
    _patch_order_test(monkeypatch, _RejectingExecutionEngine)
    cases = [
        ["--permit-id", "bad", "--permit-version", "1"],
        ["--permit-id", ORDER_TEST_PERMIT_ID, "--permit-version", "0"],
        ["--permit-id", ORDER_TEST_PERMIT_ID, "--permit-version", "-1"],
        ["--permit-id", ORDER_TEST_PERMIT_ID, "--permit-version", "not-an-int"],
    ]
    for extra in cases:
        before_rows, before_actions = _execution_before(permit_env)
        result = _run_cli(order_test_cli.main, ["--submit-test-order", *extra])
        _assert_execution_rejected(permit_env, before_rows, before_actions, result)


def test_order_test_cli_forwards_exact_permit_once_without_bypass_or_transport(monkeypatch, permit_env):
    _patch_order_test(monkeypatch, _RecordingExecutionEngine)
    before_rows, before_actions = _execution_before(permit_env)
    result = _run_cli(order_test_cli.main, ["--submit-test-order", "--confirm-testnet-order-test", "CONFIRM_BINANCE_FUTURES_TESTNET_ORDER_TEST", "--permit-id", ORDER_TEST_PERMIT_ID, "--permit-version", "7"])
    assert result.code == 1
    assert _RecordingExecutionEngine.constructor_count == 1
    assert len(_RecordingExecutionEngine.instances) == 1
    assert _engine_method_call_count() == 1
    call, kwargs = _RecordingExecutionEngine.instances[0].calls[0]
    assert call == "submit_test_order"
    assert kwargs["permit"].permit_id == ORDER_TEST_PERMIT_ID
    assert kwargs["permit"].expected_version == 7
    _assert_no_permit_persistence_activity()
    _assert_db_and_audit_unchanged(permit_env, before_rows, before_actions)
    _assert_no_permit_mutation_audits(permit_env)
    _assert_no_execution_transport()
    _assert_sanitized(result.stdout, result.stderr)


def test_permit_issue_cli_rejects_malformed_fingerprint_input_fail_closed(tmp_path, permit_env):
    cases: list[tuple[str, str, dict | str, str]] = []
    invalid_operation = _valid_request_payload()
    invalid_operation["operation"] = "BAD"
    cases.append(("invalid operation", "BAD", invalid_operation, ISSUE_CONFIRMATION))
    production_environment = _valid_request_payload()
    production_environment["environment"] = "PRODUCTION"
    cases.append(("invalid environment", LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value, production_environment, ISSUE_CONFIRMATION))
    invalid_symbol = _valid_request_payload()
    invalid_symbol["symbol"] = "ETHUSDT"
    cases.append(("invalid symbol", LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value, invalid_symbol, ISSUE_CONFIRMATION))
    missing_subject = _valid_request_payload()
    missing_subject.pop("client_order_id")
    cases.append(("missing subject", LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value, missing_subject, ISSUE_CONFIRMATION))
    malformed_fields = _valid_request_payload()
    malformed_fields["reduce_only"] = "false"
    cases.append(("malformed fingerprint fields", LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value, malformed_fields, ISSUE_CONFIRMATION))
    mismatch = _valid_request_payload()
    cases.append(("fingerprint operation mismatch", LiveExecutionOperation.ORDER_LIFECYCLE_CREATE.value, mismatch, ISSUE_CONFIRMATION))
    cases.append(("malformed JSON", LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value, "{not-json", ISSUE_CONFIRMATION))

    for label, operation, payload, confirmation in cases:
        _CountingPermitPersistence.reset()
        result = _run_cli(issue_cli.main, ["--operation", operation, "--request-file", str(_write_request(tmp_path, payload)), "--issued-by", "cli-test", "--confirmation", confirmation])
        assert result.code != 0, label
        assert _CountingPermitPersistence.issue_success == 0
        assert _permit_rows(permit_env) == []
        assert "PERMIT_ISSUED" not in _audit_actions(permit_env)
        _assert_sanitized(result.stdout, result.stderr, _audit_actions(permit_env))


def test_permit_issue_cli_issues_once_only_with_explicit_confirmation_and_sanitized_output(tmp_path, permit_env):
    path = _write_request(tmp_path, _valid_request_payload())
    baseline_actions = _audit_actions(permit_env)
    missing = _run_cli(issue_cli.main, ["--operation", LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value, "--request-file", str(path), "--issued-by", "cli-test"])
    assert missing.code != 0
    assert _CountingPermitPersistence.issue_success == 0
    assert _permit_rows(permit_env) == []
    assert _audit_actions(permit_env) == baseline_actions

    wrong = _run_cli(issue_cli.main, ["--operation", LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value, "--request-file", str(path), "--issued-by", "cli-test", "--confirmation", "WRONG"])
    assert wrong.code != 0
    assert _CountingPermitPersistence.issue_attempt == 1
    assert _CountingPermitPersistence.issue_success == 0
    assert _permit_rows(permit_env) == []
    assert _audit_actions(permit_env) == baseline_actions

    result = _run_cli(issue_cli.main, ["--operation", LiveExecutionOperation.SIGNED_ORDER_TEST_CREATE.value, "--request-file", str(path), "--issued-by", "cli-test", "--confirmation", ISSUE_CONFIRMATION])
    assert result.code == 0
    data = json.loads(result.stdout)
    assert data["state"] == LiveExecutionPermitState.ISSUED.value
    assert data["version"] == 1
    rows = _permit_rows(permit_env)
    assert len(rows) == 1
    assert rows[0] == (data["permit_id"], LiveExecutionPermitState.ISSUED.value, 1)
    actions = _audit_actions(permit_env)
    assert actions.count("PERMIT_ISSUED") == 1
    assert _CountingPermitPersistence.issue_attempt == 2
    assert _CountingPermitPersistence.issue_success == 1
    assert _CountingPermitPersistence.show_success == 0
    assert _CountingPermitPersistence.revoke_success == 0
    assert _CountingPermitPersistence.consume_success == 0
    assert _CountingPermitPersistence.ensure_count == 2
    assert _CountingPermitPersistence.close_count == 2
    _assert_sanitized(missing.stdout, missing.stderr, wrong.stdout, wrong.stderr, result.stdout, result.stderr)


def test_permit_show_cli_rejects_malformed_permit_id_without_persistence_mutation(permit_env):
    before = _permit_rows(permit_env)
    before_actions = _audit_actions(permit_env)
    result = _run_cli(show_cli.main, ["--permit-id", "not-a-permit"])
    assert result.code == 1
    assert _CountingPermitPersistence.show_attempt == 1
    assert _CountingPermitPersistence.show_success == 0
    _assert_db_and_audit_unchanged(permit_env, before, before_actions)
    _assert_sanitized(result.stdout, result.stderr, _audit_actions(permit_env))


def test_permit_show_cli_is_read_only_and_sanitizes_output(tmp_path, permit_env):
    issued = _issue_permit(tmp_path, permit_env)
    _CountingPermitPersistence.reset()
    before = _permit_rows(permit_env)
    before_actions = _audit_actions(permit_env)
    result = _run_cli(show_cli.main, ["--permit-id", issued["permit_id"]])
    assert result.code == 0
    data = json.loads(result.stdout)
    assert data["permit_id"] == issued["permit_id"]
    assert data["state"] == LiveExecutionPermitState.ISSUED.value
    assert data["version"] == 1
    _assert_db_and_audit_unchanged(permit_env, before, before_actions)
    assert _CountingPermitPersistence.show_attempt == 1
    assert _CountingPermitPersistence.show_success == 1
    assert _CountingPermitPersistence.issue_success == 0
    assert _CountingPermitPersistence.revoke_success == 0
    assert _CountingPermitPersistence.consume_success == 0
    assert "PERMIT_CONSUMED" not in _audit_actions(permit_env)
    _assert_sanitized(result.stdout, result.stderr)


def test_permit_revoke_cli_requires_exact_id_version_and_confirmation(tmp_path, permit_env):
    issued = _issue_permit(tmp_path, permit_env)
    _CountingPermitPersistence.reset()
    before = _permit_rows(permit_env)
    before_actions = _audit_actions(permit_env)
    missing = _run_cli(revoke_cli.main, ["--permit-id", issued["permit_id"], "--expected-version", "1", "--reason-code", "OPERATOR_REVOKED", "--confirmation", "WRONG"])
    malformed = _run_cli(revoke_cli.main, ["--permit-id", "bad", "--expected-version", "1", "--reason-code", "OPERATOR_REVOKED", "--confirmation", REVOKE_CONFIRMATION])
    assert missing.code == 1
    assert malformed.code == 1
    assert _CountingPermitPersistence.revoke_attempt == 2
    assert _CountingPermitPersistence.revoke_success == 0
    _assert_db_and_audit_unchanged(permit_env, before, before_actions)
    _assert_sanitized(missing.stdout, missing.stderr, malformed.stdout, malformed.stderr)


def test_permit_revoke_cli_revokes_once_without_refund_reuse_or_secret_leak(tmp_path, permit_env):
    issued = _issue_permit(tmp_path, permit_env)
    _CountingPermitPersistence.reset()
    result = _run_cli(revoke_cli.main, ["--permit-id", issued["permit_id"], "--expected-version", "1", "--reason-code", "OPERATOR_REVOKED", "--confirmation", REVOKE_CONFIRMATION])
    assert result.code == 0
    data = json.loads(result.stdout)
    assert data["state"] == LiveExecutionPermitState.REVOKED.value
    assert data["version"] == 2
    assert _permit_rows(permit_env) == [(issued["permit_id"], LiveExecutionPermitState.REVOKED.value, 2)]
    assert _CountingPermitPersistence.revoke_attempt == 1
    assert _CountingPermitPersistence.revoke_success == 1
    assert _CountingPermitPersistence.consume_success == 0

    repeat = _run_cli(revoke_cli.main, ["--permit-id", issued["permit_id"], "--expected-version", "1", "--reason-code", "OPERATOR_REVOKED", "--confirmation", REVOKE_CONFIRMATION])
    assert repeat.code == 1
    assert _CountingPermitPersistence.revoke_attempt == 2
    assert _CountingPermitPersistence.revoke_success == 1
    rows = _permit_rows(permit_env)
    assert rows == [(issued["permit_id"], LiveExecutionPermitState.REVOKED.value, 2)]
    assert _permit_ids(permit_env) == [issued["permit_id"]]
    actions = _audit_actions(permit_env)
    assert actions.count("PERMIT_ISSUED") == 1
    assert actions.count("PERMIT_REVOKED") == 1
    assert actions.count("PERMIT_CONSUMED") == 0
    assert "PERMIT_REFUNDED" not in actions
    assert "PERMIT_REISSUED" not in actions
    _assert_sanitized(result.stdout, result.stderr, repeat.stdout, repeat.stderr, actions)
