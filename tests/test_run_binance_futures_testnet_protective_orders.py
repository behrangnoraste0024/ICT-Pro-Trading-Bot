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


def test_default_preview_derives_pair_specific_client_algo_ids(capsys) -> None:
    code = main([
        "--build-preview",
        "--pair-id",
        "protective-local-001",
        "--preview-position-amount",
        "0.001",
        "--preview-mark-price",
        "50000",
        "--preview-entry-price",
        "49000",
        "--preview-tick-size",
        "0.10",
    ])

    output_one = capsys.readouterr().out
    assert code == 0
    assert "smcbot-protect-sl-001" not in output_one
    assert "smcbot-protect-tp-001" not in output_one
    assert "smcbot-protect-sl-" in output_one
    assert "smcbot-protect-tp-" in output_one

    code = main([
        "--build-preview",
        "--pair-id",
        "protective-local-002",
        "--preview-position-amount",
        "0.001",
        "--preview-mark-price",
        "50000",
        "--preview-entry-price",
        "49000",
        "--preview-tick-size",
        "0.10",
    ])
    output_two = capsys.readouterr().out

    assert code == 0
    assert output_one != output_two


def test_explicit_equal_client_algo_ids_fail_closed() -> None:
    code = main([
        "--build-preview",
        "--pair-id",
        "protective-local-001",
        "--stop-client-algo-id",
        "smcbot-protect-same",
        "--take-profit-client-algo-id",
        "smcbot-protect-same",
        "--preview-position-amount",
        "0.001",
        "--preview-mark-price",
        "50000",
        "--preview-entry-price",
        "49000",
        "--preview-tick-size",
        "0.10",
    ])

    assert code == 1
