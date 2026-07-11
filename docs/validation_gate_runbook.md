# Validation Gate Operator Runbook

## Purpose

The validation gate is research, audit, and CI tooling. It is not live trading approval, and it does not activate decision thresholds in live or paper trading. Use it to produce repeatable validation artifacts, compare a candidate snapshot against the pinned baseline, and decide whether a research change is safe to merge or promote.

## Current Official Profile

- Recommended profile: `balanced_smc_decision_065`
- Decision threshold: `0.65`
- Project validation scope: BTC-first
- Official sample scope: `required_full`
- Baseline config: `configs/validation_baseline.json`
- Baseline history: `configs/validation_baseline_history.json`
- Pinned baseline snapshot: `reports\validation_snapshots\validation_snapshot_20260707T130446Z_0b9a727_balanced_smc_decision_065.json`
- Known BTC/USDT 15m baseline: `PASSED`, 5 trades, 5 wins, 0 losses, NetAfterCost about `+1404.24`, WFStatus `PASS`, MaxDD `0.00`

## Daily Commands

### Quick Smoke Check

```powershell
py scripts/run_validation_gate.py --preset quick
```

Use this for fast local smoke validation. It applies `--max-windows 100`, cache defaults, snapshot export, and the summary badge. It skips baseline comparison by default unless you explicitly provide `--baseline-snapshot` or `--baseline-config`.

This preset is diagnostic only. On current BTC 15m data, `max-windows 100` may produce 0 trades and show a failed sample. That does not mean the official full validation failed. Do not use `quick` as the official regression gate.

### Snapshot Only

```powershell
py scripts/run_validation_gate.py --preset snapshot-only
```

Use this to export the current validation snapshot without comparing to the baseline. It is useful when you need an audit artifact but are not running a regression decision.

### Full Research Gate

```powershell
py scripts/run_validation_gate.py --preset full
```

This is the daily full research validation. It uses the pinned baseline config, enables cache, exports a snapshot, compares to the baseline, exports the comparison, prints the summary badge, shows details, and fails on hard regression according to the existing regression rules.

Equivalent long form:

```powershell
py scripts/run_validation_gate.py --baseline-config configs/validation_baseline.json --fail-on-regression --export-comparison --summary-badge --show-details --use-cache --cache-dir .cache/backtests --sample-scope required_full --snapshot-dir reports/validation_snapshots --snapshot-format both
```

### CI Gate

```powershell
py scripts/run_validation_gate.py --preset ci
```

Use this for CI or research guard automation. It is like `full`, but keeps logs shorter by not enabling `--show-details` by default. It exits `1` on regression `FAIL`. A regression `WARNING` currently exits `0` unless future configuration changes that behavior.

## Reading The Summary Badge

- `Gate Status`: overall gate decision for the run.
- `Regression Status`: baseline comparison result, or `SKIPPED` when no comparison ran.
- `Profile`: recommended profile used by the validation run.
- `Baseline Commit`: commit recorded in the baseline snapshot.
- `Candidate Commit`: commit recorded in the candidate snapshot.
- `Samples`: total, completed, passed, failed, and skipped sample counts.
- `NetAfterCost Delta`: aggregate candidate minus baseline net PnL after costs.
- `MaxDD Delta`: aggregate candidate minus baseline max drawdown.
- `Regression Flags`: number of regression flags raised by comparison.
- `Cache`: cache status and elapsed-time savings for the primary sample when available.
- `Fail On Regression`: whether `--fail-on-regression` was active.

## Snapshot System

Validation snapshots are generated under `reports/validation_snapshots`. JSON and Markdown snapshots are ignored by Git:

- `reports/validation_snapshots/*.json`
- `reports/validation_snapshots/*.md`

Snapshots include metadata, git commit, sample rows, validation status, cache diagnostics, and enough data for regression comparison. Generated snapshots and comparisons should generally not be committed.

## Historical Sample Registry

Check local historical data availability:

```powershell
py scripts/check_historical_samples.py
```

Print the same report as JSON:

```powershell
py scripts/check_historical_samples.py --json
```

The registry lives at `configs/historical_sample_registry.json`. It lists expected validation fixtures, required gate status, and minimum candle counts. Missing optional samples are reported but are not fatal by default. The current full gate uses BTC 15m and BTC 1h; the CI gate uses BTC 15m for speed.

## Validation Sample Scope

