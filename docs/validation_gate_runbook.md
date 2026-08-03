# Validation Gate Operator Runbook

## Purpose

The validation gate is research, audit, and CI tooling. It is not live trading approval, and it does not activate decision thresholds in live or paper trading. Use it to produce repeatable validation artifacts, compare a candidate snapshot against the pinned baseline, and decide whether a research change is safe to merge or promote.

## Binance Futures Testnet Manual Lifecycle

Release 2.80 introduces a manual BTCUSDT Binance USD-M Futures Testnet post-only LIMIT lifecycle. It is an operator-only diagnostic and is not part of live trading, paper trading, strategy execution, or the runner loop. The command is disabled by default and requires the exact confirmation phrase before any authenticated request.

The lifecycle is intentionally narrow: one LIMIT GTX order, derived away from the best bid/ask by a configured offset, query exact order, cancel exact order, final query, and zero-position verification. It must not use MARKET, stop-loss, take-profit, conditional, algo, batch, leverage, margin, position-mode, production, or broad order-list endpoints. Unknown network state requires manual exact-order query/cancel recovery. Never run the real authenticated lifecycle from Codex; use dedicated Testnet credentials only.

## Release 2.93 One-Time Permit Mutation Enforcement

Release 2.93 enforces durable one-time permit authorization at every approved authenticated Binance Futures Testnet mutation boundary. This is Binance Futures Testnet/Demo only, BTCUSDT only, Production disabled, and supervised/manual operation only. A signal, Dashboard action, CLI confirmation phrase, or operator intent is not by itself mutation authorization.

### Scope and Purpose

The permit gate applies only to the approved BTCUSDT Testnet mutation paths. Read-only GET diagnostics remain read-only, and this section does not enable live production execution, multi-symbol operation, automatic trading, or strategy-runner mutation.

### Phase C Read-Only Status Preflight

Before any separately authorized Phase C mutation scenario, the supervising operator must complete these read-only status checks against the control plane. The decision is fail closed: only the exact success values below allow the operator to continue to separate permit preparation. Use HTTP GET only:

```text
GET <CONTROL_PLANE_BASE_URL>/api/v1/live/kill-switch/status
GET <CONTROL_PLANE_BASE_URL>/api/v1/live/recovery/status
```

1. Read durable kill-switch status from `GET /api/v1/live/kill-switch/status`.
2. Require `state == "RELEASED"`, `changed == false`, and durable `version` and `updated_at` values in the `KillSwitchControlResponse`.
3. Stop with `STOP - PHASE C MUTATION BLOCKED` when `state == "ENGAGED"`, `state` is missing, `state` is outside `ENGAGED` or `RELEASED`, persistence/schema is unavailable, the HTTP request fails, or the response is unavailable, malformed, ambiguous, or cannot be sanitized for operator reporting.
4. Read unresolved-recovery status from `GET /api/v1/live/recovery/status`.
5. Require `required == false` in the `LiveRecoveryStatusResponse`.
6. Stop with `STOP - PHASE C MUTATION BLOCKED` when `required == true`, the status request fails, or the response is unavailable, malformed, ambiguous, or cannot be sanitized for operator reporting.
7. Only after both GET checks pass may a separately authorized scenario proceed to its one-time permit and exact confirmation steps.

These status reads are not mutation routes. Do not use `POST /api/v1/live/kill-switch/engage`, `POST /api/v1/live/kill-switch/release`, or `POST /api/v1/live/recovery/run` as pre-execution status checks. Do not automatically release the kill switch, do not automatically run recovery, and do not interpret an unavailable, untrusted, or ambiguous status as safe. Passing these GET checks does not issue, consume, or authorize a permit, and it does not replace the later exact confirmation phrase required by the selected supervised scenario.

### Local Persistence Provisioning Contract

The repository-owned Compose file `docker-compose.persistence.yml` is for supervised local/Testnet persistence only. It does not authorize C2C, credentials, permit issue, signing, or Binance contact.

