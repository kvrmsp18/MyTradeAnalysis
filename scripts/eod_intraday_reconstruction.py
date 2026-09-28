#!/usr/bin/env python3
"""Reconstruct decision-time technical evidence for EOD movers.

Research-only. Historical candles are used to determine whether a discovered
mover produced a setup that was visible to the paper engine. This script never
places orders and never mutates strategy configuration.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OPPORTUNITIES = Path("public/data/eod_market_opportunities.json")
OUT = Path("public/data/eod_intraday_reconstruction.json")
HISTORICAL_URL = "https://api.dhan.co/v2/charts/historical"
TOP_N = int(os.getenv("EOD_RECONSTRUCTION_TOP_N", "20"))
INTERVAL_MIN = int(os.getenv("EOD_RECONSTRUCTION_INTERVAL", "5"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write(status: str, rows: list[dict], reason: str | None = None) -> None:
    payload = {
        "schema_version": "1.1",
        "status": status,
        "generated_at": utc_now(),
        "paper_only": True,
        "stock_specific_rules_allowed": False,
        "automatic_strategy_mutation": False,
        "interval_minutes": INTERVAL_MIN,
        "rows": rows,
    }
    if reason:
        payload["reason"] = reason
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def fetch_candles(token: str, client_id: str, security_id: str, day: str) -> dict:
    body = {
        "securityId": str(security_id),
        "exchangeSegment": "NSE_EQ",
        "instrument": "EQUITY",
        "fromDate": day,
        "toDate": day,
        "interval": str(INTERVAL_MIN),
    }
    req = urllib.request.Request(
        HISTORICAL_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "access-token": token,
            "client-id": client_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def series(payload: dict) -> list[dict]:
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        return []
    timestamps = data.get("timestamp", [])
    opens = data.get("open", [])
    highs = data.get("high", [])
    lows = data.get("low", [])
    closes = data.get("close", [])
    volumes = data.get("volume", [])
    rows: list[dict] = []
    for i, ts in enumerate(timestamps):
        try:
            rows.append({
                "timestamp": ts,
                "open": float(opens[i]),
                "high": float(highs[i]),
                "low": float(lows[i]),
                "close": float(closes[i]),
                "volume": float(volumes[i]) if i < len(volumes) else 0.0,
            })
        except (IndexError, TypeError, ValueError):
            continue
    return rows


def ema(values: list[float], period: int) -> list[float | None]:
    if len(values) < period:
        return [None] * len(values)
    alpha = 2.0 / (period + 1)
    result: list[float | None] = [None] * (period - 1)
    current = sum(values[:period]) / period
    result.append(current)
    for value in values[period:]:
        current = (value - current) * alpha + current
        result.append(current)
    return result


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    if len(values) <= period:
        return [None] * len(values)
    gains = [max(values[i] - values[i - 1], 0.0) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], 0.0) for i in range(1, len(values))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out: list[float | None] = [None] * period
    out.append(100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss))
    for i in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
        out.append(100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss))
    return out


def reconstruct(candles: list[dict]) -> dict:
    closes = [x["close"] for x in candles]
    volumes = [x["volume"] for x in candles]
    e9, e20, e50 = ema(closes, 9), ema(closes, 20), ema(closes, 50)
    rs = rsi(closes)
    first_setup = None
    for i in range(len(candles)):
        if i < 50 or e9[i] is None or e20[i] is None or e50[i] is None or rs[i] is None:
            continue
        lookback_vol = volumes[max(0, i - 20):i]
        volume_base = sum(lookback_vol) / max(1, len(lookback_vol))
        prior_highs = [x["high"] for x in candles[max(0, i - 20):i]]
        if not prior_highs:
            continue
        trend = e9[i] > e20[i] > e50[i]
        momentum = 50 <= rs[i] <= 75
        volume_ok = volume_base > 0 and volumes[i] >= 1.2 * volume_base
        breakout = closes[i] > max(prior_highs)
        if trend and momentum and volume_ok and breakout:
            first_setup = {
                "timestamp": candles[i]["timestamp"],
                "close": candles[i]["close"],
                "ema9": round(e9[i], 4),
                "ema20": round(e20[i], 4),
                "ema50": round(e50[i], 4),
                "rsi14": round(rs[i], 2),
                "volume": candles[i]["volume"],
                "volume_ratio": round(candles[i]["volume"] / volume_base, 2),
                "setup": "TREND_MOMENTUM_VOLUME_BREAKOUT",
                "research_only": True,
            }
            break
    return {
        "candle_count": len(candles),
        "first_reconstructed_setup": first_setup,
        "setup_found": first_setup is not None,
        "method": "EMA9>EMA20>EMA50 + RSI14 50-75 + volume >= 1.2x 20-bar average + 20-bar breakout",
        "note": "This is a reconstruction heuristic, not a trade authorization rule.",
    }


def main() -> int:
    if not OPPORTUNITIES.exists():
        write("DATA_UNAVAILABLE", [], "EOD opportunity report is missing.")
        return 0
    token = os.getenv("DHAN_ACCESS_TOKEN") or os.getenv("DHAN_API_KEY")
    client_id = os.getenv("DHAN_CLIENT_ID")
    if not token or not client_id:
        write("DATA_UNAVAILABLE", [], "Dhan credentials are not configured.")
        return 0
    try:
        report = json.loads(OPPORTUNITIES.read_text(encoding="utf-8"))
        if report.get("status") != "READY":
            write("PENDING", [], "EOD opportunity scan is not ready.")
            return 0
        day = datetime.now(timezone.utc).date().isoformat()
        rows = []
        for stock in report.get("stocks", [])[:TOP_N]:
            symbol = stock.get("symbol")
            security_id = stock.get("security_id")
            if not symbol or not security_id:
                continue
            try:
                candles = series(fetch_candles(token, client_id, str(security_id), day))
                reconstruction = reconstruct(candles)
                rows.append({
                    "symbol": symbol,
                    "security_id": str(security_id),
                    "change_pct": stock.get("change_pct"),
                    "reconstruction": reconstruction,
                    "attribution_status": "PENDING_ACTUAL_BOT_DECISION_MATCH" if reconstruction.get("setup_found") else "NO_RECONSTRUCTED_SETUP",
                })
            except Exception as exc:
                rows.append({
                    "symbol": symbol,
                    "security_id": str(security_id),
                    "change_pct": stock.get("change_pct"),
                    "reconstruction": {"status": "UNAVAILABLE", "reason": str(exc)},
                    "attribution_status": "UNAVAILABLE",
                })
        write("READY", rows)
        print(f"Reconstructed {len(rows)} EOD movers using {INTERVAL_MIN}-minute historical candles.")
        return 0
    except Exception as exc:
        write("DATA_UNAVAILABLE", [], str(exc))
        print(f"Intraday reconstruction unavailable: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
