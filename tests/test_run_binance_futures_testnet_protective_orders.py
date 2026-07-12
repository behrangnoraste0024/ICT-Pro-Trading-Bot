from __future__ import annotations

from scripts.run_binance_futures_testnet_protective_orders import main


def test_strict_validation_passes_for_default_config() -> None:
    assert main(["--strict"]) == 0


def test_preview_does_not_require_credentials_or_network() -> None:
    code = main(
        [
            "--build-preview",
            "--pair-id",
            "protective-local-001",
            "--stop-client-algo-id",
            "smcbot-protect-sl-001",
            "--take-profit-client-algo-id",
            "smcbot-protect-tp-001",
            "--preview-position-amount",
            "0.001",
            "--preview-mark-price",
            "50000",
            "--preview-entry-price",
            "49000",
            "--preview-tick-size",
            "0.10",
        ]
    )

    assert code == 0
