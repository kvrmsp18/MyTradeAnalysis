# Paper Trading Readiness — Truthful Status

## What is working

- GitHub Actions paper cycle runs on a 5-minute schedule during NSE cash hours.
- Market collection has a Dhan primary path and explicitly labelled NSE/Yahoo fallbacks.
- Deterministic SCRAP analysis is persisted.
- Decision-time ledgers are persisted.
- Paper BUY/SELL simulation engine exists and never calls a broker order endpoint.
- Paper entries are gated by a Dhan fund-limit check when Dhan credentials are configured.
- There is no stock-price ceiling; insufficient capital produces an explicit skip.
- EOD reverse engineering is research-only and cannot mutate strategy code automatically.
- GitHub Pages GUI is a read-only operator dashboard.
- Live Trading is locked.

## Current limitations

1. The current Dhan marketfeed request returns "Data APIs not Subscribed" in the observed cloud run. The Dhan fund-limit endpoint can still be used separately for the funds gate.
2. Until Dhan market data is subscribed, the paper cycle uses the explicitly labelled NSE/Yahoo fallback path.
3. The fallback validation universe is a broad Nifty-50 basket, not the entire NSE equity universe.
4. GitHub Pages is static. A browser button cannot securely dispatch a GitHub Action with the repository's credentials. Therefore **Run Cycle Now opens the GitHub Actions workflow page**; the scheduled engine remains the actual unattended cycle.
5. The AI council runs on labelled real-data fallbacks after validation; if either provider is unavailable or disagrees, the consensus is HOLD_FOR_REVIEW.
6. A paper session is considered operationally validated only after at least one market-hours cycle has produced a persisted paper decision and the self-test plus GUI build are green.

## Do not call the bot ready until

- a market-hours paper cycle completes successfully,
- the funds gate is PASS,
- at least one decision ledger is produced,
- paper execution produces either an auditable simulated fill or an auditable capital/risk skip,
- the public GUI reflects the latest cycle,
- EOD reconciliation runs successfully.

No live trading is authorized by this document.