The current official validation target is BTC-first. ETH samples remain useful for diagnostics and stress testing, but ETH weakness does not block the official BTC gate unless you deliberately select an all-samples scope.

Official BTC gate:

```powershell
py scripts/run_validation_gate.py --preset full
```

Explicit BTC-only full gate:

```powershell
py scripts/run_validation_gate.py --preset full --sample-scope btc_only
```

CI scope:

```powershell
py scripts/run_validation_gate.py --preset ci
```

Optional multi-asset stress test:

```powershell
py scripts/run_validation_gate.py --preset full --sample-scope all_available
```

Available sample scopes:

- `required_full`: samples marked `required_for_full_gate` in the registry. This is the official full BTC gate and includes BTC 15m plus BTC 1h.
- `required_ci`: samples marked `required_for_ci_gate` in the registry. This keeps CI lighter and currently includes BTC 15m.
- `btc_only`: all registry samples where `symbol` is `BTC/USDT`.
- `all_available`: all registry samples with available local fixture files.
- `all_registry`: every registry sample, including missing optional samples.

Excluded samples are shown as `SKIPPED_OUT_OF_SCOPE` with a reason such as `sample excluded by validation scope required_full`. Snapshot comparison treats those rows as intentionally excluded, so optional ETH rows do not create BTC-gate regressions. Use `all_available` or `all_registry` when you intentionally want optional ETH samples to participate and fail if weak.

To fail when required full-gate data is unavailable:

```powershell
py scripts/check_historical_samples.py --fail-missing-required-full
```

To print the registry report before a gate run without changing preset behavior:

```powershell
py scripts/run_validation_gate.py --preset full --check-samples
```

Plan missing or invalid sample preparation:

```powershell
py scripts/prepare_historical_samples.py
```

Dry-run a local import before writing anything:

```powershell
py scripts/prepare_historical_samples.py --sample btcusdt_1h_1000 --source C:\path\to\btcusdt_1h_1000.json --import-source --dry-run
```

Run the real local import only after reviewing the dry-run:

```powershell
py scripts/prepare_historical_samples.py --sample btcusdt_1h_1000 --source C:\path\to\btcusdt_1h_1000.json --import-source
```

The preparation helper never downloads from the network. It validates local source JSON, checks candle count, refuses overwrite unless `--overwrite` is passed, and copies into the registry fixture path. Historical files under `data/historical/*.json` are local/generated and should not be committed.

## Historical Sample Downloader

Preview missing or invalid samples without network access:

```powershell
py scripts/download_missing_historical_samples.py --dry-run
```

Download missing samples from a public exchange source and write metadata sidecars:

```powershell
py scripts/download_missing_historical_samples.py --exchange binance --write-metadata --validate-after-download
```

Download a single sample:

```powershell
py scripts/download_missing_historical_samples.py --sample ethusdt_15m_1000 --exchange binance --write-metadata --validate-after-download
```

The downloader uses public OHLCV data through `ccxt.fetch_ohlcv`; it does not use API keys. Real downloads require project dependencies with `ccxt` installed. Dry-runs do not require `ccxt` and do not call the network. Historical data files and sidecar files under `data/historical/*.json` and `data/historical/*.metadata.json` are local/generated and must not be committed. Run `py scripts/check_historical_samples.py` after downloads to verify readiness.

## Baseline Pinning

Inspect the current baseline config:

```powershell
py scripts/pin_validation_baseline.py --print --config configs/validation_baseline.json
```

Validate that the configured snapshot exists locally:

```powershell
py scripts/pin_validation_baseline.py --validate --config configs/validation_baseline.json
```

`configs/validation_baseline.json` is tracked. It points to the official local baseline snapshot. The snapshot file itself is generated and ignored, so another machine may not have it. If the file is missing, `full` and `ci` can fail with a clear missing-baseline error.

## Baseline Promotion

Prefer a dry-run first:

```powershell
$candidate = Get-ChildItem reports\validation_snapshots\validation_snapshot_*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1
py scripts/pin_validation_baseline.py --promote-candidate "$($candidate.FullName)" --config configs/validation_baseline.json --require-pass --record-history --history-config configs/validation_baseline_history.json --history-notes "promotion dry-run" --comparison-export-dir reports/validation_snapshots --dry-run
```

Run the real promotion only after explicit review:

```powershell
py scripts/pin_validation_baseline.py --promote-candidate "$($candidate.FullName)" --config configs/validation_baseline.json --require-pass --record-history --history-config configs/validation_baseline_history.json --history-notes "promote validated baseline" --comparison-export-dir reports/validation_snapshots
```

