from __future__ import annotations

import json

from scripts import run_binance_futures_testnet_order_test


def test_default_validation_prints_report(capsys) -> None:
    code = run_binance_futures_testnet_order_test.main([])

    captured = capsys.readouterr()
    assert code == 0
    assert "BINANCE FUTURES TESTNET TEST ORDER VALIDATION" in captured.out
    assert "Status                       : PASS" in captured.out


def test_json_validation_is_serializable(capsys) -> None:
    code = run_binance_futures_testnet_order_test.main(["--json"])

    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["status"] == "PASS"
    assert payload["diagnostics"]["credentials_inspected"] is False


def test_check_credentials_warns_without_values(capsys, monkeypatch) -> None:
    monkeypatch.delenv("BINANCE_FUTURES_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_FUTURES_TESTNET_API_SECRET", raising=False)

    code = run_binance_futures_testnet_order_test.main(["--check-credentials"])

    captured = capsys.readouterr()
    assert code == 0
    assert "CREDENTIALS_NOT_CONFIGURED" in captured.out
    assert "API Key Present           : false" in captured.out


def test_market_preview_cli_uses_no_credentials_or_network(capsys) -> None:
    code = run_binance_futures_testnet_order_test.main(
        [
            "--build-preview",
            "--client-order-id",
            "smcbot-test-market-001",
            "--side",
            "BUY",
            "--order-type",
            "MARKET",
            "--quantity",
            "0.001",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "ORDER_TEST_PREVIEW_VALID" in captured.out
    assert "Credentials Inspected     : false" in captured.out
    assert "Test Request Transmitted  : false" in captured.out


def test_submit_without_confirmation_does_not_use_credentials_or_network(capsys, monkeypatch) -> None:
    monkeypatch.setenv("BINANCE_FUTURES_TESTNET_API_KEY", "unit-test-key-token")
    monkeypatch.setenv("BINANCE_FUTURES_TESTNET_API_SECRET", "unit-test-private-token")

    code = run_binance_futures_testnet_order_test.main(
        [
            "--submit-test-order",
            "--client-order-id",
            "smcbot-test-market-002",
            "--side",
            "BUY",
            "--order-type",
            "MARKET",
            "--quantity",
            "0.001",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "NETWORK_CONFIRMATION_REQUIRED" in captured.out
    assert "Credentials Inspected     : false" in captured.out
    assert "Signature Generated       : false" in captured.out


def test_exports_do_not_include_signed_url_or_signature(tmp_path, capsys) -> None:
    json_path = tmp_path / "order-test.json"
    md_path = tmp_path / "order-test.md"

    code = run_binance_futures_testnet_order_test.main(["--build-preview", "--export-json", str(json_path), "--export-md", str(md_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert "[binance-futures-testnet-order-test] wrote" in captured.out
    assert "signature=" not in json_path.read_text(encoding="utf-8")
    assert "signature=" not in md_path.read_text(encoding="utf-8")
    assert "X-MBX-APIKEY" not in json_path.read_text(encoding="utf-8")
