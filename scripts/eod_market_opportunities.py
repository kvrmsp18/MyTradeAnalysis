#!/usr/bin/env python3
"""Scan the broader NSE equity universe after the market close.

This is an EOD research scanner, not an execution engine. It is deliberately
separate from the small paper-trading candidate universe so the learning report
can identify material movers the bot never evaluated.

Safety:
- Never submits an order.
- Never creates stock-specific strategy rules.
- Missing credentials/data produce a truthful UNAVAILABLE report.
- The scanner only identifies observable EOD movers; it does not claim that a
  profitable trade was executable at a particular intraday price.
"""
from __future__ import annotations

import csv
import io
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
MARKETFEED_URL = "https://api.dhan.co/v2/marketfeed/ltp"
OUT = Path("public/data/eod_market_opportunities.json")
TOP_N = int(os.getenv("EOD_OPPORTUNITY_TOP_N", "50"))
MIN_MOVE_PCT = float(os.getenv("EOD_OPPORTUNITY_MIN_MOVE_PCT", "2.0"))
CHUNK_SIZE = int(os.getenv("EOD_MARKETFEED_CHUNK", "100"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_report(status: str, reason: str | None = None, stocks: list[dict] | None = None) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "status": status,
        "generated_at": now(),
        "source": "Dhan NSE equity LTP feed",
        "paper_only": True,
        "min_move_pct": MIN_MOVE_PCT,
        "top_n": TOP_N,
        "universe_count": len(stocks or []),
        "stocks": stocks or [],
    }
    if reason:
        payload["reason"] = reason
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def fetch(url: str, headers: dict[str, str] | None = None, body: bytes | None = None) -> bytes:
    req = urllib.request.Request(
        url,
        data=body,
        headers=headers or {},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()


def pick(row: dict[str, str], *names: str) -> str:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def resolve_universe() -> dict[str, dict[str, str]]:
    text = fetch(MASTER_URL).decode("utf-8-sig", errors="replace")
    result: dict[str, dict[str, str]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        exchange = pick(row, "SEM_EXM_EXCH_ID", "EXCH_ID", "exchange").upper()
        segment = pick(row, "SEM_SEGMENT", "SEGMENT").upper()
        symbol = pick(row, "SEM_TRADING_SYMBOL", "TRADING_SYMBOL", "symbol")
        sec_id = pick(row, "SEM_SMST_SECURITY_ID", "SEM_SECURITY_ID", "SECURITY_ID", "security_id")
        instrument = pick(row, "SEM_INSTRUMENT_NAME", "INSTRUMENT", "instrument").upper()
        if exchange != "NSE" or segment not in {"E", "EQUITY", "NSE_EQ"} or not symbol or not sec_id:
            continue
        # Keep ordinary equity instruments and exclude obvious derivatives/ETFs.
        if instrument and any(x in instrument for x in ("FUT", "OPT", "INDEX")):
            continue
        result.setdefault(symbol, {"security_id": sec_id, "exchange_segment": "NSE_EQ"})
    return result


def normalise(payload: dict, ids: dict[str, dict[str, str]]) -> list[dict]:
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    segment = data.get("NSE_EQ", data.get("NSE", {})) if isinstance(data, dict) else {}
    by_id = segment if isinstance(segment, dict) else {}
    rows: list[dict] = []
    for symbol, meta in ids.items():
        quote = by_id.get(str(meta["security_id"]))
        if not isinstance(quote, dict):
            continue
        price = quote.get("last_price", quote.get("ltp"))
        close = quote.get("close")
        if price is None or close in (None, 0):
            continue
        try:
            price_f = float(price)
            close_f = float(close)
            change_pct = (price_f - close_f) / close_f * 100.0
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        rows.append({
            "symbol": symbol,
            "security_id": str(meta["security_id"]),
            "price": round(price_f, 4),
            "prev_close": round(close_f, 4),
            "change_pct": round(change_pct, 3),
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "volume": quote.get("volume"),
        })
    return rows


def main() -> int:
    token = os.getenv("DHAN_ACCESS_TOKEN") or os.getenv("DHAN_API_KEY")
    client_id = os.getenv("DHAN_CLIENT_ID")
    if not token or not client_id:
        write_report("DATA_UNAVAILABLE", "Dhan credentials are not configured.")
        return 0

    try:
        universe = resolve_universe()
        symbols = list(universe)
        all_rows: list[dict] = []
        headers = {
            "access-token": token,
            "client-id": client_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        for start in range(0, len(symbols), max(1, CHUNK_SIZE)):
            batch = symbols[start:start + max(1, CHUNK_SIZE)]
            body = json.dumps({"NSE_EQ": [int(universe[s]["security_id"]) for s in batch]}).encode()
            payload = json.loads(fetch(MARKETFEED_URL, headers, body).decode("utf-8"))
            all_rows.extend(normalise(payload, {s: universe[s] for s in batch}))
            if start + CHUNK_SIZE < len(symbols):
                time.sleep(0.25)

        movers = [row for row in all_rows if abs(row["change_pct"]) >= MIN_MOVE_PCT]
        movers.sort(key=lambda row: abs(row["change_pct"]), reverse=True)
        movers = movers[:TOP_N]
        write_report("READY", stocks=movers)
        print(f"Scanned {len(all_rows)} NSE equities; retained {len(movers)} EOD movers.")
        return 0
    except Exception as exc:
        write_report("DATA_UNAVAILABLE", str(exc))
        print(f"EOD opportunity scan unavailable: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
