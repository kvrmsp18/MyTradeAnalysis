#!/usr/bin/env python3
"""End-of-day paper-trading summary: shares bought, shares sold, day's total P/L (+ learning note).
Reads data/paper/state.json (trades + any open positions) and, for open positions, the latest
snapshot price. Writes public/data/eod_trade_summary.json and, with --text, prints a Telegram-ready
message body. P/L is gross paper P/L: brokerage, taxes and slippage are not modelled.
 python scripts/eod_trade_summary.py --text [--date YYYY-MM-DD]
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
STATE = Path("data/paper/state.json")
SNAPSHOT = Path("public/data/market_snapshot.json")
EOD_REPORT = Path("public/data/eod_report.json")
OUT = Path("public/data/eod_trade_summary.json")
IST = ZoneInfo("Asia/Kolkata")
# Telegram rejects messages over 4096 characters; the totals must always fit, so long lists are cut.
MAX_LINES = 15
def load(path: Path) -> dict:
 try:
 value = json.loads(path.read_text(encoding="utf-8"))
 return value if isinstance(value, dict) else {}
 except (OSError, json.JSONDecodeError):
 return {}
def ist_date(ts: object):
 try:
 return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(IST).date()
 except (TypeError, ValueError):
 return None
def money(x: float) -> str:
 return f"{'+' if x >= 0 else '-'}Rs.{abs(x):,.2f}"
def build(day: str | None = None) -> dict:
 target = datetime.strptime(day, "%Y-%m-%d").date() if day else datetime.now(IST).date()
 state, snapshot = load(STATE), load(SNAPSHOT)
 prices = {str(r.get("symbol")): r.get("price") for r in snapshot.get("stocks", []) if r.get("symbol")}
 trades = [t for t in state.get("trades", []) if ist_date(t.get("timestamp")) == target]
 buys = [{"symbol": t["symbol"], "quantity": t.get("quantity"), "price": t.get("price"), "time_ist": 
_hhmm(t.get("timestamp"))}
 for t in trades if t.get("side") == "BUY"]
 sells = [{"symbol": t["symbol"], "quantity": t.get("quantity"), "entry_price": t.get("entry_price"), 
"exit_price": t.get("price"),
 "pnl": round(float(t.get("pnl") or 0), 2), "reason": t.get("reason"), "time_ist": 
_hhmm(t.get("timestamp"))}
 for t in trades if t.get("side") == "SELL"]
 realized = round(sum(s["pnl"] for s in sells), 2)
 open_positions, unrealized = [], 0.0
 for symbol, pos in (state.get("positions") or {}).items():
 try:
 last = float(prices.get(symbol))
 pnl = round((last - float(pos["entry_price"])) * int(pos["quantity"]), 2)
 except (TypeError, ValueError, KeyError):
 last, pnl = None, 0.0
 unrealized += pnl
<PARSED TEXT FOR PAGE: 23 / 56>
 open_positions.append({"symbol": symbol, "quantity": pos.get("quantity"), "entry_price": 
pos.get("entry_price"),
 "last_price": last, "unrealized_pnl": pnl})
 unrealized = round(unrealized, 2)
 learning = load(EOD_REPORT).get("learning") or {}
 return {
 "schema_version": "1.0", "mode": "PAPER", "date_ist": target.isoformat(),
 "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
 "buys": buys, "sells": sells, "open_positions": open_positions,
 "realized_pnl": realized, "unrealized_pnl": unrealized, "total_pnl": round(realized + unrealized, 2),
 "wins": sum(1 for s in sells if s["pnl"] > 0), "losses": sum(1 for s in sells if s["pnl"] < 0),
 "learning_changes": learning.get("changes", []),
 "note": "Gross paper P/L; brokerage, taxes and slippage are not modelled.",
 }
def _hhmm(ts: object) -> str:
 try:
 return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(IST).strftime("%H:%M")
 except (TypeError, ValueError):
 return "--:--"
def text(s: dict) -> str:
 lines = [f"EOD paper trades - {s['date_ist']}"]
 if not s["buys"] and not s["sells"] and not s["open_positions"]:
 lines.append("No paper trades today.")
 if s["buys"]:
 lines.append("")
 lines.append(f"BOUGHT ({len(s['buys'])}):")
 lines += [f" {b['symbol']} x{b['quantity']} @ Rs.{b['price']} ({b['time_ist']})" for b in s["buys"]
[:MAX_LINES]]
 if len(s["buys"]) > MAX_LINES:
 lines.append(f" ... +{len(s['buys']) - MAX_LINES} more (see 
public/data/eod_trade_summary.json)")
 if s["sells"]:
 lines.append("")
 lines.append(f"SOLD ({len(s['sells'])}):")
 lines += [f" {x['symbol']} x{x['quantity']} {x['entry_price']} -> {x['exit_price']} 
{money(x['pnl'])} [{x['reason']}]" for x in s["sells"][:MAX_LINES]]
 if len(s["sells"]) > MAX_LINES:
 lines.append(f" ... +{len(s['sells']) - MAX_LINES} more (see 
public/data/eod_trade_summary.json)")
 if s["open_positions"]:
 lines.append("")
 lines.append("STILL OPEN (should be none after EOD exit):")
 lines += [f" {p['symbol']} x{p['quantity']} unrealized {money(p['unrealized_pnl'])}" for p in 
s["open_positions"]]
 lines += ["", f"Realized P/L: {money(s['realized_pnl'])} (wins {s['wins']}, losses {s['losses']})",
 f"Unrealized P/L: {money(s['unrealized_pnl'])}", f"TOTAL P/L TODAY: {money(s['total_pnl'])}"]
 if s["learning_changes"]:
 lines.append("")
 lines.append("Learning applied (general thresholds):")
 lines += [f" {c['parameter']}: {c['from']} -> {c['to']}" for c in s["learning_changes"]]
 lines += ["", s["note"]]
 return "\n".join(lines)
def main(argv: list[str]) -> int:
 day = argv[argv.index("--date") + 1] if "--date" in argv else None
 summary = build(day)
 OUT.parent.mkdir(parents=True, exist_ok=True)
 OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
 if "--text" in argv:
 print(text(summary))
 return 0
if __name__ == "__main__":
 raise SystemExit(main(sys.argv[1:]))