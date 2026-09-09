from __future__ import annotations

import json
import pytest

from scripts import run_binance_futures_testnet_forward_test
from tests.test_binance_futures_testnet_forward_test_engine import supervised, _no_network_or_real_signing


def _supervised_args(path, kwargs):
    reference = kwargs["permit_references"][0]
    return ["--run", "--json", "--config", path,
            "--supervised-testnet-order-test", "--authorize-supervised-testnet-order-test",
            "--enable-testnet-order-test-network",
            "--local-simulated-transport", "--order-test-confirmation", "CONFIRM_TESTNET_ORDER_TEST",
            "--testnet-api-key-identifier", kwargs["api_key_identifier"],
            "--testnet-api-secret-identifier", kwargs["api_secret_identifier"],
            "--permit-id", reference.permit_id, "--permit-version", str(reference.expected_version),
            "--order-test-client-id", "smcbot-test-bridge", "--order-test-side", "BUY",
            "--order-test-type", "LIMIT", "--order-test-quantity", "0.001",
            "--order-test-price", "50000", "--order-test-time-in-force", "GTC"]


def test_explicit_script_bridge_uses_real_gate_and_only_local_transport(supervised, capsys, monkeypatch):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    _set_runtime_env(monkeypatch, env)
    code = run_binance_futures_testnet_forward_test.main(_supervised_args(path, kwargs), order_test_engine=boundary)
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["evidence"]["permit_consumed_count"] == 1
    assert payload["evidence"]["actual_binance_demo_execution"] is False
    assert payload["evidence"]["transport_mode"] == "LOCAL_TEST_SIMULATED_TRANSPORT"
    assert events == ["committed", "closed", "simulated-signing", "local-post"]


@pytest.mark.parametrize("flag", ["--authorize-supervised-testnet-order-test", "--supervised-testnet-order-test", "--enable-testnet-order-test-network"])
def test_script_requires_explicit_order_test_switches(supervised, capsys, monkeypatch, flag):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    _set_runtime_env(monkeypatch, env)
    args = _supervised_args(path, kwargs)
    args.remove(flag)
    code = run_binance_futures_testnet_forward_test.main(args, order_test_engine=boundary)
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["evidence"]["post_count"] == 0
    assert events == []


def test_cli_without_network_enablement_does_not_load_credentials_or_select_default_transport(supervised, capsys):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    args = _supervised_args(path, kwargs)
    args.remove("--enable-testnet-order-test-network")
    args.remove("--local-simulated-transport")
    code = run_binance_futures_testnet_forward_test.main(args)
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["decision"] == "TESTNET_ORDER_TEST_NETWORK_ENABLE_REQUIRED"
    assert payload["diagnostics"]["credentials_inspected"] is False
    assert payload["evidence"]["post_count"] == 0
    assert events == []


@pytest.mark.parametrize("missing", ["BINANCE_FUTURES_TESTNET_API_KEY", "BINANCE_FUTURES_TESTNET_API_SECRET", "ICT_DATABASE_URL"])
def test_script_runtime_environment_values_are_required(supervised, capsys, monkeypatch, missing):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    _set_runtime_env(monkeypatch, env)
    monkeypatch.delenv(missing, raising=False)
    code = run_binance_futures_testnet_forward_test.main(_supervised_args(path, kwargs), order_test_engine=boundary)
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["decision"] == "TESTNET_RUNTIME_ENVIRONMENT_REQUIRED"
    assert payload["evidence"]["post_count"] == 0
    assert events == []


@pytest.mark.parametrize("blank", ["BINANCE_FUTURES_TESTNET_API_KEY", "BINANCE_FUTURES_TESTNET_API_SECRET", "ICT_DATABASE_URL"])
def test_script_runtime_environment_values_must_not_be_blank(supervised, capsys, monkeypatch, blank):
    engine, path, kwargs, boundary, env, events, requests, show = supervised
    _set_runtime_env(monkeypatch, env)
    monkeypatch.setenv(blank, " ")
    code = run_binance_futures_testnet_forward_test.main(_supervised_args(path, kwargs), order_test_engine=boundary)
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["decision"] == "TESTNET_RUNTIME_ENVIRONMENT_REQUIRED"
    assert payload["evidence"]["post_count"] == 0
    assert events == []