Operators must provide `ICT_POSTGRES_DB`, `ICT_POSTGRES_USER`, and `ICT_POSTGRES_PASSWORD` outside the repository. The required variable names are ICT_POSTGRES_DB, ICT_POSTGRES_USER, and ICT_POSTGRES_PASSWORD. Secret values must not be committed, printed, pasted into Codex prompts, or included in screenshots.

Configuration validation command:

```powershell
docker compose -f docker-compose.persistence.yml config
```

Future startup command, documented only and not executed by this runbook section:

```powershell
docker compose -p ict-pro-tradingbot -f docker-compose.persistence.yml up -d
```

Future status command, documented only:

```powershell
docker compose -p ict-pro-tradingbot -f docker-compose.persistence.yml ps
```

Future shutdown command that preserves the named volume:

```powershell
docker compose -p ict-pro-tradingbot -f docker-compose.persistence.yml down
```

`down -v` is prohibited unless separately authorized. Migration and durable state initialization remain separate future passes. Container health does not prove schema readiness or kill-switch state. Existing old-project containers must not be reused.

## Phase C Signed Order-Test Supervised Execution Runbook

DOCUMENTATION ONLY - NO DEMO/TESTNET EXECUTION IS AUTHORIZED

This runbook prepares a future separately authorized Binance Futures Testnet/Demo Signed Order-Test only. It is not execution approval, does not expose credentials, does not issue or consume a permit by itself, does not contact Binance, and does not authorize Codex to run any command shown here.

### Phase 0 - Separate Authorization Boundary

- This runbook does not authorize execution.
- The user must separately approve one exact Signed Order-Test scenario before any credential exposure, permit operation, or submit command.
- Approval applies to one Signed Order-Test attempt only.
- Scope is BTCUSDT only and Binance Futures Testnet/Demo only.
- Production remains disabled.
- Autonomous execution is prohibited.
- No actual exchange order creation is authorized; the only documented endpoint is Binance Test Order validation.
- No later protective, lifecycle, paper-position, real-position, or runner scenario is authorized by this runbook.

### Phase 1 - Operator and Environment Record

Record a local sanitized operator worksheet before any permit or credential step:

```text
scenario_id: <UNIQUE_SCENARIO_ID>
utc_timestamp: <UTC_TIMESTAMP>
local_date: <LOCAL_DATE>
operator: <OPERATOR>
repository_branch: <BRANCH>
repository_head: <HEAD_SHA>
python_exe: <PYTHON_EXE>
python_version: <PYTHON_VERSION>
environment: TESTNET
symbol: BTCUSDT
production_disabled_evidence: <EVIDENCE>
client_order_id: <UNIQUE_CLIENT_ORDER_ID>
side: <APPROVED_SIDE>
order_type: <APPROVED_ORDER_TYPE>
quantity: <APPROVED_MINIMAL_QUANTITY>
price: <APPROVED_PRICE_IF_REQUIRED>
time_in_force: <APPROVED_TIME_IN_FORCE_IF_REQUIRED>
reduce_only: <APPROVED_REDUCE_ONLY>
```

Do not record API keys, API secrets, signatures, authenticated headers, signed URLs, raw authenticated payloads, or credential lengths.

### Phase 2 - Read-Only Safety Status

Use HTTP GET only:

```text
GET <CONTROL_PLANE_BASE_URL>/api/v1/live/kill-switch/status
GET <CONTROL_PLANE_BASE_URL>/api/v1/live/recovery/status
```

Require the kill-switch response to report `state == "RELEASED"`, `changed == false`, and durable `version` and `updated_at` values. Require the recovery response to report `required == false`.

Every other outcome is:

```text
STOP - SIGNED ORDER-TEST BLOCKED
```

Do not automatically release the kill switch. Do not automatically run recovery. Do not interpret unavailable, malformed, ambiguous, failed, missing, untrusted, or unsanitizable status as safe. Do not proceed after an ambiguous response.

