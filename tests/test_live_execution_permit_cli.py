from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import Column, MetaData, String, Table, create_engine, event, select
from sqlalchemy.orm import Session

from infrastructure.persistence.execution_orm import AuditEventORM, ExecutionPersistenceBase, LiveExecutionPermitORM
from infrastructure.persistence.schema_contract import PERSISTENCE_REVISION
from scripts import issue_live_execution_permit, revoke_live_execution_permit, show_live_execution_permit

HOSTILE_MARKERS = ["postgresql://user:secret@", "connectionString", "SELECT * FROM", "traceback", "X-MBX-APIKEY", "signature=", "signed-url", "rawResponse", "Authorization", "secret-token"]


def _engine(path: Path):
    engine = create_engine(f"sqlite:///{path}", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _prepare_database(tmp_path: Path, monkeypatch) -> Path:
    db_path = tmp_path / "permit_cli.db"
    engine = _engine(db_path)
    ExecutionPersistenceBase.metadata.create_all(engine)
    metadata = MetaData()
    version = Table("alembic_version", metadata, Column("version_num", String(64), primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(version.insert().values(version_num=PERSISTENCE_REVISION))
    engine.dispose()
    monkeypatch.setenv("ICT_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return db_path


def _request_payload(**overrides) -> dict:
    payload = {
        "schema_version": "1.0",
        "operation": "PROTECTIVE_CREATE",
        "environment": "TESTNET",
        "symbol": "BTCUSDT",
        "pair_id": "pair-cli",
        "leg_type": "STOP",
        "side": "SELL",
        "position_side": "LONG",
        "quantity": "0.0016",
        "trigger_price": "62000",
        "close_position": True,
        "reduce_only": None,
        "client_algo_id": "smcbot-protect-cli",
        "order_type": "STOP_MARKET",
        "working_type": "MARK_PRICE",
        "price_protect": True,
    }
    payload.update(overrides)
    return payload


def _write_request(tmp_path: Path, payload: object) -> Path:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    return request_path


def _assert_sanitized(text: str) -> None:
    for marker in HOSTILE_MARKERS:
        assert marker not in text


def test_issue_revoke_and_show_cli_success(tmp_path: Path, monkeypatch, capsys) -> None:
    db_path = _prepare_database(tmp_path, monkeypatch)
    request_path = _write_request(tmp_path, _request_payload())

    code = issue_live_execution_permit.main([
        "--operation", "PROTECTIVE_CREATE",
        "--request-file", str(request_path),
        "--ttl-seconds", "300",
        "--issued-by", "operator-1",
        "--confirmation", "CONFIRM_TESTNET_ONE_TIME_EXECUTION_PERMIT",
    ])
    issued_out = capsys.readouterr()
    assert code == 0
    issued = json.loads(issued_out.out)
    assert issued["state"] == "ISSUED"
    assert "raw" not in issued_out.out.lower()

    show_code = show_live_execution_permit.main(["--permit-id", issued["permit_id"]])
    show_out = capsys.readouterr()
    assert show_code == 0
    shown = json.loads(show_out.out)
    assert shown["permit_id"] == issued["permit_id"]
    assert shown["effective_expired"] is False

    revoke_code = revoke_live_execution_permit.main([
        "--permit-id", issued["permit_id"],
        "--expected-version", str(issued["version"]),
        "--reason-code", "OPERATOR_REVOKED",
        "--confirmation", "CONFIRM_TESTNET_REVOKE_EXECUTION_PERMIT",
    ])
    revoke_out = capsys.readouterr()
    assert revoke_code == 0
    revoked = json.loads(revoke_out.out)
    assert revoked["state"] == "REVOKED"

    engine = _engine(db_path)
    with Session(engine, future=True) as session:
        assert len(session.scalars(select(AuditEventORM)).all()) == 2
        assert session.scalar(select(LiveExecutionPermitORM)).state == "REVOKED"
    engine.dispose()


def test_show_cli_is_read_only(tmp_path: Path, monkeypatch, capsys) -> None:
    db_path = _prepare_database(tmp_path, monkeypatch)
    request_path = _write_request(tmp_path, _request_payload())
    assert issue_live_execution_permit.main(["--operation", "PROTECTIVE_CREATE", "--request-file", str(request_path), "--issued-by", "operator-1", "--confirmation", "CONFIRM_TESTNET_ONE_TIME_EXECUTION_PERMIT"]) == 0
    issued = json.loads(capsys.readouterr().out)
    assert show_live_execution_permit.main(["--permit-id", issued["permit_id"]]) == 0
    capsys.readouterr()
    assert show_live_execution_permit.main(["--permit-id", issued["permit_id"]]) == 0
    capsys.readouterr()
    engine = _engine(db_path)
    with Session(engine, future=True) as session:
        assert len(session.scalars(select(AuditEventORM)).all()) == 1
        row = session.scalar(select(LiveExecutionPermitORM))
        assert row.state == "ISSUED"
        assert row.version == 1
    engine.dispose()


def test_issue_cli_rejects_missing_database_env_without_leaking_url(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("ICT_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    request_path = _write_request(tmp_path, _request_payload())
    code = issue_live_execution_permit.main(["--operation", "PROTECTIVE_CREATE", "--request-file", str(request_path), "--issued-by", "operator-1", "--confirmation", "CONFIRM_TESTNET_ONE_TIME_EXECUTION_PERMIT"])
    out = capsys.readouterr()
    assert code == 1
    assert json.loads(out.err)["error"] == "PERMIT_UNAVAILABLE"
    _assert_sanitized(out.err + out.out)


def test_cli_rejects_wrong_confirmation_and_sanitizes_output(tmp_path: Path, monkeypatch, capsys) -> None:
    _prepare_database(tmp_path, monkeypatch)
    request_path = _write_request(tmp_path, _request_payload())
    code = issue_live_execution_permit.main(["--operation", "PROTECTIVE_CREATE", "--request-file", str(request_path), "--issued-by", "operator-1", "--confirmation", "postgresql://user:secret@ rawResponse"])
    out = capsys.readouterr()
    assert code == 1
    assert json.loads(out.err)["error"] == "PERMIT_CONFIRMATION_REQUIRED"
    _assert_sanitized(out.err + out.out)


def test_issue_cli_rejects_malformed_request_unknown_fields_float_and_wrong_scope(tmp_path: Path, monkeypatch, capsys) -> None:
    _prepare_database(tmp_path, monkeypatch)
    cases = [
        "{not-json",
        dict(_request_payload(), rawResponse="secret-token"),
        dict(_request_payload(), quantity=0.0016),
        dict(_request_payload(), operation="UNKNOWN"),
        dict(_request_payload(), environment="PRODUCTION"),
        dict(_request_payload(), symbol="ETHUSDT"),
    ]
    for index, payload in enumerate(cases):
        request_path = tmp_path / f"request-{index}.json"
        if isinstance(payload, str):
            request_path.write_text(payload, encoding="utf-8")
        else:
            request_path.write_text(json.dumps(payload), encoding="utf-8")
        code = issue_live_execution_permit.main(["--operation", payload.get("operation", "PROTECTIVE_CREATE") if isinstance(payload, dict) else "PROTECTIVE_CREATE", "--request-file", str(request_path), "--issued-by", "operator-1", "--confirmation", "CONFIRM_TESTNET_ONE_TIME_EXECUTION_PERMIT"])
        out = capsys.readouterr()
        assert code == 1
        assert json.loads(out.err)["error"] == "PERMIT_INVALID"
        _assert_sanitized(out.err + out.out)


def test_no_consume_cli_exists() -> None:
    assert not Path("scripts/consume_live_execution_permit.py").exists()
