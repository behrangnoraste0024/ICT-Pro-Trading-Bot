from __future__ import annotations

import json

from scripts import run_binance_futures_testnet_order_lifecycle


def test_default_validation_prints_report(capsys) -> None:
    code = run_binance_futures_testnet_order_lifecycle.main([])

    captured = capsys.readouterr()
    assert code == 0
    assert "BINANCE FUTURES TESTNET MANUAL ORDER LIFECYCLE VALIDATION" in captured.out
    assert "Status                       : PASS" in captured.out


def test_json_validation_is_serializable(capsys) -> None:
    code = run_binance_futures_testnet_order_lifecycle.main(["--json"])

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["status"] == "PASS"


def test_check_credentials_warns_without_values(capsys, monkeypatch) -> None:
    monkeypatch.delenv("BINANCE_FUTURES_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_FUTURES_TESTNET_API_SECRET", raising=False)

    code = run_binance_futures_testnet_order_lifecycle.main(["--check-credentials"])

    captured = capsys.readouterr()
    assert code == 0
    assert "CREDENTIALS_NOT_CONFIGURED" in captured.out


def test_local_preview_uses_no_credentials_or_network(capsys) -> None:
    code = run_binance_futures_testnet_order_lifecycle.main(["--build-preview", "--lifecycle-id", "lifecycle-local-001", "--client-order-id", "smcbot-lifecycle-001", "--side", "BUY", "--quantity", "0.001", "--price-offset-bps", "100"])

    captured = capsys.readouterr()
    assert code == 0
    assert "LIFECYCLE_PREVIEW_VALID" in captured.out
    assert "Transmission Ready        : false" in captured.out


def test_run_lifecycle_without_confirmation_does_not_use_credentials(capsys, monkeypatch) -> None:
    monkeypatch.setenv("BINANCE_FUTURES_TESTNET_API_KEY", "unit-test-key")
    monkeypatch.setenv("BINANCE_FUTURES_TESTNET_API_SECRET", "unit-test-secret")

    code = run_binance_futures_testnet_order_lifecycle.main(
        [
            "--run-lifecycle",
            "--lifecycle-id",
            "lifecycle-testnet-001",
            "--client-order-id",
            "smcbot-lifecycle-001",
            "--side",
            "BUY",
            "--quantity",
            "0.001",
            "--create-permit-id",
            "permit-44444444444444444444444444444444",
            "--create-permit-version",
            "5",
            "--cancel-permit-id",
            "permit-55555555555555555555555555555555",
            "--cancel-permit-version",
            "6",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "CONFIRMATION_REQUIRED" in captured.out
    assert "Credentials Complete" not in captured.out


def test_recover_lifecycle_requires_exact_confirmation(capsys, monkeypatch) -> None:
    monkeypatch.setenv("BINANCE_FUTURES_TESTNET_API_KEY", "unit-test-key")
    monkeypatch.setenv("BINANCE_FUTURES_TESTNET_API_SECRET", "unit-test-secret")

    code = run_binance_futures_testnet_order_lifecycle.main(["--recover-lifecycle", "--client-order-id", "smcbot-lifecycle-001"])

    captured = capsys.readouterr()
    assert code == 0
    assert "CONFIRMATION_REQUIRED" in captured.out
