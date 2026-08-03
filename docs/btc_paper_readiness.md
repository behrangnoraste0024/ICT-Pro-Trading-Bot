# BTC Paper Trading Readiness

This diagnostic answers whether the current BTC-focused research, backtest, and validation stack is ready to move into paper trading preparation.

It does not execute trades, place orders, enable live trading, or activate paper execution. It only reads local registry, baseline, snapshot, and safety signals.

## Binance Futures Testnet Manual Lifecycle

Release 2.80 adds a manual Binance USD-M Futures Testnet post-only LIMIT lifecycle readiness check. This is the first release that can create an actual Testnet exchange order, but only through the standalone lifecycle CLI with explicit confirmation. It is Testnet-only, BTCUSDT-only, LIMIT-only, GTX post-only, one order per lifecycle, and disabled by default.

The lifecycle has no standalone create-only action. A confirmed lifecycle derives a deliberately non-marketable price from the BTCUSDT book ticker, requires One-way Mode, verifies zero BTCUSDT position before creation, creates exactly one LIMIT GTX order, queries it, immediately cancels it if still `NEW`, queries final status, verifies zero position again, and writes only a sanitized local journal. After Release 2.93, lifecycle create also requires `--create-permit-id` and `--create-permit-version`; lifecycle cancel requires `--cancel-permit-id` and `--cancel-permit-version`.

MARKET orders, stop loss, take profit, algo orders, leverage changes, margin changes, position-mode changes, production endpoints, strategy execution, runner order submission, and paper-state mutation remain forbidden. If network state is uncertain after create or cancel, use the exact-order query and exact-order recovery-cancel commands with the known client order ID. Do not run the real authenticated lifecycle from Codex; use dedicated Testnet credentials only in an operator-controlled shell.

## Release 2.93 Authenticated Mutation Prerequisites

### Canonical Safety Contract

The detailed Release 2.93 mutation-safety contract is maintained in [validation_gate_runbook.md](validation_gate_runbook.md), section `Release 2.93 One-Time Permit Mutation Enforcement`. This BTC readiness document summarizes the operator prerequisites only; it does not replace the canonical runbook.

Binance Futures authenticated mutation remains Binance Futures Testnet/Demo only, BTCUSDT only, Production disabled, and supervised/manual only. A signal, Dashboard action, CLI confirmation phrase, or operator intent is not mutation authorization.

### Phase C Supervised-Mutation Status Preflight

The canonical read-only status procedure is maintained in [validation_gate_runbook.md](validation_gate_runbook.md), section `Phase C Read-Only Status Preflight`. Before preparing any separately authorized supervised mutation, the operator must use HTTP GET only:

```text
GET <CONTROL_PLANE_BASE_URL>/api/v1/live/kill-switch/status
GET <CONTROL_PLANE_BASE_URL>/api/v1/live/recovery/status
```

The durable kill-switch status must report `state == "RELEASED"`. The recovery status must report `required == false`. The decision must fail closed: any `ENGAGED`, unavailable, malformed, ambiguous, failed, or untrusted result is `BLOCKED` and must not be interpreted as safe. `GET /api/v1/live/recovery/status` is the status check; `POST /api/v1/live/recovery/run` is a recovery action and is not part of pre-execution status verification.

These checks are necessary but not sufficient. They do not issue, consume, or authorize a one-time permit; they do not replace the separate permit requirement; they do not replace the exact operator confirmation required by the selected scenario; and they do not broaden the Testnet/Demo-only, BTCUSDT-only scope. This document update does not authorize Demo/Testnet execution.

### Phase C Signed Order-Test Runbook Gate

The canonical documentation-only procedure is maintained in [validation_gate_runbook.md](validation_gate_runbook.md), section `Phase C Signed Order-Test Supervised Execution Runbook`. This readiness document does not authorize execution.

Before any future Signed Order-Test, the operator must obtain separate approval for one exact attempt only. The scenario must remain Binance Futures Testnet/Demo only, BTCUSDT only, and Production disabled. Both read-only status checks are required: `GET /api/v1/live/kill-switch/status` must report `state == "RELEASED"`, and `GET /api/v1/live/recovery/status` must report `required == false`; every unavailable, malformed, ambiguous, failed, or untrusted result is blocked.

