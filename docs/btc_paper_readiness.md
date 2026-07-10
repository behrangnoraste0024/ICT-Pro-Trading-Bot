# BTC Paper Trading Readiness

This diagnostic answers whether the current BTC-focused research, backtest, and validation stack is ready to move into paper trading preparation.

It does not execute trades, place orders, enable live trading, or activate paper execution. It only reads local registry, baseline, snapshot, and safety signals.

## Commands

Official BTC validation gate:

```powershell
py scripts/run_validation_gate.py --preset full
```

Readiness diagnostic:

```powershell
py scripts/run_btc_paper_readiness.py
```

Strict readiness:

```powershell
py scripts/run_btc_paper_readiness.py --strict
```

Gate-backed readiness:

```powershell
py scripts/run_btc_paper_readiness.py --run-gate --use-cache --cache-dir .cache/backtests
```

JSON output:

```powershell
py scripts/run_btc_paper_readiness.py --json
```

## BTC Paper Runtime Config / Risk Guardrails

Validate the tracked BTC paper runtime config:

```powershell
py scripts/validate_btc_paper_runtime_config.py
```

Print JSON:

```powershell
py scripts/validate_btc_paper_runtime_config.py --json
```

Strict validation:

```powershell
py scripts/validate_btc_paper_runtime_config.py --strict
```

The runtime config is tracked at `configs/btc_paper_runtime.json`. It is safe by default:

- live trading remains disabled
- order submission remains disabled
- paper execution remains disabled until a later release
- dry-run remains enabled
- kill switch remains enabled
- BTC risk limits are validated before any runner is introduced

Release 2.65 makes `risk_runtime_config` pass when this config is present and valid. `paper_monitoring` is still expected to warn until a later telemetry/runner release.

## Status

- `READY`: all required checks pass and no required/recommended warnings remain.
- `WARNING`: required checks pass, but recommended preparation work remains.
- `BLOCKED`: at least one required check failed.

## Scope

The current project phase is BTC-first. The official full gate uses BTC required-full samples: BTC/USDT 15m and BTC/USDT 1h. ETH samples remain optional stress-test data and do not block BTC paper readiness unless an all-samples validation snapshot is deliberately used.

Before any real paper execution work, keep the BTC paper runtime config safe and add dry-run monitoring/telemetry. This readiness tool is pre-paper diagnostics only.

# BTC Paper Monitoring / Telemetry Readiness

Release 2.66 adds pre-runner monitoring readiness. It does not execute trades, start a runner, submit orders, connect to an exchange, or enable live trading. Paper execution, live trading, and order submission remain disabled.

Commands:

```powershell
py scripts/validate_btc_paper_monitoring.py
py scripts/validate_btc_paper_monitoring.py --json
py scripts/validate_btc_paper_monitoring.py --strict
py scripts/validate_btc_paper_monitoring.py --status
py scripts/validate_btc_paper_monitoring.py --status --json
py scripts/run_btc_paper_readiness.py
```

The monitoring status is a pre-runner readiness snapshot. `last_heartbeat_at` and `last_signal_at` are `None` because no paper runner is active yet. A READY monitoring status means the BTC paper monitoring config, heartbeat thresholds, runtime config visibility, validation gate visibility, execution-state visibility, and kill-switch visibility are ready for a later runner release.

Readiness after this release may become READY for BTC paper preparation. It is not approval for paper execution.

# BTC Paper Runner Dry-Run State Machine

Release 2.67 adds a dry-run runner lifecycle state machine. It does not execute trades, start a continuous loop, generate signals, create paper trades, submit orders, connect to an exchange, or read credentials. `--start` means a state transition only.

Commands:

```powershell
py scripts/run_btc_paper_runner.py --status
py scripts/run_btc_paper_runner.py --initialize --state-file reports/paper_runner/btc_paper_runner_state.json
py scripts/run_btc_paper_runner.py --start --state-file reports/paper_runner/btc_paper_runner_state.json
py scripts/run_btc_paper_runner.py --heartbeat --state-file reports/paper_runner/btc_paper_runner_state.json
py scripts/run_btc_paper_runner.py --pause --state-file reports/paper_runner/btc_paper_runner_state.json
py scripts/run_btc_paper_runner.py --resume --state-file reports/paper_runner/btc_paper_runner_state.json
py scripts/run_btc_paper_runner.py --stop --state-file reports/paper_runner/btc_paper_runner_state.json
```

Generated runner state files under `reports/paper_runner` are local and ignored by Git. This release prepares lifecycle visibility only.

# BTC Paper Signal Evaluation Dry-Run

Release 2.68 adds one-shot local fixture signal evaluation. It does not execute trades, create paper trades, submit orders, connect to an exchange, mutate runner state, or start a continuous loop.

Commands:

```powershell
py scripts/run_btc_paper_signal_evaluation.py
py scripts/run_btc_paper_signal_evaluation.py --json
py scripts/run_btc_paper_signal_evaluation.py --strict
py scripts/run_btc_paper_signal_evaluation.py --evaluate
py scripts/run_btc_paper_signal_evaluation.py --evaluate --json
py scripts/run_btc_paper_runner.py --evaluate-signal-dry-run
py scripts/run_btc_paper_runner.py --evaluate-signal-dry-run --state-file reports/paper_runner/btc_paper_runner_state.json
```

Generated signal evaluation reports under `reports/paper_signal_evaluation` are local and ignored by Git.

# BTC Paper Trade Candidate Dry-Run

Release 2.69 adds non-executable trade candidate diagnostics. A candidate is a report object only: it does not execute trades, persist paper trades, open positions, submit orders, connect to an exchange, or mutate runner state. If the dry-run signal score is below threshold, `candidate_created=false` is expected.

