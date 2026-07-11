from __future__ import annotations

import json
from pathlib import Path

from models.binance_futures_testnet_adapter import BinanceFuturesTestnetAdapterResult
from models.binance_futures_testnet_read_only import BinanceFuturesTestnetReadOnlyResult
from models.btc_live_market_feed import BTCLiveMarketObservationResult
from models.btc_futures_read_only_feed import (
    BTCFuturesReadOnlyFeedStatus,
    BTCFuturesReadOnlyObservationDecision,
    BTCFuturesReadOnlyObservationResult,
)
from models.btc_futures_risk_model import BTCFuturesRiskResult
from models.btc_futures_paper_position import BTCFuturesPaperActionResult
from models.btc_paper_account import (
    BTCPaperAccountAction,
    BTCPaperAccountActionResult,
    BTCPaperAccountDecision,
    BTCPaperAccountStatus,
)
from scripts import run_btc_paper_runner

from tests.test_btc_forward_test_loop_engine import _write_forward_configs
from tests.test_btc_live_market_feed_engine import _write_live_configs
from tests.test_btc_paper_runner_engine import _write_configs
from tests.test_btc_paper_candidate_journal_engine import _write_journal_configs
from tests.test_btc_paper_signal_evaluation_engine import _write_configs as _write_signal_configs
from tests.test_btc_paper_trade_candidate_engine import _write_trade_candidate_configs


class _FakeLiveMarketFeedEngine:
    def __init__(self, repo_root=None) -> None:
        self.repo_root = repo_root

    def observe_once(self, expected_profile: str = "balanced_smc_decision_065", **kwargs) -> BTCLiveMarketObservationResult:
        return BTCLiveMarketObservationResult(status="PASS", decision="FEED_OK_SIGNAL_APPROVED", public_market_data_fetch_used=True)


class _FakePaperAccountEngine:
    def __init__(self, repo_root=None) -> None:
        self.repo_root = repo_root

    def simulate_live_observation(self, **kwargs) -> BTCPaperAccountActionResult:
        return BTCPaperAccountActionResult(
            action=BTCPaperAccountAction.SIMULATE_LIVE_OBSERVATION.value,
            status=BTCPaperAccountStatus.PASS.value,
            decision=BTCPaperAccountDecision.NO_ACTION_NO_CANDIDATE.value,
            safety_summary={"real_order_submitted": False, "trading_api_used": False, "runner_state_mutated": False},
            no_action_recorded=True,
        )


class _FakeFuturesReadOnlyFeedEngine:
    def __init__(self, repo_root=None) -> None:
        self.repo_root = repo_root

    def observe_once(self, expected_profile: str = "balanced_smc_decision_065", **kwargs) -> BTCFuturesReadOnlyObservationResult:
        return BTCFuturesReadOnlyObservationResult(
            status=BTCFuturesReadOnlyFeedStatus.PASS.value,
            decision=BTCFuturesReadOnlyObservationDecision.FUTURES_FEED_OK_FUNDING_AVAILABLE.value,
            feed_status=BTCFuturesReadOnlyFeedStatus.PASS.value,
            public_futures_market_data_fetch_used=True,
            private_api_used=False,
            order_submitted=False,
            leverage_used=False,
            metadata={
                "leverage_model_available": False,
                "liquidation_model_available": False,
                "paper_futures_position_created": False,
                "futures_trade_pipeline_invoked": False,
            },
        )


class _FakeFuturesRiskModelEngine:
    def __init__(self, repo_root=None) -> None:
        self.repo_root = repo_root

    def analyze_live(self, expected_profile: str = "balanced_smc_decision_065", **kwargs) -> BTCFuturesRiskResult:
        return BTCFuturesRiskResult(
            status="PASS",
            decision="SAFE_SIMULATION",
            reason="Approximate conservative diagnostic only.",
            exchange_exact_liquidation=False,
            private_api_used=False,
            order_submitted=False,
            paper_futures_position_created=False,
            exchange_leverage_changed=False,
            runner_state_mutated=False,
        )


class _FakeFuturesPaperPositionEngine:
    def __init__(self, repo_root=None) -> None:
        self.repo_root = repo_root

    def simulate_lifecycle(self, expected_profile: str = "balanced_smc_decision_065", **kwargs) -> BTCFuturesPaperActionResult:
        return BTCFuturesPaperActionResult(
            action="SIMULATE_LIFECYCLE",
            status="PASS",
            decision="POSITION_CLOSED_MANUAL",
            reason="Fake lifecycle completed.",
            state_written=False,
            ledger_written=False,
            private_api_used=False,
            real_order_submitted=False,
            real_position_created=False,
            spot_paper_account_state_mutated=False,
            runner_state_mutated=False,
            execution_state_mutated=False,
            exchange_state_mutated=False,
            metadata={"persistent_state_used": False},
        )


