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