Commands:

```powershell
py scripts/run_btc_paper_trade_candidate.py
py scripts/run_btc_paper_trade_candidate.py --json
py scripts/run_btc_paper_trade_candidate.py --strict
py scripts/run_btc_paper_trade_candidate.py --simulate
py scripts/run_btc_paper_trade_candidate.py --simulate --json
py scripts/run_btc_paper_runner.py --simulate-trade-candidate-dry-run
py scripts/run_btc_paper_runner.py --simulate-trade-candidate-dry-run --state-file reports/paper_runner/btc_paper_runner_state.json
```

Generated candidate reports under `reports/paper_trade_candidates` are local and ignored by Git.

# BTC Paper Candidate Journal Dry-Run

Release 2.70 adds a local diagnostic audit journal for BTC paper signal/candidate dry-runs. Journal entries are local audit records only: they do not execute trades, persist active paper trades, open positions, submit orders, connect to an exchange, or mutate runner state. Rejected candidates can be recorded too, so `candidate_created=false` is expected when the signal score is below threshold.

Commands:

```powershell
py scripts/run_btc_paper_candidate_journal.py
py scripts/run_btc_paper_candidate_journal.py --json
py scripts/run_btc_paper_candidate_journal.py --strict
py scripts/run_btc_paper_candidate_journal.py --simulate-and-record
py scripts/run_btc_paper_candidate_journal.py --simulate-and-record --json
py scripts/run_btc_paper_candidate_journal.py --summary
py scripts/run_btc_paper_candidate_journal.py --summary --json
py scripts/run_btc_paper_runner.py --simulate-and-journal-candidate-dry-run
py scripts/run_btc_paper_runner.py --simulate-and-journal-candidate-dry-run --state-file reports/paper_runner/btc_paper_runner_state.json
```

Generated journal files under `reports/paper_candidate_journal` are local and ignored by Git.

# BTC Forward Test Loop Dry-Run

Release 2.71 adds a local finite forward-test loop over BTC historical/sample candles. It is a cursor-based dry-run diagnostic only: it does not use live market data, connect to an exchange, execute trades, persist active paper trades, open positions, submit orders, or mutate runner state. It may write local diagnostic journal/state/report files when explicitly requested.

Commands:

```powershell
py scripts/run_btc_forward_test_loop.py
py scripts/run_btc_forward_test_loop.py --json
py scripts/run_btc_forward_test_loop.py --strict
py scripts/run_btc_forward_test_loop.py --run
py scripts/run_btc_forward_test_loop.py --run --cycles 3
py scripts/run_btc_forward_test_loop.py --run --cycles 3 --json
py scripts/run_btc_forward_test_loop.py --run --cycles 3 --state-file reports/forward_test/btc_forward_test_state.json
py scripts/run_btc_forward_test_loop.py --summary --state-file reports/forward_test/btc_forward_test_state.json
py scripts/run_btc_forward_test_loop.py --reset-state --state-file reports/forward_test/btc_forward_test_state.json
py scripts/run_btc_paper_runner.py --run-forward-test-dry-run
```

Rejected candidates are expected when the signal score is below threshold. Generated forward-test files under `reports/forward_test` are local and ignored by Git.

# BTC Live Market Read-Only Feed Dry-Run

Release 2.72 adds a one-shot public BTC market-data observation dry-run. It may fetch public BTC OHLCV candles when explicitly requested, but it does not use API keys, private endpoints, account data, balances, positions, order endpoints, or any trading exchange connection.

Commands:

```powershell
py scripts/run_btc_live_market_feed.py
py scripts/run_btc_live_market_feed.py --json
py scripts/run_btc_live_market_feed.py --strict
py scripts/run_btc_live_market_feed.py --fetch-once
py scripts/run_btc_live_market_feed.py --fetch-once --json
py scripts/run_btc_live_market_feed.py --observe-once
py scripts/run_btc_live_market_feed.py --observe-once --json
py scripts/run_btc_live_market_feed.py --observe-once --no-journal
py scripts/run_btc_paper_runner.py --observe-live-market-read-only-dry-run
```

This uses public read-only market data only. No API keys are used. No private endpoints are used. No account, balance, or position data is fetched. No orders are submitted or cancelled. No positions are opened. No executable trades are created. No active paper trades are persisted. No runner state is mutated.

A rejected candidate is expected when the live-read-only signal score is below threshold. Generated live-feed reports and journals under `reports/live_market_feed` are local and ignored by Git. Network failures should fail safely and do not indicate trading risk.

# BTC Local Paper Account Simulation

Release 2.73 adds a local virtual paper account simulation. It may write local state and ledger files under `reports/paper_account`, but it does not submit orders, cancel orders, use API keys, call private exchange endpoints, fetch real account/balance/position data, create real positions, create executable trades, mutate runner state, or enable runtime paper execution.

Commands:

```powershell
py scripts/run_btc_paper_account.py
py scripts/run_btc_paper_account.py --json
py scripts/run_btc_paper_account.py --strict
py scripts/run_btc_paper_account.py --status
py scripts/run_btc_paper_account.py --initialize
py scripts/run_btc_paper_account.py --simulate-live-observation
py scripts/run_btc_paper_account.py --simulate-live-observation --initialize-if-missing
py scripts/run_btc_paper_account.py --mark-to-market
py scripts/run_btc_paper_account.py --ledger-summary
py scripts/run_btc_paper_account.py --reset --force
py scripts/run_btc_paper_runner.py --simulate-local-paper-account
```

A no-action event is expected when the live signal score is below threshold. If a candidate is approved in the future, this layer may create local virtual orders and local virtual positions only. Generated paper-account state, ledger, and reports are local and ignored by Git.
