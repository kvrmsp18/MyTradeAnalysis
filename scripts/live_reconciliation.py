#!/usr/bin/env python3
"""Reconcile live broker orders/positions with the local execution journal."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from dhan_order import LiveOrderBlocked, order_detail, positions

STATE=Path("data/live/state.json")
OUT=Path("public/data/live_reconciliation.json")

def main():
    try:
        if not STATE.exists():
            print("LIVE_RECONCILIATION=NO_LOCAL_STATE"); return 0
        state=json.loads(STATE.read_text(encoding="utf-8"))
        rows=[]
        for trade in state.get("trades", []):
            oid=trade.get("order_id")
            if not oid: continue
            try: rows.append({"order_id":oid,"symbol":trade.get("symbol"),"detail":order_detail(str(oid))})
            except Exception as exc: rows.append({"order_id":oid,"symbol":trade.get("symbol"),"error":type(exc).__name__})
        broker_positions=positions()
        payload={"status":"READY","generated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
                 "orders":rows,"broker_positions":broker_positions}
        OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(payload,indent=2),encoding="utf-8")
        print("LIVE_RECONCILIATION=READY")
        return 0
    except LiveOrderBlocked as exc:
        print("LIVE_RECONCILIATION=BLOCKED "+str(exc)); return 0

if __name__=="__main__": raise SystemExit(main())