class _FakeBinanceFuturesTestnetAdapterEngine:
    def __init__(self, repo_root=None, env=None) -> None:
        self.repo_root = repo_root
        self.env = env

    def build_order_intent(self, **kwargs) -> BinanceFuturesTestnetAdapterResult:
        return BinanceFuturesTestnetAdapterResult(
            action="BUILD_ORDER_INTENT",
            status="PASS",
            decision="ORDER_INTENT_VALID",
            reason="Fake local non-executable intent built.",
            payload={
                "intent_id": kwargs["intent_id"],
                "executable": False,
                "request_signed": False,
                "request_transmitted": False,
                "testnet_order_submitted": False,
                "futures_paper_state_mutated": False,
            },
            request_signed=False,
            request_transmitted=False,
            testnet_order_submitted=False,
            futures_paper_state_mutated=False,
            spot_paper_account_state_mutated=False,
            runner_state_mutated=False,
            execution_state_mutated=False,
            exchange_state_mutated=False,
        )


class _FakeBinanceFuturesTestnetReadOnlyEngine:
    def __init__(self, repo_root=None, env=None) -> None:
        self.repo_root = repo_root
        self.env = env

    def runner_validate(self, **kwargs) -> BinanceFuturesTestnetReadOnlyResult:
        return BinanceFuturesTestnetReadOnlyResult(
            action="RUNNER_VALIDATE",
            status="PASS",
            decision="CONFIG_VALID",
            reason="Fake read-only validation completed.",
            credentials_inspected=False,
            authenticated_transport_invoked=False,
            request_transmitted=False,
            order_submitted=False,
            futures_paper_state_mutated=False,
            runner_state_mutated=False,
            execution_state_mutated=False,
            exchange_state_mutated=False,
        )


def test_status_works_without_state_file(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)

    code = run_btc_paper_runner.main(["--status"])

    captured = capsys.readouterr()
    assert code == 0
    assert "BTC PAPER RUNNER DRY-RUN STATUS" in captured.out
    assert not (tmp_path / "reports" / "paper_runner" / "btc_paper_runner_state.json").exists()


def test_start_prints_no_execution_message_and_writes_state(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)

    code = run_btc_paper_runner.main(["--start", "--state-file", "reports/paper_runner/state.json"])

    captured = capsys.readouterr()
    assert code == 0
    assert "No signals, trades, orders, or exchange connections were executed" in captured.out
    assert json.loads((tmp_path / "reports" / "paper_runner" / "state.json").read_text(encoding="utf-8"))["state"] == "RUNNING"


def test_json_prints_serializable_result(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)

    code = run_btc_paper_runner.main(["--start", "--json"])

    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["current_state"] == "RUNNING"


def test_exports_json_and_markdown(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)
    json_path = tmp_path / "runner.json"
    md_path = tmp_path / "runner.md"

    code = run_btc_paper_runner.main(["--status", "--export-json", str(json_path), "--export-md", str(md_path)])

    captured = capsys.readouterr()
    assert code == 0
    assert "[btc-paper-runner] wrote" in captured.out
    assert json_path.exists()
    assert md_path.exists()


def test_pause_from_ready_exits_one(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)

    code = run_btc_paper_runner.main(["--pause"])

    capsys.readouterr()
    assert code == 1


def test_evaluate_signal_dry_run_does_not_mutate_state(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    _write_signal_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)
    state_path = tmp_path / "reports" / "paper_runner" / "state.json"
    run_btc_paper_runner.main(["--initialize", "--state-file", "reports/paper_runner/state.json"])
    before = json.loads(state_path.read_text(encoding="utf-8"))

    code = run_btc_paper_runner.main(["--evaluate-signal-dry-run", "--state-file", "reports/paper_runner/state.json"])

    captured = capsys.readouterr()
    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert code == 0
    assert before == after
    assert "BTC PAPER SIGNAL EVALUATION DRY-RUN" in captured.out
    assert "No signals, trades, orders, or exchange connections were executed" in captured.out