The approved preview, request JSON, and fingerprint must be frozen before permit issuance. The one-time permit must exactly match `SIGNED_ORDER_TEST_CREATE`, the frozen request, the permit ID, and the exact permit version. The submit confirmation must be exactly `CONFIRM_TESTNET_ORDER_TEST`. One command, one process, one attempt, and POST retry zero are mandatory. Testnet credentials must be removed immediately after the attempt or abort. A complete sanitized evidence package is required. Passing readiness does not authorize execution.
### Permit Requirements by Mutation Path

Lifecycle Create:

```text
--create-permit-id
--create-permit-version
```

Lifecycle Cancel:

```text
--cancel-permit-id
--cancel-permit-version
```

Signed Order-Test:

```text
--permit-id
--permit-version
```

Protective Create:

```text
--stop-create-permit-id
--stop-create-permit-version
--take-profit-create-permit-id
--take-profit-create-permit-version
```

Protective Cancel:

```text
--stop-cancel-permit-id
--stop-cancel-permit-version
--take-profit-cancel-permit-id
--take-profit-cancel-permit-version
```

### Mutation Safety Summary

Permits are exact and one-time. The permit must match the environment, symbol, operation, subject, and mutation fingerprint. Mutation commands do not auto-issue permits. There is no automatic renewal, refund, replacement, or reuse. Permit consumption, persistence commit, and persistence close happen before signing and authenticated transport.

POST retry is zero. DELETE retry is zero. Blind mutation retry is not allowed. Uncertainty uses exact read-only reconciliation for the persisted mutation identity.

### Operator Response to Denial or Uncertainty

Pre-consume denial remains failed-safe and must not create false recovery. Post-consume uncertainty remains recovery-required, and the consumed permit remains consumed. Restart recovery must be idempotent. Operators must follow the canonical runbook instead of issuing a second mutation blindly.
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

# BTC Futures Read-Only Market Feed

Release 2.74 adds one-shot public BTCUSDT futures market-data diagnostics. It may fetch public futures candles, mark price, and funding metadata when explicitly requested, but it does not use API keys, private futures endpoints, account data, balances, positions, order endpoints, leverage, liquidation modeling, executable trades, paper futures positions, or runner state mutation.

Commands:

```powershell
py scripts/run_btc_futures_read_only_feed.py
py scripts/run_btc_futures_read_only_feed.py --json
py scripts/run_btc_futures_read_only_feed.py --strict
py scripts/run_btc_futures_read_only_feed.py --fetch-once
py scripts/run_btc_futures_read_only_feed.py --fetch-once --json
py scripts/run_btc_futures_read_only_feed.py --observe-once
py scripts/run_btc_futures_read_only_feed.py --observe-once --json
py scripts/run_btc_paper_runner.py --observe-futures-read-only-dry-run
```

This uses public futures market data only. Network failures should fail safely and do not indicate trading risk. Futures leverage and liquidation modeling are intentionally not modeled yet and remain later-release work. Generated futures-feed reports stay local under `reports/futures_read_only_feed` and are ignored by Git.

# BTC Futures Leverage + Liquidation Risk Model

Release 2.75 adds approximate conservative BTCUSDT USDT-margined perpetual futures risk diagnostics. It calculates hypothetical isolated-margin leverage, margin, liquidation distance, stop-loss safety, and funding estimates locally. It is not an exact Binance liquidation price and does not model exchange maintenance margin tiers, cross margin, leverage brackets, ADL, liquidation fees, or portfolio margin.

Commands:

```powershell
py scripts/run_btc_futures_risk_model.py
py scripts/run_btc_futures_risk_model.py --json
py scripts/run_btc_futures_risk_model.py --strict

py scripts/run_btc_futures_risk_model.py `
  --analyze-scenario `
  --side LONG `
  --entry-price 64000 `
  --mark-price 63800 `
  --stop-loss 62000 `
  --take-profit 67000 `
  --notional 1000 `
  --account-equity 10000 `
  --leverage 3 `
  --funding-rate 0.0001

py scripts/run_btc_futures_risk_model.py `
  --analyze-live `
  --side LONG `
  --stop-loss 62000 `
  --take-profit 67000 `
  --notional 1000 `
  --account-equity 10000 `
  --leverage 3

py scripts/run_btc_futures_risk_model.py `
  --compare-leverage `
  --side LONG `
  --entry-price 64000 `
  --mark-price 63800 `
  --stop-loss 62000 `
  --take-profit 67000 `
  --notional 1000 `
  --account-equity 10000

