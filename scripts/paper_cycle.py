#!/usr/bin/env python3
"""Persist decision-time observation evidence for the paper-trading system.

This is deliberately observation-only until the real analysis/risk engine is wired in.
It never fabricates indicators, decisions or trades.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT = Path("public/data/market_snapshot.json")


def main() -> int:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%H%M%S")
    out = Path("data/ledger") / day / f"{stamp}.json"
    stocks = snapshot.get("stocks", [])
    ledger = {
        "schema_version": "1.0",
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "mode": "PAPER",
        "stage": "OBSERVATION_ONLY",
        "market_data_status": snapshot.get("status"),
        "source": snapshot.get("source"),
        "universe_count": len(stocks),
        "candidates": [
            {
                "symbol": s.get("symbol"),
                "quote": {
                    "price": s.get("price"),
                    "change": s.get("change"),
                    "open": s.get("open"),
                    "high": s.get("high"),
                    "low": s.get("low"),
                    "prev_close": s.get("prev_close"),
                    "volume": s.get("volume"),
                },
                "indicators": None,
                "market_regime": None,
                "scrap_result": None,
                "ranking": None,
                "analysis_pool_member": False,
                "decision": None,
                "rejection_reason": "ANALYSIS_NOT_YET_WIRED",
                "available_capital": 1000.0,
                "required_capital": None,
                "risk_gate": None,
                "capacity_gate": None,
            }
            for s in stocks
        ],
        "safety": {
            "live_orders_enabled": False,
            "stock_specific_learning_enabled": False,
            "auto_strategy_mutation_enabled": False,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    print(f"Wrote {out} with {len(stocks)} observed symbols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
