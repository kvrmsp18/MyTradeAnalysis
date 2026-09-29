#!/usr/bin/env python3
"""Build the deterministic technical/SCRAP analysis layer for paper trading.

SCRAP is an auditable technical-analysis gate:
- S = Structure / trend
- C = Confirmation (momentum + volume)
- R = Relative strength / range position
- A = Actionability (breakout/pullback quality)
- P = Protection (volatility / risk context)

This layer uses only evidence available at decision time. It never places
orders, never fabricates candles, and never creates symbol-specific rules.
"""
from __future__ import annotations

import json
import math
import os
import urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

SNAPSHOT = Path("public/data/market_snapshot.json")
OUT = Path("public/data/scrap_analysis.json")
DHAN_URL = "https://api.dhan.co/v2/charts/historical"
LOOKBACK_DAYS = int(os.getenv("SCRAP_LOOKBACK_DAYS", "45"))


def num(v):
    try:
        if v in (None, ""):
            return None
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def avg(values):
    values = [x for x in values if x is not None]
    return sum(values) / len(values) if values else None


def ema(values, period):
    vals = [x for x in values if x is not None]
    if len(vals) < period:
        return None
    value = sum(vals[:period]) / period
    alpha = 2 / (period + 1)
    for x in vals[period:]:
        value = (x - value) * alpha + value
    return value


def rsi(closes, period=14):
    vals = [x for x in closes if x is not None]
    if len(vals) <= period:
        return None
    gains, losses = [], []
    for a, b in zip(vals[-(period + 1):], vals[-period:]):
        delta = b - a
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))
    ag, al = avg(gains), avg(losses)
    if al == 0:
        return 100.0 if ag and ag > 0 else 50.0
    return 100 - (100 / (1 + ag / al))


def atr(candles, period=14):
    if len(candles) <= period:
        return None
    trs = []
    for prev, cur in zip(candles[-(period + 1):-1], candles[-period:]):
        h, l, pc = num(cur.get("high")), num(cur.get("low")), num(prev.get("close"))
        if None in (h, l, pc):
            continue
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return avg(trs)


