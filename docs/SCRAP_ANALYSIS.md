# Technical / SCRAP Analysis Layer

The paper-trading pipeline now runs a deterministic technical-analysis layer after the Dhan quote snapshot and before the AI research council.

## SCRAP components

- **S — Structure:** EMA 9/20/50 alignment and price-vs-trend structure.
- **C — Confirmation:** RSI and volume confirmation.
- **R — Relative strength:** position near the recent 20-session range high and range location.
- **A — Actionability:** breakout proximity, volume confirmation and short-term trend alignment.
- **P — Protection:** ATR/price volatility context and overextension checks.

The result is a normalized technical score with `REVIEW`, `WATCH`, or `OBSERVE` status.

## Data integrity

- Historical candles are requested from Dhan at decision time.
- No missing indicator is invented.
- Insufficient candle history produces `INSUFFICIENT_DATA`.
- The layer is paper-only and cannot submit broker orders.
- The analysis is generalized across the universe; it never creates a special rule for one symbol.
- The raw result is persisted to `public/data/scrap_analysis.json` so the decision-time pipeline can audit exactly what evidence was available.

## Pipeline order

`Dhan snapshot -> SCRAP technical analysis -> OpenAI/Anthropic council -> decision ledger -> paper execution`

The deterministic risk gates remain authoritative over any AI recommendation.
