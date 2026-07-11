from __future__ import annotations

import json
from pathlib import Path

from scripts import run_binance_futures_testnet_adapter
from tests.test_binance_futures_testnet_adapter_engine import _write_adapter_configs


def test_default_validate_command_passes(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_adapter_configs(tmp_path)
    monkeypatch.setattr(run_binance_futures_testnet_adapter, "ROOT_DIR", tmp_path)

    code = run_binance_futures_testnet_adapter.main([])

    captured = capsys.readouterr()
    assert code == 0
    assert "BINANCE FUTURES TESTNET ADAPTER VALIDATION" in captured.out
    assert "Status                      : PASS" in captured.out


def test_json_validate_command_is_serializable(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_adapter_configs(tmp_path)
    monkeypatch.setattr(run_binance_futures_testnet_adapter, "ROOT_DIR", tmp_path)

    code = run_binance_futures_testnet_adapter.main(["--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert payload["status"] == "PASS"


def test_check_credentials_missing_warns_without_failure(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_adapter_configs(tmp_path)
    monkeypatch.setattr(run_binance_futures_testnet_adapter, "ROOT_DIR", tmp_path)
    monkeypatch.delenv("BINANCE_FUTURES_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_FUTURES_TESTNET_API_SECRET", raising=False)

    code = run_binance_futures_testnet_adapter.main(["--check-credentials"])

    captured = capsys.readouterr()
    assert code == 0
    assert "CREDENTIALS_NOT_CONFIGURED" in captured.out
    assert "Credentials Inspected        : true" in captured.out


def test_strict_check_credentials_missing_fails(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_adapter_configs(tmp_path)
    monkeypatch.setattr(run_binance_futures_testnet_adapter, "ROOT_DIR", tmp_path)
    monkeypatch.delenv("BINANCE_FUTURES_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_FUTURES_TESTNET_API_SECRET", raising=False)

    code = run_binance_futures_testnet_adapter.main(["--check-credentials", "--strict"])

    capsys.readouterr()
    assert code == 1


def test_signed_preview_without_credentials_warns_and_does_not_transmit(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_adapter_configs(tmp_path)
    monkeypatch.setattr(run_binance_futures_testnet_adapter, "ROOT_DIR", tmp_path)
    monkeypatch.delenv("BINANCE_FUTURES_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_FUTURES_TESTNET_API_SECRET", raising=False)

    code = run_binance_futures_testnet_adapter.main(["--signed-request-preview", "--preview-path", "/fapi/v2/account"])

    captured = capsys.readouterr()
    assert code == 0
    assert "CREDENTIALS_NOT_CONFIGURED" in captured.out
    assert "Request Transmitted          : false" in captured.out


def test_build_order_intent_is_non_executable(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_adapter_configs(tmp_path)
    monkeypatch.setattr(run_binance_futures_testnet_adapter, "ROOT_DIR", tmp_path)

    code = run_binance_futures_testnet_adapter.main(
        ["--build-order-intent", "--intent-id", "intent-1", "--side", "BUY", "--order-type", "MARKET", "--quantity", "0.001"]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "ORDER_INTENT_VALID" in captured.out
    assert "request_transmitted: False" in captured.out
    assert "Testnet Order Submitted      : false" in captured.out


def test_missing_preview_path_fails(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_adapter_configs(tmp_path)
    monkeypatch.setattr(run_binance_futures_testnet_adapter, "ROOT_DIR", tmp_path)

    code = run_binance_futures_testnet_adapter.main(["--signed-request-preview"])

    captured = capsys.readouterr()
    assert code == 1
    assert "Missing required signed-request-preview argument" in captured.out


def test_exports_json_and_markdown(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_adapter_configs(tmp_path)
    monkeypatch.setattr(run_binance_futures_testnet_adapter, "ROOT_DIR", tmp_path)
    json_path = tmp_path / "adapter.json"
    md_path = tmp_path / "adapter.md"

    code = run_binance_futures_testnet_adapter.main(["--export-json", str(json_path), "--export-md", str(md_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert "[binance-futures-testnet-adapter] wrote" in captured.out
    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "PASS"
    assert "BINANCE FUTURES TESTNET ADAPTER VALIDATION" in md_path.read_text(encoding="utf-8")
