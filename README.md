# MyTradeAnalysis

A **Paper Trading first** NSE/BSE intraday research and trading-analysis application.

## Current phase

**Paper Trading only. Live order submission is disabled.** The goal is to build, test and observe the complete decision pipeline before any consideration of real-money execution.

### Core pipeline

```text
Market Data
   -> Full Universe Observation
   -> Dynamic Candidate Ranking
   -> Technical / SCRAP / Research Analysis
   -> Market Regime
   -> Risk & Funds Gates
   -> Paper Trade
   -> Position Monitoring
   -> EOD Reconciliation
   -> EOD Reverse Engineering
   -> General Optimization Proposal
   -> Validation
```

## Mandatory EOD reverse engineering

After market close, the bot must inspect the eligible universe for shares that actually made meaningful profitable moves and determine why the bot missed them using the evidence that was available **at decision time**.

The system must record decision-time quotes/indicators, regime, SCRAP/research result, ranking, analysis-pool membership, rejection reason, capital/capacity and risk gates. It then separates:

- **Analysis Error Score** — evidence that the decision logic was wrong at decision time.
- **Opportunity Miss Score** — profitable opportunity that was not captured, even when the original rejection may have been correct.

### No stock-specific learning

This is a hard requirement. A profitable outcome for one stock must **never** create a special rule, exception, permanent priority, forced watchlist entry, or stock-specific threshold. General strategy changes require repeated evidence across multiple unrelated symbols and/or sessions. Risk, liquidity, capital and reconciliation protections cannot be weakened because of hindsight winners.

EOD analysis may propose a **general** optimization, but it must be tested/backtested and validated before activation. It must not silently rewrite the live strategy.

## Free paper deployment direction

The current target is a **GitHub + free-tier cloud + browser/PWA** architecture. You do not need a VPS or a laptop running continuously for the current paper-only phase.

See:
- `docs/ARCHITECTURE.md`
- `docs/EOD_REVERSE_ENGINEERING.md`
- `docs/ROADMAP.md`
- `SOURCE_RULES.md`

## Safety defaults

- Paper Trading: **ON**
- Live Trading: **OFF**
- AI is advisory and cannot bypass deterministic gates.
- Missing market data is `DATA UNAVAILABLE`, never fabricated.
- No hard-coded preference for a particular share.
- All important decisions must be auditable from persisted decision-time evidence.

## Development rule

For major code changes, replace complete files rather than applying fragile partial patches, matching the project's established development workflow.
