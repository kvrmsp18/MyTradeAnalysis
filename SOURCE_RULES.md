# Source & Safety Rules

## Paper trading
- PAPER mode is the default and only enabled execution mode during validation.
- Live Dhan order submission must remain disabled.
- AI cannot override deterministic risk, funds, data-quality, execution or reconciliation gates.

## EOD reverse engineering — mandatory
After every market session, the bot must inspect the eligible universe for stocks that produced meaningful profitable moves and compare those outcomes with the evidence available at the bot's original decision time.

For every missed opportunity, persist:
- decision timestamp
- quote/indicator snapshot
- market regime
- SCRAP/research result
- ranking/deep-analysis status
- rejection or exclusion reason
- available paper capital and required capital
- liquidity/risk/capacity gates
- eventual market outcome

The bot must classify why an opportunity was missed, for example:
- data unavailable
- universe/ranking exclusion
- deep-analysis capacity
- technical setup rejected
- market-regime gate
- SCRAP/research rejection
- risk/reward gate
- capital/capacity constraint
- duplicate/position constraint
- protective risk control
- other validated reason

## No stock-specific learning
A single stock's profitable outcome must NEVER create a rule, exception, permanent priority, forced watchlist entry, threshold, or special handling for that stock.

Optimization candidates are allowed only when the same failure pattern is observed across multiple symbols/sessions and the proposed change is expressed as a general rule or parameter. Protective capital, liquidity, risk and capacity controls cannot be weakened merely because a missed stock later became profitable.

## Two separate measures
- **Analysis Error Score:** evidence that the bot's analysis/decision logic was wrong at decision time.
- **Opportunity Miss Score:** profitable opportunity the system did not capture, even if the original rejection was correct.

A profitable outcome alone is not proof of an analysis error.

## Controlled optimization
EOD analysis may produce a proposed general optimization. It must be recorded, explained, tested/backtested where possible, and validated before becoming active. No automatic self-modification of production trading rules is permitted during paper validation.
