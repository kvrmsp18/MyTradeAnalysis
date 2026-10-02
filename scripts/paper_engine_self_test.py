#!/usr/bin/env python3
"""Offline acceptance suite for the deterministic paper engine."""
from __future__ import annotations
import importlib.util, json, os, tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

EXECUTOR=Path(__file__).with_name("paper_executor.py").resolve()

def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(v,indent=2),encoding="utf-8")
def env(**v): os.environ.update({k:str(x) for k,x in v.items()})
def load(root):
    os.chdir(root); spec=importlib.util.spec_from_file_location("paper_exec_test",EXECUTOR)
    m=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(m); return m
def asof(clock):
    dt=datetime.strptime(clock,"%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00","Z")
def cand(symbol,price,score=80,scrap=75,ranking=1):
    return {"symbol":symbol,"ranking":ranking,"decision":"REVIEW","features":{"score":score},"scrap_result":{"status":"OK","score":scrap},"quote":{"price":price}}
def run(root,m,name,cands,stocks,clock,status="LIVE_MARKET_DATA",data_as_of=None):
    stamp=data_as_of or datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    write(root/"data/ledger/2026-01-01"/name,{"mode":"PAPER","timestamp":"2026-01-01T04:00:00Z","safety":{"live_orders_enabled":False},"candidates":cands})
    write(root/"public/data/market_snapshot.json",{"status":status,"timestamp":stamp,"data_as_of":stamp,"stocks":stocks})
    env(PAPER_ENGINE_TEST_TIME_IST=clock); assert m.main()==0
def state(root): return json.loads((root/"data/paper/state.json").read_text())
def ledger(root,name): return json.loads((root/"data/ledger/2026-01-01"/name).read_text())

def main():
    env(PAPER_STARTING_CAPITAL=1000,PAPER_ANALYSIS_BUDGET=1000,PAPER_REVIEW_SCORE=65,PAPER_MIN_SCRAP_SCORE=60,
        PAPER_MAX_POSITION_PCT=20,PAPER_TARGET_PCT=2,PAPER_STOP_PCT=1,PAPER_MAX_POSITIONS=2,
        PAPER_FUNDS_STATUS="FALLBACK_MINIMUM",PAPER_AVAILABLE_CAPITAL=0,PAPER_MAX_DATA_AGE_MINUTES=30)

    with tempfile.TemporaryDirectory() as td:
        r=Path(td); m=load(r)
        run(r,m,"100000.json",[cand("TARGET",100)],[{"symbol":"TARGET","price":100}],"2026-01-01 10:00")
        assert state(r)["positions"]["TARGET"]["quantity"]==2
        run(r,m,"100500.json",[cand("TARGET",102)],[{"symbol":"TARGET","price":102}],"2026-01-01 10:05")
        assert "TARGET" not in state(r)["positions"] and round(state(r)["realized_pnl"],2)==4
        events=ledger(r,"100500.json")["paper_events"]
        assert [e["side"] for e in events]==["SELL"] and ledger(r,"100500.json")["paper_account"]["open_positions"]=={}

    with tempfile.TemporaryDirectory() as td:
        r=Path(td); m=load(r)
        run(r,m,"110000.json",[cand("STOP",100)],[{"symbol":"STOP","price":100}],"2026-01-01 10:00")
        run(r,m,"110500.json",[cand("STOP",98)],[{"symbol":"STOP","price":98}],"2026-01-01 10:05")
        assert "STOP" not in state(r)["positions"] and round(state(r)["realized_pnl"],2)==-4
        events=ledger(r,"110500.json")["paper_events"]
        assert [e["side"] for e in events]==["SELL"] and ledger(r,"110500.json")["paper_account"]["open_positions"]=={}

    with tempfile.TemporaryDirectory() as td:
        r=Path(td); m=load(r)
        run(r,m,"120000.json",[cand("EXPENSIVE",8000,95,90)],[{"symbol":"EXPENSIVE","price":8000}],"2026-01-01 10:20")
        assert "EXPENSIVE" not in state(r)["positions"]
        assert ledger(r,"120000.json")["candidates"][0]["execution"]["reason"]=="INSUFFICIENT_CAPITAL"

    with tempfile.TemporaryDirectory() as td:
        r=Path(td); m=load(r)
        cs=[cand("A",100,ranking=1),cand("B",100,ranking=2),cand("C",100,ranking=3)]
        run(r,m,"130000.json",cs,[{"symbol":x,"price":100} for x in "ABC"],"2026-01-01 10:30")
        assert set(state(r)["positions"])=={"A","B"}
        assert ledger(r,"130000.json")["candidates"][2]["execution"]["reason"]=="MAX_POSITIONS_REACHED"

    with tempfile.TemporaryDirectory() as td:
        r=Path(td); m=load(r)
        run(r,m,"140000.json",[cand("LOW",100,64)],[{"symbol":"LOW","price":100}],"2026-01-01 10:40")
        assert "LOW" not in state(r)["positions"]

    with tempfile.TemporaryDirectory() as td:
        r=Path(td); m=load(r); (r/"data/paper").mkdir(parents=True)
        (r/"data/paper/state.json").write_text("{broken",encoding="utf-8")
        try: run(r,m,"150000.json",[],[],"2026-01-01 10:50")
        except RuntimeError as e: assert "Corrupt or invalid JSON state" in str(e)
        else: raise AssertionError("corrupt state was silently reset")

    with tempfile.TemporaryDirectory() as td:
        r=Path(td); m=load(r)
        run(r,m,"160000.json",[cand("STALE",100)],[{"symbol":"STALE","price":100}],"2026-01-01 10:00")
        stale="2026-01-01T04:00:00Z"
        run(r,m,"160500.json",[cand("STALE",103)],[{"symbol":"STALE","price":103}],"2026-01-01 10:05",data_as_of=stale)
        assert "STALE" in state(r)["positions"]
        run(r,m,"161000.json",[cand("STALE",103)],[{"symbol":"STALE","price":103}],"2026-01-01 15:29",data_as_of=stale)
        assert "STALE" not in state(r)["positions"]

    with tempfile.TemporaryDirectory() as td:
        r=Path(td); m=load(r)
        run(r,m,"170000.json",[cand("SAFE",100)],[{"symbol":"SAFE","price":100}],"2026-01-01 10:00")
        for p in (r/"data/paper/events").glob("*.json"):
            e=json.loads(p.read_text()); assert e["paper_only"] is True and e["live_trading_enabled"] is False and e["event"]["live_order_sent"] is False

    print("PAPER ENGINE SELF-TEST: PASS")
    print("PAPER ENGINE ACCEPTANCE TEST: PASS")
    print("10 scenarios PASS: BUY | TARGET | STOP | NO-REBUY | BUDGET | MAX-POSITIONS | THRESHOLDS | CORRUPT-STATE | STALE-DATA | LIVE-LOCK")
    return 0
if __name__=="__main__": raise SystemExit(main())
