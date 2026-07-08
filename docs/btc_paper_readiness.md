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

## Status

- `READY`: all required checks pass and no required/recommended warnings remain.
- `WARNING`: required checks pass, but recommended preparation work remains.
- `BLOCKED`: at least one required check failed.

## Scope

The current project phase is BTC-first. The official full gate uses BTC required-full samples: BTC/USDT 15m and BTC/USDT 1h. ETH samples remain optional stress-test data and do not block BTC paper readiness unless an all-samples validation snapshot is deliberately used.

Before any real paper execution work, create a BTC paper runtime config and add dry-run monitoring/telemetry. This readiness tool is pre-paper diagnostics only.
