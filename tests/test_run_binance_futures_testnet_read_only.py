from __future__ import annotations

import json

from models.binance_futures_testnet_read_only import BinanceFuturesTestnetReadOnlyResult
from scripts import run_binance_futures_testnet_read_only
from tests.test_binance_futures_testnet_read_only_engine import _write_read_only_configs


class _FakeEngine:
    def __init__(self, repo_root=None, env=None) -> None:
        self.repo_root = repo_root
        self.env = env

    def validate(self, *args, **kwargs):
        from models.binance_futures_testnet_read_only import BinanceFuturesTestnetReadOnlyValidationReport

        return BinanceFuturesTestnetReadOnlyValidationReport(status="PASS", config_path=args[0])

    def check_credentials(self, *args, **kwargs):
        return BinanceFuturesTestnetReadOnlyResult(action="CHECK_CREDENTIALS", status="WARNING", decision="CREDENTIALS_NOT_CONFIGURED", reason="missing")

    def fetch_account(self, *args, **kwargs):
        return BinanceFuturesTestnetReadOnlyResult(action="FETCH_ACCOUNT", status="PASS", decision="ACCOUNT_READ_SUCCESS", reason="ok", authenticated_transport_invoked=True)

    def fetch_balance(self, *args, **kwargs):
        return BinanceFuturesTestnetReadOnlyResult(action="FETCH_BALANCE", status="PASS", decision="BALANCE_READ_SUCCESS", reason="ok", authenticated_transport_invoked=True)

    def fetch_position_risk(self, *args, **kwargs):
        return BinanceFuturesTestnetReadOnlyResult(action="FETCH_POSITION_RISK", status="PASS", decision="POSITION_READ_SUCCESS", reason="ok", authenticated_transport_invoked=True)

    def fetch_account_snapshot(self, *args, **kwargs):
        return BinanceFuturesTestnetReadOnlyResult(action="FETCH_ACCOUNT_SNAPSHOT", status="PASS", decision="ACCOUNT_SNAPSHOT_SUCCESS", reason="ok", authenticated_transport_invoked=True)


def test_default_validate_and_json_are_serializable(tmp_path, capsys, monkeypatch) -> None:
    _write_read_only_configs(tmp_path)
    monkeypatch.setattr(run_binance_futures_testnet_read_only, "ROOT_DIR", tmp_path)

    code = run_binance_futures_testnet_read_only.main(["--json"])

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["status"] == "PASS"


def test_strict_safe_config_exits_zero(tmp_path, capsys, monkeypatch) -> None:
    _write_read_only_configs(tmp_path)
    monkeypatch.setattr(run_binance_futures_testnet_read_only, "ROOT_DIR", tmp_path)

    code = run_binance_futures_testnet_read_only.main(["--strict"])

    capsys.readouterr()
    assert code == 0


def test_fetch_account_requires_confirmation_without_inspecting_credentials(tmp_path, capsys, monkeypatch) -> None:
    _write_read_only_configs(tmp_path)
    monkeypatch.setattr(run_binance_futures_testnet_read_only, "ROOT_DIR", tmp_path)

    code = run_binance_futures_testnet_read_only.main(["--fetch-account"])

    captured = capsys.readouterr()
    assert code == 0
    assert "NETWORK_CONFIRMATION_REQUIRED" in captured.out
    assert "Credentials Inspected        : false" in captured.out


def test_action_clis_work_with_fake_engine(capsys, monkeypatch) -> None:
    monkeypatch.setattr(run_binance_futures_testnet_read_only, "BinanceFuturesTestnetReadOnlyEngine", _FakeEngine)

    for argv, expected in (
        (["--check-credentials"], "CREDENTIALS_NOT_CONFIGURED"),
        (["--fetch-account", "--confirm-testnet-read-only", "CONFIRM_TESTNET_READ_ONLY"], "ACCOUNT_READ_SUCCESS"),
        (["--fetch-balance", "--asset", "USDT", "--confirm-testnet-read-only", "CONFIRM_TESTNET_READ_ONLY"], "BALANCE_READ_SUCCESS"),
        (["--fetch-position-risk", "--symbol", "BTCUSDT", "--confirm-testnet-read-only", "CONFIRM_TESTNET_READ_ONLY"], "POSITION_READ_SUCCESS"),
        (["--fetch-account-snapshot", "--confirm-testnet-read-only", "CONFIRM_TESTNET_READ_ONLY"], "ACCOUNT_SNAPSHOT_SUCCESS"),
    ):
        code = run_binance_futures_testnet_read_only.main(argv)
        captured = capsys.readouterr()
        assert code == 0
        assert expected in captured.out


def test_exports_do_not_contain_secret_strings(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(run_binance_futures_testnet_read_only, "BinanceFuturesTestnetReadOnlyEngine", _FakeEngine)
    json_path = tmp_path / "read-only.json"
    md_path = tmp_path / "read-only.md"

    code = run_binance_futures_testnet_read_only.main(["--fetch-account", "--confirm-testnet-read-only", "CONFIRM_TESTNET_READ_ONLY", "--export-json", str(json_path), "--export-md", str(md_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert "[binance-futures-testnet-read-only] wrote" in captured.out
    assert json_path.exists()
    assert md_path.exists()
    assert "unit-test-private-token" not in json_path.read_text(encoding="utf-8")
    assert "unit-test-key-token" not in json_path.read_text(encoding="utf-8")
    assert "signature=" not in md_path.read_text(encoding="utf-8")