def fetch_history(token, client_id, security_id, from_date, to_date):
    body = json.dumps({
        "securityId": str(security_id),
        "exchangeSegment": "NSE_EQ",
        "instrument": "EQUITY",
        "expiryCode": 0,
        "fromDate": from_date,
        "toDate": to_date,
    }).encode()
    req = urllib.request.Request(
        DHAN_URL,
        data=body,
        headers={
            "access-token": token,
            "client-id": client_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        return []

    ts = payload.get("timestamp", [])
    opens = payload.get("open", [])
    highs = payload.get("high", [])
    lows = payload.get("low", [])
    closes = payload.get("close", [])
    volumes = payload.get("volume", [])
    rows = []
    for i in range(min(len(ts), len(opens), len(highs), len(lows), len(closes))):
        rows.append({
            "timestamp": ts[i],
            "open": num(opens[i]),
            "high": num(highs[i]),
            "low": num(lows[i]),
            "close": num(closes[i]),
            "volume": num(volumes[i]) if i < len(volumes) else None,
        })
    return rows


def fetch_yahoo_history(symbol):
    ticker = urllib.parse.quote({
        "RELIANCE":"RELIANCE.NS","HDFCBANK":"HDFCBANK.NS","INFY":"INFY.NS",
        "TCS":"TCS.NS","SUNPHARMA":"SUNPHARMA.NS","M&M":"M&M.NS"
    }.get(symbol, symbol + ".NS"), safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=5m&range=1mo"
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
    with urllib.request.urlopen(req, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = (payload.get("chart", {}).get("result") or [])
    if not result:
        return []
    r = result[0]
    timestamps = r.get("timestamp", [])
    quote = (r.get("indicators", {}).get("quote") or [{}])[0]
    opens, highs, lows, closes, volumes = [quote.get(k, []) for k in ("open","high","low","close","volume")]
    rows=[]
    for i in range(min(len(timestamps),len(opens),len(highs),len(lows),len(closes))):
        rows.append({"timestamp":timestamps[i],"open":num(opens[i]),"high":num(highs[i]),"low":num(lows[i]),"close":num(closes[i]),"volume":num(volumes[i]) if i<len(volumes) else None})
    return rows

def analyse(symbol, quote, candles):
    closes = [num(x.get("close")) for x in candles]
    volumes = [num(x.get("volume")) for x in candles]
    highs = [num(x.get("high")) for x in candles]
    lows = [num(x.get("low")) for x in candles]
    price = num(quote.get("price"))

    usable_closes = [x for x in closes if x is not None]
    if len(usable_closes) < 50:
        return {
            "symbol": symbol,
            "status": "INSUFFICIENT_DATA",
            "candle_count": len(candles),
            "required_candles": 50,
            "score": None,
            "action": "OBSERVE",
        }

    e9, e20, e50 = ema(closes, 9), ema(closes, 20), ema(closes, 50)
    r = rsi(closes)
    a = atr(candles)
    vol_avg20 = avg(volumes[-20:])
    last_vol = volumes[-1] if volumes else None
    volume_ratio = last_vol / vol_avg20 if last_vol is not None and vol_avg20 not in (None, 0) else None
    high20 = max([x for x in highs[-20:] if x is not None], default=None)
    low20 = min([x for x in lows[-20:] if x is not None], default=None)

    structure = 0
    if price is not None and e20 is not None and price > e20:
        structure += 1
    if e20 is not None and e50 is not None and e20 > e50:
        structure += 1
    if price is not None and e9 is not None and e20 is not None and price > e9 > e20:
        structure += 1

    confirmation = 0
    if r is not None and 50 <= r <= 70:
        confirmation += 1
    if volume_ratio is not None and volume_ratio >= 1.2:
        confirmation += 1
    if r is not None and r > 50:
        confirmation += 1

    relative = 0
    if price is not None and high20 is not None and high20 > 0:
        range_pct = price / high20 * 100
        if range_pct >= 98:
            relative += 2
        elif range_pct >= 95:
            relative += 1
    if price is not None and low20 is not None and high20 is not None and high20 > low20:
        pos = (price - low20) / (high20 - low20)
        if pos >= 0.70:
            relative += 1

    actionability = 0
    if price is not None and high20 is not None and price >= high20 * 0.995:
        actionability += 2
    if volume_ratio is not None and volume_ratio >= 1.2:
        actionability += 1
    if e9 is not None and e20 is not None and e9 > e20:
        actionability += 1

    protection = 0
    atr_pct = (a / price * 100) if a is not None and price else None
    if atr_pct is not None and atr_pct <= 3:
        protection += 2
    elif atr_pct is not None and atr_pct <= 5:
        protection += 1
    if r is not None and r < 75:
        protection += 1

    # Component maxima are 3 + 3 + 3 + 4 + 3 = 16.
    # Keep the normalization truthful so the score can never exceed 100.
    max_raw = 16
    raw = structure + confirmation + relative + actionability + protection
    score = round(raw / max_raw * 100, 1)
    if score >= 70:
        action = "REVIEW"
    elif score >= 50:
        action = "WATCH"
    else:
        action = "OBSERVE"

    return {
        "symbol": symbol,
        "status": "OK",
        "candle_count": len(candles),
        "indicators": {
            "ema9": round(e9, 4) if e9 is not None else None,
            "ema20": round(e20, 4) if e20 is not None else None,
            "ema50": round(e50, 4) if e50 is not None else None,
            "rsi14": round(r, 2) if r is not None else None,
            "atr14": round(a, 4) if a is not None else None,
            "atr_pct": round(atr_pct, 2) if atr_pct is not None else None,
            "volume_ratio_20": round(volume_ratio, 2) if volume_ratio is not None else None,
            "high20": high20,
            "low20": low20,
        },
        "components": {
            "structure": structure,
            "confirmation": confirmation,
            "relative_strength": relative,
            "actionability": actionability,
            "protection": protection,
        },
        "score": score,
        "action": action,
        "reasons": [
            "price_above_ema20" if price is not None and e20 is not None and price > e20 else "price_not_above_ema20",
            "ema9_above_ema20" if e9 is not None and e20 is not None and e9 > e20 else "ema9_not_above_ema20",
            "volume_confirmed" if volume_ratio is not None and volume_ratio >= 1.2 else "volume_not_confirmed",
            "near_20d_high" if price is not None and high20 is not None and price >= high20 * 0.995 else "not_near_20d_high",
        ],
        "decision_time_only": True,
        "stock_specific_rule_created": False,
    }


def main():
    if not SNAPSHOT.exists():
        raise SystemExit("Market snapshot is missing")
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    token = (os.getenv("DHAN_ACCESS_TOKEN") or "").strip()
    client_id = (os.getenv("DHAN_CLIENT_ID") or "").strip()
    result = {
        "status": "UNAVAILABLE",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "Dhan historical candles + deterministic technical calculations",
        "paper_only": True,
        "stock_specific_rule_created": False,
        "stocks": [],
    }
    if not token or not client_id:
        result["reason"] = "Dhan credentials are not configured."
    elif snapshot.get("status") not in ("LIVE_MARKET_DATA","LIVE_MARKET_DATA_FALLBACK"):
        result["reason"] = "Fresh market snapshot is unavailable."
    else:
        to_date = datetime.now(timezone.utc).date()
        from_date = to_date - timedelta(days=LOOKBACK_DAYS)
        result["status"] = "LIVE_TECHNICAL_DATA"
        for quote in snapshot.get("stocks", []):
            symbol = quote.get("symbol")
            try:
                candles = []
                if quote.get("security_id") and snapshot.get("status") in ("LIVE_MARKET_DATA","LIVE_MARKET_DATA_NSE"):
                    try:
                        candles = fetch_history(token, client_id, quote.get("security_id"), str(from_date), str(to_date))
                    except Exception:
                        candles = []
                if not candles:
                    candles = fetch_yahoo_history(symbol)
                row = analyse(symbol, quote, candles)
                row["data_source"] = "Dhan historical candles" if quote.get("security_id") and snapshot.get("status") == "LIVE_MARKET_DATA" else "Yahoo Finance 5-minute fallback"
                result["stocks"].append(row)
            except Exception as exc:
                result["stocks"].append({
                    "symbol": symbol, "status": "UNAVAILABLE", "reason": str(exc),
                    "candle_count": 0, "score": None, "action": "OBSERVE",
                })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