### Phase 3 - Local Static and Preview Preparation

Use the exact interpreter path approved for the future scenario:

```powershell
$PythonExe = "<PYTHON_EXE>"
& $PythonExe --version
& $PythonExe -m pytest --version
```

Run validation and preview only after separate authorization in an operator shell; these templates are documentation and must not be executed by this task:

```powershell
& $PythonExe scripts/run_binance_futures_testnet_order_test.py --validate-only
```

MARKET preview template:

```powershell
& $PythonExe scripts/run_binance_futures_testnet_order_test.py `
  --build-preview `
  --client-order-id <UNIQUE_CLIENT_ORDER_ID> `
  --side <APPROVED_SIDE> `
  --order-type MARKET `
  --quantity <APPROVED_MINIMAL_QUANTITY> `
  --reduce-only
```

For a MARKET preview, omit `--price` and omit `--time-in-force`. If `reduce_only` is false, omit `--reduce-only` from the preview command and record `reduce_only: false` explicitly. The frozen JSON must record `price: null` and `time_in_force: null`.

LIMIT preview template:

```powershell
& $PythonExe scripts/run_binance_futures_testnet_order_test.py `
  --build-preview `
  --client-order-id <UNIQUE_CLIENT_ORDER_ID> `
  --side <APPROVED_SIDE> `
  --order-type LIMIT `
  --quantity <APPROVED_MINIMAL_QUANTITY> `
  --price <APPROVED_PRICE> `
  --time-in-force <APPROVED_TIME_IN_FORCE> `
  --reduce-only
```

For a LIMIT preview, include both `--price <APPROVED_PRICE>` and `--time-in-force <APPROVED_TIME_IN_FORCE>`. The approved `time_in_force` for the frozen fingerprint is exactly `GTC` or `GTX`. If `reduce_only` is false, omit `--reduce-only` from the preview command and record `reduce_only: false` explicitly. Do not rely on an implicit CLI default for any mutation-relevant value.

Record the sanitized preview, exact unsigned business parameters, notional/filter result, and local `transmission_ready` status. Do not include credentials or permit references in preview unless a later production CLI contract requires them.

### Phase 4 - Fingerprint and Request-File Freeze

Create one immutable request artifact:

```text
<SIGNED_ORDER_TEST_REQUEST_JSON>
```

The frozen JSON must contain exactly the fingerprint business fields for `SIGNED_ORDER_TEST_CREATE`:

```json
{
  "schema_version": "1.0",
  "operation": "SIGNED_ORDER_TEST_CREATE",
  "environment": "TESTNET",
  "symbol": "BTCUSDT",
  "client_order_id": "<UNIQUE_CLIENT_ORDER_ID>",
  "side": "<APPROVED_SIDE>",
  "position_side": "BOTH",
  "order_type": "<APPROVED_ORDER_TYPE>",
  "quantity": "<APPROVED_MINIMAL_QUANTITY>",
  "price": "<APPROVED_PRICE_IF_REQUIRED_OR_NULL>",
  "time_in_force": "<APPROVED_TIME_IN_FORCE_IF_REQUIRED_OR_NULL>",
  "reduce_only": <APPROVED_REDUCE_ONLY>
}
```

The request must include the exact environment, exact BTCUSDT symbol, exact operation `SIGNED_ORDER_TEST_CREATE`, exact subject/client order ID, exact business parameters, and exact fingerprint. It must not include timestamp, recvWindow, signature, API key, API secret, header, credential, authenticated URL, raw request, raw response, or metadata.

After the preview and request JSON are frozen, any parameter change invalidates the scenario and requires a new preview plus separate approval. Do not manually modify a request after permit issuance.

### Phase 5 - One-Time Permit Preparation

Issue the one-time permit only after the frozen request is reviewed:

```powershell
& $PythonExe scripts/issue_live_execution_permit.py `
  --operation SIGNED_ORDER_TEST_CREATE `
  --request-file <SIGNED_ORDER_TEST_REQUEST_JSON> `
  --issued-by <OPERATOR> `
  --confirmation CONFIRM_TESTNET_ONE_TIME_EXECUTION_PERMIT
```

