# Development Roadmap

## Phase 1 — Foundation
- [x] Initialize MyTradeAnalysis repository
- [x] Define paper-only safety rules
- [x] Define EOD reverse-engineering contract
- [x] Define no-stock-specific-learning rule

## Phase 2 — Application
- [ ] Import the uploaded React/Vite dashboard as the PWA frontend
- [ ] Add paper dashboard state model
- [ ] Add Screener / Stock 360 / Paper Trading / SCRAP / Supervisor / Post-Mortem views
- [x] Add Paper/Live mode UI with server-side Live control

## Phase 3 — Market engine
- [x] Connect real Dhan market-data path
- [x] Build complete NSE universe loader (scripts/universe.py; the live full-market scan needs the Dhan Data API)
- [x] Implement dynamic rotating analysis pool
- [x] Persist decision-time evidence for every candidate and rejection

## Phase 4 — EOD learning
- [ ] Universe-wide profitable-move detector
- [ ] Miss-reason classifier
- [ ] Analysis Error Score
- [ ] Opportunity Miss Score
- [ ] Cross-symbol pattern aggregation
- [x] General optimization proposal + bounded validation/activation workflow

## Phase 5 — Cloud paper deployment
- [ ] Free-tier web hosting
- [ ] Scheduled paper cycles
- [ ] Cloud persistence
- [ ] Telegram alerts
- [ ] PWA install/offline shell

## Phase 6 — Validation
- [ ] Automated tests
- [ ] Backtest/replay validation
- [ ] Multi-session paper validation
- [ ] EOD learning audit
- [ ] Confirm no stock-specific rules are introduced

Live trading is out of scope for the current phase.

## Phase 7 — Live execution readiness
- [x] Dhan live order adapter with fail-closed gates
- [x] Live BUY execution and broker order journaling
- [x] Target / stop-loss / end-of-day live position management
- [x] Broker position/order reconciliation
- [x] Live execution safety self-test
- [x] GUI Live Trading control and runtime status
- [ ] Supply Dhan live API credential and explicit server-side Live activation
