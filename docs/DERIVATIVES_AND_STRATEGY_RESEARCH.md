# Derivatives and Strategy Research — Integration Plan

## Scope

This work adds derivatives analytics and strategy research to MyTradeAnalysis without changing the live-order path. The first implementation is a deterministic, dependency-free analytics module; it does not submit orders and does not treat an analytics label as an execution instruction.

## First slice delivered

- Black–Scholes call/put delta, gamma, vega and theta calculations, with explicit units and validation.
- Normalized option-chain summaries: total call/put OI and volume, PCR (OI and volume), max-pain estimate, mean IV, and IV rank/percentile when a historical IV sample is supplied.
- Nearest-strike Greeks are produced only when spot, strike, IV and time-to-expiry are all available.
- Missing/invalid data stays unavailable or partial. No prices, expiry, volatility or Greeks are fabricated.
- Self-test runnable with `python scripts/derivatives_analysis_self_test.py`.

## Next integration slices

1. **Market-data adapter:** identify a supported Dhan endpoint and instrument master for NSE index/stock options and futures; preserve source timestamp, expiry, strike, lot size, instrument/security ID and quote freshness. Do not assume equity-only quote APIs provide option-chain data.
2. **Research payload:** publish a timestamped derivatives snapshot and expose it in the GUI as a new Derivatives/Options view. Keep raw evidence alongside calculated fields.
3. **Strategy registry:** implement ATR/range expansion, breakout, trend/VWAP, pairs/cointegration and defined-risk option templates behind a common interface. Every strategy must state eligible instruments, required data, regime assumptions, entry/exit logic, maximum loss and expiry handling.
4. **Backtest harness:** use time-ordered data, no look-ahead, walk-forward/out-of-sample splits, realistic fills, slippage, brokerage, taxes and expiry-aware option pricing. Label in-sample results as indicative only.
5. **Portfolio/risk gate:** evaluate aggregate exposure, margin, liquidity, spread, max loss, correlated positions, position limits, daily loss and exit capability before any order. The deterministic risk engine—not an AI model—has final authority.
6. **AI research council:** have OpenAI and Anthropic review the same timestamped evidence independently and cross-critique. Provider failure or insufficient quorum must be explicit; no fabricated consensus.
7. **Execution integration:** paper first for new derivatives strategies. Live support remains disabled until data contract, broker product types, lot-size/quantity rules, margin checks, order/position reconciliation, kill-switch and dedicated tests pass. Existing live equity execution must not be silently repurposed for options.
8. **EOD learning:** report missed opportunities and strategy performance across multiple symbols/sessions. Only propose generalized parameter changes; require out-of-sample validation and human approval before activation.

## Important limits

- PCR, max pain, OI buildup and IV metrics are contextual evidence, not reliable standalone directional predictions.
- Black–Scholes is an approximation; American exercise, dividends, volatility skew, discrete markets and Indian contract details can materially affect values.
- The current module expects a normalized option chain and historical IV supplied by a trusted upstream source. It does not yet fetch live option-chain data.
- This PR is a research foundation, not proof that derivatives live trading is ready.