def test_simulate_trade_candidate_dry_run_does_not_mutate_state(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    _write_signal_configs(tmp_path)
    _write_trade_candidate_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)
    state_path = tmp_path / "reports" / "paper_runner" / "state.json"
    run_btc_paper_runner.main(["--initialize", "--state-file", "reports/paper_runner/state.json"])
    before = json.loads(state_path.read_text(encoding="utf-8"))

    code = run_btc_paper_runner.main(["--simulate-trade-candidate-dry-run", "--state-file", "reports/paper_runner/state.json"])

    captured = capsys.readouterr()
    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert code == 0
    assert before == after
    assert "BTC PAPER TRADE CANDIDATE DRY-RUN" in captured.out
    assert "Order Submitted     : false" in captured.out


def test_simulate_and_journal_candidate_dry_run_does_not_mutate_state(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    _write_signal_configs(tmp_path)
    _write_trade_candidate_configs(tmp_path)
    _write_journal_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)
    state_path = tmp_path / "reports" / "paper_runner" / "state.json"
    run_btc_paper_runner.main(["--initialize", "--state-file", "reports/paper_runner/state.json"])
    before = json.loads(state_path.read_text(encoding="utf-8"))

    code = run_btc_paper_runner.main(["--simulate-and-journal-candidate-dry-run", "--state-file", "reports/paper_runner/state.json"])

    captured = capsys.readouterr()
    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert code == 0
    assert before == after
    assert "BTC PAPER CANDIDATE JOURNAL DRY-RUN RECORD" in captured.out
    assert "Order Submitted     : false" in captured.out


def test_run_forward_test_dry_run_does_not_mutate_runner_state(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    _write_forward_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)
    state_path = tmp_path / "reports" / "paper_runner" / "state.json"
    run_btc_paper_runner.main(["--initialize", "--state-file", "reports/paper_runner/state.json"])
    before = json.loads(state_path.read_text(encoding="utf-8"))

    code = run_btc_paper_runner.main(["--run-forward-test-dry-run", "--state-file", "reports/paper_runner/state.json"])

    captured = capsys.readouterr()
    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert code == 0
    assert before == after
    assert "BTC FORWARD TEST LOOP DRY-RUN" in captured.out
    assert "Order Submitted     : false" in captured.out


def test_observe_live_market_read_only_dry_run_does_not_mutate_runner_state(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    _write_live_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "BTCLiveMarketFeedEngine", _FakeLiveMarketFeedEngine)
    state_path = tmp_path / "reports" / "paper_runner" / "state.json"
    run_btc_paper_runner.main(["--initialize", "--state-file", "reports/paper_runner/state.json"])
    before = json.loads(state_path.read_text(encoding="utf-8"))

    code = run_btc_paper_runner.main(["--observe-live-market-read-only-dry-run", "--state-file", "reports/paper_runner/state.json"])

    captured = capsys.readouterr()
    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert code == 0
    assert before == after
    assert "BTC LIVE MARKET READ-ONLY OBSERVATION DRY-RUN" in captured.out
    assert "Private API Used    : false" in captured.out
    assert "Order Submitted     : false" in captured.out


def test_simulate_local_paper_account_does_not_mutate_runner_state(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "BTCPaperAccountEngine", _FakePaperAccountEngine)
    state_path = tmp_path / "reports" / "paper_runner" / "state.json"
    run_btc_paper_runner.main(["--initialize", "--state-file", "reports/paper_runner/state.json"])
    before = json.loads(state_path.read_text(encoding="utf-8"))

    code = run_btc_paper_runner.main(["--simulate-local-paper-account", "--state-file", "reports/paper_runner/state.json"])

    captured = capsys.readouterr()
    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert code == 0
    assert before == after
    assert "BTC LOCAL PAPER ACCOUNT" in captured.out
    assert "Real Order Sent    : false" in captured.out


def test_observe_futures_read_only_dry_run_does_not_mutate_runner_state(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "BTCFuturesReadOnlyFeedEngine", _FakeFuturesReadOnlyFeedEngine)
    state_path = tmp_path / "reports" / "paper_runner" / "state.json"
    run_btc_paper_runner.main(["--initialize", "--state-file", "reports/paper_runner/state.json"])
    before = json.loads(state_path.read_text(encoding="utf-8"))

    code = run_btc_paper_runner.main(["--observe-futures-read-only-dry-run", "--state-file", "reports/paper_runner/state.json"])

    captured = capsys.readouterr()
    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert code == 0
    assert before == after
    assert "BTC FUTURES READ-ONLY OBSERVATION DRY-RUN" in captured.out
    assert "Order Submitted     : false" in captured.out
    assert "Leverage Used       : false" in captured.out


