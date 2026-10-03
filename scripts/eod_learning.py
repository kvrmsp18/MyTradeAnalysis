#!/usr/bin/env python3
"""Analyze paper observations plus broad-market EOD movers.
Research-only diagnostic layer. It connects historical intraday reconstruction
with the paper engine's recorded decision evidence, but never creates
stock-specific rules or mutates strategy configuration automatically.
"""
from __future__ import annotations
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
LEDGER_ROOT = Path("data/ledger")
MARKET_OPPORTUNITIES = Path("public/data/eod_market_opportunities.json")
RECONSTRUCTION = Path("public/data/eod_intraday_reconstruction.json")
OUT = Path("public/data/eod_report.json")
THRESHOLD = float(os.getenv("MISSED_MOVE_THRESHOLD_PCT", "1.0"))
STATE = Path("data/paper/state.json")
# A REVIEW candidate that was NOT filled for one of these reasons is a real capture miss.
EXECUTION_MISS_REASONS = {
 "FEATURE_SCORE_BELOW_THRESHOLD", "SCRAP_SCORE_BELOW_THRESHOLD", "MAX_POSITIONS_REACHED", 
"INSUFFICIENT_CAPITAL",
}
try:
 import sys as _sys
 _sys.path.insert(0, str(Path(__file__).resolve().parent))
 import learning_policy
except Exception: # pragma: no cover
 learning_policy = None
def load_today() -> tuple[str, list[dict]]:
 day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
 folder = LEDGER_ROOT / day
 rows: list[dict] = []
 if folder.exists():
 for path in sorted(folder.glob("*.json")):
 try:
 rows.append(json.loads(path.read_text(encoding="utf-8")))
 except (OSError, json.JSONDecodeError):
 continue
 return day, rows
def price(item: dict) -> float | None:
 try:
 value = float(item.get("quote", {}).get("price"))
 return value if value > 0 else None
 except (TypeError, ValueError):
 return None
def analyze_ledger(day: str, ledgers: list[dict]) -> tuple[list[dict], Counter[str], int]:
 by_symbol: dict[str, list[tuple[datetime, dict]]] = defaultdict(list)
 for ledger in ledgers:
 try:
 ts = datetime.fromisoformat(str(ledger["timestamp"]).replace("Z", "+00:00"))
 except (KeyError, ValueError):
 continue
 for candidate in ledger.get("candidates", []):
 symbol = candidate.get("symbol")
 if symbol:
 by_symbol[str(symbol)].append((ts, candidate))
 misses: list[dict] = []
 reason_counts: Counter[str] = Counter()
