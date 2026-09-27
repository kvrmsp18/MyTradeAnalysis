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
Validation / backtest / approval
      |
      v
Future paper strategy version
```

## Deployment direction

The current phase is designed for a free cloud/browser workflow. The dashboard is a PWA and the paper engine can use scheduled cloud execution. A VPS is not required for the current paper-only phase.

## Runtime principle

The dashboard is an observation/control surface. The trading engine remains authoritative. The UI cannot bypass risk or execution gates.
