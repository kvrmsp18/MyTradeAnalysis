#!/usr/bin/env python3
"""Offline pre-market self-test for the paper execution engine."""
from __future__ import annotations
import json, os, runpy, tempfile
from pathlib import Path

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")

def main():
    executor = Path(__file__).with_name("paper_executor.py").resolve()
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); os.chdir(root)
        base={
          "mode":"PAPER","timestamp":"2026-01-01T03:50:00Z","review_candidates":1,
          "safety":{"live_orders_enabled":False},
          "candidates":[{
            "symbol":"TEST","ranking":1,"decision":"REVIEW",
            "features":{"score":80},
            "scrap_result":{"status":"OK","score":75},
            "quote":{"price":100}
          }]
        }
        write(root/"data/ledger/2026-01-01/035000.json",base)
        write(root/"public/data/market_snapshot.json",{"status":"LIVE_MARKET_DATA","stocks":[{"symbol":"TEST","price":100}]})
        os.environ.update({"PAPER_STARTING_CAPITAL":"1000","PAPER_MAX_POSITION_PCT":"20","PAPER_TARGET_PCT":"2","PAPER_STOP_PCT":"1","PAPER_MAX_POSITIONS":"2"})
        runpy.run_path(str(executor),run_name="__main__")
        state=json.loads((root/"data/paper/state.json").read_text())
        assert len(state["positions"])==1 and state["cash"]==900, state
        base["timestamp"]="2026-01-01T03:55:00Z"
        base["candidates"][0]["quote"]["price"]=102
        write(root/"data/ledger/2026-01-01/035500.json",base)
        write(root/"public/data/market_snapshot.json",{"status":"LIVE_MARKET_DATA","stocks":[{"symbol":"TEST","price":102}]})
        runpy.run_path(str(executor),run_name="__main__")
        state=json.loads((root/"data/paper/state.json").read_text())
        assert len(state["positions"])==0 and round(state["realized_pnl"],2)==4.0, state
        events=list((root/"data/paper/events").glob("*.json"))
        assert len(events)==2, events
        print("PAPER ENGINE SELF-TEST: PASS (BUY, target SELL, P&L, state persistence, live-off guard)")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