<PARSED TEXT FOR PAGE: 18 / 56>
 reason_symbols: dict[str, set[str]] = defaultdict(set)
 profitable_symbols: set[str] = set()
 for symbol, observations in by_symbol.items():
 observations.sort(key=lambda x: x[0])
 for index, (ts, current) in enumerate(observations):
 current_price = price(current)
 if current_price is None:
 continue
 future = [(future_ts, price(candidate)) for future_ts, candidate in observations[index + 1:]]
 future = [(future_ts, p) for future_ts, p in future if p is not None]
 if not future:
 continue
 max_future = max(future, key=lambda x: x[1])
 max_return = (max_future[1] - current_price) / current_price * 100.0
 if max_return < THRESHOLD:
 continue
 profitable_symbols.add(symbol)
 decision = current.get("decision")
 if decision == "REVIEW":
 execution = current.get("execution") or {}
 skip = execution.get("reason")
 if execution.get("order_submitted") or skip not in EXECUTION_MISS_REASONS:
 continue
 reason = f"EXECUTION_{skip}"
 else:
 reason = current.get("rejection_reason") or "UNKNOWN"
 reason_counts[reason] += 1
 reason_symbols[reason].add(symbol)
 misses.append({
 "source": "paper_observation",
 "symbol": symbol,
 "decision_timestamp": ts.isoformat().replace("+00:00", "Z"),
 "decision": decision,
 "reason": reason,
 "decision_price": round(current_price, 4),
 "best_observed_future_price": round(max_future[1], 4),
 "best_forward_return_pct": round(max_return, 3),
 "generalized_factors": current.get("features", {}).get("factors", []),
 "reconstruction": {"status": "NOT_APPLICABLE", "note": "Symbol was already evaluated; paper 
decision evidence is the primary source."},
 })
 return misses, reason_counts, len(profitable_symbols) # distinct shares, not 5-minute observations
def load_external_movers() -> dict:
 if not MARKET_OPPORTUNITIES.exists():
 return {"status": "NOT_RUN", "stocks": []}
 try:
 value = json.loads(MARKET_OPPORTUNITIES.read_text(encoding="utf-8"))
 return value if isinstance(value, dict) else {"status": "INVALID", "stocks": []}
 except (OSError, json.JSONDecodeError):
 return {"status": "INVALID", "stocks": []}
def load_reconstruction() -> dict:
 if not RECONSTRUCTION.exists():
 return {"status": "NOT_RUN", "rows": []}
 try:
 value = json.loads(RECONSTRUCTION.read_text(encoding="utf-8"))
 return value if isinstance(value, dict) else {"status": "INVALID", "rows": []}
 except (OSError, json.JSONDecodeError):
 return {"status": "INVALID", "rows": []}
def external_misses(movers: dict, reconstruction: dict, evaluated_symbols: set[str]) -> list[dict]:
 misses: list[dict] = []
 recon_map = {str(row.get("symbol")): row for row in reconstruction.get("rows", []) if row.get("symbol")}
 if movers.get("status") != "READY":
 return misses
 for row in movers.get("stocks", []):
 symbol = str(row.get("symbol") or "")
 if not symbol or symbol in evaluated_symbols:
<PARSED TEXT FOR PAGE: 19 / 56>
 continue
 try:
 move_f = float(row.get("change_pct"))
 except (TypeError, ValueError):
 continue
 if abs(move_f) < THRESHOLD:
 continue
 recon = recon_map.get(symbol, {})
 recon_payload = recon.get("reconstruction", {}) if isinstance(recon, dict) else {}
 setup = recon_payload.get("first_reconstructed_setup") if isinstance(recon_payload, dict) else None
 setup_found = bool(recon_payload.get("setup_found")) if isinstance(recon_payload, dict) else False
 if setup_found:
 reason = "NOT_IN_PAPER_CANDIDATE_UNIVERSE_WITH_RECONSTRUCTED_SETUP"
 interpretation = "A historical technical setup was reconstructed, but the symbol was outside the 
paper engine's evaluated universe. This is evidence for universe/selection review, not an execution 
authorization."
 elif recon.get("reconstruction", {}).get("status") == "UNAVAILABLE":
 reason = "NOT_IN_PAPER_CANDIDATE_UNIVERSE_RECONSTRUCTION_UNAVAILABLE"
 interpretation = "The symbol was a material EOD mover outside the evaluated universe, but 
historical reconstruction was unavailable; no executable setup is claimed."
 else:
 reason = "NOT_IN_PAPER_CANDIDATE_UNIVERSE_NO_RECONSTRUCTED_SETUP"
 interpretation = "The symbol moved materially but the reconstruction heuristic did not find the 
configured setup; no executable missed trade is claimed."
 misses.append({
 "source": "broad_market_eod_scan",
 "symbol": symbol,
 "decision_timestamp": movers.get("generated_at"),
 "decision": "NOT_EVALUATED",
 "reason": reason,
 "eod_price": row.get("price"),
 "prev_close": row.get("prev_close"),
 "eod_move_pct": move_f,
 "observable_evidence": {"open": row.get("open"), "high": row.get("high"), "low": row.get("low"), 
"volume": row.get("volume")},
 "intraday_reconstruction": {
 "status": "FOUND_SETUP" if setup_found else recon.get("reconstruction", {}).get("status", 
reconstruction.get("status")),
 "first_reconstructed_setup": setup,
 "method": recon_payload.get("method") if isinstance(recon_payload, dict) else None,
 },
 "interpretation": interpretation,
 })
 return misses
def analyze(day: str, ledgers: list[dict]) -> dict:
 ledger_misses, reason_counts, realized_candidates = analyze_ledger(day, ledgers)
 evaluated_symbols = {str(c.get("symbol")) for l in ledgers for c in l.get("candidates", []) if 
c.get("symbol")}
 paper_orders_submitted = sum(
 1
 for ledger in ledgers
 for candidate in ledger.get("candidates", [])
 if bool(candidate.get("execution", {}).get("order_submitted"))
 )
 review_candidates = sum(int(ledger.get("review_candidates", 0) or 0) for ledger in ledgers)
 movers = load_external_movers()
 reconstruction = load_reconstruction()
 market_misses = external_misses(movers, reconstruction, evaluated_symbols)
 all_misses = ledger_misses + market_misses
 reason_symbols: dict[str, set[str]] = defaultdict(set)
 all_reason_counts: Counter[str] = Counter()
 for item in all_misses:
 reason = str(item.get("reason") or "UNKNOWN")
 all_reason_counts[reason] += 1
 reason_symbols[reason].add(str(item.get("symbol") or "UNKNOWN"))
 pattern_candidates = [(reason, len(symbols)) for reason, symbols in reason_symbols.items() if 
len(symbols) >= 3]
<PARSED TEXT FOR PAGE: 20 / 56>
 patterns = [
 {
 "pattern": reason,
 "distinct_symbols": distinct_symbols,
 "occurrences": all_reason_counts[reason],
 "action": "Review the generalized universe/threshold/feature interaction across multiple symbols;
do not create a symbol-specific rule.",
 }
 for reason, distinct_symbols in sorted(pattern_candidates, key=lambda x: (-x[1], 
-all_reason_counts[x[0]], x[0]))
 ]
 reconstructed_setups = sum(1 for x in market_misses if x.get("intraday_reconstruction", {}).get("status")
== "FOUND_SETUP")
 return {
 "schema_version": "2.1",
 "status": "READY" if (ledgers or movers.get("status") == "READY") else "NOT_READY",
 "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
 "trading_day_utc": day,
 "source_ledger_count": len(ledgers),
 "evaluated_symbol_count": len(evaluated_symbols),
 "broad_market_scan_status": movers.get("status"),
 "broad_market_mover_count": len(movers.get("stocks", [])),
 "intraday_reconstruction_status": reconstruction.get("status"),
 "external_movers_with_reconstructed_setup": reconstructed_setups,
 "profitable_forward_moves_in_ledger": realized_candidates,
 "paper_orders_submitted": paper_orders_submitted,
 "review_candidates_seen": review_candidates,
 "no_trade_day": bool(ledgers) and paper_orders_submitted == 0,
 "no_trade_day_explanation": (
 "No paper order was submitted during the trading day; EOD analysis still scans broad-market 
movers and reconstructs candidate setups."
 if ledgers and paper_orders_submitted == 0
 else "Paper orders were submitted or no usable intraday ledger exists."
 ),
 "missed_opportunities": all_misses,
 "general_patterns": patterns,
 "threshold_pct": THRESHOLD,
 "optimization_policy": {
 "stock_specific_rules_allowed": False,
 # Bounded, general parameters only (see scripts/learning_policy.py). Never a symbol rule,
 # never capital/risk limits, always logged, reversible with LEARNING_ENABLED=0.
 "automatic_strategy_mutation": "BOUNDED_GENERAL_PARAMETERS_ONLY",
 "required_next_step": "Review data/learning/policy.json log; delete it or set LEARNING_ENABLED=0 
to reset.",
 },
 "limitations": [
 "An EOD move alone is not proof that an executable trade existed at the decision price.",
 "A reconstructed setup is a historical heuristic and is not a trade authorization.",
 "The broad-market scan currently reconstructs only the configured top movers, not every NSE 
symbol.",
 "The report never changes strategy code; it only nudges bounded general thresholds via 
data/learning/policy.json.",
 ],
 }
def day_stats(day: str) -> dict:
 """Realized P/L and stop-loss exits for the trading day, from the paper account trades."""
 try:
 trades = json.loads(STATE.read_text(encoding="utf-8")).get("trades", [])
 except (OSError, json.JSONDecodeError, AttributeError):
 trades = []
 sells = [t for t in trades if t.get("side") == "SELL" and str(t.get("timestamp", ""))[:10] == day]
 return {
 "realized_pnl": round(sum(float(t.get("pnl") or 0) for t in sells), 2),
 "sell_count": len(sells),
 "stop_loss_exits": sum(1 for t in sells if t.get("reason") == "STOP_LOSS"),
 }
<PARSED TEXT FOR PAGE: 21 / 56>
def apply_and_save(report: dict, day: str, persist: bool = True) -> dict:
 """Feed the EOD findings back into the bot (bounded, general, logged). Returns the report."""
 if learning_policy is None:
 report["learning"] = {"enabled": False, "reason": "learning_policy module unavailable"}
 return report
 stats = day_stats(day)
 outcome = learning_policy.apply_learning(day, report.get("general_patterns", []), stats)
 if persist:
 learning_policy.save(outcome["policy"])
 report["learning"] = {
 "enabled": learning_policy.enabled(),
 "day_stats": stats,
 "changes": outcome["changes"],
 "skipped": outcome["skipped"][:20],
 "effective_policy_for_next_session": learning_policy.effective(outcome["policy"]),
 "scope": "general thresholds only; no stock-specific rule; capital/risk limits untouched",
 }
 return report
def main() -> int:
 day, ledgers = load_today()
 report = apply_and_save(analyze(day, ledgers), day)
 OUT.parent.mkdir(parents=True, exist_ok=True)
 OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
 print(f"Wrote {OUT}: {len(report['missed_opportunities'])} missed/discovery opportunities; 
{report['external_movers_with_reconstructed_setup']} reconstructed external setups")
 return 0
if __name__ == "__main__":
 raise SystemExit(main())