def test_runtime_environment_from_process_is_allowlisted(monkeypatch):
    values = {
        "BINANCE_FUTURES_TESTNET_API_KEY": "sentinel-key",
        "BINANCE_FUTURES_TESTNET_API_SECRET": "sentinel-secret",
        "ICT_DATABASE_URL": "sqlite:///sentinel.db",
        "DATABASE_URL": "sqlite:///fallback.db",
        "BINANCE_API_KEY": "prod-key",
        "AWS_SECRET_ACCESS_KEY": "extra-secret",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    runtime = run_binance_futures_testnet_forward_test._runtime_environment_from_process()
    assert set(runtime) == {
        "BINANCE_FUTURES_TESTNET_API_KEY",
        "BINANCE_FUTURES_TESTNET_API_SECRET",
        "ICT_DATABASE_URL",
        "DATABASE_URL",
    }
    assert "prod-key" not in json.dumps(runtime)
    assert "extra-secret" not in json.dumps(runtime)


def test_default_validation_prints_disabled_report(capsys) -> None:
    code = run_binance_futures_testnet_forward_test.main([])

    captured = capsys.readouterr()
    assert code == 0
    assert "BINANCE FUTURES TESTNET FORWARD TEST VALIDATION" in captured.out
    assert "Status                     : PASS" in captured.out
    assert "Execution Enabled          : false" in captured.out


def test_json_validation_is_sanitized_and_serializable(capsys) -> None:
    code = run_binance_futures_testnet_forward_test.main(["--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert payload["status"] == "PASS"
    assert payload["config"]["execution_enabled"] is False
    assert payload["diagnostics"]["network_used"] is False
    assert "signature=" not in captured.out
    assert "X-MBX-APIKEY" not in captured.out


def test_run_without_local_simulation_fails_closed(capsys) -> None:
    code = run_binance_futures_testnet_forward_test.main(
        [
            "--run",
            "--permit-id",
            "permit-88888888888888888888888888888888",
            "--permit-version",
            "4",
            "--strategy-decisions",
            "3",
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "EXECUTION_NOT_AUTHORIZED" in captured.out
    assert "Permits Consumed           : 0" in captured.out
    assert "Signing Count              : 0" in captured.out
    assert "POST Count                 : 0" in captured.out
    assert "DELETE Count               : 0" in captured.out


def test_local_simulated_transport_report_never_claims_demo_execution(capsys) -> None:
    code = run_binance_futures_testnet_forward_test.main(["--run", "--local-simulated-transport", "--strategy-decisions", "2"])

    captured = capsys.readouterr()
    assert code == 0
    assert "LOCAL TEST / SIMULATED TRANSPORT" in captured.out
    assert "ACTUAL BINANCE DEMO EXECUTION: false" in captured.out
    assert "Actual Binance Demo        : false" in captured.out


def test_mismatched_permit_arguments_are_sanitized(capsys) -> None:
    code = run_binance_futures_testnet_forward_test.main(["--run", "--permit-id", "permit-99999999999999999999999999999999"])

    captured = capsys.readouterr()
    assert code == 1
    assert "sanitized forward-test error" in captured.out
    assert "traceback" not in captured.out.lower()


def _set_runtime_env(monkeypatch, env):
    for key in (
        "BINANCE_FUTURES_TESTNET_API_KEY",
        "BINANCE_FUTURES_TESTNET_API_SECRET",
        "ICT_DATABASE_URL",
        "DATABASE_URL",
    ):
        if key in env:
            monkeypatch.setenv(key, env[key])