py scripts/run_btc_paper_runner.py --analyze-futures-risk-dry-run
```

This is a calculation layer only. It does not create real or paper futures positions, change exchange leverage, change margin mode, submit or cancel orders, use private APIs, fetch account data, mutate the paper account, or mutate runner/execution state. Funding is an estimate.

# BTC Futures Local Paper Position Simulation

Release 2.76 adds a local-only BTCUSDT futures paper position simulator. A paper futures position is a local JSON state file, a local virtual position object, and an append-only local JSONL ledger. It is separate from the Release 2.73 spot paper account and does not mutate the spot paper account.

The simulator does not use API keys, private APIs, exchange account data, exchange balances, exchange positions, exchange leverage changes, exchange margin-mode changes, real orders, testnet orders, external paper positions, runner state mutation, or execution state mutation. Local state and ledger writes happen only through explicit CLI actions. Liquidation remains approximate and conservative through the Release 2.75 model. Live mark/funding updates use public read-only futures data only and fail safely without local mutation on fetch failure.

Commands:

```powershell
py scripts/run_btc_futures_paper_position.py
py scripts/run_btc_futures_paper_position.py --json
py scripts/run_btc_futures_paper_position.py --strict
py scripts/run_btc_futures_paper_position.py --status
py scripts/run_btc_futures_paper_position.py --initialize

py scripts/run_btc_futures_paper_position.py `
  --open-position `
  --side LONG `
  --entry-price 64000 `
  --mark-price 64000 `
  --stop-loss 62000 `
  --take-profit 67000 `
  --notional 1000 `
  --leverage 3 `
  --action-id open-001

py scripts/run_btc_futures_paper_position.py --mark-to-market --mark-price 65000 --action-id mark-001
py scripts/run_btc_futures_paper_position.py --apply-funding --funding-rate 0.0001 --funding-periods 1 --action-id funding-001
py scripts/run_btc_futures_paper_position.py --close-position --close-price 66000 --close-reason MANUAL --action-id close-001
py scripts/run_btc_futures_paper_position.py --ledger-summary
py scripts/run_btc_futures_paper_position.py --reset --force
py scripts/run_btc_futures_paper_position.py --simulate-lifecycle
py scripts/run_btc_paper_runner.py --simulate-futures-paper-position-lifecycle-dry-run
```

The runner integration is in-memory only and does not persist futures state or ledger entries. A future release may introduce a disabled-by-default Binance Futures Testnet adapter, but Release 2.76 does not.

# Binance Futures Testnet Adapter - Disabled by Default

Release 2.77 adds a disabled-by-default Binance USD-M Futures Testnet adapter boundary. Only the exact public testnet host `https://demo-fapi.binance.com` is allowed. Production endpoints are blocked, and the adapter does not fall back to any alternate Binance host.

Commands:

```powershell
py scripts/run_binance_futures_testnet_adapter.py
py scripts/run_binance_futures_testnet_adapter.py --json
py scripts/run_binance_futures_testnet_adapter.py --strict
py scripts/run_binance_futures_testnet_adapter.py --ping-testnet
py scripts/run_binance_futures_testnet_adapter.py --fetch-server-time
py scripts/run_binance_futures_testnet_adapter.py --fetch-exchange-info
py scripts/run_binance_futures_testnet_adapter.py --check-credentials
py scripts/run_binance_futures_testnet_adapter.py --signed-request-preview --preview-path /fapi/v2/account
py scripts/run_binance_futures_testnet_adapter.py --build-order-intent --intent-id testnet-intent-001 --side BUY --order-type MARKET --quantity 0.001
py scripts/run_btc_paper_runner.py --validate-binance-futures-testnet-adapter-dry-run
```

Public diagnostics do not use credentials. Credential checks inspect only `BINANCE_FUTURES_TESTNET_API_KEY` and `BINANCE_FUTURES_TESTNET_API_SECRET`, returning presence and length metadata only. Signing previews are local-only, redacted, and never transmitted. Order intents are non-executable local data objects.

Release 2.77 does not submit or cancel testnet orders, fetch account/balance/position data, change leverage, change margin mode, create exchange positions, open a user-data stream, start a WebSocket, mutate Release 2.76 futures paper state, mutate the spot paper account, mutate runner/execution state, or mutate exchange state. Credentials, signatures, request headers, signed URLs, generated reports, and `.env` files must never be committed. A later release may add separately gated authenticated testnet read-only access.

# Binance Futures Testnet Authenticated Read-Only Account Snapshot

