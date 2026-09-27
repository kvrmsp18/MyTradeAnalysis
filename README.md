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
   -> OpenAI + Anthropic Research Council
   -> Deterministic Risk & Funds Gates
   -> Paper Trade
   -> Position Monitoring
   -> EOD Reconciliation
   -> EOD Reverse Engineering
   -> General Optimization Proposal
   -> Validation
```

## Current implementation status

- GitHub Pages browser/PWA GUI: **deployed**
- 5-minute GitHub Actions paper-market cycle: **implemented**
- Dhan market snapshot adapter: **implemented**
- Decision-time observation ledger: **implemented**
- OpenAI + Anthropic research-council module: **implemented as non-executing advisory analysis**
- Paper execution engine: **next integration stage**
- Full technical/SCRAP/ranking engine: **next integration stage**
- EOD reverse-engineering engine: **next integration stage**
- Live orders: **disabled**

## Dhan market-data setup

The scheduled paper cycle runs on GitHub Actions, so no VPS or continuously running laptop is required.

For the current market-data collector, configure:

- `DHAN_CLIENT_ID`
- `DHAN_ACCESS_TOKEN`

`DHAN_API_KEY` is supported as a fallback credential by the collector, but it is **not required for the current paper-market snapshot path when `DHAN_ACCESS_TOKEN` is available**. There is no need to add it just for this stage. We can add/use it later if a future Dhan integration specifically requires it.

The collector never places an order. If credentials are missing, expired, rejected, or market data cannot be read, it writes `DATA_UNAVAILABLE` instead of inventing prices or signals.

The scheduled cycle runs every 5 minutes during the configured weekday UTC window and the GUI refreshes the published snapshot automatically.

## OpenAI + Anthropic research council

The project now includes a two-model research-council design. OpenAI and Anthropic are intended to review the same decision-time evidence independently, challenge each other's reasoning, and produce a research consensus covering evidence, contradictions, uncertainty and data gaps.

This is deliberately **not an autonomous order-execution layer**. The AI council cannot bypass deterministic capital, risk, liquidity, position, loss-limit or reconciliation gates. Missing AI providers never result in invented output, and no provider API key is exposed to the browser GUI.

Configure these only when we are ready to activate the council:

- `OPENAI_API_KEY` — GitHub Actions secret
- `ANTHROPIC_API_KEY` — GitHub Actions secret
- `OPENAI_MODEL` — GitHub Actions repository variable
- `ANTHROPIC_MODEL` — GitHub Actions repository variable

See `docs/AI_COUNCIL.md` for the full protocol.

## Mandatory EOD reverse engineering

After market close, the bot must inspect the eligible universe for shares that actually made meaningful profitable moves and determine why the bot missed them using the evidence that was available **at decision time**.

The system must record decision-time quotes/indicators, regime, SCRAP/research result, ranking, analysis-pool membership, rejection reason, capital/capacity and risk gates. It then separates:

- **Analysis Error Score** — evidence that the decision logic was wrong at decision time.
- **Opportunity Miss Score** — profitable opportunity that was not captured, even when the original rejection may have been correct.

## No stock-specific learning

This is a hard requirement. A profitable outcome for one stock must **never** create a special rule, exception, permanent priority, forced watchlist entry, or stock-specific threshold. General strategy changes require repeated evidence across multiple unrelated symbols and/or sessions. Risk, liquidity, capital and reconciliation protections cannot be weakened because of hindsight winners.

EOD analysis may propose a **general** optimization, but it must be tested/backtested and validated before activation. It must not silently rewrite the active strategy.

## Free paper deployment direction

The target architecture is **GitHub + free-tier cloud + browser/PWA**. You do not need a VPS or a laptop running continuously for the current paper-only phase.

See:
- `docs/ARCHITECTURE.md`
- `docs/AI_COUNCIL.md`
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

## GUI deployment

The browser/PWA GUI is deployed through GitHub Actions and GitHub Pages. Pages is configured to use **GitHub Actions** as its source.
