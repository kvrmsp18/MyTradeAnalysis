# Strategy Lab — research integration plan

## Purpose
This module provides common, research-only signal primitives inspired by strategy categories shown in BullsAI: range expansion, trend following, momentum, mean reversion, pair-spread exploration, market-regime classification, industry rotation, and delivery-backed activity.

## Safety contract
- Every strategy result is marked `RESEARCH_ONLY` and `execution_eligible: false`.
- No strategy sends orders or changes PAPER/LIVE mode.
- Missing data and insufficient history fail closed.
- Pair-spread z-scores are exploratory; they do not prove cointegration. A proper stationarity/cointegration test and walk-forward hedge-ratio estimation are still required before use.
- Industry rotation requires correctly aligned, survivorship-aware sector/industry constituent and price histories.
- Delivery activity requires verified exchange delivery data; turnover alone is not a proxy for delivery.
- Seasonality is intentionally not a trading signal yet: it needs a survivorship-aware multi-year dataset, sample-size reporting, and out-of-sample significance checks before it can be added responsibly.

## Current scope
This is the first isolated implementation on a feature branch. It is not yet wired into the paper/live executors. Integration requires a follow-up change to the snapshot schema and decision ledger, plus backtest and dashboard work. Do not enable real-money trading based on these primitives alone.

## Validation
Run:
```bash
python scripts/strategy_lab_self_test.py
```