def test_analyze_futures_risk_dry_run_does_not_mutate_runner_state(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "BTCFuturesRiskModelEngine", _FakeFuturesRiskModelEngine)
    state_path = tmp_path / "reports" / "paper_runner" / "state.json"
    run_btc_paper_runner.main(["--initialize", "--state-file", "reports/paper_runner/state.json"])
    before = json.loads(state_path.read_text(encoding="utf-8"))

    code = run_btc_paper_runner.main(["--analyze-futures-risk-dry-run", "--state-file", "reports/paper_runner/state.json"])

    captured = capsys.readouterr()
    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert code == 0
    assert before == after
    assert "BTC FUTURES LEVERAGE / LIQUIDATION RISK ANALYSIS" in captured.out
    assert "Exchange Exact       : false" in captured.out
    assert "Order Submitted      : false" in captured.out
    assert "Paper Futures Pos    : false" in captured.out


def test_simulate_futures_paper_position_lifecycle_dry_run_does_not_mutate_runner_state(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "BTCFuturesPaperPositionEngine", _FakeFuturesPaperPositionEngine)
    state_path = tmp_path / "reports" / "paper_runner" / "state.json"
    run_btc_paper_runner.main(["--initialize", "--state-file", "reports/paper_runner/state.json"])
    before = json.loads(state_path.read_text(encoding="utf-8"))

    code = run_btc_paper_runner.main(["--simulate-futures-paper-position-lifecycle-dry-run", "--state-file", "reports/paper_runner/state.json"])

    captured = capsys.readouterr()
    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert code == 0
    assert before == after
    assert "BTC FUTURES LOCAL PAPER POSITION" in captured.out
    assert "Runner is not running; futures paper position lifecycle executed as standalone local dry-run simulation." in captured.out
    assert "State Written           : false" in captured.out
    assert "Ledger Written          : false" in captured.out
    assert "Real Order Submitted    : false" in captured.out
    assert "Spot Account Mutated    : false" in captured.out


def test_validate_binance_futures_testnet_adapter_dry_run_does_not_mutate_runner_state(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "BinanceFuturesTestnetAdapterEngine", _FakeBinanceFuturesTestnetAdapterEngine)
    state_path = tmp_path / "reports" / "paper_runner" / "state.json"
    run_btc_paper_runner.main(["--initialize", "--state-file", "reports/paper_runner/state.json"])
    before = json.loads(state_path.read_text(encoding="utf-8"))

    code = run_btc_paper_runner.main(["--validate-binance-futures-testnet-adapter-dry-run", "--state-file", "reports/paper_runner/state.json"])

    captured = capsys.readouterr()
    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert code == 0
    assert before == after
    assert "BINANCE FUTURES TESTNET ADAPTER DIAGNOSTIC" in captured.out
    assert "Runner is not running; Binance futures testnet adapter validation executed as standalone disabled dry-run diagnostic." in captured.out
    assert "Testnet Order Submitted      : false" in captured.out
    assert "Futures Paper State Mutated  : false" in captured.out


def test_validate_binance_futures_testnet_read_only_dry_run_does_not_mutate_runner_state(tmp_path, capsys, monkeypatch) -> None:
    _write_configs(tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(run_btc_paper_runner, "BinanceFuturesTestnetReadOnlyEngine", _FakeBinanceFuturesTestnetReadOnlyEngine)
    state_path = tmp_path / "reports" / "paper_runner" / "state.json"
    run_btc_paper_runner.main(["--initialize", "--state-file", "reports/paper_runner/state.json"])
    before = json.loads(state_path.read_text(encoding="utf-8"))

    code = run_btc_paper_runner.main(["--validate-binance-futures-testnet-read-only-dry-run", "--state-file", "reports/paper_runner/state.json"])

    captured = capsys.readouterr()
    after = json.loads(state_path.read_text(encoding="utf-8"))
    assert code == 0
    assert before == after
    assert "BINANCE FUTURES TESTNET READ-ONLY DIAGNOSTIC" in captured.out
    assert "Runner is not running; Binance futures testnet read-only validation executed as standalone explicit-only dry-run diagnostic." in captured.out
    assert "Credentials Inspected        : false" in captured.out
    assert "Authenticated Transport      : false" in captured.out
    assert "Order Submitted              : false" in captured.out
    assert "Futures Paper State Mutated  : false" in captured.out
