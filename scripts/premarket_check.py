#!/usr/bin/env python3
"""Build a truthful pre-market readiness report for MyTradeAnalysis.

Paper trading only. Dhan funds are read-only and are never used for orders.
The suggested list is a watchlist, not a trade authorization.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("public/data/premarket_report.json")
SNAPSHOT = Path("public/data/market_snapshot.json")
SCRAP = Path("public/data/scrap_analysis.json")
COUNCIL = Path("public/data/ai_research_council.json")
PAPER_CAPITAL = float(os.getenv("PAPER_REFERENCE_CAPITAL", "1000"))


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def dhan_funds() -> dict:
    token = os.getenv("DHAN_ACCESS_TOKEN") or os.getenv("DHAN_API_KEY")
    client_id = os.getenv("DHAN_CLIENT_ID")
    if not token or not client_id:
        return {"status": "UNAVAILABLE", "reason": "Dhan credentials not configured"}

    req = urllib.request.Request(
        "https://api.dhan.co/v2/fundlimit",
        headers={
            "access-token": token,
            "client-id": client_id,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            return {"status": "INVALID", "reason": "Unexpected Dhan fundlimit response"}

        # Dhan has used different field names across API revisions; retain
        # whichever available balance fields are present without inventing data.
        available = None
        for key in ("availabelBalance", "availableBalance", "available_balance", "availabel_balance"):
            if key in payload:
                available = num(payload.get(key))
                if available is not None:
                    break
        return {
            "status": "READY",
            "available_balance": available,
            "raw_fields": {
                k: payload.get(k)
                for k in payload.keys()
                if "balance" in str(k).lower() or "limit" in str(k).lower()
            },
        }
    except Exception as exc:
        return {"status": "UNAVAILABLE", "reason": str(exc)}


def build_watchlist(snapshot: dict, scrap: dict) -> list[dict]:
    scrap_map = {str(x.get("symbol")): x for x in scrap.get("stocks", []) if x.get("symbol")}
    rows = []
    for stock in snapshot.get("stocks", []):
        symbol = str(stock.get("symbol") or "")
        if not symbol:
            continue
        change = num(stock.get("change"))
        scrap_row = scrap_map.get(symbol, {})
        scrap_score = num(scrap_row.get("score"))
        score = 50.0
        reasons = []
        if change is not None:
            score += max(-15.0, min(15.0, change * 5.0))
            reasons.append("positive_latest_change" if change > 0 else "latest_change_not_positive")
        if scrap_score is not None:
            score += max(-20.0, min(20.0, (scrap_score - 60.0) * 0.5))
            reasons.append("SCRAP_available")
        rows.append({
            "symbol": symbol,
            "latest_price": stock.get("price"),
            "latest_change_pct": change,
            "scrap_score": scrap_score,
            "watch_score": round(max(0.0, min(100.0, score)), 2),
            "reasons": reasons,
            "status": "WATCHLIST_ONLY",
        })
    rows.sort(key=lambda x: x["watch_score"], reverse=True)
    return rows[:5]


def main() -> int:
    snapshot = read_json(SNAPSHOT)
    scrap = read_json(SCRAP)
    council = read_json(COUNCIL)
    funds = dhan_funds()
    watchlist = build_watchlist(snapshot, scrap)

    report = {
        "schema_version": "1.0",
        "status": "READY",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "market_phase": "PREMARKET",
        "market_open_ist": "09:15",
        "market_close_ist": "15:30",
        "paper_only": True,
        "live_trading_enabled": False,
        "paper_reference_capital": PAPER_CAPITAL,
        "dhan_funds_read_only": funds,
        "market_data_status": snapshot.get("status", "UNKNOWN"),
        "ai_council_status": council.get("status", "NOT_RUN"),
        "suggested_watchlist": watchlist,
        "selection_note": "Watchlist candidates use the latest available Dhan/SCRAP evidence. They are not pre-authorized trades; the live paper engine must revalidate at market time.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
