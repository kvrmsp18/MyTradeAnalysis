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
   -> Strategy Framework Evidence
   -> OpenAI + Anthropic Research Council
   -> Deterministic Risk & Funds Gates
   -> Paper Trade
   -> Position Monitoring
   -> EOD Reconciliation
   -> EOD Reverse Engineering
   -> General Optimization Proposal
   -> Out-of-Sample Validation
```

## Current implementation status

- GitHub Pages browser/PWA GUI: **deployed**
- 5-minute GitHub Actions paper-market cycle: **implemented**
- Dhan market snapshot adapter: **implemented**
- Decision-time observation ledger: **implemented**
- Deterministic paper screening/ranking evidence: **implemented**
- Buffett / Jhunjhunwala / Peter Lynch / 100 Baggers / CANSLIM evidence layer: **integrated into the decision ledger**
- OpenAI + Anthropic research-council module: **implemented and invoked by the paper cycle when credentials/models are configured**
- EOD missed-opportunity report: **implemented as diagnostic analysis**
- Full technical/SCRAP/ranking engine: **next integration stage**
- Paper execution engine: **next integration stage**
- Full EOD strategy-optimization validator: **next integration stage**
- Live orders: **disabled**

## Dhan market-data setup

The scheduled paper cycle runs on GitHub Actions, so no VPS or continuously running laptop is required.

For the current market-data collector, configure:

- `DHAN_CLIENT_ID`
- `DHAN_ACCESS_TOKEN`

`DHAN_API_KEY` is supported as a fallback credential by the collector, but it is **not required for the current paper-market snapshot path when `DHAN_ACCESS_TOKEN` is available**. There is no need to add it just for this stage. We can add/use it later if a future Dhan integration specifically requires it.

The collector never places an order. If credentials are missing, expired, rejected, or market data cannot be read, it writes `DATA_UNAVAILABLE` instead of inventing prices or signals.

The scheduled cycle runs every 5 minutes during the configured weekday UTC window and the GUI refreshes the published snapshot automatically.

## Strategy framework evidence

The paper ledger now evaluates generalized evidence from five research frameworks:

- Warren Buffett — quality, returns on capital, cash generation and balance-sheet discipline
- Rakesh Jhunjhunwala — earnings/revenue growth, sector tailwind and operating leverage
- Peter Lynch — growth relative to valuation
- 100 Baggers — reinvestment, returns on capital and growth runway
- CANSLIM / William O'Neil — earnings/sales growth, momentum, relative strength and volume confirmation

The framework layer never invents unavailable fundamentals. Missing data is explicitly marked `UNAVAILABLE`. Framework evidence contributes only a bounded research component to the generalized score; it cannot bypass deterministic risk or safety gates and cannot create a stock-specific rule.

## OpenAI + Anthropic research council

The project includes a two-model research-council design. OpenAI and Anthropic review the same evidence independently, challenge each other's reasoning, and produce a research consensus covering evidence, contradictions, uncertainty and data gaps.

The paper cycle now runs the council after verified market collection and before the decision-time ledger is persisted. If either provider is unavailable, the ledger records the unavailable/quorum state rather than inventing an AI opinion.

This is deliberately **not an autonomous order-execution layer**. The AI council cannot bypass deterministic capital, risk, liquidity, position, loss-limit or reconciliation gates, and no provider API key is exposed to the browser GUI.

Configure these only when we are ready to activate the council:

- `OPENAI_API_KEY` — GitHub Actions secret
- `ANTHROPIC_API_KEY` — GitHub Actions secret
- `OPENAI_MODEL` — GitHub Actions repository variable
- `ANTHROPIC_MODEL` — GitHub Actions repository variable

See `docs/AI_COUNCIL.md` for the full protocol.

## Mandatory EOD reverse engineering

After market close, the bot must inspect the eligible universe for shares that actually made meaningful profitable moves and determine why the bot missed them using evidence available **at decision time**.

The current EOD diagnostic reads the persisted intraday ledgers and compares each decision-time observation with later same-session observations. A forward move above the configured generalized threshold is flagged for review. The report explicitly distinguishes a profitable forward move from proof that an executable trade was guaranteed.

The system records decision-time quotes/features, strategy-framework evidence, ranking, analysis-pool membership, rejection reason, capital/capacity and risk-gate state. The EOD report then groups misses by generalized reasons instead of creating rules for individual stocks.

## No stock-specific learning

This is a hard requirement. A profitable outcome for one stock must **never** create a special rule, exception, permanent priority, forced watchlist entry, or stock-specific threshold. General strategy changes require repeated evidence across multiple unrelated symbols and/or sessions. Risk, liquidity, capital and reconciliation protections cannot be weakened because of hindsight winners.

EOD analysis may propose a **general** optimization, but it must be tested/backtested and validated before activation. The current EOD report does **not** modify the active strategy automatically.

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
- Automatic strategy mutation: **OFF**.

## Development rule

For major code changes, replace complete files rather than applying fragile partial patches, matching the project's established development workflow.

## GUI deployment

The browser/PWA GUI is deployed through GitHub Actions and GitHub Pages. Pages is configured to use **GitHub Actions** as its source.
