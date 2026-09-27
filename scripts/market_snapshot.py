#!/usr/bin/env python3
"""Collect a truthful Dhan market snapshot for the paper-trading GUI.

Safety:
- Never fabricates market data.
- Never submits an order.
- Missing credentials/data are reported as DATA_UNAVAILABLE.
- Instrument IDs are resolved from Dhan's public scrip master.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
MARKETFEED_URL = "https://api.dhan.co/v2/marketfeed/ltp"
OUT = Path("public/data/market_snapshot.json")
SYMBOLS = ["RELIANCE", "HDFCBANK", "INFY", "TCS", "SUNPHARMA", "M&M"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_unavailable(reason: str) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "status": "DATA_UNAVAILABLE",
        "timestamp": utc_now(),
        "source": "Dhan market feed",
        "reason": reason,
        "paper_only": True,
        "stocks": [],
    }, indent=2), encoding="utf-8")


def fetch(url: str, headers: dict[str, str] | None = None, body: bytes | None = None) -> bytes:
    req = urllib.request.Request(url, data=body, headers=headers or {}, method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


def pick(row: dict[str, str], *names: str) -> str:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        if name.lower() in lowered and lowered[name.lower()] not in (None, ""):
            return str(lowered[name.lower()]).strip()
    return ""


def resolve_ids() -> dict[str, str]:
    raw = fetch(MASTER_URL)
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    result: dict[str, str] = {}
    for row in reader:
        exchange = pick(row, "SEM_EXM_EXCH_ID", "EXCH_ID", "exchange")
        segment = pick(row, "SEM_SEGMENT", "SEGMENT")
        symbol = pick(row, "SEM_TRADING_SYMBOL", "TRADING_SYMBOL", "symbol")
        sec_id = pick(row, "SEM_SMST_SECURITY_ID", "SEM_SECURITY_ID", "SECURITY_ID", "security_id")
        if exchange.upper() == "NSE" and segment.upper() in ("E", "EQUITY", "NSE_EQ") and symbol in SYMBOLS and sec_id:
            result[symbol] = sec_id
    missing = [s for s in SYMBOLS if s not in result]
    if missing:
        raise RuntimeError("Instrument IDs unavailable for: " + ", ".join(missing))
    return result


def normalise_feed(payload: dict, ids: dict[str, str]) -> list[dict]:
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    segment = data.get("NSE_EQ", data.get("NSE", {})) if isinstance(data, dict) else {}
    by_id = {str(k): v for k, v in segment.items()} if isinstance(segment, dict) else {}
    rows = []
    for symbol, sec_id in ids.items():
        q = by_id.get(str(sec_id))
        if not isinstance(q, dict):
            continue
        ltp = q.get("last_price", q.get("ltp"))
        close = q.get("close")
        if ltp is None:
            continue
        change_pct = q.get("change_percent")
        if change_pct is None and close not in (None, 0):
            change_pct = ((float(ltp) - float(close)) / float(close)) * 100
        rows.append({
            "symbol": symbol,
            "price": float(ltp),
            "change": round(float(change_pct or 0), 2),
            "open": q.get("open"),
            "high": q.get("high"),
            "low": q.get("low"),
            "prev_close": close,
            "volume": q.get("volume"),
            "security_id": str(sec_id),
        })
    return rows


def main() -> int:
    token = os.getenv("DHAN_ACCESS_TOKEN") or os.getenv("DHAN_API_KEY")
    client_id = os.getenv("DHAN_CLIENT_ID")
    if not token or not client_id:
        write_unavailable("Dhan credentials are not configured in GitHub Actions secrets.")
        return 0
    try:
        ids = resolve_ids()
        body = json.dumps({"NSE_EQ": [int(v) for v in ids.values()]}).encode()
        payload = json.loads(fetch(MARKETFEED_URL, {
            "access-token": token,
            "client-id": client_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }, body).decode("utf-8"))
        rows = normalise_feed(payload, ids)
        if not rows:
            raise RuntimeError("Dhan returned no usable NSE equity quotes.")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "status": "LIVE_MARKET_DATA",
            "timestamp": utc_now(),
            "source": "Dhan market feed",
            "paper_only": True,
            "stocks": rows,
        }, indent=2), encoding="utf-8")
        return 0
    except Exception as exc:
        write_unavailable(str(exc))
        print(f"Market data unavailable: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
