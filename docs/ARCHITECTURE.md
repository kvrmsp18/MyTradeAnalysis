# MyTradeAnalysis Architecture

```text
Real market data
      |
      v
Universe observation -> dynamic ranking -> bounded deep analysis
      |                         |
      |                         +--> technical / SCRAP / research / AI advisory
      v
Deterministic setup + risk gates
      |
      v
Paper execution -> position monitoring -> EOD square-off
      |
      v
Persistent decision-time evidence
      |
      v
EOD Reverse Engineering
      |
      +--> profitable universe moves
      +--> missed-opportunity classification
      +--> Analysis Error Score
      +--> Opportunity Miss Score
      +--> cross-symbol pattern detection
      +--> general optimization proposal
      |
      v
Validation / bounded general learning
      |
      v
Decision authorization
      |
      +--> PAPER executor
      |
      +--> LIVE Dhan executor -> broker reconciliation

```

## Deployment direction

The current phase is designed for a free cloud/browser workflow. The dashboard is a PWA and the paper engine can use scheduled cloud execution. A VPS is not required for the current paper-only phase.

## Runtime principle

The dashboard is an observation/control surface. The trading engine remains authoritative. The UI cannot bypass risk or execution gates.


## Live execution architecture

The same decision-time ledger feeds both execution modes. The live path is server-side only:

```text
Dynamic NSE universe -> SCRAP -> OpenAI/Anthropic council -> deterministic gates
                                      |
                                      v
                              decision-time ledger
                               /              \\
                         PAPER executor    LIVE executor
                                             |
                                             v
                                      Dhan order API
                                             |
                                             v
                                      broker reconciliation
```

Live orders are fail-closed unless all of these are true: `TRADING_MODE=LIVE`, `LIVE_TRADING_ENABLED=1`, `LIVE_TRADING_CONFIRMATION=I_UNDERSTAND_LIVE_ORDERS`, `LIVE_KILL_SWITCH!=1`, and the required Dhan credentials are present. The browser is never given broker credentials and cannot directly submit an order.

The live engine manages existing intraday positions for target, stop-loss and end-of-day exits before opening new positions. It requires primary Dhan market data, current broker funds, an available per-symbol AI `SUPPORT` verdict, position limits, and the daily-loss gate.
