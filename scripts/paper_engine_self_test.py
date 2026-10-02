#!/usr/bin/env python3
"""Offline acceptance tests for the paper execution engine.

These tests prove:
- BUY can be simulated without a broker
- TARGET SELL realizes P&L
- STOP LOSS realizes negative P&L
- unaffordable shares are skipped before a BUY
- live broker execution remains disabled
- ledger/state persistence works
"""
from __future__ import annotations
import json, os, runpy, tempfile
from pathlib import Path

EXECUTOR = Path(__file__).with_name("paper_executor.py").resolve()

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")

def env(**values):
    os.environ.update({k:str(v) for k,v in values.items()})

def run_case(root, ledger_name, candidates, stocks, clock):
    write(root/"data/ledger/2026-01-01"/ledger_name, {
        "mode":"PAPER",
        "timestamp":"2026-01-01T04:00:00Z",
        "safety":{"live_orders_enabled":False},
        "candidates":candidates,
    })
    write(root/"public/data/market_snapshot.json", {
        "status":"LIVE_MARKET_DATA",
        "stocks":stocks,
    })
    env(PAPER_ENGINE_TEST_TIME_IST=clock)
    runpy.run_path(str(EXECUTOR), run_name="__main__")

def main():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); os.chdir(root)
        env(
            PAPER_STARTING_CAPITAL=1000,
            PAPER_ANALYSIS_BUDGET=1000,
            PAPER_MAX_POSITION_PCT=20,
            PAPER_TARGET_PCT=2,
            PAPER_STOP_PCT=1,
            PAPER_MAX_POSITIONS=2,
            PAPER_FUNDS_STATUS="FALLBACK_MINIMUM",
            PAPER_AVAILABLE_CAPITAL=0,
        )

        # 1) BUY + target SELL + realized P&L.
        candidate={
            "symbol":"TEST","ranking":1,"decision":"REVIEW",
            "features":{"score":80},"scrap_result":{"status":"OK","score":75},
            "quote":{"price":100}
        }
        run_case(root,"040000.json",[candidate],[{"symbol":"TEST","price":100}],"2026-01-01 10:00")
        state=json.loads((root/"data/paper/state.json").read_text())
        assert len(state["positions"])==1 and state["cash"]==800, state

        candidate["quote"]["price"]=102
        run_case(root,"040500.json",[candidate],[{"symbol":"TEST","price":102}],"2026-01-01 10:05")
        state=json.loads((root/"data/paper/state.json").read_text())
        assert not state["positions"] and round(state["realized_pnl"],2)==4.0, state

        # 2) STOP LOSS.
        candidate["quote"]["price"]=100
        run_case(root,"041000.json",[candidate],[{"symbol":"TEST","price":100}],"2026-01-01 10:10")
        candidate["quote"]["price"]=98
        run_case(root,"041500.json",[candidate],[{"symbol":"TEST","price":98}],"2026-01-01 10:15")
        state=json.loads((root/"data/paper/state.json").read_text())
        assert not state["positions"] and round(state["realized_pnl"],2)==0.0, state

        # 3) Budget gate: ₹8,000 stock must never fill with ₹1,000 budget.
        expensive={
            "symbol":"EXPENSIVE","ranking":1,"decision":"REVIEW",
            "features":{"score":95},"scrap_result":{"status":"OK","score":90},
            "quote":{"price":8000}
        }
        run_case(root,"042000.json",[expensive],[{"symbol":"EXPENSIVE","price":8000}],"2026-01-01 10:20")
        state=json.loads((root/"data/paper/state.json").read_text())
        assert "EXPENSIVE" not in state["positions"], state

        # 4) Every persisted event must be paper-only and no live order field
        # may ever indicate that a broker order was sent.
        for event in (root/"data/paper/events").glob("*.json"):
            payload=json.loads(event.read_text())
            assert payload["paper_only"] is True
            assert payload["live_trading_enabled"] is False
            assert payload["event"].get("live_order_sent") is False

        print("PAPER ENGINE ACCEPTANCE TEST: PASS")
        print("BUY: PASS | TARGET SELL/P&L: PASS | STOP LOSS: PASS | BUDGET GATE: PASS | LIVE BROKER LOCK: PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
