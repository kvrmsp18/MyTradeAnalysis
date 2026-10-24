# Strategy Reference v1 — Implementation Notes

This change records the frozen strategy patterns and keeps execution disabled.

## 125-day breakout
- Current price above the highest high of the previous 125 completed daily candles.
- Current daily volume greater than 2 times the average volume of those sessions.
- Daily RSI(14) below 70.
- All three conditions must pass.

## Richie Rich 125-day breakdown
- Current price below the lowest low of the previous 125 completed daily candles.
- Current daily volume greater than the average volume of those sessions.
- Daily RSI(14) above 30.
- Recorded as a bearish warning only. It does not authorize short or options orders.

## Hourly RSI momentum
- Entry signal when hourly RSI(14) is strictly between 58 and 65.
- Target signal above 75.
- Stop signal below 40.
- Current SCRAP integration does not fetch hourly candles; it marks this strategy unavailable rather than inventing data.

## Safety and data constraints
- Daily strategies require 125 complete historical daily candles plus current price, current volume, and RSI.
- Five-minute fallback candles cannot satisfy daily strategy conditions.
- Missing or insufficient data fails closed.
- Signals are evidence only and do not bypass SCRAP, AI, capital, duplicate-order, broker, or risk gates.
- No live trading is enabled by this change.
- RSI signals are not guaranteed fills; independent protective stops remain necessary.