Promotion updates `configs/validation_baseline.json`. When `--record-history` is used, it also appends an audit entry to `configs/validation_baseline_history.json`. After real promotion, commit both tracked config files. Do not commit the generated snapshot or comparison files unless a future release explicitly changes that policy.

## Baseline History

Print friendly history:

```powershell
py scripts/pin_validation_baseline.py --history-print --history-config configs/validation_baseline_history.json
```

Print raw JSON:

```powershell
py scripts/pin_validation_baseline.py --history-json --history-config configs/validation_baseline_history.json
```

`configs/validation_baseline_history.json` is tracked. It records `PIN`, `PROMOTE`, and `CLEAR` entries when `--record-history` is used. Dry-run prepares and prints the entry but does not write history.

## Regression Interpretation

`PASS` means no warning or fail flags were raised.

`WARNING` means mild degradation was detected, but not a hard fail. Review the flags and decide whether the change is acceptable.

`FAIL` means an official regression was detected. Do not merge or promote without explicit review.

Common regression signals include:

- sample status changed from `PASSED` to `FAILED`
- walk-forward status changed from `PASS` to `FAIL`
- large NetAfterCost drop
- large MaxDD increase
- recommended profile mismatch

## Cache Notes

Backtest cache files live under `.cache/backtests` and are ignored by Git. Cache hits report original elapsed time, cache read time, and estimated saved time. Cache does not change strategy results; it only speeds repeated validation.

## Git Hygiene

Generated snapshots and comparisons should not appear in tracked git status. Expected tracked files are source, tests, docs, and selected configs such as:

- `configs/validation_baseline.json`
- `configs/validation_baseline_history.json`
- `docs/validation_gate_runbook.md`

Before pushing a validation-related change:

```powershell
git status --short --untracked-files=all
py -m pytest
py scripts/run_validation_gate.py --preset full
```

If generated snapshots appear in `git status`, check `.gitignore` before committing.

## Troubleshooting

### Full Or CI Says Baseline Snapshot Not Found

Run:

```powershell
py scripts/pin_validation_baseline.py --print --config configs/validation_baseline.json
py scripts/pin_validation_baseline.py --validate --config configs/validation_baseline.json
```

Ensure the local baseline snapshot exists. If it does not, create or copy a valid baseline snapshot, then pin it deliberately.

### Quick Preset Shows Failed

This can be expected because `quick` uses `max-windows 100`, which may produce 0 trades on current BTC 15m data. Use `full` for official validation.

### Generated Snapshots Appear In Git Status

Check `.gitignore` for:

```text
reports/validation_snapshots/*.json
reports/validation_snapshots/*.md
```

Do not commit generated snapshots or comparisons during ordinary validation work.

### Regression Fail

Inspect the comparison report and regression flags. Do not promote the candidate. Investigate code, config, data, and profile changes before rerunning validation.

### Cache Seems Stale

Clear `.cache/backtests` or use the available cache refresh or no-cache controls for the relevant runner. Cache is a speed layer only; it should not change validation metrics.

## Current Recommended Workflow

Daily local validation:

```powershell
py scripts/run_validation_gate.py --preset full
```

Fast smoke check:

```powershell
py scripts/run_validation_gate.py --preset quick
```

CI:

```powershell
py scripts/run_validation_gate.py --preset ci
```

BTC paper readiness diagnostics:

```powershell
py scripts/run_btc_paper_readiness.py
```

BTC paper runtime config validation:

```powershell
py scripts/validate_btc_paper_runtime_config.py
py scripts/validate_btc_paper_runtime_config.py --json
py scripts/validate_btc_paper_runtime_config.py --strict
```

Strict readiness diagnostics:

```powershell
py scripts/run_btc_paper_readiness.py --strict
```

Gate-backed readiness diagnostics:

```powershell
py scripts/run_btc_paper_readiness.py --run-gate --use-cache --cache-dir .cache/backtests
```

The BTC readiness report is diagnostics only. It does not execute trades, enable paper execution, or imply live trading approval. ETH samples remain optional/stress-test data and do not block BTC readiness unless a multi-asset/all-samples validation snapshot is intentionally used.

The BTC paper runtime config at `configs/btc_paper_runtime.json` is also diagnostics/config only. It keeps live trading, order submission, and paper execution disabled while validating BTC risk guardrails. After Release 2.65, the remaining expected readiness warning is `paper_monitoring`, which belongs to a later telemetry/runner release.

