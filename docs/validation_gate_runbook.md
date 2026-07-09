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
