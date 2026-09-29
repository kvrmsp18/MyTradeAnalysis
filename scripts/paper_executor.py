#!/usr/bin/env python3
"""Deterministic paper execution engine. Never sends broker orders."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

LEDGER_ROOT=Path("data/ledger")
STATE=Path("data/paper/state.json")
EVENTS=Path("data/paper/events")
SNAPSHOT=Path("public/data/market_snapshot.json")
CAPITAL=float(os.getenv("PAPER_STARTING_CAPITAL","1000"))
MAX_POS_PCT=float(os.getenv("PAPER_MAX_POSITION_PCT","20"))
TARGET_PCT=float(os.getenv("PAPER_TARGET_PCT","2.0"))
STOP_PCT=float(os.getenv("PAPER_STOP_PCT","1.0"))
MAX_POSITIONS=int(os.getenv("PAPER_MAX_POSITIONS","2"))

def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def read(p,default):
    try:
        x=json.loads(p.read_text(encoding="utf-8")); return x if isinstance(x,dict) else default
    except Exception: return default
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(x,indent=2),encoding="utf-8")
def latest_ledger():
    files=sorted(LEDGER_ROOT.glob("*/[0-9]*.json"))
    return files[-1] if files else None
def price(c):
    try: return float(c.get("quote",{}).get("price"))
    except Exception: return None

def main():
    lp=latest_ledger()
    if not lp: print("No ledger; no paper execution."); return 0
    ledger=read(lp,{})
    snapshot=read(SNAPSHOT,{})
    if ledger.get("mode")!="PAPER" or snapshot.get("status") not in ("LIVE_MARKET_DATA","LIVE_MARKET_DATA_FALLBACK"):
        print("No live market snapshot or non-paper ledger; no execution."); return 0
    state=read(STATE,{"schema_version":"1.0","cash":CAPITAL,"positions":{},"realized_pnl":0.0,"trades":[],"last_processed_ledger":None})
    if state.get("last_processed_ledger")==str(lp):
        print("Ledger already processed."); return 0
    state.setdefault("cash",CAPITAL); state.setdefault("positions",{}); state.setdefault("realized_pnl",0.0); state.setdefault("trades",[])
    events=[]
    quote_map={str(s.get("symbol")):s for s in snapshot.get("stocks",[]) if s.get("symbol")}
    test_clock=os.getenv("PAPER_ENGINE_TEST_TIME_IST")
    if test_clock:
        ist=datetime.strptime(test_clock, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    else:
        ist=datetime.now(ZoneInfo("Asia/Kolkata"))
    market_minutes=ist.hour*60+ist.minute
    eod_exit=ist.weekday()<5 and market_minutes>=15*60+29
    entry_allowed=ist.weekday()<5 and 9*60+15<=market_minutes<15*60+25

    for symbol,pos in list(state["positions"].items()):
        q=quote_map.get(symbol); p=price({"quote":q}) if q else None
        if p is None: continue
        entry=float(pos["entry_price"]); qty=int(pos["quantity"]); ret=(p-entry)/entry*100
        reason="EOD_EXIT" if eod_exit else ("TARGET" if ret>=TARGET_PCT else ("STOP_LOSS" if ret<=-STOP_PCT else None))
        if reason:
            proceeds=p*qty; pnl=(p-entry)*qty
            state["cash"]=round(state["cash"]+proceeds,2); state["realized_pnl"]=round(state["realized_pnl"]+pnl,2)
            trade={"side":"SELL","symbol":symbol,"quantity":qty,"price":p,"entry_price":entry,"pnl":round(pnl,2),"reason":reason,"timestamp":now()}
            state["trades"].append(trade); del state["positions"][symbol]; events.append(trade)
    open_count=len(state["positions"]); position_value_cap=state["cash"]*MAX_POS_PCT/100
    if not entry_allowed:
        candidates=[]
    else:
        candidates=[c for c in ledger.get("candidates",[]) if c.get("decision")=="REVIEW" and c.get("features",{}).get("score",0)>=65]
        candidates.sort(key=lambda c:c.get("ranking",9999))
    for c in candidates:
        if open_count>=MAX_POSITIONS: break
        symbol=str(c.get("symbol")); p=price(c)
        if not symbol or p is None or symbol in state["positions"] or p<=0: continue
        try: ss=float(c.get("scrap_result",{}).get("score"))
        except Exception: continue
        if ss<60: continue
        qty=int(position_value_cap//p)
        if qty<1 or qty*p>state["cash"]: continue
        cost=qty*p; state["cash"]=round(state["cash"]-cost,2)
        state["positions"][symbol]={"quantity":qty,"entry_price":p,"entry_time":now(),"target_price":round(p*(1+TARGET_PCT/100),4),"stop_price":round(p*(1-STOP_PCT/100),4),"score":c.get("features",{}).get("score")}
        trade={"side":"BUY","symbol":symbol,"quantity":qty,"price":p,"cost":round(cost,2),"score":c.get("features",{}).get("score"),"timestamp":now()}
        state["trades"].append(trade); events.append(trade); open_count+=1
    state["last_processed_ledger"]=str(lp); save(STATE,state)
    for c in ledger.get("candidates",[]):
        sym=str(c.get("symbol")); matching=[e for e in events if e["symbol"]==sym]
        c.setdefault("execution",{}); c["execution"].update({"mode":"PAPER","order_submitted":bool(matching),"paper_events":matching,"reason":"PAPER_SIMULATED_FILL" if matching else c["execution"].get("reason","NO_PAPER_ORDER")})
    ledger["paper_account"]={"cash":state["cash"],"open_positions":state["positions"],"realized_pnl":state["realized_pnl"]}
    ledger["paper_events"]=events; ledger["safety"]["live_orders_enabled"]=False; save(lp,ledger)
    stamp=datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    for i,event in enumerate(events,1):
        save(EVENTS/f"{stamp}_{i}_{event['side'].lower()}_{event['symbol']}.json",{"schema_version":"1.0","paper_only":True,"live_trading_enabled":False,"event":event})
    print(f"Paper execution complete: {len(events)} event(s), cash={state['cash']}, realized_pnl={state['realized_pnl']}")
    return 0

if __name__=="__main__": raise SystemExit(main())