Baseline promotion:

1. Run the full gate.
2. Inspect the snapshot, comparison, and summary badge.
3. Run promotion dry-run with `--require-pass --record-history`.
4. Run real promotion only after explicit approval.
5. Commit the tracked baseline config and history files.

# BTC Paper Monitoring / Telemetry Readiness

Use these commands to validate the BTC paper monitoring configuration and pre-runner status:

```powershell
py scripts/validate_btc_paper_monitoring.py
py scripts/validate_btc_paper_monitoring.py --json
py scripts/validate_btc_paper_monitoring.py --strict
py scripts/validate_btc_paper_monitoring.py --status
py scripts/validate_btc_paper_monitoring.py --status --json
py scripts/run_btc_paper_readiness.py
```

This monitoring layer is diagnostics-only. It does not start a paper runner, execute trades, place orders, read credentials, or connect to exchange APIs. The heartbeat fields are intentionally empty before a runner exists. Live trading, order submission, and paper execution must remain disabled until a later release explicitly introduces execution.

# BTC Paper Runner Dry-Run State Machine

Use these commands to exercise the dry-run lifecycle state machine:

```powershell
py scripts/run_btc_paper_runner.py --status
py scripts/run_btc_paper_runner.py --initialize --state-file reports/paper_runner/btc_paper_runner_state.json
py scripts/run_btc_paper_runner.py --start --state-file reports/paper_runner/btc_paper_runner_state.json
py scripts/run_btc_paper_runner.py --heartbeat --state-file reports/paper_runner/btc_paper_runner_state.json
py scripts/run_btc_paper_runner.py --pause --state-file reports/paper_runner/btc_paper_runner_state.json
py scripts/run_btc_paper_runner.py --resume --state-file reports/paper_runner/btc_paper_runner_state.json
py scripts/run_btc_paper_runner.py --stop --state-file reports/paper_runner/btc_paper_runner_state.json
```

This is lifecycle/reporting only. `--start` does not start a loop and does not generate signals, create trades, submit orders, connect to an exchange, or enable live/paper execution. Generated state files stay local under `reports/paper_runner`.

# BTC Paper Signal Evaluation Dry-Run

Use these commands to validate and run a one-shot local fixture signal evaluation:

```powershell
py scripts/run_btc_paper_signal_evaluation.py
py scripts/run_btc_paper_signal_evaluation.py --json
py scripts/run_btc_paper_signal_evaluation.py --strict
py scripts/run_btc_paper_signal_evaluation.py --evaluate
py scripts/run_btc_paper_signal_evaluation.py --evaluate --json
py scripts/run_btc_paper_runner.py --evaluate-signal-dry-run
py scripts/run_btc_paper_runner.py --evaluate-signal-dry-run --state-file reports/paper_runner/btc_paper_runner_state.json
```

This is diagnostics only. It does not create paper trades, persist trades, submit orders, connect to exchanges, mutate runner state, or activate live/paper execution. Generated signal evaluation reports stay local under `reports/paper_signal_evaluation`.

# BTC Paper Trade Candidate Dry-Run

Use these commands to validate and simulate a non-executable BTC paper trade candidate:

```powershell
py scripts/run_btc_paper_trade_candidate.py
py scripts/run_btc_paper_trade_candidate.py --json
py scripts/run_btc_paper_trade_candidate.py --strict
py scripts/run_btc_paper_trade_candidate.py --simulate
py scripts/run_btc_paper_trade_candidate.py --simulate --json
py scripts/run_btc_paper_runner.py --simulate-trade-candidate-dry-run
py scripts/run_btc_paper_runner.py --simulate-trade-candidate-dry-run --state-file reports/paper_runner/btc_paper_runner_state.json
```

This is diagnostics only. A trade candidate is non-executable and is not a paper trade. It does not persist trades, open positions, submit orders, connect to an exchange, or mutate runner state. Generated candidate reports stay local under `reports/paper_trade_candidates`.

# BTC Paper Candidate Journal Dry-Run

Use these commands to validate, write, or summarize local BTC paper candidate journal diagnostics:

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

This is diagnostics only. Journal entries are local audit records, not paper trades, positions, executable signals, or order records. Rejected candidates are recorded too. The command does not open positions, submit orders, connect to an exchange, or mutate runner state. Generated journal files stay local under `reports/paper_candidate_journal`.

# BTC Forward Test Loop Dry-Run