Show the permit without mutating it:

```powershell
& $PythonExe scripts/show_live_execution_permit.py --permit-id <PERMIT_ID>
```

Record permit ID, exact expected version, state `ISSUED`, environment, symbol, operation, subject/client order ID, fingerprint, issued time, and expiry when present. The permit must exactly match the frozen request. Any mismatch is:

```text
STOP - PERMIT DOES NOT MATCH SCENARIO
```

### Phase 6 - Final Human Hold Point

Immediately before credential exposure, perform a second explicit human review. Verify separate user authorization is still valid, kill switch still reports `RELEASED`, recovery still reports `required == false`, scenario parameters are unchanged, frozen request hash is unchanged, permit is still `ISSUED`, permit version is unchanged, permit is not expired, Production remains disabled, and BTCUSDT/Testnet-Demo scope is unchanged.

The CLI confirmation phrase is not the same as user execution authorization. Both are required.

### Phase 7 - Temporary Credential Boundary

Expose only Binance Futures Testnet/Demo credentials, only immediately before the one approved submission, and only in the operator-controlled shell. Never print credential values. Never place credentials in command history, documents, request JSON, permit files, reports, screenshots, or logs. Never use production credentials. Stop when the credential source or environment cannot be proven. Do not run credential inspection commands that print values.

Static credential-readiness template, documentation only:

```powershell
& $PythonExe scripts/run_binance_futures_testnet_order_test.py --check-credentials
```

### Phase 8 - Exact One-Attempt Submit Template

The future approved submit must use exactly one command, one process, and one attempt:

MARKET submit template:

```powershell
& $PythonExe scripts/run_binance_futures_testnet_order_test.py `
  --submit-test-order `
  --client-order-id <UNIQUE_CLIENT_ORDER_ID> `
  --side <APPROVED_SIDE> `
  --order-type MARKET `
  --quantity <APPROVED_MINIMAL_QUANTITY> `
  --reduce-only `
  --permit-id <PERMIT_ID> `
  --permit-version <PERMIT_VERSION> `
  --confirm-testnet-order-test CONFIRM_TESTNET_ORDER_TEST
```

For a MARKET submit, omit `--price` and omit `--time-in-force`.

LIMIT submit template:

```powershell
& $PythonExe scripts/run_binance_futures_testnet_order_test.py `
  --submit-test-order `
  --client-order-id <UNIQUE_CLIENT_ORDER_ID> `
  --side <APPROVED_SIDE> `
  --order-type LIMIT `
  --quantity <APPROVED_MINIMAL_QUANTITY> `
  --price <APPROVED_PRICE> `
  --time-in-force <APPROVED_TIME_IN_FORCE> `
  --reduce-only `
  --permit-id <PERMIT_ID> `
  --permit-version <PERMIT_VERSION> `
  --confirm-testnet-order-test CONFIRM_TESTNET_ORDER_TEST
```

For a LIMIT submit, pass both exact approved values: `--price <APPROVED_PRICE>` and `--time-in-force <APPROVED_TIME_IN_FORCE>`. The selected submit form must match the selected preview form, and every submitted value must equal the frozen request. If `reduce_only` is false, omit `--reduce-only` from the submit command and record `reduce_only: false`. Use one command, one process, and one attempt. POST retry zero is mandatory. No automatic retry, no second permit, no permit replacement, and no parameter change after authorization is allowed.

This template is documentation only and must not be executed by this task.

### Phase 9 - Expected Safe Outcome

The endpoint is `/fapi/v1/order/test`. A successful Test Order validates parameters and must not create an exchange order, matching-engine order, exchange position, local paper state, or exchange state mutation. The permit is one-time and may be consumed before transport. Persistence must commit and close before signing and transport. Output must be sanitized. Secret, signature, authenticated URL, SQL, traceback, raw request, raw response, authenticated headers, and credential output is forbidden.

