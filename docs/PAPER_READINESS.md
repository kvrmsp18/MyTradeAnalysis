# Paper Trading Readiness — Truthful Status

## What is working

- GitHub Actions paper cycle runs on a 5-minute schedule during NSE cash hours.
- Market collection has a Dhan primary path and explicitly labelled NSE/Yahoo fallbacks.
- Deterministic SCRAP analysis is persisted.
- Decision-time ledgers are persisted.
- Paper BUY/SELL simulation engine exists and never calls a broker order endpoint.
- Offline acceptance tests cover BUY, target SELL/P&L, stop loss, affordability/budget exclusion, state persistence, and the live-order lock.
- The AI Development Council is a mandatory validation gate; a synthesized `CHANGES_REQUIRED` result fails the workflow.
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

## Acceptance evidence required before calling the system ready

1. Paper engine acceptance test is green.
2. GUI build is green and all dashboard health states are sourced from runtime evidence rather than hard-coded claims.
3. A market-hours cycle completes with a persisted decision ledger.
4. At least one cycle produces an auditable paper BUY/SELL simulation or an auditable risk/capital skip.
5. EOD reconciliation completes against the paper ledger.
6. OpenAI and Anthropic both complete the development/review council and the synthesized council result is PASS.
7. No live broker endpoint is invoked by any test or paper cycle.

Until all seven conditions are evidenced, the GUI/documentation must not describe the bot as `READY`.