Use these commands to validate or run the local finite BTC forward-test dry-run:

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

This is local finite forward-test dry-run only. It does not use live market data, connect to an exchange, execute trades, persist active paper trades, open positions, submit orders, or mutate runner state. It may write local diagnostic journal entries and forward-test state/report files when explicitly requested. Generated forward-test files stay local under `reports/forward_test`.

# BTC Live Market Read-Only Feed Dry-Run

Use these commands to validate or run the one-shot public BTC market-data observation dry-run:

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

This uses public read-only market data only. It does not use API keys, private endpoints, account data, balance data, position data, order submission, order cancellation, paper persistence, executable trades, or runner state mutation. A rejected candidate is expected when the live-read-only signal score is below threshold. Generated live-feed reports stay local under `reports/live_market_feed`.

If public network access is unavailable, fetch and observe commands fail safely with private API usage, API key usage, trading API usage, order submission, trading connection, and state mutation all reported as `false`.

# BTC Local Paper Account Simulation

Use these commands to validate or run the local virtual paper account simulation:

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

This is local virtual paper account simulation only. It may write local state and ledger files under `reports/paper_account`. It does not submit or cancel orders, use API keys, call private endpoints, fetch real account/balance/position data, create real positions, create executable trades, mutate runner state, or enable runtime paper execution.

A no-action event is expected when the live signal score is below threshold. If a candidate is approved in the future, any virtual order or virtual position remains a local diagnostic object only. Generated paper-account files stay local under `reports/paper_account`.

# BTC Futures Read-Only Market Feed

Use these commands to validate or run public BTCUSDT futures read-only diagnostics:

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

This uses public futures market data only. It does not use API keys, private futures endpoints, account/balance/position data, order submission, order cancellation, real futures positions, paper futures positions, leverage, leverage simulation, liquidation modeling, executable trades, or runner state mutation.

If public network access is unavailable, fetch and observe commands fail safely with private API usage, API key usage, trading API usage, account data, balance fetch, position fetch, order submission, real position creation, paper position creation, leverage, liquidation modeling, trading connection, runner mutation, and execution mutation all reported as `false`. Generated futures-feed reports stay local under `reports/futures_read_only_feed`.

# BTC Futures Leverage + Liquidation Risk Model

Use these commands to validate or run local hypothetical BTCUSDT futures risk diagnostics:

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

Results are `APPROXIMATE_CONSERVATIVE` estimates only, not exact Binance liquidation prices. The model does not include exchange maintenance margin tiers, cross-margin collateral, private leverage bracket data, ADL, liquidation fee schedules, or portfolio margin.

This release does not create real or paper futures positions, change exchange leverage, change margin mode, submit orders, cancel orders, use private APIs, fetch account/balance/position data, mutate the local paper account, or mutate runner/execution state. Funding is diagnostic only.

# BTC Futures Local Paper Position Simulation

Release 2.76 adds a local-only BTCUSDT futures paper position simulator for explicit operator dry-run actions. It stores only local JSON state and append-only JSONL ledger entries under `reports/futures_paper_position`, and those generated files are ignored by Git.

It is separate from the spot local paper account. It does not mutate the spot paper account, runner state, execution state, or any exchange state. It does not use API keys, private APIs, account endpoints, balance endpoints, position endpoints, order endpoints, leverage-setting endpoints, margin-mode endpoints, real orders, testnet orders, or external paper positions.

Useful commands:

```powershell
py scripts/run_btc_futures_paper_position.py
py scripts/run_btc_futures_paper_position.py --json
py scripts/run_btc_futures_paper_position.py --strict
py scripts/run_btc_futures_paper_position.py --status
py scripts/run_btc_futures_paper_position.py --initialize
py scripts/run_btc_futures_paper_position.py --open-position --side LONG --entry-price 64000 --mark-price 64000 --stop-loss 62000 --take-profit 67000 --notional 1000 --leverage 3 --action-id open-001
py scripts/run_btc_futures_paper_position.py --mark-to-market --mark-price 65000 --action-id mark-001
py scripts/run_btc_futures_paper_position.py --apply-funding --funding-rate 0.0001 --funding-periods 1 --action-id funding-001
py scripts/run_btc_futures_paper_position.py --close-position --close-price 66000 --close-reason MANUAL --action-id close-001
py scripts/run_btc_futures_paper_position.py --ledger-summary
py scripts/run_btc_futures_paper_position.py --reset --force
py scripts/run_btc_futures_paper_position.py --simulate-lifecycle
py scripts/run_btc_paper_runner.py --simulate-futures-paper-position-lifecycle-dry-run
```