Do not claim success without exact evidence.

### Phase 10 - Post-Attempt Verification

Record exact CLI exit code, sanitized decision/result, `mutation_transmitted`, `permit_consumed`, `recovery_required`, signing count when available, POST count when available, retry count, permit show after attempt, final permit state/version, final kill-switch status, and final recovery status.

If a supported read-only command proves no order or position was created, record that evidence. Do not invent an unsupported query command. When no exact read-only query is proven, require separate authorization before reconciliation.

### Phase 11 - Uncertainty and Failure Rules

No blind retry. No rerun with the same permit. No permit refund. No permit reuse. No replacement permit in the same scenario. Do not infer failure merely from a missing response. Do not infer safety from a timeout. Preserve sanitized terminal evidence, inspect permit state, inspect recovery status, and stop for independent review. Exact reconciliation requires separate authorization when not already covered by a proven read-only command.

Distinguish:

```text
pre-consume denial: failed safe, no mutation transmitted
post-consume uncertainty: permit remains consumed, recovery may be required, no retry
```

### Phase 12 - Credential Removal and Closure

Remove Testnet credential environment variables immediately after the attempt or abort. Do not print their values. Verify only their absence. Preserve sanitized evidence. Do not leave a credential-bearing terminal or process running. Do not persist credentials in files or logs.

### Phase 13 - Unused-Permit Abort Procedure

When submission did not begin and the permit remains `ISSUED`, revoke only after separate operator approval:

```powershell
& $PythonExe scripts/revoke_live_execution_permit.py `
  --permit-id <PERMIT_ID> `
  --expected-version <PERMIT_VERSION> `
  --reason-code OPERATOR_REVOKED `
  --confirmation CONFIRM_TESTNET_REVOKE_EXECUTION_PERMIT
```

Revoke only after proving submit did not begin. Do not revoke a consumed permit. Do not refund or replace a consumed permit. Revocation is a permit operation and requires separate operator approval during a real scenario.

### Phase 14 - Required Evidence Package

Produce one sanitized report containing separate user authorization reference, scenario ID, UTC timestamps, branch and HEAD, interpreter version, Testnet/Demo and BTCUSDT proof, production-disabled proof, pre/post kill-switch status, pre/post recovery status, exact scenario parameters, preview identity, frozen request SHA-256, fingerprint, permit ID and versions without secrets, permit state before and after, exact submit command with secrets absent, exact confirmation phrase used, exit code, sanitized outcome, `mutation_transmitted`, `permit_consumed`, `recovery_required`, POST count and retry count when available, no-order/no-position evidence when proven, credential-removal evidence, deviations, warnings, and unresolved uncertainty.

The report must end with one of:

```text
SIGNED ORDER-TEST SCENARIO EVIDENCE COMPLETE - READY FOR REVIEW
SIGNED ORDER-TEST SCENARIO BLOCKED - <exact reason>
```

Do not state that the scenario is accepted. Only independent review may accept it.
## Enforced Mutation Boundaries

The five permit-gated mutation boundaries are:

- protective create POST;
- protective cancel DELETE;
- lifecycle create POST;
- lifecycle cancel DELETE;
- signed Order-Test POST.

### Exact Permit Contract

A valid mutation requires an exact permit ID, permit version, environment, symbol, operation, subject, and mutation fingerprint. The operation values are `PROTECTIVE_CREATE`, `PROTECTIVE_CANCEL`, `ORDER_LIFECYCLE_CREATE`, `ORDER_LIFECYCLE_CANCEL`, and `SIGNED_ORDER_TEST_CREATE`.

There is no permit bypass, automatic issue, automatic renewal, refund, replacement, or reuse. Malformed permit references fail closed, and mutation commands do not auto-issue permits.

### Required Mutation Ordering

The required order is:

```text
policy
-> persistence
-> consume
-> commit
-> close
-> signing
-> transport
```

