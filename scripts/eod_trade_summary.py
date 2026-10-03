#!/usr/bin/env python3
"""Compact gross P/L summary for Telegram EOD notification."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

EVENTS=Path("data/paper/events")
STATE=Path("data/paper/state.json")

def day():
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")

def load_events():
    rows=[]
    if not EVENTS.exists(): return rows
    for p in sorted(EVENTS.glob("*.json")):
        try:
            x=json.loads(p.read_text(encoding="utf-8"))
            x=x.get("event", x) if isinstance(x,dict) else {}
            ts=str(x.get("timestamp") or x.get("submitted_at") or "")
            if ts.startswith(day()): rows.append(x)
        except (OSError,json.JSONDecodeError): pass
    return rows

def main():
    events=load_events(); buys=[e for e in events if str(e.get("side","")).upper()=="BUY"]; sells=[e for e in events if str(e.get("side","")).upper()=="SELL"]
    total=0.0
    lines=["BOUGHT:"]
    lines += [f"- {e.get('symbol')} x{e.get('quantity',e.get('qty',0))} @ ₹{float(e.get('price',0) or 0):.2f}" for e in buys[:15]] or ["- None"]
    lines.append("SOLD:")
    for e in sells[:15]:
        pnl=float(e.get("pnl",e.get("realized_pnl",0)) or 0); total+=pnl
        lines.append(f"- {e.get('symbol')} x{e.get('quantity',e.get('qty',0))} ₹{float(e.get('price',0) or 0):.2f} | P/L ₹{pnl:.2f} | {e.get('reason','')}")
    if not sells: lines.append("- None")
    state={}
    try: state=json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError): pass
    unrealized=0.0
    for p in state.get("positions",{}).values():
        try: unrealized+=float(p.get("unrealized_pnl",0) or 0)
        except (TypeError,ValueError): pass
    lines += [f"REALIZED P/L TODAY: ₹{total:.2f}",f"UNREALIZED P/L: ₹{unrealized:.2f}",f"TOTAL P/L TODAY: ₹{total+unrealized:.2f}"]
    learning=Path("public/data/eod_report.json")
    try:
        report=json.loads(learning.read_text(encoding="utf-8")); changes=report.get("learning",{}).get("changes",[])
        if changes: lines.append("Learning applied: "+", ".join(f"{x.get('setting')} {x.get('old')}→{x.get('new')}" for x in changes[:5]))
    except (OSError,json.JSONDecodeError): pass
    msg="\n".join(lines)
    print(msg[:4000])
    return 0

if __name__=="__main__": raise SystemExit(main())