Release 2.78 adds the first explicitly confirmed authenticated Binance USD-M Futures Testnet read-only diagnostics. This is not trading activation. The layer is explicit CLI only, GET only, exact testnet host only, and limited to `/fapi/v3/account`, `/fapi/v3/balance`, and `/fapi/v3/positionRisk` for BTCUSDT.

Commands:

```powershell
py scripts/run_binance_futures_testnet_read_only.py
py scripts/run_binance_futures_testnet_read_only.py --json
py scripts/run_binance_futures_testnet_read_only.py --strict
py scripts/run_binance_futures_testnet_read_only.py --check-credentials

py scripts/run_binance_futures_testnet_read_only.py --fetch-account --confirm-testnet-read-only CONFIRM_TESTNET_READ_ONLY
py scripts/run_binance_futures_testnet_read_only.py --fetch-balance --asset USDT --confirm-testnet-read-only CONFIRM_TESTNET_READ_ONLY
py scripts/run_binance_futures_testnet_read_only.py --fetch-position-risk --symbol BTCUSDT --confirm-testnet-read-only CONFIRM_TESTNET_READ_ONLY
py scripts/run_binance_futures_testnet_read_only.py --fetch-account-snapshot --confirm-testnet-read-only CONFIRM_TESTNET_READ_ONLY

py scripts/run_btc_paper_runner.py --validate-binance-futures-testnet-read-only-dry-run
```

Readiness and runner validation do not inspect credentials and do not use network. Authenticated reads require the confirmation phrase `CONFIRM_TESTNET_READ_ONLY` and dedicated testnet variables `BINANCE_FUTURES_TESTNET_API_KEY` and `BINANCE_FUTURES_TESTNET_API_SECRET`. The API key is transmitted only as `X-MBX-APIKEY` during confirmed read-only GET actions. The API secret is used locally for HMAC SHA256 signing and is never transmitted.

No API key, API secret, full signature, signed URL, authenticated headers, or raw authenticated responses are printed or persisted. No orders, test orders, cancellations, order/trade history, leverage changes, margin changes, position creation/closing, streams, WebSockets, production access, or local paper-state mutation are allowed. Future releases may add separately gated Testnet order simulation, but Release 2.78 does not.

# Binance Futures Testnet Test Order Preflight

Release 2.79 adds an explicitly confirmed Binance USD-M Futures Testnet Test Order preflight. This is still diagnostics only. The only authenticated trade-related endpoint allowed is `POST /fapi/v1/order/test`, which validates hypothetical parameters without creating a matching-engine order, exchange order ID, position, balance mutation, or local paper state mutation.

Commands:

```powershell
py scripts/run_binance_futures_testnet_order_test.py
py scripts/run_binance_futures_testnet_order_test.py --json
py scripts/run_binance_futures_testnet_order_test.py --strict
py scripts/run_binance_futures_testnet_order_test.py --check-credentials
py scripts/run_binance_futures_testnet_order_test.py --build-preview --client-order-id smcbot-test-market-001 --side BUY --order-type MARKET --quantity 0.001
py scripts/run_binance_futures_testnet_order_test.py --build-preview --client-order-id smcbot-test-limit-001 --side BUY --order-type LIMIT --quantity 0.001 --price 50000 --time-in-force GTC
py scripts/run_binance_futures_testnet_order_test.py --submit-test-order --client-order-id smcbot-test-market-002 --side BUY --order-type MARKET --quantity 0.001
py scripts/run_binance_futures_testnet_order_test.py --submit-test-order --client-order-id smcbot-test-market-003 --side BUY --order-type MARKET --quantity 0.001 --confirm-testnet-order-test CONFIRM_TESTNET_ORDER_TEST
py scripts/run_btc_paper_runner.py --validate-binance-futures-testnet-order-test-dry-run
```

Readiness and runner validation build a local MARKET preview only. They do not inspect credentials, fetch server time, fetch exchange info, generate a signature, transmit a Test Order request, or mutate runner, paper, execution, or exchange state.

An authenticated Test Order request requires the exact phrase `CONFIRM_TESTNET_ORDER_TEST`, the one-time permit flags `--permit-id` and `--permit-version`, and the dedicated variables `BINANCE_FUTURES_TESTNET_API_KEY` and `BINANCE_FUTURES_TESTNET_API_SECRET`. The actual order endpoint `POST /fapi/v1/order`, cancellation, modification, order/trade queries, conditional/algo orders, leverage or margin changes, user streams, WebSockets, production endpoints, and raw request/response persistence remain forbidden.