Signing and authenticated transport must not occur before durable permit consumption, persistence commit, and persistence close. If the permit gate cannot prove the exact consumed permit state, the mutation is blocked.

### Retry and Uncertainty Rules

POST retry is zero. DELETE retry is zero. Uncertain mutation outcomes use exact read-only reconciliation, not blind mutation retry. Reconciliation must use the exact persisted mutation identity for the original client order or client algo ID.

### Failed-Safe and Recovery-Required Outcomes

A denial or failure before permit consumption is failed-safe and must not create false recovery. Uncertainty after permit consumption preserves the consumed permit and produces recovery-required behavior. A consumed permit is not refunded, renewed, replaced, or reused after uncertainty.

### Recovery Idempotency

Restart recovery must not duplicate a mutation. Repeated recovery checks are idempotent and use exact persisted mutation identity. A successful recovery rerun performs read-only reconciliation and must not consume another permit or issue another POST or DELETE.

### Request Immutability and Sanitization

Caller-owned mappings remain unchanged, unsigned mutation requests remain unchanged, authentication fields are added only to a fresh transport copy, and approved business parameters remain stable. Operator output and durable output must not expose secrets, API keys, signatures, authenticated URLs, sensitive SQL, tracebacks, exception chains, raw authenticated responses, or sensitive internal metadata.

### Permit Operator Prerequisites

Issue a permit only from an exact request-fingerprint payload and explicit operator confirmation:

```powershell
py scripts/issue_live_execution_permit.py --operation <OPERATION> --request-file <REQUEST_JSON> --issued-by <OPERATOR> --confirmation CONFIRM_TESTNET_ONE_TIME_EXECUTION_PERMIT
```

Show is read-only:

```powershell
py scripts/show_live_execution_permit.py --permit-id <PERMIT_ID>
```

Revoke requires the exact permit ID, expected version, reason code, and explicit operator confirmation:

```powershell
py scripts/revoke_live_execution_permit.py --permit-id <PERMIT_ID> --expected-version <VERSION> --reason-code OPERATOR_REVOKED --confirmation CONFIRM_TESTNET_REVOKE_EXECUTION_PERMIT
```

### Pre-Mutation Operator Checklist

Before any authenticated mutation, verify the exact operation and pass the matching permit reference:

- Protective create requires `--stop-create-permit-id`, `--stop-create-permit-version`, `--take-profit-create-permit-id`, and `--take-profit-create-permit-version`.
- Protective cancel requires `--take-profit-cancel-permit-id`, `--take-profit-cancel-permit-version`, `--stop-cancel-permit-id`, and `--stop-cancel-permit-version`.
- Lifecycle create requires `--create-permit-id` and `--create-permit-version`.
- Lifecycle cancel requires `--cancel-permit-id` and `--cancel-permit-version`.
- Signed Order-Test POST requires `--permit-id` and `--permit-version`.

Confirmation phrases and credentials are still required where the older sections describe them, but they do not replace the one-time permit reference.

### Post-Denial and Post-Uncertainty Actions

For pre-consume denial, stop and correct the failed prerequisite; do not treat it as exchange uncertainty. For post-consume uncertainty or recovery-required output, do not retry POST or DELETE. Use only the exact read-only reconciliation or recovery path for the persisted mutation identity, and preserve the consumed permit record as final evidence.
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

Submitting a Test Order request requires `--confirm-testnet-order-test CONFIRM_TESTNET_ORDER_TEST`, a valid one-time permit reference supplied with `--permit-id` and `--permit-version`, and dedicated Testnet credentials from `BINANCE_FUTURES_TESTNET_API_KEY` and `BINANCE_FUTURES_TESTNET_API_SECRET`. Validation, readiness, runner dry-run, and local preview do not inspect credentials or use network. Reports must say "Test Order request accepted" rather than "order submitted" or "position opened", and must show actual order, matching-engine submission, exchange order creation, position creation, and exchange state mutation as false.
