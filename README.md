# MyTradeAnalysis

Paper-trading web application and research runtime.

## Scope
- Paper Trading only; live order submission disabled.
- Browser/PWA dashboard.
- EOD universe-wide reverse engineering: identify profitable moves the bot missed, classify the actual miss cause, and learn only from repeated cross-symbol patterns.
- No stock-specific hard-coded rules, exceptions, watchlists or forced priorities.
- Analysis Error Score and Opportunity Miss Score remain separate.

## Source of truth
The Python trading engine is authoritative for market data, deterministic technical/risk gates, paper execution, persistence, reconciliation and EOD learning.

## Deployment direction
GitHub repository + free-tier cloud dashboard/scheduler for paper validation. A persistent VPS is not required for the current paper-only phase.
