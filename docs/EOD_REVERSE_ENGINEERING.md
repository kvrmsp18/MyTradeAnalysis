# EOD Reverse Engineering Specification

## Objective
At market close, determine which eligible shares actually produced profitable intraday opportunities and determine, using decision-time evidence, why the bot did or did not select them.

## Required process
1. Freeze the decision-time dataset for the session.
2. Evaluate the eligible universe using actual market outcomes.
3. Identify meaningful profitable moves that were not captured.
4. Join each outcome to the bot's decision-time evidence.
5. Classify the miss reason.
6. Calculate Analysis Error Score separately from Opportunity Miss Score.
7. Aggregate the same failure reason across symbols and sessions.
8. Generate general optimization candidates only when cross-symbol evidence supports them.
9. Validate candidates through tests/backtests before activation.
10. Record the optimization version and rationale for auditability.

## Guardrails
- Never optimize toward one named share.
- Never add a permanent stock-specific exception because it made money.
- Never treat hindsight profitability alone as proof of a bad decision.
- Never weaken risk, capital, liquidity or reconciliation controls to capture a hindsight winner.
- Never let AI silently change production parameters.

## Example
If five unrelated stocks were missed because the deep-analysis pool was too narrow under the same market conditions, the system may propose a general capacity/ranking change. If only one stock was missed, that is an observation and cannot create a stock-specific rule.