Approximate liquidation monitoring is conservative and uses the Release 2.75 model. Live mark/funding actions use public read-only futures data only; network failures fail safely without state mutation. The runner lifecycle action is in-memory only. A disabled-by-default Binance Futures Testnet adapter may come later, but it is not part of Release 2.76.

# Binance Futures Testnet Adapter - Disabled by Default

Release 2.77 introduces a Binance USD-M Futures Testnet adapter boundary while keeping the adapter disabled by default. The only allowed REST host is `demo-fapi.binance.com`; production Binance hosts, non-HTTPS URLs, user-info URLs, IP addresses, localhost, loopback/private-network hosts, and redirects outside the allowlist are rejected.

Operator commands:

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

Public ping, server-time, and exchange-info diagnostics are credential-free. Credential checks are explicit and inspect only the dedicated testnet environment variables, returning presence and length metadata without logging or persisting secrets. Signing previews are local-only and redacted; signed requests are not transmitted. Order intents are non-executable and do not sign, transmit, reserve margin, create local positions, or mutate Release 2.76 state.

No testnet orders are submitted or cancelled. No authenticated account, balance, or position data is fetched. No leverage or margin mode is changed. No user-data stream or WebSocket is opened. Release 2.76 local futures paper state, the spot paper account, runner state, execution state, and exchange state remain untouched. A future release may add separately gated authenticated testnet read-only access.

# Binance Futures Testnet Authenticated Read-Only Account Snapshot

Release 2.78 adds explicitly confirmed authenticated read-only Binance USD-M Futures Testnet account diagnostics. This is a diagnostics layer only and does not activate paper execution, live trading, order submission, runner activity, monitoring polling, or exchange mutation.

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

Operational rules:

- authenticated transport is GET only
- the only host is `https://demo-fapi.binance.com`
- the only authenticated paths are `/fapi/v3/account`, `/fapi/v3/balance`, and `/fapi/v3/positionRisk`
- BTCUSDT is the only position-risk symbol
- the confirmation phrase `CONFIRM_TESTNET_READ_ONLY` is required for authenticated reads
- credentials must come from `BINANCE_FUTURES_TESTNET_API_KEY` and `BINANCE_FUTURES_TESTNET_API_SECRET`
- the API secret is never transmitted
- raw authenticated responses, signed URLs, signatures, and authenticated headers are not printed or persisted
- readiness and runner validation do not inspect credentials and do not use network
- no orders, test orders, cancellation, order/trade history, leverage changes, margin changes, position changes, listen keys, user streams, WebSockets, production endpoints, or state mutation are permitted in Release 2.78.

# Binance Futures Testnet Test Order Preflight

Release 2.79 introduces an explicit Test Order preflight for Binance USD-M Futures Testnet. The only authenticated trade-related endpoint allowed is `POST /fapi/v1/order/test`; `POST /fapi/v1/order` and every cancellation, modification, order query, trade query, conditional/algo order, leverage, margin, stream, WebSocket, production, and state mutation path remains blocked.

Useful commands:

```powershell
py scripts/run_binance_futures_testnet_order_test.py
py scripts/run_binance_futures_testnet_order_test.py --json
py scripts/run_binance_futures_testnet_order_test.py --strict
py scripts/run_binance_futures_testnet_order_test.py --check-credentials
py scripts/run_binance_futures_testnet_order_test.py --build-preview --client-order-id smcbot-test-market-001 --side BUY --order-type MARKET --quantity 0.001
py scripts/run_binance_futures_testnet_order_test.py --submit-test-order --client-order-id smcbot-test-market-002 --side BUY --order-type MARKET --quantity 0.001
py scripts/run_btc_paper_runner.py --validate-binance-futures-testnet-order-test-dry-run
```

Submitting a Test Order request requires `--confirm-testnet-order-test CONFIRM_TESTNET_ORDER_TEST` and dedicated Testnet credentials from `BINANCE_FUTURES_TESTNET_API_KEY` and `BINANCE_FUTURES_TESTNET_API_SECRET`. Validation, readiness, runner dry-run, and local preview do not inspect credentials or use network. Reports must say "Test Order request accepted" rather than "order submitted" or "position opened", and must show actual order, matching-engine submission, exchange order creation, position creation, and exchange state mutation as false.
