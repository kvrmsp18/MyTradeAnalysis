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
- [ ] Add Paper/Live mode UI with Live locked off during validation

## Phase 3 — Market engine
- [ ] Connect real Dhan market-data path
- [x] Build complete NSE universe loader (scripts/universe.py; the live full-market scan needs the Dhan Data API)
- [ ] Implement dynamic rotating analysis pool
- [ ] Persist decision-time evidence for every candidate and rejection

## Phase 4 — EOD learning
- [ ] Universe-wide profitable-move detector
- [ ] Miss-reason classifier
- [ ] Analysis Error Score
- [ ] Opportunity Miss Score
- [ ] Cross-symbol pattern aggregation
- [ ] General optimization proposal + validation workflow

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
